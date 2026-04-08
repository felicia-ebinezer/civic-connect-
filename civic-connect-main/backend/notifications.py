import os
import httpx
from dotenv import load_dotenv

load_dotenv()

EMAILJS_SERVICE_ID = os.getenv("EMAILJS_SERVICE_ID", "")
EMAILJS_TEMPLATE_ID = os.getenv("EMAILJS_TEMPLATE_ID", "")
EMAILJS_PUBLIC_KEY = os.getenv("EMAILJS_PUBLIC_KEY", "")

EMAILJS_URL = "https://api.emailjs.com/api/v1.0/email/send"

STAGE_SUBJECTS = {
    2: "Team Assigned to Your Complaint #{id}",
    4: "Work Has Started on Your Complaint #{id}",
    7: "Your Complaint #{id} is Resolved!",
}


def build_stage2_body(complaint_id: int, tracking_link: str, eta: str) -> str:
    return (
        f"Dear Citizen,\n\n"
        f"A team has been assembled to address your complaint #{complaint_id}.\n"
        f"Estimated completion: {eta}\n\n"
        f"Track your complaint here: {tracking_link}\n\n"
        f"— Civic Connect Team"
    )


def build_stage4_body(complaint_id: int, tracking_link: str, eta: str) -> str:
    return (
        f"Dear Citizen,\n\n"
        f"Work has officially started on your complaint #{complaint_id}.\n"
        f"Estimated time remaining: {eta}\n\n"
        f"Track your complaint here: {tracking_link}\n\n"
        f"— Civic Connect Team"
    )


def build_stage7_body(complaint_id: int, tracking_link: str, time_taken: str) -> str:
    return (
        f"Dear Citizen,\n\n"
        f"Great news! Your complaint #{complaint_id} has been fully resolved.\n"
        f"Total time taken: {time_taken}\n\n"
        f"25 reward points have been added to your account!\n\n"
        f"Track your complaint: {tracking_link}\n"
        f"We'd love your feedback — thank you for helping improve our city!\n\n"
        f"— Civic Connect Team"
    )


async def send_stage_email(stage: int, complaint_id: int, citizen_email: str, citizen_name: str, extra: dict = None):
    """Send EmailJS email for stage transitions 2, 4, 7."""
    if stage not in (2, 4, 7):
        return

    if not EMAILJS_SERVICE_ID or not EMAILJS_PUBLIC_KEY:
        print(f"[EmailJS] Skipping email — EMAILJS vars not configured")
        return

    tracking_link = f"http://localhost:8000/citizen/track.html?id={complaint_id}"
    extra = extra or {}

    subject = STAGE_SUBJECTS[stage].replace("{id}", str(complaint_id))

    if stage == 2:
        body = build_stage2_body(complaint_id, tracking_link, extra.get("eta", "48 hours"))
    elif stage == 4:
        body = build_stage4_body(complaint_id, tracking_link, extra.get("eta", "24 hours"))
    else:
        body = build_stage7_body(complaint_id, tracking_link, extra.get("time_taken", "N/A"))

    payload = {
        "service_id": EMAILJS_SERVICE_ID,
        "template_id": EMAILJS_TEMPLATE_ID,
        "user_id": EMAILJS_PUBLIC_KEY,
        "template_params": {
            "to_email": citizen_email,
            "to_name": citizen_name,
            "subject": subject,
            "message": body
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(EMAILJS_URL, json=payload, timeout=10)
            print(f"[EmailJS] Stage {stage} email sent → {resp.status_code}")
    except Exception as e:
        print(f"[EmailJS] Failed to send stage {stage} email: {e}")


async def send_voucher_email(citizen_email: str, citizen_name: str, voucher_type: str, qr_code: str, expires_at: str):
    """Send bus pass QR code email to citizen."""
    if not EMAILJS_SERVICE_ID or not EMAILJS_PUBLIC_KEY:
        print("[EmailJS] Skipping voucher email — EMAILJS vars not configured")
        return

    pass_label = "1-Day" if voucher_type == "bus_1day" else "7-Day"
    subject = f"Your {pass_label} Bus Pass — Civic Connect"
    body = (
        f"Dear {citizen_name},\n\n"
        f"Your {pass_label} Bus Pass has been generated!\n"
        f"Voucher Code: {qr_code}\n"
        f"Expires: {expires_at}\n\n"
        f"Show this code at any bus terminal to activate your pass.\n\n"
        f"— Civic Connect Team"
    )

    payload = {
        "service_id": EMAILJS_SERVICE_ID,
        "template_id": EMAILJS_TEMPLATE_ID,
        "user_id": EMAILJS_PUBLIC_KEY,
        "template_params": {
            "to_email": citizen_email,
            "to_name": citizen_name,
            "subject": subject,
            "message": body
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(EMAILJS_URL, json=payload, timeout=10)
            print(f"[EmailJS] Voucher email sent → {resp.status_code}")
    except Exception as e:
        print(f"[EmailJS] Failed to send voucher email: {e}")
