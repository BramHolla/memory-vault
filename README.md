# Memory Vault

A self-hosted, multi-user web gallery for your Snapchat memories. Browse, filter, and relive your snaps — privately, with no third-party access to your data.

**Stack:** Python Flask · Cloudflare R2 · Fly.io · SQLite · Tailwind CSS · Leaflet.js

---

## Features

- **Private gallery** — each user sees only their own memories
- **Infinite scroll** grid with photo and video thumbnails
- **Lightbox viewer** with keyboard navigation and download button
- **Filters** — date range, year, month, media type (photo/video), location radius
- **Map view** — memories plotted on an interactive Leaflet map with clustering
- **Multi-user** — admin panel to invite users, reset passwords, rotate API keys
- **Sync tool** — a standalone `sync.exe` that processes your Snapchat export ZIP and uploads everything to R2
- **Dark theme** with Snapchat yellow accents

---

## Architecture

```
Snapchat export ZIP
       ↓
  sync.exe (local)
  - Reads memories_history.json
  - Downloads / extracts media
  - Writes EXIF / video metadata
  - Uploads media → R2: users/{id}/media/
  - Uploads database → R2: users/{id}/memories.db
       ↓
  Fly.io (Flask app)
  - Serves the gallery UI
  - Caches per-user memories.db from R2 (5 min TTL)
  - API: /api/memories, /api/map-points, /api/stats
  - Auth: email + password, Flask sessions (30 days)
  - Admin: invite users via email, reset passwords, rotate keys
```

---

## Self-hosting Guide

### Prerequisites

- Python 3.11+
- A [Cloudflare account](https://cloudflare.com) with R2 enabled (free tier is sufficient)
- A [Fly.io account](https://fly.io) (free hobby plan works)
- A Gmail account with [App Password](https://support.google.com/accounts/answer/185833) enabled (for invite emails)

### 1. Clone and configure

```bash
git clone https://github.com/BramHolla/memory-vault.git
cd memory-vault
cp .env.example .env
```

Edit `.env` with your credentials (see comments in the file).

### 2. Create a Cloudflare R2 bucket

1. Go to Cloudflare dashboard → R2 → Create bucket
2. Enable **Public Access** on the bucket
3. Create an **API token** with R2 read/write permissions
4. Fill in `R2_ACCOUNT_ID`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET_NAME`, and `R2_PUBLIC_URL` in `.env`

### 3. Set up Python environment

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # Windows
# or
.venv/bin/pip install -r requirements.txt        # macOS/Linux
```

### 4. Deploy to Fly.io

```bash
# Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth login
fly launch   # follow the prompts, skip Postgres/Redis

# Set secrets from your .env
fly secrets set FLASK_SECRET_KEY="..." R2_ACCOUNT_ID="..." R2_ACCESS_KEY="..." \
    R2_SECRET_KEY="..." R2_BUCKET_NAME="..." R2_PUBLIC_URL="..." \
    GMAIL_USER="..." GMAIL_APP_PASSWORD="..."

fly deploy
```

### 5. Create your admin account

Use the migration script to bootstrap the first user:

```bash
.venv\Scripts\python.exe migrate.py --user-id yourid --email you@example.com --admin
```

Or create the users.db manually and upload it to R2 (see `migrate.py` for reference).

### 6. Run locally (optional)

```bash
.venv\Scripts\python.exe app.py
```
Open http://localhost:5000

---

## Sync Tool

The sync tool (`sync.py` / `sync.exe`) processes your Snapchat data export and uploads it to R2.

### Basic usage

```powershell
# With Python
.venv\Scripts\python.exe sync.py --api-key sk_YOUR_KEY "C:\path\to\mydata~*.zip"

# With pre-built binary
sync.exe --api-key sk_YOUR_KEY path\to\mydata~*.zip
```

### What it does

1. Validates your API key against `users.db` in R2
2. Extracts the ZIP and processes `memories_history.json`
3. Downloads or extracts media files, writes EXIF/video metadata
4. Composites overlay images onto photos/videos where present
5. Uploads new media files to `users/{your_id}/media/` in R2
6. Uploads `memories.db` to `users/{your_id}/memories.db` in R2
7. Cleans up local files

### Build sync.exe (for sharing)

```powershell
.venv\Scripts\pip.exe install pyinstaller
.venv\Scripts\pyinstaller.exe --onefile sync.py --name sync
# Output: dist\sync.exe
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `FLASK_SECRET_KEY` | Random secret for Flask session encryption |
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY` | R2 API access key |
| `R2_SECRET_KEY` | R2 API secret key |
| `R2_BUCKET_NAME` | R2 bucket name |
| `R2_PUBLIC_URL` | Public base URL of the R2 bucket |
| `GMAIL_USER` | Gmail address for sending invite/reset emails |
| `GMAIL_APP_PASSWORD` | Gmail App Password (not your login password) |

---

## License

MIT — see [LICENSE](LICENSE).
