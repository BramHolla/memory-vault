"""
Memory Vault — multi-user Snapchat memories gallery
Usage: gunicorn app:app  (production) or  python app.py  (dev)
"""

import tempfile
import threading
import time
from pathlib import Path

import boto3
from flask import (Flask, abort, jsonify, redirect, render_template,
                   request, send_from_directory, url_for)
from flask_login import (LoginManager, UserMixin, current_user,
                         login_required, login_user, logout_user)

import config
import db
import mailer
import users_db

app = Flask(__name__)
app.secret_key = config.FLASK_SECRET_KEY

login_manager = LoginManager(app)
login_manager.login_view = "login"


# ---------------------------------------------------------------------------
# Flask-Login user class
# ---------------------------------------------------------------------------

class User(UserMixin):
    def __init__(self, data: dict):
        self.id       = data["id"]
        self.email    = data["email"]
        self.is_admin = bool(data["is_admin"])

    def get_id(self):
        return self.id


@login_manager.user_loader
def load_user(user_id: str):
    path = _get_users_db_path()
    if path is None:
        return None
    data = users_db.get_user_by_id(path, user_id)
    return User(data) if data else None


# ---------------------------------------------------------------------------
# users.db cache (downloaded from R2, refreshed every 5 min)
# ---------------------------------------------------------------------------

_users_db_path: Path | None = None
_users_db_lock  = threading.Lock()
_users_db_last_refresh = 0.0
USERS_DB_REFRESH = 300  # seconds


def _get_users_db_path() -> Path | None:
    global _users_db_path, _users_db_last_refresh
    if not config.CLOUD_MODE:
        return None
    now = time.time()
    with _users_db_lock:
        if now - _users_db_last_refresh > USERS_DB_REFRESH:
            try:
                new_path = users_db.download_users_db(silent=True)
                old = _users_db_path
                _users_db_path = new_path
                _users_db_last_refresh = now
                if old and old.exists():
                    try:
                        old.unlink()
                    except Exception:
                        pass
            except Exception as e:
                app.logger.warning(f"users.db refresh failed: {e}")
    return _users_db_path


def _invalidate_users_db_cache():
    """Force re-download on next request (after a write operation)."""
    global _users_db_last_refresh
    with _users_db_lock:
        _users_db_last_refresh = 0.0


# ---------------------------------------------------------------------------
# Per-user memories.db cache
# ---------------------------------------------------------------------------

_user_db_cache: dict[str, tuple[Path, float]] = {}  # user_id -> (path, timestamp)
_user_db_lock  = threading.Lock()


def get_user_db(user_id: str) -> Path | None:
    if not config.CLOUD_MODE:
        return None
    now = time.time()
    with _user_db_lock:
        cached_path, cached_ts = _user_db_cache.get(user_id, (None, 0.0))
        if now - cached_ts > 300:
            try:
                s3 = boto3.client(
                    "s3",
                    endpoint_url=config.R2_ENDPOINT,
                    aws_access_key_id=config.R2_ACCESS_KEY,
                    aws_secret_access_key=config.R2_SECRET_KEY,
                    region_name="auto",
                )
                tmp = Path(tempfile.mktemp(suffix=f"_{user_id}.db"))
                s3.download_file(
                    config.R2_BUCKET_NAME,
                    f"users/{user_id}/memories.db",
                    str(tmp),
                )
                old = cached_path
                _user_db_cache[user_id] = (tmp, now)
                if old and old.exists():
                    try:
                        old.unlink()
                    except Exception:
                        pass
                return tmp
            except Exception as e:
                app.logger.warning(f"memories.db download failed for {user_id}: {e}")
                return cached_path  # fall back to stale cache
        return cached_path


