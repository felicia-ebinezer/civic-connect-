from datetime import datetime, timedelta
import uuid
from sqlalchemy.orm import Session
import models


def generate_voucher(citizen_id: int, voucher_type: str, db: Session) -> models.Voucher:
    """
    Generate a bus pass voucher for the citizen.
    voucher_type: 'bus_1day' | 'bus_7day'
    """
    if voucher_type not in ("bus_1day", "bus_7day"):
        raise ValueError(f"Invalid voucher type: {voucher_type}")

    days = 1 if voucher_type == "bus_1day" else 7
    generated_at = datetime.utcnow()
    expires_at = generated_at + timedelta(days=days)

    qr_code = str(uuid.uuid4())

    voucher = models.Voucher(
        citizen_id=citizen_id,
        type=voucher_type,
        qr_code=qr_code,
        status="active",
        generated_at=generated_at,
        expires_at=expires_at
    )
    db.add(voucher)
    db.commit()
    db.refresh(voucher)
    return voucher


def expire_old_vouchers(citizen_id: int, db: Session):
    """Mark expired vouchers as 'expired'."""
    now = datetime.utcnow()
    expired = db.query(models.Voucher).filter(
        models.Voucher.citizen_id == citizen_id,
        models.Voucher.status == "active",
        models.Voucher.expires_at < now
    ).all()
    for v in expired:
        v.status = "expired"
    db.commit()
