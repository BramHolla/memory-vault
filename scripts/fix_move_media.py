"""
Eenmalig: verplaats losse mediabestanden uit de R2-root naar users/bramh/media/

Gebruik:
  .venv\Scripts\python.exe fix_move_media.py --user-id bramh [--delete]

Zonder --delete worden de originelen NIET verwijderd (veilig om eerst te testen).
Met --delete worden ze daarna verwijderd.
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow imports from the project root (config, etc.)
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
from tqdm import tqdm

import config

MEDIA_EXTENSIONS = {".jpg", ".jpeg", ".png", ".mp4", ".mov", ".gif"}


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT,
        aws_access_key_id=config.R2_ACCESS_KEY,
        aws_secret_access_key=config.R2_SECRET_KEY,
        region_name="auto",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default="bramh")
    parser.add_argument("--delete", action="store_true", help="Verwijder originelen na kopiëren")
    args = parser.parse_args()

    if not config.CLOUD_MODE:
        print("Fout: R2 credentials niet ingesteld.")
        sys.exit(1)

    s3 = s3_client()
    user_id = args.user_id.lower()
    dest_prefix = f"users/{user_id}/media/"

    # Haal alle objecten op in de root (geen slash in de key)
    print("R2-inhoud ophalen...")
    paginator = s3.get_paginator("list_objects_v2")

    root_media = []
    for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            # Alleen root-level bestanden (geen / in de key) met mediaextensie
            if "/" not in key:
                ext = "." + key.rsplit(".", 1)[-1].lower() if "." in key else ""
                if ext in MEDIA_EXTENSIONS:
                    root_media.append(key)

    print(f"  {len(root_media)} mediabestanden gevonden in de R2-root")

    if not root_media:
        print("Niets te doen.")
        return

    # Check welke al in de doelmap staan
    existing_dest = set()
    for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME, Prefix=dest_prefix):
        for obj in page.get("Contents", []):
            existing_dest.add(obj["Key"].removeprefix(dest_prefix))

    to_copy = [k for k in root_media if k not in existing_dest]
    already = len(root_media) - len(to_copy)
    print(f"  {already} al aanwezig in {dest_prefix}")
    print(f"  {len(to_copy)} te kopiëren")

    if not to_copy:
        print("Alles al op de juiste plek.")
    else:
        failed = []
        print(f"\nKopiëren naar {dest_prefix}...")
        with tqdm(total=len(to_copy), unit="bestand") as pbar:
            def _copy(key):
                try:
                    s3.copy_object(
                        Bucket=config.R2_BUCKET_NAME,
                        CopySource={"Bucket": config.R2_BUCKET_NAME, "Key": key},
                        Key=f"{dest_prefix}{key}",
                    )
                    return True
                except Exception as e:
                    print(f"\n  Mislukt: {key}: {e}")
                    return False

            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = {pool.submit(_copy, k): k for k in to_copy}
                for future in as_completed(futures):
                    if not future.result():
                        failed.append(futures[future])
                    pbar.update(1)

        if failed:
            print(f"\nWaarschuwing: {len(failed)} kopieën mislukt — originelen worden NIET verwijderd.")
            args.delete = False
        else:
            print(f"\nAlle {len(to_copy)} bestanden gekopieerd naar {dest_prefix}")

    # Originelen verwijderen
    all_done = list(set(root_media))  # ook de al-aanwezige
    if args.delete:
        print(f"\n{len(all_done)} originelen verwijderen uit root...")
        for key in tqdm(all_done, unit="object"):
            try:
                s3.delete_object(Bucket=config.R2_BUCKET_NAME, Key=key)
            except Exception as e:
                print(f"  Verwijderen mislukt: {key}: {e}")
        print("Klaar.")
    else:
        print(f"\nOriginelen zijn NIET verwijderd (run opnieuw met --delete om ze weg te halen).")
        print("Eerst verifiëren of de app de foto's correct toont, dan --delete runnen.")


if __name__ == "__main__":
    main()
