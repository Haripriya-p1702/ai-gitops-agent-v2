import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
if not api_key:
    print("No API key found in .env")
    exit(1)

genai.configure(api_key=api_key)
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"Model ID: {m.name}")
except Exception as e:
    print(f"Failed to list models: {e}")
