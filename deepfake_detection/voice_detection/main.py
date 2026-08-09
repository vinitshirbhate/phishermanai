import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("AURIGIN_API_KEY", "aurigin_test_1234567890abcdef")
BASE_URL = "https://api.aurigin.ai/v1"
FILE_PATH = "samples/fake_audio.wav"  # Replace with the path to your local audio file

with open(FILE_PATH, "rb") as f:
    files = {
        "file": (os.path.basename(FILE_PATH), f, "audio/wav")
    }
    r2 = requests.post(f"{BASE_URL}/predict", headers={"x-api-key": API_KEY}, files=files)
    print("Multipart response:", r2.status_code, r2.json())