def _set_db_for_user(user_id: str):
    path = get_user_db(user_id)
    if path:
        db.set_db_path(path)


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        path = _get_users_db_path()
        user_data = users_db.get_user_by_email(path, email) if path else None
        if user_data and users_db.check_password(user_data, password):
            login_user(User(user_data), remember=True)
            return redirect(url_for("index"))
        error = "Unknown email address or incorrect password."
    return render_template("login.html", error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def index():
    _set_db_for_user(current_user.id)
    media_base = f"{config.R2_PUBLIC_URL}/users/{current_user.id}/media" if config.CLOUD_MODE else "/media"
    return render_template("index.html", media_base=media_base)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route("/api/memories")
@login_required
def api_memories():
    _set_db_for_user(current_user.id)
    filters = {
        "date_from":      request.args.get("date_from"),
        "date_to":        request.args.get("date_to"),
        "month_day_from": request.args.get("month_day_from"),
        "month_day_to":   request.args.get("month_day_to"),
        "month":          request.args.get("month"),
        "year":           request.args.get("year", type=int),
        "media_type":     request.args.get("media_type"),
        "lat":            request.args.get("lat",        type=float),
        "lon":            request.args.get("lon",        type=float),
        "radius_km":      request.args.get("radius_km",  5.0, type=float),
        "page":           request.args.get("page",       1,   type=int),
        "per_page":       request.args.get("per_page",   50,  type=int),
    }
    return jsonify(db.query_memories(filters, current_user.id))


@app.route("/api/map-points")
@login_required
def api_map_points():
    _set_db_for_user(current_user.id)
    return jsonify(db.get_map_points(current_user.id))


@app.route("/api/date-bounds")
@login_required
def api_date_bounds():
    _set_db_for_user(current_user.id)
    return jsonify(db.get_date_bounds(current_user.id))


@app.route("/api/stats")
@login_required
def api_stats():
    _set_db_for_user(current_user.id)
    return jsonify(db.get_stats(current_user.id))


# ---------------------------------------------------------------------------
# Media serving (local mode)
# ---------------------------------------------------------------------------

@app.route("/media/<path:filename>")
@login_required
def serve_media(filename):
    return send_from_directory(config.MEDIA_DIR, filename)


# ---------------------------------------------------------------------------
# Invite & password reset
# ---------------------------------------------------------------------------

@app.route("/invite/<token>", methods=["GET", "POST"])
def accept_invite(token: str):
    path = _get_users_db_path()
    user = users_db.get_user_by_token(path, token, "invite") if path else None
    if not user:
        return render_template("set_password.html", error="This link is invalid or has expired.", token=None, mode="invite")

    if request.method == "POST":
        pw  = request.form.get("password", "")
        pw2 = request.form.get("password2", "")
        if len(pw) < 8:
            return render_template("set_password.html", error="Password must be at least 8 characters.", token=token, mode="invite")
        if pw != pw2:
            return render_template("set_password.html", error="Passwords do not match.", token=token, mode="invite")
        users_db.set_password(path, user["id"], pw)
        users_db.upload_users_db(path)
        _invalidate_users_db_cache()
        # Reload user and log in
        fresh_path = _get_users_db_path()
        fresh_user = users_db.get_user_by_id(fresh_path, user["id"])
        login_user(User(fresh_user), remember=True)
        return redirect(url_for("index"))

    return render_template("set_password.html", error=None, token=token, mode="invite", user_id=user["id"])


@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token: str):
    path = _get_users_db_path()
    user = users_db.get_user_by_token(path, token, "reset") if path else None
    if not user:
        return render_template("set_password.html", error="This link is invalid or has expired.", token=None, mode="reset")

    if request.method == "POST":
        pw  = request.form.get("password", "")
        pw2 = request.form.get("password2", "")
        if len(pw) < 8:
            return render_template("set_password.html", error="Password must be at least 8 characters.", token=token, mode="reset")
        if pw != pw2:
            return render_template("set_password.html", error="Passwords do not match.", token=token, mode="reset")
        users_db.set_password(path, user["id"], pw)
        users_db.upload_users_db(path)
        _invalidate_users_db_cache()
        return redirect(url_for("login"))

    return render_template("set_password.html", error=None, token=token, mode="reset", user_id=user["id"])


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@app.route("/admin")
@login_required
@admin_required
def admin():
    path = _get_users_db_path()
    users = users_db.list_users(path) if path else []

    # Fetch memory count and last sync time per user
    s3 = boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT,
        aws_access_key_id=config.R2_ACCESS_KEY,
        aws_secret_access_key=config.R2_SECRET_KEY,
        region_name="auto",
    ) if config.CLOUD_MODE else None

    for u in users:
        u["memory_count"] = 0
        u["last_sync"]    = None
        if s3:
            try:
                resp = s3.head_object(
                    Bucket=config.R2_BUCKET_NAME,
                    Key=f"users/{u['id']}/memories.db",
                )
                u["last_sync"] = resp["LastModified"].strftime("%Y-%m-%d %H:%M UTC")
                # Count memories via cached db
                cached = _user_db_cache.get(u["id"])
                if cached and cached[0] and cached[0].exists():
                    u["memory_count"] = db.count_memories_for_user(cached[0], u["id"])
            except Exception:
                pass

    return render_template("admin.html", users=users)


