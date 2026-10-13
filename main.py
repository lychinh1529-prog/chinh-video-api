from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Cho phép trang web quản lý và app gọi API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Giả lập Database lưu tài khoản
users_db = {
    "chinhly_212": {
        "username": "chinhly_212",
        "created_at": datetime.now().isoformat(),
        "is_pro": False,
        "trial_expires_at": (datetime.now() + timedelta(days=14)).isoformat(),
    }
}


class UserUpdateModel(BaseModel):
  is_pro: bool
  extend_days: int = 0


@app.get("/api/user/{username}")
def get_user_status(username: str):
  if username not in users_db:
    # Tự động cấp 14 ngày dùng thử khi user mới xuất hiện
    users_db[username] = {
        "username": username,
        "created_at": datetime.now().isoformat(),
        "is_pro": False,
        "trial_expires_at": (datetime.now() + timedelta(days=14)).isoformat(),
    }
  user = users_db[username]
  trial_expire = datetime.fromisoformat(user["trial_expires_at"])
  is_trial_active = datetime.now() < trial_expire
  return {
      "username": user["username"],
      "is_pro": user["is_pro"],
      "is_trial_active": is_trial_active,
      "trial_expires_at": user["trial_expires_at"],
  }


@app.post("/api/admin/update-user/{username}")
def admin_update_user(username: str, data: UserUpdateModel):
  if username not in users_db:
    users_db[username] = {
        "username": username,
        "created_at": datetime.now().isoformat(),
        "is_pro": data.is_pro,
        "trial_expires_at": (datetime.now() + timedelta(days=14)).isoformat(),
    }

  users_db[username]["is_pro"] = data.is_pro
  if data.extend_days > 0:
    current_expire = max(
        datetime.now(), datetime.fromisoformat(users_db[username]["trial_expires_at"])
    )
    new_expire = current_expire + timedelta(days=data.extend_days)
    users_db[username]["trial_expires_at"] = new_expire.isoformat()

  return {"status": "success", "message": f"Đã cập nhật thành công cho {username}"}
    
