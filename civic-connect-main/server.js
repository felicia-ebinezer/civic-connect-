require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');
const fs = require('fs');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const multer = require('multer');
const crypto = require('crypto');
const Datastore = require('nedb-promises');
const { GoogleGenerativeAI } = require('@google/generative-ai');

const app = express();
const PORT = process.env.PORT || 5000;
const JWT_SECRET = process.env.JWT_SECRET || 'civic_connect_secret_key';
const GEMINI_API_KEY = process.env.GEMINI_API_KEY || '';
const genAI = GEMINI_API_KEY ? new GoogleGenerativeAI(GEMINI_API_KEY) : null;

// Create directories
if (!fs.existsSync('uploads')) fs.mkdirSync('uploads');
if (!fs.existsSync('data')) fs.mkdirSync('data');

// NeDB databases
const usersDB = Datastore.create({ filename: 'data/users.db', autoload: true });
const complaintsDB = Datastore.create({ filename: 'data/complaints.db', autoload: true });
const vouchersDB = Datastore.create({ filename: 'data/vouchers.db', autoload: true });

usersDB.ensureIndex({ fieldName: 'email', unique: true });

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));
app.use('/uploads', express.static(path.join(__dirname, 'uploads')));

// Multer config
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, 'uploads/'),
  filename: (req, file, cb) => {
    cb(null, Date.now() + '-' + Math.round(Math.random() * 1E9) + path.extname(file.originalname));
  }
});
const upload = multer({
  storage,
  limits: { fileSize: 10 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const allowed = /jpeg|jpg|png|webp/;
    if (allowed.test(path.extname(file.originalname).toLowerCase()) && allowed.test(file.mimetype)) return cb(null, true);
    cb(new Error('Only JPG, PNG, WEBP images allowed'));
  }
});

// ═══════════ CONSTANTS ═══════════
const STAGES = [
  { id: 0, name: 'Submitted', icon: '📝', description: 'Complaint has been submitted' },
  { id: 1, name: 'Under Review', icon: '🔍', description: 'Being reviewed by civic authority' },
  { id: 2, name: 'Assigned', icon: '👷', description: 'Assigned to field team' },
  { id: 3, name: 'In Progress', icon: '🔧', description: 'Work is in progress' },
  { id: 4, name: 'Inspection', icon: '📋', description: 'Work being inspected' },
  { id: 5, name: 'Verification', icon: '✅', description: 'Final verification by admin' },
  { id: 6, name: 'Resolved', icon: '🎉', description: 'Issue has been resolved!' }
];

const LEVELS = [
  { level: 1, name: 'Newcomer', minPoints: 0 },
  { level: 2, name: 'Active Citizen', minPoints: 100 },
  { level: 3, name: 'Community Helper', minPoints: 300 },
  { level: 4, name: 'Urban Champion', minPoints: 600 },
  { level: 5, name: 'Civic Legend', minPoints: 1000 }
];

const REWARDS = [
  { id: 'bus_1day', name: '1-Day Bus Pass', description: 'Free bus travel for 1 day', cost: 100, minLevel: 1, type: 'bus_pass', durationDays: 1 },
  { id: 'bus_7day', name: '7-Day Bus Pass', description: 'Free bus travel for 7 days', cost: 300, minLevel: 2, type: 'bus_pass', durationDays: 7 },
  { id: 'bus_30day', name: '30-Day Bus Pass', description: 'Free bus travel for 30 days', cost: 800, minLevel: 3, type: 'bus_pass', durationDays: 30 },
  { id: 'cafe_50', name: '₹50 Café Voucher', description: '₹50 off at partner cafés', cost: 150, minLevel: 2, type: 'voucher', durationDays: 30 },
  { id: 'movie_ticket', name: 'Movie Ticket', description: 'Free single movie ticket', cost: 500, minLevel: 3, type: 'voucher', durationDays: 14 },
  { id: 'amazon_100', name: '₹100 Amazon Gift', description: '₹100 Amazon gift card', cost: 1000, minLevel: 4, type: 'gift_card', durationDays: 90 }
];

