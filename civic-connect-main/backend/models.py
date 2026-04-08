from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Citizen(Base):
    __tablename__ = "citizens"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    points = Column(Integer, default=0)
    level = Column(String(20), default="Bronze")
    streak_days = Column(Integer, default=0)
    last_reported = Column(String(20), nullable=True)  # ISO date string YYYY-MM-DD
    created_at = Column(DateTime, default=datetime.utcnow)

    complaints = relationship("Complaint", back_populates="citizen")
    vouchers = relationship("Voucher", back_populates="citizen")
    point_logs = relationship("PointLog", back_populates="citizen")
    redemptions = relationship("Redemption", back_populates="citizen")


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(200), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    department = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Complaint(Base):
    __tablename__ = "complaints"

    id = Column(Integer, primary_key=True, index=True)
    citizen_id = Column(Integer, ForeignKey("citizens.id"), nullable=False)
    category = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    photo_url = Column(String(500), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    status = Column(String(50), default="pending")  # pending / in_progress / resolved
    current_stage = Column(Integer, default=0)
    stage_timestamps = Column(Text, default="{}")  # JSON string
    stage_marked_by = Column(Text, default="{}")   # JSON string
    ai_detected = Column(Boolean, default=False)
    ai_confidence = Column(Float, nullable=True)
    severity = Column(String(20), default="Medium")
    priority_boosted = Column(Boolean, default=False)
    upvotes = Column(Integer, default=0)
    sla_deadline = Column(DateTime, nullable=True)
    notes = Column(Text, default="[]")  # JSON list of note dicts
    created_at = Column(DateTime, default=datetime.utcnow)

    citizen = relationship("Citizen", back_populates="complaints")
    team = relationship("Team", back_populates="complaint", uselist=False)
    upvote_records = relationship("Upvote", back_populates="complaint")


class Upvote(Base):
    __tablename__ = "upvotes"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"), nullable=False)
    citizen_id = Column(Integer, ForeignKey("citizens.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    complaint = relationship("Complaint", back_populates="upvote_records")


class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    department = Column(String(100), nullable=False)
    phone = Column(String(20), nullable=True)
    status = Column(String(20), default="free")  # free / busy / off_duty
    active_job_count = Column(Integer, default=0)
    avg_resolution_hours = Column(Float, default=0.0)

    team_members = relationship("TeamMember", back_populates="worker")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    complaint_id = Column(Integer, ForeignKey("complaints.id"), unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    complaint = relationship("Complaint", back_populates="team")
    members = relationship("TeamMember", back_populates="team")


class TeamMember(Base):
    __tablename__ = "team_members"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    role = Column(String(20), default="worker")  # lead / worker

    team = relationship("Team", back_populates="members")
    worker = relationship("Worker", back_populates="team_members")


class Voucher(Base):
    __tablename__ = "vouchers"

    id = Column(Integer, primary_key=True, index=True)
    citizen_id = Column(Integer, ForeignKey("citizens.id"), nullable=False)
    type = Column(String(20), nullable=False)    # bus_1day / bus_7day
    qr_code = Column(String(100), unique=True, nullable=False)
    status = Column(String(20), default="active")  # active / used / expired
    generated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    citizen = relationship("Citizen", back_populates="vouchers")


class PointLog(Base):
    __tablename__ = "point_log"

    id = Column(Integer, primary_key=True, index=True)
    citizen_id = Column(Integer, ForeignKey("citizens.id"), nullable=False)
    action = Column(String(200), nullable=False)
    points_earned = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    citizen = relationship("Citizen", back_populates="point_logs")


class Redemption(Base):
    __tablename__ = "redemptions"

    id = Column(Integer, primary_key=True, index=True)
    citizen_id = Column(Integer, ForeignKey("citizens.id"), nullable=False)
    reward_type = Column(String(50), nullable=False)
    points_cost = Column(Integer, nullable=False)
    status = Column(String(20), default="completed")
    requested_at = Column(DateTime, default=datetime.utcnow)

    citizen = relationship("Citizen", back_populates="redemptions")
