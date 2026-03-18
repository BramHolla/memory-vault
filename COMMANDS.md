# Memory Vault — Commands

## Sync new memories

```powershell
.venv\Scripts\python.exe sync.py --api-key sk_YOUR_API_KEY_HERE "C:\path\to\mydata~*.zip"
```

Automatically: processes the ZIP → sets user_id → uploads media to R2 → uploads database.
The app shows new content within ~5 minutes.

---

## Fly.io — App management (`memory-vault`)

### View status
```powershell
fly status -a memory-vault
```

### View live logs
```powershell
fly logs -a memory-vault
```

### Restart app
```powershell
fly apps restart memory-vault
```

### Deploy new version (after code changes)
```powershell
fly deploy
```

### List secrets (names only, not values)
```powershell
fly secrets list -a memory-vault
```

### Update a secret
```powershell
fly secrets set GMAIL_APP_PASSWORD="new_value" -a memory-vault
```

### Open app in browser
```powershell
fly apps open -a memory-vault
```

---

## Admin panel

Manage users at: **https://your-app.fly.dev/admin**

- Add user → invitation email is sent automatically
- Reset password → reset email is sent to the user
- Copy API key → share with user for sync

---

## Build sync.exe (for sharing with friends)

```powershell
.venv\Scripts\pip.exe install pyinstaller
.venv\Scripts\pyinstaller.exe --onefile sync.py --name sync
```

Output is in `dist\sync.exe`. Only rebuild if `sync.py`, `config.py`, `users_db.py`, or `downloader.py` changes.

**Instructions for the user:**
```
sync.exe --api-key sk_THEIR_KEY path\to\mydata~*.zip
```

---

## Run locally (for development/testing)

```powershell
.venv\Scripts\python.exe app.py
```
Go to: http://localhost:5000

---

## One-time: reorganize media files (already done)

```powershell
# Dry run (no deletions)
.venv\Scripts\python.exe fix_move_media.py --user-id YOUR_USER_ID

# Delete originals after verification
.venv\Scripts\python.exe fix_move_media.py --user-id YOUR_USER_ID --delete
```

---

## R2 bucket structure

```
your-bucket-name (bucket)
  users.db                        ← user database
  users/
    alice/
      memories.db                 ← Alice's memories database
      media/                      ← Alice's photos and videos
    bob/
      memories.db
      media/
```
