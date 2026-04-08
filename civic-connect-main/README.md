# 🏛️ Civic Connect
### Smart Civic Issue Reporting and Resolution Platform
> *Connecting citizens to a better city*

---

## 🚀 Quick Start

### 1. Install Python dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env and add your API keys
```

### 3. Start the backend server
```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Open the app
Navigate to **http://localhost:8000** in your browser.

---

## 🔑 Demo Credentials

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@civicconnect.app | admin123 |
| Admin 2 | priya@civicconnect.app | admin123 |
| Citizen | arjun@example.com | citizen123 |
| Citizen | kavya@example.com | citizen123 |

---

## 📁 Project Structure

```
civcconnect/
├── backend/
│   ├── main.py          # All FastAPI routes
│   ├── models.py        # SQLAlchemy models
│   ├── database.py      # SQLite connection
│   ├── auth.py          # JWT + bcrypt
│   ├── ai_detection.py  # Claude Vision API
│   ├── reward_engine.py # Points, streaks, levels
│   ├── voucher_engine.py# QR bus pass generation
│   ├── notifications.py # EmailJS helper
│   └── requirements.txt
└── frontend/
    ├── index.html           # Landing page
    ├── citizen/
    │   ├── login.html
    │   ├── register.html
    │   ├── dashboard.html
    │   ├── report.html      # AI detection + map
    │   ├── track.html       # 7-stage pipeline
    │   ├── profile.html     # Points + streak
    │   ├── rewards.html     # Rewards store
    │   └── vouchers.html    # QR bus passes
    └── admin/
        ├── login.html
        ├── dashboard.html   # Complaints table
        ├── complaint.html   # Stage control panel
        ├── map.html         # Live Leaflet map
        ├── workers.html     # Worker management
        └── analytics.html  # Chart.js charts
```

---

## 🌟 Features

### Citizen Portal
- 📸 **AI Photo Detection** — Upload photo → Claude Vision auto-detects issue type, severity & description
- 📍 **GPS Location** — Leaflet.js map with GPS pin or manual map click
- 📋 **Dashboard** — View and filter all your complaints
- 🔄 **7-Stage Tracker** — Visual pipeline with timestamps and ETA
- 🎁 **Rewards System** — Earn points for resolved issues and reporting streaks
- 🎫 **Bus Passes** — Redeem points for QR-code vouchers (1-day / 7-day)
- 🔥 **Streak Bonuses** — Daily reporting streak milestones: +20/50/200 pts

### Admin Portal
- 📊 **Full Dashboard** — All complaints with filters, search, SLA tracking
- ▶️ **Stage Control** — Advance complaints through 7 stages with one click
- 👷 **Team Assignment** — Assign lead + workers per complaint with availability check
- 🗺️ **Live Map** — Leaflet.js clustered map, color-coded by status
- 📈 **Analytics** — Pie, line, bar charts + SLA gauge + worker performance table
- 📝 **Notes** — Add admin notes at any stage

---

## ⚙️ Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Gemini API key for AI detection |
| `JWT_SECRET` | Secret for JWT signing (change in production!) |
| `EMAILJS_SERVICE_ID` | EmailJS service ID |
| `EMAILJS_TEMPLATE_ID` | EmailJS template ID |
| `EMAILJS_PUBLIC_KEY` | EmailJS public key |

> **Note:** The app works without any API keys (graceful fallbacks). AI detection returns a mock result, and emails are skipped silently.

---

## 🗄️ Database

SQLite database (`backend/civicconnect.db`) is auto-created on first run with seed data:
- 2 admin accounts
- 5 field workers across 4 departments
- 3 citizen accounts with varied point balances
- 10 sample complaints in various stages

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python) |
| Database | SQLite + SQLAlchemy |
| Auth | JWT (python-jose) + bcrypt |
| AI | Google Gemini 1.5 Flash Vision |
| Frontend | Vanilla HTML/CSS/JS (CDN-based) |
| Maps | Leaflet.js |
| Charts | Chart.js |
| QR Codes | qrcode.js |
| Email | EmailJS |