const STREAK_BONUSES = { 3: 20, 7: 50, 14: 100, 30: 200 };

// ═══════════ AUTH MIDDLEWARE ═══════════
function authMiddleware(req, res, next) {
  try {
    const token = req.header('Authorization')?.replace('Bearer ', '');
    if (!token) return res.status(401).json({ error: 'Access denied.' });
    req.user = jwt.verify(token, JWT_SECRET);
    next();
  } catch (err) {
    res.status(401).json({ error: 'Invalid or expired token.' });
  }
}

function adminOnly(req, res, next) {
  if (req.user.role !== 'admin') return res.status(403).json({ error: 'Admin privileges required.' });
  next();
}

// ═══════════ HELPERS ═══════════
function getAutoPriority(category) {
  const map = { 'Water Leakage': 'High', 'Electricity': 'High', 'Drainage': 'High', 'Pothole': 'Medium', 'Road Damage': 'Medium', 'Street Light': 'Low', 'Garbage': 'Low', 'Other': 'Low' };
  return map[category] || 'Medium';
}

function getAutoDepartment(category) {
  const map = { 'Pothole': 'Road', 'Road Damage': 'Road', 'Water Leakage': 'Water', 'Drainage': 'Water', 'Street Light': 'Electricity', 'Electricity': 'Electricity', 'Garbage': 'Sanitation', 'Other': 'General' };
  return map[category] || 'General';
}

function getLevel(points) {
  let current = LEVELS[0];
  for (const l of LEVELS) {
    if (points >= l.minPoints) current = l;
  }
  return current;
}

function getStatusFromStage(stage) {
  if (stage === 0) return 'Pending';
  if (stage >= 1 && stage <= 5) return 'In Progress';
  return 'Resolved';
}

// ═══════════ AUTH ROUTES ═══════════
app.post('/api/auth/register', async (req, res) => {
  try {
    const { name, email, password, phone } = req.body;
    if (!name || !email || !password) return res.status(400).json({ error: 'Name, email, and password are required.' });
    if (password.length < 6) return res.status(400).json({ error: 'Password must be at least 6 characters.' });

    const exists = await usersDB.findOne({ email: email.toLowerCase() });
    if (exists) return res.status(400).json({ error: 'Email already registered.' });

    const hashed = await bcrypt.hash(password, 12);
    const user = await usersDB.insert({
      name, email: email.toLowerCase(), password: hashed,
      phone: phone || '', role: 'citizen',
      points: 0, streak: 0, lastReportDate: null,
      pointsHistory: [],
      createdAt: new Date()
    });

    const token = jwt.sign({ id: user._id, name: user.name, email: user.email, role: user.role }, JWT_SECRET, { expiresIn: '24h' });
    res.status(201).json({ token, user: { id: user._id, name: user.name, email: user.email, role: user.role } });
  } catch (err) {
    res.status(500).json({ error: 'Registration failed.' });
  }
});

app.post('/api/auth/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    if (!email || !password) return res.status(400).json({ error: 'Email and password are required.' });

    const user = await usersDB.findOne({ email: email.toLowerCase() });
    if (!user) return res.status(401).json({ error: 'Invalid email or password.' });

    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) return res.status(401).json({ error: 'Invalid email or password.' });

    const token = jwt.sign({ id: user._id, name: user.name, email: user.email, role: user.role }, JWT_SECRET, { expiresIn: '24h' });
    res.json({ token, user: { id: user._id, name: user.name, email: user.email, role: user.role } });
  } catch (err) {
    res.status(500).json({ error: 'Login failed.' });
  }
});

app.get('/api/auth/me', authMiddleware, async (req, res) => {
  try {
    const user = await usersDB.findOne({ _id: req.user.id });
    if (!user) return res.status(404).json({ error: 'User not found.' });
    const { password, ...safe } = user;
    res.json(safe);
  } catch (err) {
    res.status(500).json({ error: 'Server error.' });
  }
});

