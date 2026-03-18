"""
Sync Snapchat memories naar de cloud.
Gebruik: python sync.py --api-key sk_xxx pad/naar/mydata~*.zip

Stappen:
  1. Valideer API-key tegen users.db in R2 → geeft user_id
  2. Verwerk ZIP lokaal via downloader.py (media/ + memories.db)
  3. Voeg user_id toe aan alle records in memories.db
  4. Upload nieuwe mediabestanden naar users/{user_id}/media/ in R2
  5. Upload memories.db naar users/{user_id}/memories.db in R2
  6. App toont nieuwe inhoud binnen 5 minuten
"""

import argparse
import sqlite3
import sys
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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
}


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT,
        aws_access_key_id=config.R2_ACCESS_KEY,
        aws_secret_access_key=config.R2_SECRET_KEY,
        region_name="auto",
    )


def get_existing_r2_keys(s3, prefix: str) -> set:
    keys = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys


def upload_file(s3, local_path: Path, key: str) -> bool:
    content_type = CONTENT_TYPES.get(local_path.suffix.lower(), "application/octet-stream")
    for attempt in range(3):
        try:
            s3.upload_file(
                str(local_path),
                config.R2_BUCKET_NAME,
                key,
                ExtraArgs={
                    "ContentType": content_type,
                    "CacheControl": "public, max-age=31536000, immutable",
                },
            )
            return True
        except Exception as e:
            if attempt == 2:
                print(f"  Upload mislukt voor {key}: {e}")
                return False
            time.sleep(2 ** attempt)
    return False


def set_user_id_in_db(db_path: Path, user_id: str):
    """Vul user_id in voor alle records die dat nog niet hebben."""
    conn = sqlite3.connect(str(db_path))
    # Voeg kolom toe als die nog niet bestaat (voor bestaande DB's)
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN user_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # kolom bestaat al
    conn.execute("UPDATE memories SET user_id = ? WHERE user_id IS NULL", (user_id,))
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Sync Snapchat memories naar R2")
    parser.add_argument("--api-key", required=True, help="Jouw persoonlijke API-key (sk_...)")
    parser.add_argument("zip_path", nargs="?", help="Pad naar mydata~*.zip")
    args, extra = parser.parse_known_args()

    if not config.CLOUD_MODE:
        print("Fout: R2 credentials niet ingesteld. Zet R2_* variabelen in .env")
        sys.exit(1)

    # Stap 1: API-key valideren
    print("=== Stap 1: API-key valideren ===")
    s3 = s3_client()
    try:
        users_db_path = users_db.download_users_db(s3)
    except Exception as e:
        print(f"Fout: kon users.db niet downloaden: {e}")
        sys.exit(1)

    user = users_db.get_user_by_api_key(users_db_path, args.api_key)
    if not user:
        print("Fout: ongeldige API-key.")
        sys.exit(1)

    user_id = user["id"]
    print(f"  Ingelogd als: {user_id}")

    # Stap 2: ZIP verwerken via downloader.py
    print("\n=== Stap 2: ZIP verwerken (lokaal) ===")
    zip_args = []
    if args.zip_path:
        zip_args = [args.zip_path]
    elif extra:
        zip_args = extra

    result = subprocess.run(
        [sys.executable, str(config.BASE_DIR / "downloader.py")] + zip_args,
        check=False,
    )
    if result.returncode != 0:
        print(f"Downloader afgesloten met code {result.returncode}. Upload wordt toch geprobeerd.")

    # Stap 3: user_id instellen in lokale DB
    print("\n=== Stap 3: user_id instellen in database ===")
    set_user_id_in_db(config.DB_PATH, user_id)
    print(f"  user_id='{user_id}' ingesteld voor alle records.")

    # Stap 4: Nieuwe bestanden uploaden naar users/{user_id}/media/
    print(f"\n=== Stap 4: Media uploaden naar users/{user_id}/media/ ===")
    media_prefix = f"users/{user_id}/media/"
    existing_keys = get_existing_r2_keys(s3, media_prefix)
    print(f"  {len(existing_keys)} bestanden al in R2")

    media_files = [
        f for f in config.MEDIA_DIR.iterdir()
        if f.is_file()
        and not f.name.startswith("_")
        and f.suffix.lower() in CONTENT_TYPES
    ]

    to_upload = [f for f in media_files if f"{media_prefix}{f.name}" not in existing_keys]
    print(f"  {len(to_upload)} nieuwe bestanden te uploaden")

    failed = []
    if to_upload:
        with tqdm(total=len(to_upload), unit="bestand") as pbar:
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {
                    pool.submit(upload_file, s3, f, f"{media_prefix}{f.name}"): f
                    for f in to_upload
                }
                for future in as_completed(futures):
                    if not future.result():
                        failed.append(futures[future].name)
                    pbar.update(1)

        if failed:
            print(f"  Waarschuwing: {len(failed)} uploads mislukt: {failed[:5]}")
        else:
            print(f"  Alle {len(to_upload)} bestanden geüpload.")
    else:
        print("  Niets te uploaden.")

    # Stap 5: Database uploaden
    print(f"\n=== Stap 5: Database uploaden naar users/{user_id}/memories.db ===")
    s3.upload_file(
        str(config.DB_PATH),
        config.R2_BUCKET_NAME,
        f"users/{user_id}/memories.db",
        ExtraArgs={"ContentType": "application/x-sqlite3"},
    )
    print("  memories.db geüpload.")

    # Stap 6: Lokale bestanden opruimen
    print("\n=== Stap 6: Lokale bestanden opruimen ===")
    import shutil
    removed_media = removed_db = 0
    if config.MEDIA_DIR.exists():
        shutil.rmtree(config.MEDIA_DIR)
        removed_media = 1
        print(f"  media/ verwijderd.")
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
        removed_db = 1
        print(f"  memories.db verwijderd.")

    print("\nSync klaar!")
    if failed:
        print(f"  Let op: {len(failed)} mediabestanden zijn niet geüpload.")
    print("  De app toont de nieuwe inhoud binnen 5 minuten.")
    print("  Of herstart direct: flyctl restart")


if __name__ == "__main__":
    main()
