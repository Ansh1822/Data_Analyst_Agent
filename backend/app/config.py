"""All settings come from environment variables (see .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.getenv("RUNS_DIR", BASE_DIR / "workspace"))
(RUNS_DIR / "datasets").mkdir(parents=True, exist_ok=True)
(RUNS_DIR / "runs").mkdir(parents=True, exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL = os.getenv("ANALYST_MODEL", "llama-3.1-8b-instant")  # free on Groq; see console.groq.com/docs/models
SANDBOX_MODE = os.getenv("SANDBOX_MODE", "local")  # local | docker
SANDBOX_IMAGE = os.getenv("SANDBOX_IMAGE", "analyst-sandbox")
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "60"))
MAX_FIX_ATTEMPTS = int(os.getenv("MAX_FIX_ATTEMPTS", "3"))  # retries after the first try
MAX_STEPS = int(os.getenv("MAX_STEPS", "5"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]

# If set, /api/upload and /api/analyze require the header X-Access-Code to match (protects a public deployment).
ACCESS_CODE = os.getenv("ACCESS_CODE", "")