// ═══════════ PROFILE / POINTS ═══════════
app.get('/api/profile', authMiddleware, async (req, res) => {
  try {
    const user = await usersDB.findOne({ _id: req.user.id });
    if (!user) return res.status(404).json({ error: 'User not found.' });

    const complaints = await complaintsDB.find({ citizen: req.user.id });
    const level = getLevel(user.points || 0);
    const nextLevel = LEVELS.find(l => l.minPoints > (user.points || 0)) || level;

    res.json({
      name: user.name,
      email: user.email,
      phone: user.phone,
      points: user.points || 0,
      streak: user.streak || 0,
      level: level,
      nextLevel: nextLevel,
      totalComplaints: complaints.length,
      resolved: complaints.filter(c => c.stage === 6).length,
      pending: complaints.filter(c => c.stage < 6).length,
      pointsHistory: (user.pointsHistory || []).slice(-20).reverse(),
      joinedDate: user.createdAt
    });
  } catch (err) {
    res.status(500).json({ error: 'Failed to load profile.' });
  }
});

// ═══════════ REWARDS ═══════════
app.get('/api/rewards', authMiddleware, (req, res) => {
  res.json(REWARDS);
});

app.post('/api/rewards/redeem', authMiddleware, async (req, res) => {
  try {
    const { rewardId } = req.body;
    const reward = REWARDS.find(r => r.id === rewardId);
    if (!reward) return res.status(404).json({ error: 'Reward not found.' });

    const user = await usersDB.findOne({ _id: req.user.id });
    if (!user) return res.status(404).json({ error: 'User not found.' });

    const userLevel = getLevel(user.points || 0);
    if (userLevel.level < reward.minLevel) {
      return res.status(400).json({ error: `Requires Level ${reward.minLevel} (${LEVELS[reward.minLevel - 1].name})` });
    }
    if ((user.points || 0) < reward.cost) {
      return res.status(400).json({ error: `Not enough points. Need ${reward.cost}, have ${user.points || 0}.` });
    }

    // Deduct points
    const newPoints = (user.points || 0) - reward.cost;
    const historyEntry = { action: `Redeemed: ${reward.name}`, points: -reward.cost, date: new Date() };
    await usersDB.update({ _id: req.user.id }, {
      $set: { points: newPoints },
      $push: { pointsHistory: historyEntry }
    });

    // Create voucher
    const voucher = await vouchersDB.insert({
      code: crypto.randomUUID().split('-')[0].toUpperCase(),
      rewardId: reward.id,
      rewardName: reward.name,
      rewardType: reward.type,
      citizen: req.user.id,
      citizenName: req.user.name,
      expiresAt: new Date(Date.now() + reward.durationDays * 24 * 60 * 60 * 1000),
      used: false,
      createdAt: new Date()
    });

    res.json({ voucher, remainingPoints: newPoints });
  } catch (err) {
    res.status(500).json({ error: 'Redemption failed: ' + err.message });
  }
});

// ═══════════ VOUCHERS ═══════════
app.get('/api/vouchers', authMiddleware, async (req, res) => {
  try {
    const vouchers = await vouchersDB.find({ citizen: req.user.id }).sort({ createdAt: -1 });
    res.json(vouchers);
  } catch (err) {
    res.status(500).json({ error: 'Failed to load vouchers.' });
  }
});

// ═══════════ COMPLAINTS ═══════════

