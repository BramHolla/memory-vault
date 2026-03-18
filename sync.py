"""
Sync Snapchat memories to the cloud.
Usage: python sync.py --api-key sk_xxx path/to/mydata~*.zip

Steps:
  1. Validate API key against users.db in R2 → returns user_id
  2. Process ZIP locally via downloader.py (media/ + memories.db)
  3. Set user_id on all records in memories.db
  4. Upload new media files to users/{user_id}/media/ in R2
  5. Upload memories.db to users/{user_id}/memories.db in R2
  6. App shows new content within 5 minutes
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
    """Populate user_id for all records that don't have it yet."""
    conn = sqlite3.connect(str(db_path))
    # Add column if it doesn't exist (for existing databases)
    try:
        conn.execute("ALTER TABLE memories ADD COLUMN user_id TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.execute("UPDATE memories SET user_id = ? WHERE user_id IS NULL", (user_id,))
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Sync Snapchat memories to R2")
    parser.add_argument("--api-key", required=True, help="Your personal API key (sk_...)")
    parser.add_argument("zip_path", nargs="?", help="Pad naar mydata~*.zip")
    args, extra = parser.parse_known_args()

    if not config.CLOUD_MODE:
        print("Error: R2 credentials not configured. Set R2_* variables in .env")
        sys.exit(1)

    # Step 1: Validate API key
    print("=== Step 1: Validating API key ===")
    s3 = s3_client()
    try:
        users_db_path = users_db.download_users_db(s3)
    except Exception as e:
        print(f"Error: could not download users.db: {e}")
        sys.exit(1)

    user = users_db.get_user_by_api_key(users_db_path, args.api_key)
    if not user:
        print("Error: invalid API key.")
        sys.exit(1)

    user_id = user["id"]
    print(f"  Logged in as: {user_id}")

    # Step 2: Process ZIP via downloader.py
    print("\n=== Step 2: Processing ZIP (locally) ===")
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
        print(f"Downloader exited with code {result.returncode}. Attempting upload anyway.")

    # Step 3: Set user_id in local database
    print("\n=== Step 3: Setting user_id in database ===")
    set_user_id_in_db(config.DB_PATH, user_id)
    print(f"  user_id='{user_id}' set for all records.")

    # Step 4: Upload new files to users/{user_id}/media/
    print(f"\n=== Step 4: Uploading media to users/{user_id}/media/ ===")
    media_prefix = f"users/{user_id}/media/"
    existing_keys = get_existing_r2_keys(s3, media_prefix)
    print(f"  {len(existing_keys)} files already in R2")

    media_files = [
        f for f in config.MEDIA_DIR.iterdir()
        if f.is_file()
        and not f.name.startswith("_")
        and f.suffix.lower() in CONTENT_TYPES
    ]

    to_upload = [f for f in media_files if f"{media_prefix}{f.name}" not in existing_keys]
    print(f"  {len(to_upload)} new files to upload")

    failed = []
    if to_upload:
        with tqdm(total=len(to_upload), unit="file") as pbar:
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
            print(f"  Warning: {len(failed)} uploads failed: {failed[:5]}")
        else:
            print(f"  All {len(to_upload)} files uploaded.")
    else:
        print("  Nothing to upload.")

    # Step 5: Upload database
    print(f"\n=== Step 5: Uploading database to users/{user_id}/memories.db ===")
    s3.upload_file(
        str(config.DB_PATH),
        config.R2_BUCKET_NAME,
        f"users/{user_id}/memories.db",
        ExtraArgs={"ContentType": "application/x-sqlite3"},
    )
    print("  memories.db uploaded.")

    # Step 6: Clean up local files
    print("\n=== Step 6: Cleaning up local files ===")
    import shutil
    removed_media = removed_db = 0
    if config.MEDIA_DIR.exists():
        shutil.rmtree(config.MEDIA_DIR)
        removed_media = 1
        print(f"  media/ removed.")
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
        removed_db = 1
        print(f"  memories.db removed.")

    print("\nSync complete!")
    if failed:
        print(f"  Note: {len(failed)} media files were not uploaded.")
    print("  The app will show new content within 5 minutes.")
    print("  Or restart immediately: flyctl restart")


if __name__ == "__main__":
    main()