@app.route("/admin/users", methods=["POST"])
@login_required
@admin_required
def admin_create_user():
    user_id  = request.form.get("user_id", "").strip().lower()
    email    = request.form.get("email", "").strip()
    is_admin = bool(request.form.get("is_admin"))

    if not user_id or not email:
        abort(400)

    path = _get_users_db_path()
    try:
        users_db.create_user(path, user_id, email, password=None, is_admin=is_admin)
        token = users_db.set_invite_token(path, user_id)
        users_db.upload_users_db(path)
        _invalidate_users_db_cache()
        try:
            mailer.send_invite(email, user_id, token)
        except Exception as e:
            app.logger.warning(f"Invite email failed: {e}")
    except Exception as e:
        app.logger.error(f"Failed to create user: {e}")
        abort(500)

    return redirect(url_for("admin"))


@app.route("/admin/users/<user_id>/rotate-key", methods=["POST"])
@login_required
@admin_required
def admin_rotate_key(user_id: str):
    path = _get_users_db_path()
    users_db.rotate_api_key(path, user_id)
    users_db.upload_users_db(path)
    _invalidate_users_db_cache()
    return redirect(url_for("admin"))


@app.route("/admin/users/<user_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def admin_reset_password(user_id: str):
    path = _get_users_db_path()
    user = users_db.get_user_by_id(path, user_id)
    if not user:
        abort(404)
    token = users_db.set_reset_token(path, user_id)
    users_db.upload_users_db(path)
    _invalidate_users_db_cache()
    try:
        mailer.send_password_reset(user["email"], user["id"], token)
    except Exception as e:
        app.logger.warning(f"Password reset email failed: {e}")
    return redirect(url_for("admin"))


@app.route("/admin/users/<user_id>/delete", methods=["POST"])
@login_required
@admin_required
def admin_delete_user(user_id: str):
    if user_id == current_user.id:
        abort(400)  # cannot delete yourself

    path = _get_users_db_path()
    users_db.delete_user(path, user_id)
    users_db.upload_users_db(path)
    _invalidate_users_db_cache()

    # Delete the user's R2 data
    if config.CLOUD_MODE:
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=config.R2_ENDPOINT,
                aws_access_key_id=config.R2_ACCESS_KEY,
                aws_secret_access_key=config.R2_SECRET_KEY,
                region_name="auto",
            )
            paginator = s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME, Prefix=f"users/{user_id}/"):
                for obj in page.get("Contents", []):
                    s3.delete_object(Bucket=config.R2_BUCKET_NAME, Key=obj["Key"])
        except Exception as e:
            app.logger.warning(f"Failed to delete R2 data for {user_id}: {e}")

    return redirect(url_for("admin"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if config.CLOUD_MODE:
        print("Cloud mode: downloading users.db...")
        try:
            p = users_db.download_users_db(silent=True)
            _users_db_path = p
            _users_db_last_refresh = time.time()
            print("users.db loaded.")
        except Exception as e:
            print(f"Warning: users.db not loaded: {e}")
    else:
        db.init_db()

    print("Memory Vault running at http://localhost:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
