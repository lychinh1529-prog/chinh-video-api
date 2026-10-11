import os
import re
import glob
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI(title="Chinh TikTok Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chinh-video-downloader.pages.dev",
        "http://localhost:3000",
        "http://127.0.0.1:5500",
    ],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "chinh_video_downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

download_lock = threading.Lock()


def validate_tiktok_url(url: str):
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


def make_options(output_template, download=False):
    return {
        "format": "best[ext=mp4]/best",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "retries": 2,
        "socket_timeout": 30,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.tiktok.com/",
        },
    }


@app.get("/")
def root():
    return {"status": "API is running successfully!"}


@app.get("/api/download")
def get_video_info(url: str = Query(...)):
    validate_tiktok_url(url)

    try:
        with yt_dlp.YoutubeDL(make_options("%(id)s.%(ext)s")) as ydl:
            info = ydl.extract_info(url, download=False)

        video_url = info.get("url")

        if not video_url:
            raise HTTPException(
                status_code=502,
                detail="Không lấy được đường dẫn video."
            )

        return {
            "code": 0,
            "data": {
                "play": video_url,
                "hdplay": video_url,
                "cover": info.get("thumbnail", ""),
                "title": info.get("title", "TikTok video"),
                "author": {
                    "nickname": info.get("uploader", "Tác giả"),
                    "avatar": ""
                }
            }
        }

    except HTTPException:
        raise

    except Exception as e:
        return {
            "code": -1,
            "msg": f"Lỗi xử lý video: {str(e)[:500]}"
        }


@app.get("/api/download-file")
def download_video_file(url: str = Query(...)):
    validate_tiktok_url(url)

    # Tránh nhiều lượt tải đồng thời làm quá tải máy chủ miễn phí.
    if not download_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=503,
            detail="Máy chủ đang xử lý video khác. Hãy thử lại sau."
        )

    try:
        # Dọn các tệp tạm cũ còn sót lại.
        for old_file in DOWNLOAD_DIR.iterdir():
            try:
                if old_file.is_file():
                    old_file.unlink(missing_ok=True)
            except OSError:
                pass

        output_template = str(DOWNLOAD_DIR / "video.%(ext)s")
        options = make_options(output_template, download=True)
        options["format"] = "best[ext=mp4]/best"
        options["max_filesize"] = 100 * 1024 * 1024

        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        files = [
            p for p in DOWNLOAD_DIR.iterdir()
            if p.is_file() and p.name.startswith("video.")
            and not p.name.endswith(".part")
        ]

        if not files:
            raise HTTPException(
                status_code=502,
                detail="Máy chủ không tạo được tệp video."
            )

        file_path = files[0]

        def cleanup():
            try:
                file_path.unlink(missing_ok=True)
            finally:
                download_lock.release()

        return FileResponse(
            path=str(file_path),
            media_type="video/mp4",
            filename="chinh-tiktok-video.mp4",
            background=__import__(
                "starlette.background",
                fromlist=["BackgroundTask"]
            ).BackgroundTask(cleanup)
        )

    except HTTPException:
        download_lock.release()
        raise

    except Exception as e:
        download_lock.release()
        raise HTTPException(
            status_code=502,
            detail=f"Không tải được video: {str(e)[:500]}"
        )
