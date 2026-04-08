import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
print(f"Key used: {api_key}")

if not api_key:
    print("Error: GEMINI_API_KEY not found in .env")
else:
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Say 'Key is working!'")
        print(f"Response: {response.text}")
    except Exception as e:
        print(f"Failed: {str(e)}")
