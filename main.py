from datetime import datetime, timedelta, timezone
import os
import sqlite3
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="CHINH VIDEO API")

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "users.db")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lychinh1529-prog.github.io",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


def now_utc():
    return datetime.now(timezone.utc)


def to_iso(value):
    return value.astimezone(timezone.utc).isoformat()


def parse_datetime(value):
    dt = datetime.fromisoformat(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


@contextmanager
def db_connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=20)
    conn.row_factory = sqlite3.Row

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                is_pro INTEGER NOT NULL DEFAULT 0,
                trial_expires_at TEXT NOT NULL
            )
        """)


init_db()


class UserCreateModel(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=80,
        pattern=r"^[A-Za-z0-9_.-]+$"
    )


class UserUpdateModel(BaseModel):
    is_pro: Optional[bool] = None
    extend_days: int = Field(default=0, ge=0, le=3650)


def require_admin(x_admin_token: Optional[str]):
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Admin chưa được cấu hình ADMIN_TOKEN."
        )

    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Không có quyền quản trị."
        )


def get_user_row(username):
    with db_connection() as conn:
        return conn.execute(
            """
            SELECT username, created_at, is_pro, trial_expires_at
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()


def public_user(row):
    expires = parse_datetime(row["trial_expires_at"])

    return {
        "username": row["username"],
        "created_at": row["created_at"],
        "is_pro": bool(row["is_pro"]),
        "is_trial_active": now_utc() < expires,
        "trial_expires_at": row["trial_expires_at"]
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/register")
def register_user(data: UserCreateModel):
    username = data.username.strip()

    if not username:
        raise HTTPException(
            status_code=400,
            detail="Tên tài khoản không hợp lệ."
        )

    created = now_utc()
    expires = created + timedelta(days=14)

    try:
        with db_connection() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    username,
                    created_at,
                    is_pro,
                    trial_expires_at
                )
                VALUES (?, ?, 0, ?)
                """,
                (
                    username,
                    to_iso(created),
                    to_iso(expires)
                )
            )

    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Tài khoản đã tồn tại."
        )

    return {
        "status": "success",
        "username": username
    }


@app.get("/api/user/{username}")
def get_user_status(username: str):
    # Không tự tạo tài khoản khi tìm kiếm.
    row = get_user_row(username)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy tài khoản."
        )

    return public_user(row)


@app.post("/api/admin/update-user/{username}")
def admin_update_user(
    username: str,
    data: UserUpdateModel,
    x_admin_token: Optional[str] = Header(
        default=None,
        alias="X-Admin-Token"
    )
):
    require_admin(x_admin_token)

    row = get_user_row(username)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy tài khoản; không tạo mới."
        )

    with db_connection() as conn:
        current = conn.execute(
            """
            SELECT is_pro, trial_expires_at
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()

        if data.is_pro is None:
            new_is_pro = current["is_pro"]
        else:
            new_is_pro = int(data.is_pro)

        expiry = parse_datetime(
            current["trial_expires_at"]
        )

        if data.extend_days > 0:
            expiry = max(now_utc(), expiry) + timedelta(
                days=data.extend_days
            )

        conn.execute(
            """
            UPDATE users
            SET is_pro = ?,
                trial_expires_at = ?
            WHERE username = ?
            """,
            (
                new_is_pro,
                to_iso(expiry),
                username
            )
        )

    updated = get_user_row(username)

    return {
        "status": "success",
        "message": f"Đã cập nhật tài khoản {username}.",
        "user": public_user(updated)
    }
