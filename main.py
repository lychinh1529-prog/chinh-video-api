import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel


app = FastAPI(title="Chinh Video API")


# ==============================
# CẤU HÌNH CORS
# ==============================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chinh-video-downloader.pages.dev",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ==============================
# KIỂM TRA ĐƯỜNG DẪN
# ==============================

def check_url(url: str):
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()

        if parsed.scheme not in ("http", "https"):
            raise ValueError()

        if not (
            host == "tiktok.com"
            or host.endswith(".tiktok.com")
        ):
            raise ValueError()

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Liên kết TikTok không hợp lệ."
        )


# ==============================
# MODEL NHẬN DỮ LIỆU
# ==============================

class DownloadRequest(BaseModel):
    url: str


# ==============================
# LẤY THÔNG TIN VIDEO
# ==============================

def get_info(url: str):
    check_url(url)

    options = {
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise HTTPException(
                status_code=502,
                detail="Không lấy được thông tin video."
            )

        return {
            "title": info.get("title") or "Video",
            "description": info.get("description") or "",
            "uploader": info.get("uploader") or "",
            "thumbnail": info.get("thumbnail") or "",
            "duration": info.get("duration"),
            "webpage_url": info.get("webpage_url") or url,
        }

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Không thể lấy thông tin video: {str(exc)[:300]}"
        )


# ==============================
# TẢI VIDEO VÀO TỆP TẠM
# ==============================

def save_video(url: str, folder: str):
    check_url(url)

    output_template = str(
        Path(folder) / "video.%(ext)s"
    )

    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 45,
        "retries": 2,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        files = list(Path(folder).glob("video.*"))

        if not files:
            raise HTTPException(
                status_code=502,
                detail="Máy chủ không tải được tệp video."
            )

        return str(files[0])

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Lỗi tải video: {str(exc)[:300]}"
        )


# ==============================
# API KIỂM TRA MÁY CHỦ
# ==============================

@app.get("/")
def home():
    return {
        "status": "ok",
        "message": "Chinh Video API is running."
    }





# ==============================
# API LẤY THÔNG TIN VIDEO
# ==============================

@app.post("/api/download")
def download_info(request: DownloadRequest):
    url = request.url.strip()

    info = get_info(url)

    return {
        "code": 0,
        "message": "success",
        "data": info
    } 
    @app.get("/health")
def health():
    return {
        "status": "ok",
        "yt_dlp_version": yt_dlp.version.__version__
    }


# ==============================
# API XEM VIDEO
# ==============================

@app.get("/api/video")
def get_video(url: str = Query(..., min_length=1)):
    url = url.strip()

    with tempfile.TemporaryDirectory() as folder:
        video_path = save_video(url, folder)

        # Đọc nội dung vào bộ nhớ trước khi thư mục tạm bị xóa.
        with open(video_path, "rb") as video_file:
            video_data = video_file.read()

    from fastapi.responses import Response

    return Response(
        content=video_data,
        media_type="video/mp4",
        headers={
            "Content-Disposition": 'inline; filename="video.mp4"',
            "Cache-Control": "no-store",
        }
    )


# ==============================
# API TẢI VIDEO XUỐNG
# ==============================

@app.get("/api/download-file")
def download_file(url: str = Query(..., min_length=1)):
    url = url.strip()

    check_url(url)

    folder = tempfile.mkdtemp(prefix="chinh_video_")

    try:
        video_path = save_video(url, folder)

        return FileResponse(
            path=video_path,
            media_type="application/octet-stream",
            filename="video.mp4",
            background=BackgroundTask(
                shutil.rmtree,
                folder,
                ignore_errors=True
            )
        )

    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