// Create complaint
app.post('/api/complaints', authMiddleware, upload.single('image'), async (req, res) => {
  try {
    const { title, description, category, location } = req.body;
    if (!title || !description || !category || !location) {
      return res.status(400).json({ error: 'Title, description, category, and location are required.' });
    }

    // Duplicate check
    const existing = await complaintsDB.find({ category, status: { $ne: 'Resolved' } });
    const duplicate = existing.find(c => c.location.toLowerCase().trim() === location.toLowerCase().trim());
    if (duplicate) {
      return res.status(409).json({ error: 'A similar complaint already exists at this location.', existingId: duplicate._id });
    }

    const complaint = await complaintsDB.insert({
      title, description, category, location,
      image: req.file ? `/uploads/${req.file.filename}` : '',
      status: 'Pending',
      stage: 0,
      stageHistory: [{ stage: 0, name: 'Submitted', timestamp: new Date() }],
      priority: getAutoPriority(category),
      department: getAutoDepartment(category),
      citizen: req.user.id,
      citizenName: req.user.name,
      citizenEmail: req.user.email,
      adminNotes: '',
      upvotes: 0,
      resolvedAt: null,
      createdAt: new Date(),
      updatedAt: new Date()
    });

    // Award points + update streak
    const user = await usersDB.findOne({ _id: req.user.id });
    const today = new Date().toDateString();
    const lastReport = user.lastReportDate ? new Date(user.lastReportDate).toDateString() : null;
    const yesterday = new Date(Date.now() - 86400000).toDateString();

    let newStreak = 1;
    if (lastReport === yesterday) newStreak = (user.streak || 0) + 1;
    else if (lastReport === today) newStreak = user.streak || 1;

    let pointsEarned = 10; // base points for reporting
    const historyEntries = [{ action: 'Complaint submitted', points: 10, date: new Date() }];

    // Streak bonuses
    for (const [milestone, bonus] of Object.entries(STREAK_BONUSES)) {
      if (newStreak === parseInt(milestone)) {
        pointsEarned += bonus;
        historyEntries.push({ action: `${milestone}-day streak bonus! 🔥`, points: bonus, date: new Date() });
      }
    }

    await usersDB.update({ _id: req.user.id }, {
      $set: { streak: newStreak, lastReportDate: new Date(), points: (user.points || 0) + pointsEarned },
      $push: { pointsHistory: { $each: historyEntries } }
    });

    res.status(201).json({ complaint, pointsEarned, streak: newStreak });
  } catch (err) {
    res.status(500).json({ error: 'Failed to create complaint: ' + err.message });
  }
});

// My complaints
app.get('/api/complaints/my', authMiddleware, async (req, res) => {
  try {
    const complaints = await complaintsDB.find({ citizen: req.user.id }).sort({ createdAt: -1 });
    res.json(complaints);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch complaints.' });
  }
});

// Stats (admin)
app.get('/api/complaints/stats/summary', authMiddleware, adminOnly, async (req, res) => {
  try {
    const all = await complaintsDB.find({});
    res.json({
      total: all.length,
      pending: all.filter(c => c.status === 'Pending').length,
      inProgress: all.filter(c => c.status === 'In Progress').length,
      resolved: all.filter(c => c.status === 'Resolved').length,
      highPriority: all.filter(c => c.priority === 'High').length
    });
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch statistics.' });
  }
});

// All complaints (admin)
app.get('/api/complaints/all', authMiddleware, adminOnly, async (req, res) => {
  try {
    const { category, status, priority, department, location, sort } = req.query;
    const filter = {};
    if (category) filter.category = category;
    if (status) filter.status = status;
    if (priority) filter.priority = priority;
    if (department) filter.department = department;

    let complaints = await complaintsDB.find(filter).sort({ createdAt: -1 });

    if (location) {
      const loc = location.toLowerCase();
      complaints = complaints.filter(c => c.location.toLowerCase().includes(loc));
    }

    if (sort === 'oldest') complaints.sort((a, b) => new Date(a.createdAt) - new Date(b.createdAt));
    if (sort === 'priority') {
      const order = { 'High': 0, 'Medium': 1, 'Low': 2 };
      complaints.sort((a, b) => order[a.priority] - order[b.priority]);
    }
    if (sort === 'status') {
      const order = { 'Pending': 0, 'In Progress': 1, 'Resolved': 2 };
      complaints.sort((a, b) => order[a.status] - order[b.status]);
    }

    res.json(complaints);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch complaints.' });
  }
});

// Get single complaint
app.get('/api/complaints/:id', authMiddleware, async (req, res) => {
  try {
    const complaint = await complaintsDB.findOne({ _id: req.params.id });
    if (!complaint) return res.status(404).json({ error: 'Complaint not found.' });
    if (req.user.role === 'citizen' && complaint.citizen !== req.user.id) {
      return res.status(403).json({ error: 'Access denied.' });
    }
    res.json({ ...complaint, stages: STAGES });
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch complaint.' });
  }
});

