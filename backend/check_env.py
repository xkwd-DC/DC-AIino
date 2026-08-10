"""Quick check: .env loaded correctly?"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)

key = os.getenv("DEEPSEEK_API_KEY", "")
print(f"API Key loaded: {bool(key)} ({len(key)} chars)")
print(f"Model: {os.getenv('DEEPSEEK_MODEL', 'NOT SET')}")
print(f"Base URL: {os.getenv('DEEPSEEK_BASE_URL', 'NOT SET')}")

if key:
    print("Ready to build index!")
else:
    print("WARNING: DEEPSEEK_API_KEY not set in .env")
