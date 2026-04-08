const mongoose = require('mongoose');

const complaintSchema = new mongoose.Schema({
  title: { type: String, required: true, trim: true },
  description: { type: String, required: true },
  category: {
    type: String,
    required: true,
    enum: ['Pothole', 'Water Leakage', 'Street Light', 'Garbage', 'Road Damage', 'Electricity', 'Drainage', 'Other']
  },
  location: { type: String, required: true },
  image: { type: String, default: '' },
  status: {
    type: String,
    enum: ['Pending', 'In Progress', 'Resolved'],
    default: 'Pending'
  },
  priority: {
    type: String,
    enum: ['High', 'Medium', 'Low'],
    default: 'Medium'
  },
  department: {
    type: String,
    enum: ['Road', 'Water', 'Electricity', 'Sanitation', 'General'],
    default: 'General'
  },
  citizen: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  citizenName: { type: String, default: '' },
  citizenEmail: { type: String, default: '' },
  adminNotes: { type: String, default: '' },
  resolvedAt: { type: Date, default: null },
  createdAt: { type: Date, default: Date.now },
  updatedAt: { type: Date, default: Date.now }
});

// Auto-assign priority based on category
complaintSchema.pre('save', function (next) {
  if (this.isNew || this.isModified('category')) {
    const priorityMap = {
      'Water Leakage': 'High',
      'Electricity': 'High',
      'Drainage': 'High',
      'Pothole': 'Medium',
      'Road Damage': 'Medium',
      'Street Light': 'Low',
      'Garbage': 'Low',
      'Other': 'Low'
    };
    this.priority = priorityMap[this.category] || 'Medium';

    // Auto-assign department
    const deptMap = {
      'Pothole': 'Road',
      'Road Damage': 'Road',
      'Water Leakage': 'Water',
      'Drainage': 'Water',
      'Street Light': 'Electricity',
      'Electricity': 'Electricity',
      'Garbage': 'Sanitation',
      'Other': 'General'
    };
    this.department = deptMap[this.category] || 'General';
  }
  this.updatedAt = Date.now();
  next();
});

// Index for duplicate detection
complaintSchema.index({ location: 1, category: 1 });

module.exports = mongoose.model('Complaint', complaintSchema);
