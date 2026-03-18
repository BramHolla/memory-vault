"""
Gebruikersbeheer via users.db in Cloudflare R2.
"""

import secrets
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from werkzeug.security import check_password_hash, generate_password_hash

import config

USERS_DB_KEY = "users.db"

INVITE_TTL_DAYS  = 7
RESET_TTL_HOURS  = 1


# ---------------------------------------------------------------------------
# R2 helpers
# ---------------------------------------------------------------------------

def _s3():
    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT,
        aws_access_key_id=config.R2_ACCESS_KEY,
        aws_secret_access_key=config.R2_SECRET_KEY,
        region_name="auto",
    )


def download_users_db(s3=None, silent: bool = False) -> Path:
    if s3 is None:
        s3 = _s3()
    tmp = Path(tempfile.mktemp(suffix="_users.db"))
    try:
        # Gebruik get_object i.p.v. download_file — R2 tokens blokkeren soms
        # de HeadObject-aanroep die download_file intern doet.
        response = s3.get_object(Bucket=config.R2_BUCKET_NAME, Key=USERS_DB_KEY)
        tmp.write_bytes(response["Body"].read())
    except Exception as e:
        if silent:
            _init_users_db(tmp)
        else:
            raise RuntimeError(f"Kon users.db niet downloaden van R2: {e}") from e
    return tmp


def upload_users_db(path: Path, s3=None):
    if s3 is None:
        s3 = _s3()
    s3.upload_file(
        str(path),
        config.R2_BUCKET_NAME,
        USERS_DB_KEY,
        ExtraArgs={"ContentType": "application/x-sqlite3"},
    )


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS users (
        id              TEXT PRIMARY KEY,
        email           TEXT UNIQUE NOT NULL,
        password        TEXT,
        api_key         TEXT UNIQUE NOT NULL,
        is_admin        INTEGER DEFAULT 0,
        created         TEXT NOT NULL,
        invite_token    TEXT,
        invite_expires  TEXT,
        reset_token     TEXT,
        reset_expires   TEXT
    );
"""


def _init_users_db(path: Path):
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def _get_conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    # Migreer bestaande DB's met ontbrekende kolommen
    for col, defn in [
        ("invite_token",   "TEXT"),
        ("invite_expires", "TEXT"),
        ("reset_token",    "TEXT"),
        ("reset_expires",  "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {defn}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # kolom bestaat al
    # Wachtwoord mag NULL zijn (uitgenodigde gebruiker nog niet ingesteld)
    return conn


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_user(path: Path, user_id: str, email: str, password: str | None = None,
                is_admin: bool = False) -> str:
    """Maak gebruiker aan. Wachtwoord mag None zijn (uitnodiging). Geeft api_key terug."""
    api_key = "sk_" + secrets.token_hex(32)
    hashed  = generate_password_hash(password) if password else None
    created = datetime.now(timezone.utc).isoformat()
    conn = _get_conn(path)
    with conn:
        conn.execute(
            "INSERT INTO users (id, email, password, api_key, is_admin, created) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id.lower(), email.lower(), hashed, api_key, int(is_admin), created),
        )
    conn.close()
    return api_key


def get_user_by_email(path: Path, email: str) -> dict | None:
    conn = _get_conn(path)
    row = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.lower(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(path: Path, user_id: str) -> dict | None:
    conn = _get_conn(path)
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id.lower(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_api_key(path: Path, api_key: str) -> dict | None:
    conn = _get_conn(path)
    row = conn.execute(
        "SELECT * FROM users WHERE api_key = ?", (api_key,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_token(path: Path, token: str, token_type: str) -> dict | None:
    """token_type: 'invite' of 'reset'"""
    col_token   = f"{token_type}_token"
    col_expires = f"{token_type}_expires"
    conn = _get_conn(path)
    row = conn.execute(
        f"SELECT * FROM users WHERE {col_token} = ?", (token,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    user = dict(row)
    expires = user.get(col_expires)
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        return None  # verlopen
    return user


def list_users(path: Path) -> list[dict]:
    conn = _get_conn(path)
    rows = conn.execute("SELECT * FROM users ORDER BY created").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_invite_token(path: Path, user_id: str) -> str:
    token   = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)).isoformat()
    conn = _get_conn(path)
    with conn:
        conn.execute(
            "UPDATE users SET invite_token = ?, invite_expires = ? WHERE id = ?",
            (token, expires, user_id.lower()),
        )
    conn.close()
    return token


def set_reset_token(path: Path, user_id: str) -> str:
    token   = secrets.token_urlsafe(32)
    expires = (datetime.now(timezone.utc) + timedelta(hours=RESET_TTL_HOURS)).isoformat()
    conn = _get_conn(path)
    with conn:
        conn.execute(
            "UPDATE users SET reset_token = ?, reset_expires = ? WHERE id = ?",
            (token, expires, user_id.lower()),
        )
    conn.close()
    return token


def set_password(path: Path, user_id: str, password: str):
    hashed = generate_password_hash(password)
    conn = _get_conn(path)
    with conn:
        conn.execute(
            "UPDATE users SET password = ?, invite_token = NULL, invite_expires = NULL, "
            "reset_token = NULL, reset_expires = NULL WHERE id = ?",
            (hashed, user_id.lower()),
        )
    conn.close()


def rotate_api_key(path: Path, user_id: str) -> str:
    new_key = "sk_" + secrets.token_hex(32)
    conn = _get_conn(path)
    with conn:
        conn.execute("UPDATE users SET api_key = ? WHERE id = ?", (new_key, user_id.lower()))
    conn.close()
    return new_key


def delete_user(path: Path, user_id: str):
    conn = _get_conn(path)
    with conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id.lower(),))
    conn.close()


def check_password(user: dict, password: str) -> bool:
    if not user.get("password"):
        return False  # nog geen wachtwoord ingesteld (uitnodiging niet geaccepteerd)
    return check_password_hash(user["password"], password)
