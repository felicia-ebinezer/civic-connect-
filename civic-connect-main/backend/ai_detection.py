import base64
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)

PROMPT = """Analyze this image and respond ONLY in JSON:
{
  "category": "one of [Pothole, Garbage, Street Light, Water Leakage, Road Damage]",
  "confidence": 0-100,
  "severity": "one of [Low, Medium, High, Critical]",
  "description": "one line description of what you see"
}
No extra text, no markdown formatting, just valid JSON."""


def detect_image(image_bytes: bytes, media_type: str = "image/jpeg") -> dict:
    """Send image to Gemini Vision and return parsed detection result."""
    if not os.getenv("GEMINI_API_KEY"):
        return {
            "category": "Pothole",
            "confidence": 75,
            "severity": "Medium",
            "description": "AI detection unavailable — GEMINI_API_KEY not set. Please configure your API key.",
            "error": "API key not configured"
        }

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        image_part = {
            "mime_type": media_type,
            "data": image_bytes
        }

        response = model.generate_content([image_part, PROMPT])
        
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        result = json.loads(text)

        # Validate and sanitize
        valid_categories = ["Pothole", "Garbage", "Street Light", "Water Leakage", "Road Damage"]
        valid_severities = ["Low", "Medium", "High", "Critical"]

        if result.get("category") not in valid_categories:
            result["category"] = "Pothole"
        if result.get("severity") not in valid_severities:
            result["severity"] = "Medium"
        if not isinstance(result.get("confidence"), (int, float)):
            result["confidence"] = 70
        result["confidence"] = max(0, min(100, int(result["confidence"])))

        return result

    except json.JSONDecodeError:
        return {
            "category": "Road Damage",
            "confidence": 60,
            "severity": "Medium",
            "description": "Could not parse AI response. Please fill in the details manually.",
            "error": "Parse error"
        }
    except Exception as e:
        error_msg = str(e)
        print(f"DEBUG: Gemini Detection Failed: {error_msg}")
        return {
            "category": "Pothole",
            "confidence": 50,
            "severity": "Low",
            "description": f"AI detection failed: {error_msg}",
            "error": error_msg
        }
