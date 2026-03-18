import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR  = Path(__file__).parent
MEDIA_DIR = BASE_DIR / "media"
DB_PATH   = BASE_DIR / "memories.db"

MAX_WORKERS  = 6
RETRY_DELAYS = [2, 4, 8]  # seconds between attempts

# R2 / Cloud config
R2_ACCOUNT_ID  = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY  = os.environ.get("R2_ACCESS_KEY", "")
R2_SECRET_KEY  = os.environ.get("R2_SECRET_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "")
R2_PUBLIC_URL  = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")
R2_ENDPOINT    = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Auth
APP_PASSWORD     = os.environ.get("APP_PASSWORD", "")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-insecure-key")
ADMIN_EMAIL      = os.environ.get("ADMIN_EMAIL", "")

# Gmail SMTP (voor uitnodigingen en wachtwoordresets)
GMAIL_USER         = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

# Cloud mode: True when R2 is fully configured
CLOUD_MODE = bool(R2_ACCOUNT_ID and R2_ACCESS_KEY and R2_BUCKET_NAME)