// Upvote complaint
app.post('/api/complaints/:id/upvote', authMiddleware, async (req, res) => {
  try {
    const complaint = await complaintsDB.findOne({ _id: req.params.id });
    if (!complaint) return res.status(404).json({ error: 'Complaint not found.' });
    await complaintsDB.update({ _id: req.params.id }, { $set: { upvotes: (complaint.upvotes || 0) + 1 } });
    res.json({ upvotes: (complaint.upvotes || 0) + 1 });
  } catch (err) {
    res.status(500).json({ error: 'Failed to upvote.' });
  }
});

// Advance stage (admin)
app.post('/api/complaints/:id/advance', authMiddleware, adminOnly, async (req, res) => {
  try {
    const complaint = await complaintsDB.findOne({ _id: req.params.id });
    if (!complaint) return res.status(404).json({ error: 'Complaint not found.' });

    const currentStage = complaint.stage || 0;
    if (currentStage >= 6) return res.status(400).json({ error: 'Complaint is already resolved.' });

    const nextStage = currentStage + 1;
    const newStatus = getStatusFromStage(nextStage);
    const stageEntry = { stage: nextStage, name: STAGES[nextStage].name, timestamp: new Date() };

    const update = {
      stage: nextStage,
      status: newStatus,
      updatedAt: new Date()
    };
    if (nextStage === 6) update.resolvedAt = new Date();

    await complaintsDB.update({ _id: req.params.id }, {
      $set: update,
      $push: { stageHistory: stageEntry }
    });

    // Award points when resolved
    if (nextStage === 6) {
      const user = await usersDB.findOne({ _id: complaint.citizen });
      if (user) {
        const bonus = 25;
        await usersDB.update({ _id: complaint.citizen }, {
          $set: { points: (user.points || 0) + bonus },
          $push: { pointsHistory: { action: 'Complaint resolved! 🎉', points: bonus, date: new Date() } }
        });
      }
    }

    const updated = await complaintsDB.findOne({ _id: req.params.id });
    res.json({ ...updated, stages: STAGES });
  } catch (err) {
    res.status(500).json({ error: 'Failed to advance stage: ' + err.message });
  }
});

// Update complaint (admin)
app.patch('/api/complaints/:id', authMiddleware, adminOnly, async (req, res) => {
  try {
    const { department, adminNotes, priority } = req.body;
    const update = { updatedAt: new Date() };

    if (department) update.department = department;
    if (adminNotes !== undefined) update.adminNotes = adminNotes;
    if (priority) update.priority = priority;

    await complaintsDB.update({ _id: req.params.id }, { $set: update });
    const updated = await complaintsDB.findOne({ _id: req.params.id });
    res.json(updated);
  } catch (err) {
    res.status(500).json({ error: 'Failed to update complaint: ' + err.message });
  }
});

// Get stages info
app.get('/api/stages', (req, res) => res.json(STAGES));
app.get('/api/levels', (req, res) => res.json(LEVELS));

