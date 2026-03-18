"""
Eenmalige migratie: bestaande single-user data → users/{user_id}/

Gebruik:
  .venv\\Scripts\\python.exe migrate.py \\
      --user-id bramh \\
      --email bram.holla@gmail.com \\
      --password "kies-een-wachtwoord"

Wat dit script doet:
  1. Maakt users.db aan in R2 met jouw admin-account
  2. Kopieert media/* → users/{user_id}/media/* (alleen wat nog niet bestaat)
  3. Kopieert memories.db → users/{user_id}/memories.db (voegt user_id toe aan records)
  4. Vraagt bevestiging voordat oude root-bestanden verwijderd worden
"""

import argparse
import sqlite3
import sys
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from tqdm import tqdm

import config
import users_db


CONTENT_TYPES = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".mp4":  "video/mp4",
    ".mov":  "video/quicktime",
    ".gif":  "image/gif",
    ".db":   "application/x-sqlite3",
}


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT,
        aws_access_key_id=config.R2_ACCESS_KEY,
        aws_secret_access_key=config.R2_SECRET_KEY,
        region_name="auto",
    )


def copy_object(s3, source_key: str, dest_key: str):
    """Kopieer object binnen dezelfde bucket."""
    s3.copy_object(
        Bucket=config.R2_BUCKET_NAME,
        CopySource={"Bucket": config.R2_BUCKET_NAME, "Key": source_key},
        Key=dest_key,
    )


def add_user_id_to_db(db_path: Path, user_id: str):
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN user_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # kolom bestaat al
    conn.execute("UPDATE memories SET user_id = ? WHERE user_id IS NULL", (user_id,))
    conn.commit()
    updated = conn.execute("SELECT COUNT(*) FROM memories WHERE user_id = ?", (user_id,)).fetchone()[0]
    conn.close()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Migreer single-user data naar multi-user structuur")
    parser.add_argument("--user-id",  required=True, help="Jouw gebruiker-ID (bijv. bramh)")
    parser.add_argument("--email",    required=True, help="Admin e-mailadres")
    parser.add_argument("--password", required=True, help="Admin wachtwoord")
    args = parser.parse_args()

    if not config.CLOUD_MODE:
        print("Fout: R2 credentials niet ingesteld. Zet R2_* variabelen in .env")
        sys.exit(1)

    user_id = args.user_id.lower()
    s3 = s3_client()

    # -----------------------------------------------------------------
    # Stap 1: users.db aanmaken / bijwerken
    # -----------------------------------------------------------------
    print("=== Stap 1: Admin-account aanmaken in users.db ===")
    users_path = users_db.download_users_db(s3)

    existing = users_db.get_user_by_email(users_path, args.email)
    if existing:
        print(f"  Gebruiker '{existing['id']}' bestaat al voor {args.email} — stap overgeslagen.")
        api_key = existing["api_key"]
    else:
        api_key = users_db.create_user(
            users_path, user_id, args.email, args.password, is_admin=True
        )
        users_db.upload_users_db(users_path, s3)
        print(f"  Admin-account aangemaakt: id={user_id}, email={args.email}")
        print(f"  API-key: {api_key}")

    # -----------------------------------------------------------------
    # Stap 2: memories.db migreren
    # -----------------------------------------------------------------
    print(f"\n=== Stap 2: memories.db migreren naar users/{user_id}/memories.db ===")

    # Download bestaande root memories.db
    tmp_db = Path(tempfile.mktemp(suffix="_migrate.db"))
    try:
        s3.download_file(config.R2_BUCKET_NAME, "memories.db", str(tmp_db))
        print("  memories.db gedownload van R2.")
    except Exception as e:
        print(f"  Geen memories.db gevonden in R2 root: {e}")
        print("  (Misschien is de lokale DB nog niet geüpload. Sla stap 2 over.)")
        tmp_db = None

    if tmp_db and tmp_db.exists():
        count = add_user_id_to_db(tmp_db, user_id)
        print(f"  user_id='{user_id}' ingesteld voor {count} records.")
        s3.upload_file(
            str(tmp_db),
            config.R2_BUCKET_NAME,
            f"users/{user_id}/memories.db",
            ExtraArgs={"ContentType": "application/x-sqlite3"},
        )
        print(f"  Geüpload naar users/{user_id}/memories.db")
        tmp_db.unlink()

    # -----------------------------------------------------------------
    # Stap 3: media/* kopiëren naar users/{user_id}/media/
    # -----------------------------------------------------------------
    print(f"\n=== Stap 3: media/* kopiëren naar users/{user_id}/media/ ===")

    # Haal bestaande root-mediabestanden op
    root_media = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME, Prefix="media/"):
        for obj in page.get("Contents", []):
            root_media.append(obj["Key"])
    print(f"  {len(root_media)} bestanden gevonden in media/")

    # Check welke al gekopieerd zijn
    existing_new = set()
    for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME, Prefix=f"users/{user_id}/media/"):
        for obj in page.get("Contents", []):
            existing_new.add(obj["Key"])

    to_copy = [
        k for k in root_media
        if f"users/{user_id}/{k}" not in existing_new
    ]
    print(f"  {len(to_copy)} bestanden te kopiëren ({len(existing_new)} al aanwezig)")

    if to_copy:
        failed = []
        with tqdm(total=len(to_copy), unit="bestand") as pbar:
            def _copy(key):
                filename = key.split("/", 1)[-1]  # "media/foo.jpg" → "foo.jpg"
                dest = f"users/{user_id}/media/{filename}"
                try:
                    copy_object(s3, key, dest)
                    return True
                except Exception as e:
                    print(f"  Kopie mislukt {key}: {e}")
                    return False

            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {pool.submit(_copy, k): k for k in to_copy}
                for future in as_completed(futures):
                    if not future.result():
                        failed.append(futures[future])
                    pbar.update(1)

        if failed:
            print(f"  Waarschuwing: {len(failed)} kopieën mislukt.")
        else:
            print(f"  Alle {len(to_copy)} bestanden gekopieerd.")

    # -----------------------------------------------------------------
    # Stap 4: Optioneel oude root-objecten verwijderen
    # -----------------------------------------------------------------
    print("\n=== Stap 4: Oude root-objecten verwijderen (optioneel) ===")
    old_keys = root_media + (["memories.db"] if tmp_db is not None else [])
    if not old_keys:
        print("  Niets te verwijderen.")
        return

    print(f"  Te verwijderen: {len(old_keys)} objecten (media/* + memories.db in root)")
    answer = input("  Verwijderen? Dit kan niet ongedaan worden. [j/N]: ").strip().lower()
    if answer == "j":
        for key in tqdm(old_keys, unit="object"):
            try:
                s3.delete_object(Bucket=config.R2_BUCKET_NAME, Key=key)
            except Exception as e:
                print(f"  Verwijderen mislukt voor {key}: {e}")
        print("  Oude objecten verwijderd.")
    else:
        print("  Overgeslagen. Je kunt dit later handmatig doen via het Cloudflare dashboard.")

    print("\n=== Migratie klaar! ===")
    print(f"  Gebruiker-ID : {user_id}")
    print(f"  E-mail       : {args.email}")
    print(f"  API-key      : {api_key}")
    print()
    print("Volgende stap: fly deploy")


if __name__ == "__main__":
    main()
