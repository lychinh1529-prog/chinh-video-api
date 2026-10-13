import os
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="CHINH VIDEO API")

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
FIREBASE_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lychinh1529-prog.github.io",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)


def connect_firebase():
    if firebase_admin._apps:
        return firestore.client()

    if not FIREBASE_JSON:
        raise RuntimeError("Thiếu FIREBASE_SERVICE_ACCOUNT_JSON")

    info = json.loads(FIREBASE_JSON)
    credential = credentials.Certificate(info)
    firebase_admin.initialize_app(credential)

    return firestore.client()


try:
    db = connect_firebase()
except Exception:
    db = None


def get_db():
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="Firebase chưa kết nối. Kiểm tra cấu hình Render."
        )
    return db


def check_admin(token):
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Chưa cấu hình ADMIN_TOKEN trên Render."
        )

    if not token or not hmac.compare_digest(token, ADMIN_TOKEN):
        raise HTTPException(
            status_code=401,
            detail="Không có quyền quản trị."
        )


def now_utc():
    return datetime.now(timezone.utc)


def parse_date(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            return None

    return None


def find_user(username_or_id):
    database = get_db()
    key = username_or_id.strip()

    if not key:
        raise HTTPException(
            status_code=400,
            detail="Vui lòng nhập username hoặc ID."
        )

    # Tìm theo ID document, vốn là username.
    doc = database.collection("app_users").document(key).get()

    if doc.exists:
        data = doc.to_dict() or {}
        data["_documentId"] = doc.id
        return data

    # Nếu không tìm thấy username thì tìm uniqueId.
    results = (
        database.collection("app_users")
        .where("uniqueId", "==", key)
        .limit(1)
        .stream()
    )

    for item in results:
        data = item.to_dict() or {}
        data["_documentId"] = item.id
        return data

    return None


def safe_user(data):
    # Không trả mật khẩu ra ngoài API.
    result = {
        key: value
        for key, value in data.items()
        if key.lower() not in {
            "password",
            "passwordhash",
            "password_hash"
        }
    }

    result.pop("_documentId", None)

    for key, value in list(result.items()):
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        elif not isinstance(
            value,
            (str, int, float, bool, list, dict, type(None))
        ):
            result[key] = str(value)

    return result


class UserUpdateModel(BaseModel):
    is_pro: Optional[bool] = None
    status: Optional[str] = None
    extend_days: int = Field(default=0, ge=0, le=3650)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "firebase_connected": db is not None,
        "firebase_error": FIREBASE_ERROR
    }


@app.get("/api/user/{username_or_id}")
def get_user_status(username_or_id: str):
    user = find_user(username_or_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy tài khoản."
        )

    return safe_user(user)


@app.get("/api/admin/users")
def list_users(
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    x_admin_token: Optional[str] = Header(
        default=None,
        alias="X-Admin-Token"
    )
):
    check_admin(x_admin_token)
    database = get_db()

    documents = (
        database.collection("app_users")
        .limit(limit)
        .stream()
    )

    users = []

    for document in documents:
        data = document.to_dict() or {}
        data["_documentId"] = document.id

        if q:
            keyword = q.strip().lower()

            username = str(
                data.get("username", document.id)
            ).lower()

            unique_id = str(
                data.get("uniqueId", "")
            ).lower()

            if keyword not in username and keyword not in unique_id:
                continue

        users.append(safe_user(data))

    return {
        "count": len(users),
        "users": users
    }


@app.post("/api/admin/update-user/{username_or_id}")
def admin_update_user(
    username_or_id: str,
    data: UserUpdateModel,
    x_admin_token: Optional[str] = Header(
        default=None,
        alias="X-Admin-Token"
    )
):
    check_admin(x_admin_token)
    database = get_db()

    user = find_user(username_or_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy tài khoản; không tạo mới."
        )

    document_id = user.get("_documentId")

    if not document_id:
        raise HTTPException(
            status_code=500,
            detail="Không xác định được tài khoản."
        )

    updates = {}

    if data.status is not None:
        if data.status not in {
            "trial",
            "active",
            "disabled"
        }:
            raise HTTPException(
                status_code=400,
                detail="status phải là trial, active hoặc disabled."
            )

        updates["status"] = data.status

    if data.is_pro is not None:
        updates["is_pro"] = data.is_pro

        if data.is_pro:
            updates["status"] = "active"

    if data.extend_days > 0:
        expiry_field = None

        for field in [
            "expiresAt",
            "expires_at",
            "trialExpiresAt",
            "trial_expires_at",
            "proExpiresAt",
            "pro_expires_at"
        ]:
            if field in user:
                expiry_field = field
                break

        if expiry_field is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Không tìm thấy trường ngày hết hạn. "
                    "Cần xác định trường mà website đang sử dụng."
                )
            )

        current_expiry = parse_date(user.get(expiry_field))

        base = (
            max(now_utc(), current_expiry)
            if current_expiry
            else now_utc()
        )

        updates[expiry_field] = (
            base + timedelta(days=data.extend_days)
        )

    if not updates:
        raise HTTPException(
            status_code=400,
            detail="Chưa có thông tin cần cập nhật."
        )

    (
        database.collection("app_users")
        .document(document_id)
        .update(updates)
    )

    updated = find_user(document_id)

    return {
        "status": "success",
        "message": f"Đã cập nhật {document_id}.",
        "user": safe_user(updated or {})
    }
