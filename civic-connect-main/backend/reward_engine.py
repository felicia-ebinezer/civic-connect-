from datetime import datetime, date
from sqlalchemy.orm import Session
import models


LEVEL_THRESHOLDS = [
    (0, "Bronze"),
    (100, "Silver"),
    (300, "Gold"),
    (600, "Diamond"),
]

STREAK_BONUSES = {
    3: 20,
    7: 50,
    30: 200,
}


def calculate_level(points: int) -> str:
    level = "Bronze"
    for threshold, name in LEVEL_THRESHOLDS:
        if points >= threshold:
            level = name
    return level


def award_points(citizen: models.Citizen, action: str, points: int, db: Session) -> dict:
    """Award points to citizen, update level, log action. Returns level-up info."""
    old_level = citizen.level
    citizen.points += points

    new_level = calculate_level(citizen.points)
    citizen.level = new_level

    log = models.PointLog(
        citizen_id=citizen.id,
        action=action,
        points_earned=points,
        timestamp=datetime.utcnow()
    )
    db.add(log)
    db.commit()
    db.refresh(citizen)

    leveled_up = old_level != new_level
    return {
        "points_earned": points,
        "total_points": citizen.points,
        "level": citizen.level,
        "leveled_up": leveled_up,
        "old_level": old_level if leveled_up else None
    }


def check_and_update_streak(citizen: models.Citizen, db: Session) -> list:
    """Update citizen streak on new complaint submission. Returns list of bonus awards."""
    today_str = date.today().isoformat()
    bonuses = []

    if citizen.last_reported == today_str:
        # Already reported today, no change
        return bonuses

    if citizen.last_reported:
        last_date = date.fromisoformat(citizen.last_reported)
        diff = (date.today() - last_date).days

        if diff == 1:
            # Consecutive day
            citizen.streak_days += 1
        else:
            # Streak broken
            citizen.streak_days = 1
    else:
        citizen.streak_days = 1

    citizen.last_reported = today_str

    # Check streak milestones
    for milestone, bonus_pts in STREAK_BONUSES.items():
        if citizen.streak_days == milestone:
            result = award_points(
                citizen,
                f"{milestone}-day reporting streak bonus",
                bonus_pts,
                db
            )
            bonuses.append(result)

    db.commit()
    db.refresh(citizen)
    return bonuses


def process_resolution_reward(citizen: models.Citizen, complaint_id: int, db: Session) -> dict:
    """Award 25 pts when a complaint reaches Stage 7 (resolved)."""
    return award_points(
        citizen,
        f"Issue resolved — Complaint #{complaint_id}",
        25,
        db
    )
