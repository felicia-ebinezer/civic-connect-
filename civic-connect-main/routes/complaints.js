const express = require('express');
const multer = require('multer');
const path = require('path');
const Complaint = require('../models/Complaint');
const { auth, adminOnly } = require('../middleware/auth');
const router = express.Router();

// Multer config for image uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => cb(null, 'uploads/'),
  filename: (req, file, cb) => {
    const uniqueName = Date.now() + '-' + Math.round(Math.random() * 1E9) + path.extname(file.originalname);
    cb(null, uniqueName);
  }
});
const upload = multer({
  storage,
  limits: { fileSize: 10 * 1024 * 1024 },
  fileFilter: (req, file, cb) => {
    const allowed = /jpeg|jpg|png|webp/;
    const ext = allowed.test(path.extname(file.originalname).toLowerCase());
    const mime = allowed.test(file.mimetype);
    if (ext && mime) return cb(null, true);
    cb(new Error('Only JPG, PNG, WEBP images allowed'));
  }
});

// Create complaint (citizen)
router.post('/', auth, upload.single('image'), async (req, res) => {
  try {
    const { title, description, category, location } = req.body;

    if (!title || !description || !category || !location) {
      return res.status(400).json({ error: 'Title, description, category, and location are required.' });
    }

    // Duplicate check: same location + category with unresolved status
    const duplicate = await Complaint.findOne({
      location: { $regex: new RegExp(location.trim(), 'i') },
      category,
      status: { $ne: 'Resolved' }
    });
    if (duplicate) {
      return res.status(409).json({
        error: 'A similar complaint already exists at this location.',
        existingId: duplicate._id
      });
    }

    const complaint = new Complaint({
      title,
      description,
      category,
      location,
      image: req.file ? `/uploads/${req.file.filename}` : '',
      citizen: req.user.id,
      citizenName: req.user.name,
      citizenEmail: req.user.email
    });

    await complaint.save();
    res.status(201).json(complaint);
  } catch (err) {
    res.status(500).json({ error: 'Failed to create complaint: ' + err.message });
  }
});

// Get citizen's own complaints
router.get('/my', auth, async (req, res) => {
  try {
    const complaints = await Complaint.find({ citizen: req.user.id }).sort({ createdAt: -1 });
    res.json(complaints);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch complaints.' });
  }
});

// Get ALL complaints (admin only)
router.get('/all', auth, adminOnly, async (req, res) => {
  try {
    const { category, location, status, priority, department, sort } = req.query;
    const filter = {};

    if (category) filter.category = category;
    if (status) filter.status = status;
    if (priority) filter.priority = priority;
    if (department) filter.department = department;
    if (location) filter.location = { $regex: new RegExp(location, 'i') };

    let sortObj = { createdAt: -1 };
    if (sort === 'priority') {
      sortObj = { priority: 1, createdAt: -1 };
    } else if (sort === 'status') {
      sortObj = { status: 1, createdAt: -1 };
    } else if (sort === 'oldest') {
      sortObj = { createdAt: 1 };
    }

    const complaints = await Complaint.find(filter).sort(sortObj);
    res.json(complaints);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch complaints.' });
  }
});

// Get single complaint
router.get('/:id', auth, async (req, res) => {
  try {
    const complaint = await Complaint.findById(req.params.id);
    if (!complaint) return res.status(404).json({ error: 'Complaint not found.' });

    // Citizens can only view their own complaints
    if (req.user.role === 'citizen' && complaint.citizen.toString() !== req.user.id) {
      return res.status(403).json({ error: 'Access denied.' });
    }
    res.json(complaint);
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch complaint.' });
  }
});

// Update complaint status (admin only)
router.patch('/:id', auth, adminOnly, async (req, res) => {
  try {
    const { status, department, adminNotes, priority } = req.body;
    const update = { updatedAt: Date.now() };

    if (status) {
      const validFlow = { 'Pending': 'In Progress', 'In Progress': 'Resolved' };
      const complaint = await Complaint.findById(req.params.id);
      if (!complaint) return res.status(404).json({ error: 'Complaint not found.' });

      // Validate status transition
      if (validFlow[complaint.status] !== status && status !== complaint.status) {
        return res.status(400).json({ error: `Cannot change status from "${complaint.status}" to "${status}".` });
      }
      update.status = status;
      if (status === 'Resolved') update.resolvedAt = Date.now();
    }
    if (department) update.department = department;
    if (adminNotes !== undefined) update.adminNotes = adminNotes;
    if (priority) update.priority = priority;

    const complaint = await Complaint.findByIdAndUpdate(req.params.id, update, { new: true });
    if (!complaint) return res.status(404).json({ error: 'Complaint not found.' });

    res.json(complaint);
  } catch (err) {
    res.status(500).json({ error: 'Failed to update complaint: ' + err.message });
  }
});

// Get stats (admin only)
router.get('/stats/summary', auth, adminOnly, async (req, res) => {
  try {
    const total = await Complaint.countDocuments();
    const pending = await Complaint.countDocuments({ status: 'Pending' });
    const inProgress = await Complaint.countDocuments({ status: 'In Progress' });
    const resolved = await Complaint.countDocuments({ status: 'Resolved' });
    const highPriority = await Complaint.countDocuments({ priority: 'High' });

    const byCategory = await Complaint.aggregate([
      { $group: { _id: '$category', count: { $sum: 1 } } }
    ]);
    const byDepartment = await Complaint.aggregate([
      { $group: { _id: '$department', count: { $sum: 1 } } }
    ]);

    res.json({ total, pending, inProgress, resolved, highPriority, byCategory, byDepartment });
  } catch (err) {
    res.status(500).json({ error: 'Failed to fetch statistics.' });
  }
});

module.exports = router;
