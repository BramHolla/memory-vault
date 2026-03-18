# Memory Vault

> Snapchat wants you to pay for extra storage to keep your old memories. This is the free, self-hosted alternative.

Download your Snapchat data export, run the sync tool once, and your entire memories library lives in your own private gallery — forever, with no subscription and no third-party access to your photos.

![Memory Vault preview](preview.png)

---

## Why this exists

Snapchat introduced paid tiers that limit how many memories you can store. Once you hit the free quota, older snaps become inaccessible unless you subscribe. Memory Vault is the workaround: export your data from Snapchat (**Settings → My Data**), run the included sync tool, and everything is uploaded to your own storage bucket. You own the data, you control it, and the cost is essentially zero.

---

## Features

Just like Snapchat Memories — but yours:

- **Infinite scroll gallery** — browse all your photos and videos in a fast, responsive grid
- **Lightbox viewer** — full-size view with keyboard navigation and one-click download
- **Filters** — date range, year, month, media type (photo/video), location radius
- **"On this day"** — quick-filter buttons for today, this week, or this month *across all years*
- **Map view** — every geotagged snap plotted on an interactive map with clustering
- **Multi-user** — invite friends or family; each user sees only their own memories
- **Per-user language** — UI switches between English and Dutch per account
- **Admin panel** — invite users, reset passwords, rotate API keys
- **Sync tool** — a standalone `sync.exe` that processes your Snapchat export ZIP (no Python required for end users)
- **Dark theme** with Snapchat yellow accents
- **Demo mode** — visit `/?demo=true` to preview the UI with placeholder images

---

## Hosting options

### Option A — Free (run it yourself, just for you)

If you only need it for yourself and are comfortable running a local server, you can host Memory Vault on your own machine at no cost whatsoever:

- **Storage:** Cloudflare R2 — free tier (10 GB/month egress, 10 million requests/month)
- **App:** runs on your laptop or a spare Raspberry Pi (`python app.py`)
- **Total cost: €0/month**

### Option B — Hosted (a few euros/month, accessible anywhere)

To access your gallery from any device — and to invite friends — deploy the web app to [Fly.io](https://fly.io). Their smallest machine costs around **€1–3/month** and handles multiple users easily.

- **Storage:** Cloudflare R2 (same free tier, or pay-as-you-go cents for large libraries)
- **App:** Fly.io (shared-cpu-1x, 256 MB RAM)
- **Total cost: ~€1–3/month**

This is the recommended setup if you want a permanent link you can bookmark and share with friends.

---

## Architecture

```
Snapchat export ZIP
       ↓
  sync/ (local CLI tool)
  - Reads memories_history.json
  - Downloads / extracts media
  - Writes EXIF / video metadata
  - Uploads media → R2: users/{id}/media/
  - Uploads database → R2: users/{id}/memories.db
       ↓
  Fly.io (Flask app)              ← or localhost for Option A
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
- A [Fly.io account](https://fly.io) — only needed for Option B (hosted)
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

### 4a. Run locally — Option A (free)

```bash
.venv\Scripts\python.exe app.py
```

Open http://localhost:5000. Your gallery is only accessible on your own machine.

### 4b. Deploy to Fly.io — Option B (hosted, ~€1–3/month)

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

```bash
.venv\Scripts\python.exe scripts/migrate.py --user-id yourid --email you@example.com --admin
```

---

## Demo mode

Visit `/?demo=true` on your deployed app to see the gallery with placeholder images instead of your real photos. Useful for screenshots or sharing the UI without exposing personal content.

---

## Sync Tool

The sync tool (`sync.py` / `sync.exe`) processes your Snapchat data export and uploads it to R2.

### Basic usage

```powershell
# With Python
.venv\Scripts\python.exe sync/sync.py --api-key sk_YOUR_KEY "C:\path\to\mydata~*.zip"

# With pre-built binary (share this with friends — no Python needed)
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

### Build sync.exe (for sharing with friends)

```powershell
.venv\Scripts\pip.exe install pyinstaller
.venv\Scripts\pyinstaller.exe --onefile sync/sync.py --name sync --paths .
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

## Contributing

Contributions are welcome! Whether it's a bug fix, a new feature, or an improvement to the docs — feel free to open a pull request.

1. Fork the repo and create a branch (`git checkout -b feature/your-idea`)
2. Make your changes and test locally (`python app.py`)
3. Open a pull request with a clear description of what you changed and why

If you have an idea but don't want to code it yourself, open an issue and let's discuss it.

---

## License

MIT — see [LICENSE](LICENSE).