// ═══════════ AI IMAGE ANALYSIS ═══════════
app.post('/api/analyze-image', authMiddleware, upload.single('image'), async (req, res) => {
  try {
    if (!req.file) return res.status(400).json({ error: 'No image uploaded' });

    // If no API key, use a smart mock response so the demo works instantly
    if (!genAI) {
      console.log('No GEMINI_API_KEY found. Sending a smart simulated AI response...');
      const filename = req.file.originalname.toLowerCase();
      
      let category = 'Other';
      let title = 'Civic Issue Detected';
      let description = 'AI Analysis: I have analyzed the image and identified a civic issue. Please provide additional details. (Note: Simulated response because no Gemini API key is configured)';

      if (filename.includes('light') || filename.includes('street') || filename.includes('pole')) {
        category = 'Street Light';
        title = 'Street Light Malfunction';
        description = 'AI Analysis: I detected an issue with a street light. This poses a safety risk for pedestrians and drivers at night and requires maintenance. (Simulated AI)';
      } else if (filename.includes('water') || filename.includes('leak') || filename.includes('pipe')) {
        category = 'Water Leakage';
        title = 'Severe Water Leakage';
        description = 'AI Analysis: The image shows significant water accumulation or leakage from a broken pipe. This could lead to resource wastage and structural damage if not fixed. (Simulated AI)';
      } else if (filename.includes('garbage') || filename.includes('trash') || filename.includes('waste')) {
        category = 'Garbage';
        title = 'Garbage Accumulation';
        description = 'AI Analysis: I detected an uncollected pile of garbage/waste. This is a public sanitation and health hazard that requires immediate clearing. (Simulated AI)';
      } else if (filename.includes('pothole') || filename.includes('hole')) {
        category = 'Pothole';
        title = 'Dangerous Pothole';
        description = 'AI Analysis: I detected a severe pothole on the road surface. It requires immediate repair to prevent accidents and vehicle damage. (Simulated AI)';
      } else if (filename.includes('road') || filename.includes('crack')) {
        category = 'Road Damage';
        title = 'Road Surface Damage';
        description = 'AI Analysis: The road surface shows significant signs of wear and cracking, which may worsen over time with heavy traffic. (Simulated AI)';
      } else if (filename.includes('electric') || filename.includes('wire')) {
        category = 'Electricity';
        title = 'Dangerous Exposed Wires';
        description = 'AI Analysis: Dangerous exposed electrical wires or damaged infrastructure detected. This is a severe, high-priority safety risk. (Simulated AI)';
      } else if (filename.includes('drain')) {
        category = 'Drainage';
        title = 'Blocked Drainage';
        description = 'AI Analysis: Blocked or overflowing drainage system detected, which could cause flooding in the area. (Simulated AI)';
      } else {
        // Default random if name doesn't match
        const cats = ['Pothole', 'Garbage', 'Street Light', 'Water Leakage'];
        category = cats[Math.floor(Math.random() * cats.length)];
        title = `Suspected ${category} Issue`;
        description = `AI Analysis: Based on the visual patterns, this appears to be an issue related to ${category}. (Simulated AI)`;
      }

      return res.json({ title, description, category });
    }

    // Call real Google Gemini AI
    const model = genAI.getGenerativeModel({ model: 'gemini-1.5-flash' });
    const imagePart = {
      inlineData: {
        data: fs.readFileSync(req.file.path).toString("base64"),
        mimeType: req.file.mimetype
      }
    };

    const prompt = `
      You are an expert civic infrastructure inspector.
      Analyze this image of a civic issue and return exactly a JSON object with 3 keys:
      - "title": A short, clear title of the issue (max 6 words).
      - "description": A detailed, professional description of the issue and its severity (2-3 sentences).
      - "category": Match the issue exactly to one of these: Pothole, Water Leakage, Street Light, Garbage, Road Damage, Electricity, Drainage, Other.
      Do not include any other text, markdown, or backticks. Return raw JSON.
    `;

    const result = await model.generateContent([prompt, imagePart]);
    let responseText = result.response.text();
    responseText = responseText.replace(/\`\`\`json/g, '').replace(/\`\`\`/g, '').trim();
    
    const analysis = JSON.parse(responseText);
    res.json(analysis);

  } catch (err) {
    console.error('AI Analysis Error:', err.message);
    res.status(500).json({ error: 'AI analysis failed: ' + err.message });
  }
});

// ═══════════ PAGES ═══════════
app.get('/', (req, res) => res.sendFile(path.join(__dirname, 'public', 'index.html')));
app.get('/citizen', (req, res) => res.sendFile(path.join(__dirname, 'public', 'citizen.html')));
app.get('/admin', (req, res) => res.sendFile(path.join(__dirname, 'public', 'admin.html')));
app.get('/track', (req, res) => res.sendFile(path.join(__dirname, 'public', 'track.html')));
app.get('/profile', (req, res) => res.sendFile(path.join(__dirname, 'public', 'profile.html')));
app.get('/rewards', (req, res) => res.sendFile(path.join(__dirname, 'public', 'rewards.html')));

// ═══════════ SEED DATA ═══════════
async function seedData() {
  try {
    const adminExists = await usersDB.findOne({ email: 'admin@civicconnect.com' });
    if (!adminExists) {
      const hashed = await bcrypt.hash('admin123', 12);
      await usersDB.insert({
        name: 'Ravi Kumar', email: 'admin@civicconnect.com', password: hashed,
        role: 'admin', phone: '9876500001', points: 0, streak: 0,
        lastReportDate: null, pointsHistory: [], createdAt: new Date()
      });
      console.log('✅ Admin seeded: admin@civicconnect.com / admin123');
    }

    const citizenExists = await usersDB.findOne({ email: 'citizen@example.com' });
    let citizenId;
    if (!citizenExists) {
      const hashed = await bcrypt.hash('citizen123', 12);
      const citizen = await usersDB.insert({
        name: 'Arjun Kumar', email: 'citizen@example.com', password: hashed,
        role: 'citizen', phone: '9876543210',
        points: 250, streak: 5, lastReportDate: new Date(),
        pointsHistory: [
          { action: 'Complaint submitted', points: 10, date: new Date(Date.now() - 5*86400000) },
          { action: 'Complaint submitted', points: 10, date: new Date(Date.now() - 4*86400000) },
          { action: '3-day streak bonus! 🔥', points: 20, date: new Date(Date.now() - 3*86400000) },
          { action: 'Complaint submitted', points: 10, date: new Date(Date.now() - 3*86400000) },
          { action: 'Complaint resolved! 🎉', points: 25, date: new Date(Date.now() - 2*86400000) },
          { action: 'Complaint submitted', points: 10, date: new Date(Date.now() - 1*86400000) },
          { action: 'Complaint submitted', points: 10, date: new Date() },
        ],
        createdAt: new Date(Date.now() - 30*86400000)
      });
      citizenId = citizen._id;
      console.log('✅ Citizen seeded: citizen@example.com / citizen123');
    } else {
      citizenId = citizenExists._id;
    }

    const complaintCount = await complaintsDB.count({});
    if (complaintCount === 0 && citizenId) {
      const sampleComplaints = [
        { title: 'Large Pothole on MG Road', description: 'A large pothole near the bus stop causing accidents. Multiple vehicles have been damaged.', category: 'Pothole', location: 'MG Road, Near City Center', stage: 3,
          stageHistory: [
            { stage: 0, name: 'Submitted', timestamp: new Date(Date.now() - 5*86400000) },
            { stage: 1, name: 'Under Review', timestamp: new Date(Date.now() - 4*86400000) },
            { stage: 2, name: 'Assigned', timestamp: new Date(Date.now() - 3*86400000) },
            { stage: 3, name: 'In Progress', timestamp: new Date(Date.now() - 1*86400000) }
          ]},
        { title: 'Water pipe burst on 5th Cross', description: 'Water pipe has burst and is flooding the road. Wastage of water for the past 2 days.', category: 'Water Leakage', location: '5th Cross, Jayanagar', stage: 5,
          stageHistory: [
            { stage: 0, name: 'Submitted', timestamp: new Date(Date.now() - 7*86400000) },
            { stage: 1, name: 'Under Review', timestamp: new Date(Date.now() - 6*86400000) },
            { stage: 2, name: 'Assigned', timestamp: new Date(Date.now() - 5*86400000) },
            { stage: 3, name: 'In Progress', timestamp: new Date(Date.now() - 4*86400000) },
            { stage: 4, name: 'Inspection', timestamp: new Date(Date.now() - 2*86400000) },
            { stage: 5, name: 'Verification', timestamp: new Date(Date.now() - 1*86400000) }
          ]},
        { title: 'Street light not working', description: 'The street light at the junction has been off for a week.', category: 'Street Light', location: 'Park Avenue Junction', stage: 1,
          stageHistory: [
            { stage: 0, name: 'Submitted', timestamp: new Date(Date.now() - 2*86400000) },
            { stage: 1, name: 'Under Review', timestamp: new Date(Date.now() - 1*86400000) }
          ]},
        { title: 'Garbage pile near school', description: 'Garbage has been accumulating near the school gate. Health hazard.', category: 'Garbage', location: 'Near DPS School, Koramangala', stage: 6,
          stageHistory: [
            { stage: 0, name: 'Submitted', timestamp: new Date(Date.now() - 10*86400000) },
            { stage: 1, name: 'Under Review', timestamp: new Date(Date.now() - 9*86400000) },
            { stage: 2, name: 'Assigned', timestamp: new Date(Date.now() - 8*86400000) },
            { stage: 3, name: 'In Progress', timestamp: new Date(Date.now() - 6*86400000) },
            { stage: 4, name: 'Inspection', timestamp: new Date(Date.now() - 4*86400000) },
            { stage: 5, name: 'Verification', timestamp: new Date(Date.now() - 3*86400000) },
            { stage: 6, name: 'Resolved', timestamp: new Date(Date.now() - 2*86400000) }
          ]},
        { title: 'Road surface damaged after rain', description: 'Heavy rain has washed away the road surface. Deep cracks.', category: 'Road Damage', location: 'Outer Ring Road, Marathahalli', stage: 0,
          stageHistory: [{ stage: 0, name: 'Submitted', timestamp: new Date() }]},
        { title: 'Exposed electrical wires', description: 'Electrical wires hanging dangerously low near the playground.', category: 'Electricity', location: 'Children Park, Indiranagar', stage: 4,
          stageHistory: [
            { stage: 0, name: 'Submitted', timestamp: new Date(Date.now() - 6*86400000) },
            { stage: 1, name: 'Under Review', timestamp: new Date(Date.now() - 5*86400000) },
            { stage: 2, name: 'Assigned', timestamp: new Date(Date.now() - 4*86400000) },
            { stage: 3, name: 'In Progress', timestamp: new Date(Date.now() - 3*86400000) },
            { stage: 4, name: 'Inspection', timestamp: new Date(Date.now() - 1*86400000) }
          ]},
        { title: 'Blocked drainage causing flooding', description: 'Drainage blocked with plastic waste causing water logging.', category: 'Drainage', location: 'Silk Board Junction', stage: 2,
          stageHistory: [
            { stage: 0, name: 'Submitted', timestamp: new Date(Date.now() - 3*86400000) },
            { stage: 1, name: 'Under Review', timestamp: new Date(Date.now() - 2*86400000) },
            { stage: 2, name: 'Assigned', timestamp: new Date(Date.now() - 1*86400000) }
          ]},
      ];

      for (const c of sampleComplaints) {
        await complaintsDB.insert({
          ...c,
          image: '',
          status: getStatusFromStage(c.stage),
          priority: getAutoPriority(c.category),
          department: getAutoDepartment(c.category),
          citizen: citizenId,
          citizenName: 'Arjun Kumar',
          citizenEmail: 'citizen@example.com',
          adminNotes: '',
          upvotes: Math.floor(Math.random() * 20),
          resolvedAt: c.stage === 6 ? new Date(Date.now() - 2*86400000) : null,
          createdAt: c.stageHistory[0].timestamp,
          updatedAt: new Date()
        });
      }
      console.log('✅ 7 sample complaints seeded with stage history');
    }
  } catch (err) {
    console.error('Seed error:', err.message);
  }
}

// ═══════════ START SERVER ═══════════
seedData().then(() => {
  app.listen(PORT, () => {
    console.log(`\n🏛️  Civic Connect is running!\n`);
    console.log(`   🌐 App:      http://localhost:${PORT}`);
    console.log(`   👤 Citizen:  http://localhost:${PORT}/citizen`);
    console.log(`   🔧 Admin:    http://localhost:${PORT}/admin`);
    console.log(`   📊 Track:    http://localhost:${PORT}/track`);
    console.log(`   🏆 Profile:  http://localhost:${PORT}/profile`);
    console.log(`   🎁 Rewards:  http://localhost:${PORT}/rewards`);
    console.log(`\n   Demo Accounts:`);
    console.log(`   Citizen: citizen@example.com / citizen123`);
    console.log(`   Admin:   admin@civicconnect.com / admin123\n`);
  });
});
