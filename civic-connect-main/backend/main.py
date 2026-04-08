import json
import os
import shutil
from datetime import datetime, timedelta, date
from typing import Optional, List
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
import database
import auth
import ai_detection
import reward_engine
import voucher_engine
import notifications
from database import get_db

from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Civic Connect API", version="1.0.0")
api_key = os.getenv("GEMINI_API_KEY")
print("API KEY:", api_key)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Upload directory ───────────────────────────────────────────────────────
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ──────────────────────────────────────────────────────────────────────────────
# Pydantic Schemas
# ──────────────────────────────────────────────────────────────────────────────

class CitizenRegister(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ComplaintCreate(BaseModel):
    category: str
    description: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    severity: Optional[str] = "Medium"
    ai_detected: Optional[bool] = False
    ai_confidence: Optional[float] = None
    photo_url: Optional[str] = None


class StageAdvance(BaseModel):
    admin_name: Optional[str] = "Admin"


class TeamAssign(BaseModel):
    worker_ids: List[int]
    lead_id: int


class NoteAdd(BaseModel):
    note: str
    admin_name: Optional[str] = "Admin"


# ──────────────────────────────────────────────────────────────────────────────
# Startup — init DB + seed
# ──────────────────────────────────────────────────────────────────────────────

@app.on_event("startup")
def startup():
    database.init_db()
    seed_database()


def seed_database():
    db = database.SessionLocal()
    try:
        # Skip if already seeded
        if db.query(models.Admin).count() >= 2:
            return

        # ── Admins ──────────────────────────────────────────────────────────
        admins_data = [
            {"name": "Ravi Kumar", "email": "admin@civicconnect.app", "department": "General"},
            {"name": "Priya Sharma", "email": "priya@civicconnect.app", "department": "Roads & Infrastructure"},
        ]
        admins = []
        for a in admins_data:
            admin = models.Admin(
                name=a["name"],
                email=a["email"],
                password_hash=auth.hash_password("admin123"),
                department=a["department"]
            )
            db.add(admin)
            admins.append(admin)
        db.commit()

        # ── Workers ─────────────────────────────────────────────────────────
        workers_data = [
            {"name": "Suresh Patel", "department": "Roads", "phone": "9876543210", "status": "free", "active_job_count": 0, "avg_resolution_hours": 18.5},
            {"name": "Anjali Nair", "department": "Sanitation", "phone": "9876543211", "status": "busy", "active_job_count": 2, "avg_resolution_hours": 12.0},
            {"name": "Manoj Singh", "department": "Electrical", "phone": "9876543212", "status": "free", "active_job_count": 1, "avg_resolution_hours": 8.0},
            {"name": "Deepa Reddy", "department": "Water", "phone": "9876543213", "status": "off_duty", "active_job_count": 0, "avg_resolution_hours": 22.0},
            {"name": "Kiran Das", "department": "Roads", "phone": "9876543214", "status": "free", "active_job_count": 0, "avg_resolution_hours": 16.0},
        ]
        for w in workers_data:
            worker = models.Worker(**w)
            db.add(worker)
        db.commit()

        # ── Citizens ────────────────────────────────────────────────────────
        citizens_data = [
            {"name": "Arjun Mehta", "email": "arjun@example.com", "points": 275, "level": "Silver", "streak_days": 5},
            {"name": "Kavya Iyer", "email": "kavya@example.com", "points": 450, "level": "Gold", "streak_days": 12},
            {"name": "Rohit Verma", "email": "rohit@example.com", "points": 80, "level": "Bronze", "streak_days": 2},
        ]
        citizens = []
        for c in citizens_data:
            citizen = models.Citizen(
                name=c["name"],
                email=c["email"],
                password_hash=auth.hash_password("citizen123"),
                points=c["points"],
                level=c["level"],
                streak_days=c["streak_days"],
                last_reported=date.today().isoformat()
            )
            db.add(citizen)
            citizens.append(citizen)
        db.commit()
        for c in citizens:
            db.refresh(c)

        # ── Point Logs for citizens ─────────────────────────────────────────
        logs_data = [
            (citizens[0].id, "Issue resolved — Complaint #1", 25),
            (citizens[0].id, "7-day reporting streak bonus", 50),
            (citizens[0].id, "Issue resolved — Complaint #3", 25),
            (citizens[1].id, "Issue resolved — Complaint #2", 25),
            (citizens[1].id, "30-day reporting streak bonus", 200),
            (citizens[1].id, "Issue resolved — Complaint #5", 25),
            (citizens[2].id, "Issue resolved — Complaint #4", 25),
        ]
        for cid, action, pts in logs_data:
            db.add(models.PointLog(citizen_id=cid, action=action, points_earned=pts))
        db.commit()

        # ── Complaints ──────────────────────────────────────────────────────
        base_time = datetime.utcnow()
        complaints_data = [
            {
                "citizen_id": citizens[0].id, "category": "Pothole",
                "description": "Large pothole near the main intersection causing traffic delays and vehicle damage.",
                "latitude": 12.9716, "longitude": 77.5946,
                "status": "resolved", "current_stage": 7,
                "severity": "High", "ai_detected": True, "ai_confidence": 92.5,
                "upvotes": 14, "priority_boosted": False,
                "created_at": base_time - timedelta(days=10),
                "sla_deadline": base_time - timedelta(days=3),
            },
            {
                "citizen_id": citizens[1].id, "category": "Garbage",
                "description": "Overflowing garbage bins near the park entrance creating health hazard.",
                "latitude": 12.9352, "longitude": 77.6245,
                "status": "in_progress", "current_stage": 4,
                "severity": "Medium", "ai_detected": True, "ai_confidence": 88.0,
                "upvotes": 8, "priority_boosted": False,
                "created_at": base_time - timedelta(days=5),
                "sla_deadline": base_time + timedelta(days=2),
            },
            {
                "citizen_id": citizens[2].id, "category": "Street Light",
                "description": "Three consecutive street lights not working on MG Road creating safety concern.",
                "latitude": 12.9758, "longitude": 77.6002,
                "status": "in_progress", "current_stage": 3,
                "severity": "Medium", "ai_detected": False, "ai_confidence": None,
                "upvotes": 21, "priority_boosted": True,
                "created_at": base_time - timedelta(days=3),
                "sla_deadline": base_time + timedelta(days=4),
            },
            {
                "citizen_id": citizens[0].id, "category": "Water Leakage",
                "description": "Water pipe burst causing water logging on residential street.",
                "latitude": 12.9610, "longitude": 77.5730,
                "status": "pending", "current_stage": 1,
                "severity": "Critical", "ai_detected": True, "ai_confidence": 96.0,
                "upvotes": 5, "priority_boosted": False,
                "created_at": base_time - timedelta(days=1),
                "sla_deadline": base_time + timedelta(days=1),
            },
            {
                "citizen_id": citizens[1].id, "category": "Road Damage",
                "description": "Severe road damage after recent rains making road impassable.",
                "latitude": 12.9900, "longitude": 77.6900,
                "status": "resolved", "current_stage": 7,
                "severity": "High", "ai_detected": True, "ai_confidence": 85.0,
                "upvotes": 31, "priority_boosted": False,
                "created_at": base_time - timedelta(days=14),
                "sla_deadline": base_time - timedelta(days=7),
            },
            {
                "citizen_id": citizens[2].id, "category": "Garbage",
                "description": "Illegal dumping of construction waste on public land.",
                "latitude": 12.9450, "longitude": 77.6100,
                "status": "pending", "current_stage": 0,
                "severity": "Low", "ai_detected": False, "ai_confidence": None,
                "upvotes": 2, "priority_boosted": False,
                "created_at": base_time - timedelta(hours=6),
                "sla_deadline": base_time + timedelta(days=7),
            },
            {
                "citizen_id": citizens[0].id, "category": "Pothole",
                "description": "Multiple potholes forming a chain along the service road.",
                "latitude": 12.9520, "longitude": 77.5810,
                "status": "in_progress", "current_stage": 5,
                "severity": "High", "ai_detected": True, "ai_confidence": 79.0,
                "upvotes": 17, "priority_boosted": True,
                "created_at": base_time - timedelta(days=7),
                "sla_deadline": base_time + timedelta(hours=12),
            },
            {
                "citizen_id": citizens[1].id, "category": "Street Light",
                "description": "Flickering street light causing visibility issues at night.",
                "latitude": 12.9680, "longitude": 77.6320,
                "status": "pending", "current_stage": 1,
                "severity": "Low", "ai_detected": False, "ai_confidence": None,
                "upvotes": 3, "priority_boosted": False,
                "created_at": base_time - timedelta(days=2),
                "sla_deadline": base_time + timedelta(days=5),
            },
            {
                "citizen_id": citizens[2].id, "category": "Water Leakage",
                "description": "Underground pipe leakage causing road subsidence.",
                "latitude": 12.9800, "longitude": 77.5600,
                "status": "in_progress", "current_stage": 2,
                "severity": "Critical", "ai_detected": True, "ai_confidence": 91.0,
                "upvotes": 9, "priority_boosted": False,
                "created_at": base_time - timedelta(days=4),
                "sla_deadline": base_time - timedelta(hours=6),  # SLA breached
            },
            {
                "citizen_id": citizens[0].id, "category": "Road Damage",
                "description": "Broken road divider posing danger to two-wheeler riders.",
                "latitude": 12.9560, "longitude": 77.6150,
                "status": "pending", "current_stage": 0,
                "severity": "Medium", "ai_detected": False, "ai_confidence": None,
                "upvotes": 6, "priority_boosted": False,
                "created_at": base_time - timedelta(hours=2),
                "sla_deadline": base_time + timedelta(days=6),
            },
        ]

        complaint_objs = []
        for i, cd in enumerate(complaints_data):
            stage_ts = {}
            marked_by = {}
            for s in range(cd["current_stage"] + 1):
                stage_ts[str(s)] = (cd["created_at"] + timedelta(hours=s * 8)).isoformat()
                marked_by[str(s)] = "Admin"

            c = models.Complaint(
                citizen_id=cd["citizen_id"],
                category=cd["category"],
                description=cd["description"],
                latitude=cd["latitude"],
                longitude=cd["longitude"],
                status=cd["status"],
                current_stage=cd["current_stage"],
                stage_timestamps=json.dumps(stage_ts),
                stage_marked_by=json.dumps(marked_by),
                ai_detected=cd["ai_detected"],
                ai_confidence=cd["ai_confidence"],
                severity=cd["severity"],
                priority_boosted=cd["priority_boosted"],
                upvotes=cd["upvotes"],
                sla_deadline=cd["sla_deadline"],
                notes=json.dumps([]),
                created_at=cd["created_at"]
            )
            db.add(c)
            complaint_objs.append(c)
        db.commit()

        print("[Civic Connect] ✅ Database seeded successfully")

    except Exception as e:
        print(f"[Civic Connect] ⚠️  Seed error: {e}")
        db.rollback()
    finally:
        db.close()


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def complaint_to_dict(c: models.Complaint, include_citizen=False) -> dict:
    d = {
        "id": c.id,
        "citizen_id": c.citizen_id,
        "category": c.category,
        "description": c.description,
        "photo_url": c.photo_url,
        "latitude": c.latitude,
        "longitude": c.longitude,
        "status": c.status,
        "current_stage": c.current_stage,
        "stage_timestamps": json.loads(c.stage_timestamps or "{}"),
        "stage_marked_by": json.loads(c.stage_marked_by or "{}"),
        "ai_detected": c.ai_detected,
        "ai_confidence": c.ai_confidence,
        "severity": c.severity,
        "priority_boosted": c.priority_boosted,
        "upvotes": c.upvotes,
        "sla_deadline": c.sla_deadline.isoformat() if c.sla_deadline else None,
        "notes": json.loads(c.notes or "[]"),
        "created_at": c.created_at.isoformat(),
    }
    if include_citizen and c.citizen:
        d["citizen_name"] = c.citizen.name
        d["citizen_email"] = c.citizen.email
    return d


def sla_hours_by_severity(severity: str) -> int:
    mapping = {"Critical": 24, "High": 48, "Medium": 72, "Low": 120}
    return mapping.get(severity, 72)


# ──────────────────────────────────────────────────────────────────────────────
# AUTH ROUTES
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/citizen/register")
def citizen_register(data: CitizenRegister, db: Session = Depends(get_db)):
    if db.query(models.Citizen).filter(models.Citizen.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    citizen = models.Citizen(
        name=data.name,
        email=data.email,
        password_hash=auth.hash_password(data.password)
    )
    db.add(citizen)
    db.commit()
    db.refresh(citizen)
    token = auth.create_token(citizen.id, "citizen")
    return {"token": token, "role": "citizen", "name": citizen.name, "id": citizen.id}


@app.post("/citizen/login")
def citizen_login(data: LoginRequest, db: Session = Depends(get_db)):
    citizen = db.query(models.Citizen).filter(models.Citizen.email == data.email).first()
    if not citizen or not auth.verify_password(data.password, citizen.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth.create_token(citizen.id, "citizen")
    return {"token": token, "role": "citizen", "name": citizen.name, "id": citizen.id}


@app.post("/admin/login")
def admin_login(data: LoginRequest, db: Session = Depends(get_db)):
    admin = db.query(models.Admin).filter(models.Admin.email == data.email).first()
    if not admin or not auth.verify_password(data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth.create_token(admin.id, "admin")
    return {"token": token, "role": "admin", "name": admin.name, "id": admin.id}


# ──────────────────────────────────────────────────────────────────────────────
# AI DETECTION ROUTE
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/detect-image")
async def detect_image(file: UploadFile = File(...)):
    contents = await file.read()
    media_type = file.content_type or "image/jpeg"
    result = ai_detection.detect_image(contents, media_type)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# PHOTO UPLOAD
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/upload-photo")
async def upload_photo(file: UploadFile = File(...), citizen=Depends(auth.get_current_citizen)):
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{citizen.id}_{int(datetime.utcnow().timestamp())}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"photo_url": f"/uploads/{filename}"}


# ──────────────────────────────────────────────────────────────────────────────
# COMPLAINT ROUTES
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/complaints")
def create_complaint(
    data: ComplaintCreate,
    citizen: models.Citizen = Depends(auth.get_current_citizen),
    db: Session = Depends(get_db)
):
    sla_hours = sla_hours_by_severity(data.severity or "Medium")
    complaint = models.Complaint(
        citizen_id=citizen.id,
        category=data.category,
        description=data.description,
        photo_url=data.photo_url,
        latitude=data.latitude,
        longitude=data.longitude,
        status="pending",
        current_stage=0,
        stage_timestamps=json.dumps({"0": datetime.utcnow().isoformat()}),
        stage_marked_by=json.dumps({"0": "System"}),
        ai_detected=data.ai_detected or False,
        ai_confidence=data.ai_confidence,
        severity=data.severity or "Medium",
        sla_deadline=datetime.utcnow() + timedelta(hours=sla_hours),
        notes=json.dumps([])
    )
    db.add(complaint)
    db.commit()
    db.refresh(complaint)

    # Streak update
    streak_bonuses = reward_engine.check_and_update_streak(citizen, db)

    return {
        "complaint": complaint_to_dict(complaint),
        "streak_bonuses": streak_bonuses
    }


@app.get("/complaints")
def get_all_complaints(
    status_filter: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    admin: models.Admin = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    q = db.query(models.Complaint)
    if status_filter:
        q = q.filter(models.Complaint.status == status_filter)
    if category:
        q = q.filter(models.Complaint.category == category)
    if severity:
        q = q.filter(models.Complaint.severity == severity)
    complaints = q.order_by(
        models.Complaint.priority_boosted.desc(),
        models.Complaint.created_at.desc()
    ).all()
    return [complaint_to_dict(c, include_citizen=True) for c in complaints]


@app.get("/complaints/feed")
def public_feed(db: Session = Depends(get_db)):
    """Public feed — no auth needed."""
    complaints = db.query(models.Complaint).order_by(
        models.Complaint.upvotes.desc(),
        models.Complaint.created_at.desc()
    ).limit(50).all()
    result = []
    for c in complaints:
        d = complaint_to_dict(c, include_citizen=False)
        d.pop("citizen_id", None)
        result.append(d)
    return result


@app.get("/complaints/my")
def my_complaints(
    citizen: models.Citizen = Depends(auth.get_current_citizen),
    db: Session = Depends(get_db)
):
    complaints = db.query(models.Complaint).filter(
        models.Complaint.citizen_id == citizen.id
    ).order_by(models.Complaint.created_at.desc()).all()
    return [complaint_to_dict(c) for c in complaints]


@app.get("/complaints/{complaint_id}")
def get_complaint(
    complaint_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    # Try to determine role from bearer token
    auth_header = request.headers.get("Authorization", "")
    include_full = False
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = auth.decode_token(token)
        if payload and payload.get("role") == "admin":
            include_full = True

    return complaint_to_dict(complaint, include_citizen=include_full)


@app.patch("/complaints/{complaint_id}/stage")
async def advance_stage(
    complaint_id: int,
    data: StageAdvance,
    admin: models.Admin = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if complaint.current_stage >= 7:
        raise HTTPException(status_code=400, detail="Complaint already resolved")

    complaint.current_stage += 1
    stage_ts = json.loads(complaint.stage_timestamps or "{}")
    stage_marked = json.loads(complaint.stage_marked_by or "{}")
    stage_ts[str(complaint.current_stage)] = datetime.utcnow().isoformat()
    stage_marked[str(complaint.current_stage)] = data.admin_name or admin.name
    complaint.stage_timestamps = json.dumps(stage_ts)
    complaint.stage_marked_by = json.dumps(stage_marked)

    if complaint.current_stage >= 1:
        complaint.status = "in_progress"
    if complaint.current_stage == 7:
        complaint.status = "resolved"

    db.commit()
    db.refresh(complaint)

    # Email triggers
    citizen = db.query(models.Citizen).filter(models.Citizen.id == complaint.citizen_id).first()
    extra = {}
    if complaint.current_stage in (2, 4, 7):
        if complaint.sla_deadline:
            remaining = complaint.sla_deadline - datetime.utcnow()
            hours = max(0, int(remaining.total_seconds() / 3600))
            extra["eta"] = f"{hours} hours"

        if complaint.current_stage == 7 and citizen:
            elapsed = datetime.utcnow() - complaint.created_at
            days = elapsed.days
            hours = elapsed.seconds // 3600
            extra["time_taken"] = f"{days}d {hours}h"
            # Award resolution points
            reward_info = reward_engine.process_resolution_reward(citizen, complaint.id, db)
            await notifications.send_stage_email(complaint.current_stage, complaint.id, citizen.email, citizen.name, extra)
            return {
                "complaint": complaint_to_dict(complaint, include_citizen=True),
                "reward": reward_info
            }

        if citizen:
            await notifications.send_stage_email(complaint.current_stage, complaint.id, citizen.email, citizen.name, extra)

    return {"complaint": complaint_to_dict(complaint, include_citizen=True)}


@app.post("/complaints/{complaint_id}/upvote")
def upvote_complaint(
    complaint_id: int,
    citizen: models.Citizen = Depends(auth.get_current_citizen),
    db: Session = Depends(get_db)
):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if complaint.citizen_id == citizen.id:
        raise HTTPException(status_code=400, detail="Cannot upvote your own complaint")

    existing = db.query(models.Upvote).filter(
        models.Upvote.complaint_id == complaint_id,
        models.Upvote.citizen_id == citizen.id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already upvoted")

    db.add(models.Upvote(complaint_id=complaint_id, citizen_id=citizen.id))
    complaint.upvotes += 1
    db.commit()
    return {"upvotes": complaint.upvotes}


@app.post("/complaints/{complaint_id}/note")
def add_note(
    complaint_id: int,
    data: NoteAdd,
    admin: models.Admin = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    notes = json.loads(complaint.notes or "[]")
    notes.append({
        "text": data.note,
        "by": data.admin_name or admin.name,
        "at": datetime.utcnow().isoformat()
    })
    complaint.notes = json.dumps(notes)
    db.commit()
    return {"notes": notes}


# ──────────────────────────────────────────────────────────────────────────────
# WORKER ROUTES
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/workers")
def get_workers(admin: models.Admin = Depends(auth.get_current_admin), db: Session = Depends(get_db)):
    workers = db.query(models.Worker).all()
    return [
        {
            "id": w.id, "name": w.name, "department": w.department,
            "phone": w.phone, "status": w.status,
            "active_job_count": w.active_job_count,
            "avg_resolution_hours": w.avg_resolution_hours
        }
        for w in workers
    ]


@app.get("/workers/available")
def get_available_workers(
    department: Optional[str] = None,
    admin: models.Admin = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    q = db.query(models.Worker).filter(models.Worker.status != "off_duty")
    if department:
        q = q.filter(models.Worker.department == department)
    workers = q.order_by(models.Worker.active_job_count.asc()).all()
    return [
        {
            "id": w.id, "name": w.name, "department": w.department,
            "phone": w.phone, "status": w.status,
            "active_job_count": w.active_job_count,
            "avg_resolution_hours": w.avg_resolution_hours,
            "warning": w.active_job_count >= 3
        }
        for w in workers
    ]


@app.post("/complaints/{complaint_id}/team")
def assign_team(
    complaint_id: int,
    data: TeamAssign,
    admin: models.Admin = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    complaint = db.query(models.Complaint).filter(models.Complaint.id == complaint_id).first()
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    # Check for off-duty workers
    for wid in data.worker_ids:
        w = db.query(models.Worker).filter(models.Worker.id == wid).first()
        if w and w.status == "off_duty":
            raise HTTPException(status_code=400, detail=f"Worker {w.name} is off duty")

    # Remove existing team
    existing_team = db.query(models.Team).filter(models.Team.complaint_id == complaint_id).first()
    if existing_team:
        db.query(models.TeamMember).filter(models.TeamMember.team_id == existing_team.id).delete()
        db.delete(existing_team)
        db.commit()

    # Create new team
    team = models.Team(complaint_id=complaint_id)
    db.add(team)
    db.commit()
    db.refresh(team)

    for wid in data.worker_ids:
        role = "lead" if wid == data.lead_id else "worker"
        db.add(models.TeamMember(team_id=team.id, worker_id=wid, role=role))
        worker = db.query(models.Worker).filter(models.Worker.id == wid).first()
        if worker:
            worker.active_job_count += 1
            if worker.active_job_count > 0:
                worker.status = "busy"

    db.commit()
    return {"team_id": team.id, "message": "Team assigned successfully"}


@app.delete("/complaints/{complaint_id}/team/{worker_id}")
def remove_worker_from_team(
    complaint_id: int,
    worker_id: int,
    admin: models.Admin = Depends(auth.get_current_admin),
    db: Session = Depends(get_db)
):
    team = db.query(models.Team).filter(models.Team.complaint_id == complaint_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="No team for this complaint")

    member = db.query(models.TeamMember).filter(
        models.TeamMember.team_id == team.id,
        models.TeamMember.worker_id == worker_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Worker not in this team")

    db.delete(member)
    worker = db.query(models.Worker).filter(models.Worker.id == worker_id).first()
    if worker and worker.active_job_count > 0:
        worker.active_job_count -= 1
        if worker.active_job_count == 0:
            worker.status = "free"
    db.commit()
    return {"message": "Worker removed from team"}


# ──────────────────────────────────────────────────────────────────────────────
# CITIZEN PROFILE + REWARDS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/citizen/profile")
def get_profile(
    citizen: models.Citizen = Depends(auth.get_current_citizen),
    db: Session = Depends(get_db)
):
    logs = db.query(models.PointLog).filter(
        models.PointLog.citizen_id == citizen.id
    ).order_by(models.PointLog.timestamp.desc()).limit(20).all()

    level_thresholds = [0, 100, 300, 600]
    level_names = ["Bronze", "Silver", "Gold", "Diamond"]
    current_idx = 0
    for i, t in enumerate(level_thresholds):
        if citizen.points >= t:
            current_idx = i

    next_threshold = level_thresholds[current_idx + 1] if current_idx < len(level_thresholds) - 1 else None
    current_threshold = level_thresholds[current_idx]
    progress = 0
    if next_threshold:
        progress = int(((citizen.points - current_threshold) / (next_threshold - current_threshold)) * 100)

    return {
        "id": citizen.id,
        "name": citizen.name,
        "email": citizen.email,
        "points": citizen.points,
        "level": citizen.level,
        "streak_days": citizen.streak_days,
        "last_reported": citizen.last_reported,
        "next_threshold": next_threshold,
        "progress_to_next": progress,
        "point_history": [
            {"action": l.action, "points": l.points_earned, "timestamp": l.timestamp.isoformat()}
            for l in logs
        ]
    }


@app.get("/rewards/store")
def rewards_store(citizen: models.Citizen = Depends(auth.get_current_citizen)):
    return [
        {
            "id": "priority_boost",
            "name": "Priority Boost",
            "description": "Move your most recent open complaint to the top of the admin queue.",
            "cost": 50,
            "level_required": "Bronze",
            "icon": "🚀"
        },
        {
            "id": "bus_1day",
            "name": "1-Day Bus Pass",
            "description": "A free 1-day city bus pass delivered as a QR code voucher.",
            "cost": 150,
            "level_required": "Silver",
            "icon": "🚌"
        },
        {
            "id": "bus_7day",
            "name": "7-Day Bus Pass",
            "description": "A free 7-day city bus pass delivered as a QR code voucher.",
            "cost": 500,
            "level_required": "Gold",
            "icon": "🎫"
        },
    ]


@app.post("/rewards/redeem/{reward_id}")
async def redeem_reward(
    reward_id: str,
    citizen: models.Citizen = Depends(auth.get_current_citizen),
    db: Session = Depends(get_db)
):
    level_order = {"Bronze": 0, "Silver": 1, "Gold": 2, "Diamond": 3}
    rewards = {
        "priority_boost": {"cost": 50, "level_required": "Bronze"},
        "bus_1day": {"cost": 150, "level_required": "Silver"},
        "bus_7day": {"cost": 500, "level_required": "Gold"},
    }

    reward = rewards.get(reward_id)
    if not reward:
        raise HTTPException(status_code=404, detail="Reward not found")

    if citizen.points < reward["cost"]:
        raise HTTPException(status_code=400, detail=f"Not enough points. Need {reward['cost']}, have {citizen.points}")

    citizen_level_idx = level_order.get(citizen.level, 0)
    required_level_idx = level_order.get(reward["level_required"], 0)
    if citizen_level_idx < required_level_idx:
        raise HTTPException(status_code=400, detail=f"Requires {reward['level_required']} level")

    # Deduct points
    citizen.points -= reward["cost"]
    citizen.level = reward_engine.calculate_level(citizen.points)

    # Log redemption
    db.add(models.PointLog(
        citizen_id=citizen.id,
        action=f"Redeemed: {reward_id}",
        points_earned=-reward["cost"]
    ))
    db.add(models.Redemption(
        citizen_id=citizen.id,
        reward_type=reward_id,
        points_cost=reward["cost"],
        status="completed"
    ))

    result = {"reward_id": reward_id, "points_spent": reward["cost"], "points_remaining": citizen.points}

    if reward_id == "priority_boost":
        # Boost most recent open complaint
        complaint = db.query(models.Complaint).filter(
            models.Complaint.citizen_id == citizen.id,
            models.Complaint.status != "resolved"
        ).order_by(models.Complaint.created_at.desc()).first()

        if complaint:
            complaint.priority_boosted = True
            result["complaint_id"] = complaint.id
            result["message"] = f"Complaint #{complaint.id} is now priority!"
        else:
            result["message"] = "No open complaints to boost"

    elif reward_id in ("bus_1day", "bus_7day"):
        voucher = voucher_engine.generate_voucher(citizen.id, reward_id, db)
        result["voucher"] = {
            "id": voucher.id,
            "qr_code": voucher.qr_code,
            "type": voucher.type,
            "expires_at": voucher.expires_at.isoformat()
        }
        result["message"] = f"Bus pass generated! Expires: {voucher.expires_at.strftime('%Y-%m-%d %H:%M')} UTC"

        await notifications.send_voucher_email(
            citizen.email,
            citizen.name,
            reward_id,
            voucher.qr_code,
            voucher.expires_at.strftime('%Y-%m-%d %H:%M UTC')
        )

    db.commit()
    db.refresh(citizen)
    return result


@app.get("/citizen/vouchers")
def get_vouchers(
    citizen: models.Citizen = Depends(auth.get_current_citizen),
    db: Session = Depends(get_db)
):
    voucher_engine.expire_old_vouchers(citizen.id, db)
    vouchers = db.query(models.Voucher).filter(
        models.Voucher.citizen_id == citizen.id
    ).order_by(models.Voucher.generated_at.desc()).all()
    return [
        {
            "id": v.id,
            "type": v.type,
            "qr_code": v.qr_code,
            "status": v.status,
            "generated_at": v.generated_at.isoformat(),
            "expires_at": v.expires_at.isoformat() if v.expires_at else None
        }
        for v in vouchers
    ]


# ──────────────────────────────────────────────────────────────────────────────
# ADMIN ANALYTICS
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/admin/analytics")
def get_analytics(admin: models.Admin = Depends(auth.get_current_admin), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    all_complaints = db.query(models.Complaint).all()
    total = len(all_complaints)
    resolved = sum(1 for c in all_complaints if c.status == "resolved")
    in_progress = sum(1 for c in all_complaints if c.status == "in_progress")
    pending = sum(1 for c in all_complaints if c.status == "pending")
    sla_breached = sum(1 for c in all_complaints if c.sla_deadline and c.sla_deadline < now and c.status != "resolved")

    # By category
    by_category = {}
    for c in all_complaints:
        by_category[c.category] = by_category.get(c.category, 0) + 1

    # Last 30 days
    thirty_days_ago = now - timedelta(days=30)
    daily = {}
    for c in all_complaints:
        if c.created_at >= thirty_days_ago:
            day = c.created_at.strftime("%Y-%m-%d")
            daily[day] = daily.get(day, 0) + 1

    # Avg resolution by category
    resolution_by_cat = {}
    counts_by_cat = {}
    for c in all_complaints:
        if c.status == "resolved":
            ts = json.loads(c.stage_timestamps or "{}")
            if "0" in ts and "7" in ts:
                start = datetime.fromisoformat(ts["0"])
                end = datetime.fromisoformat(ts["7"])
                hrs = (end - start).total_seconds() / 3600
                resolution_by_cat[c.category] = resolution_by_cat.get(c.category, 0) + hrs
                counts_by_cat[c.category] = counts_by_cat.get(c.category, 0) + 1

    avg_resolution = {
        cat: round(resolution_by_cat[cat] / counts_by_cat[cat], 1)
        for cat in resolution_by_cat
    }

    # Workers
    workers = db.query(models.Worker).all()
    active_workers = sum(1 for w in workers if w.status == "busy")

    return {
        "total_complaints": total,
        "resolved": resolved,
        "in_progress": in_progress,
        "pending": pending,
        "sla_breached": sla_breached,
        "sla_breach_rate": round(sla_breached / total * 100, 1) if total else 0,
        "by_category": by_category,
        "daily_counts": daily,
        "avg_resolution_hours": avg_resolution,
        "active_workers": active_workers,
        "total_workers": len(workers),
    }


@app.get("/admin/redemptions")
def get_redemptions(admin: models.Admin = Depends(auth.get_current_admin), db: Session = Depends(get_db)):
    redemptions = db.query(models.Redemption).order_by(models.Redemption.requested_at.desc()).limit(50).all()
    return [
        {
            "id": r.id,
            "citizen_id": r.citizen_id,
            "reward_type": r.reward_type,
            "points_cost": r.points_cost,
            "status": r.status,
            "requested_at": r.requested_at.isoformat()
        }
        for r in redemptions
    ]


# ──────────────────────────────────────────────────────────────────────────────
# STATIC FILES + SPA FALLBACK
# ──────────────────────────────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "..", "uploads")

if os.path.exists(UPLOADS_DIR):
    app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
