import os
import json
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


app = FastAPI(title="Chinh Video API")

SAVEAPI_KEY = os.getenv("SAVEAPI_KEY", "").strip()
SAVEAPI_URL = "https://api.saveapi.org/v1/download"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chinh-video-downloader.pages.dev",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class DownloadRequest(BaseModel):
    url: str


def check_url(url: str):
    try:
        parsed = urlparse(url.strip())
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


def get_info(url: str):
    check_url(url)

    if not SAVEAPI_KEY:
        raise HTTPException(
            status_code=500,
            detail="Máy chủ chưa cấu hình SAVEAPI_KEY."
        )

    params = urlencode({"url": url})
    request = Request(
        f"{SAVEAPI_URL}?{params}",
        headers={
            "Authorization": f"Bearer {SAVEAPI_KEY}",
            "Accept": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))

    except HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"SaveAPI trả về lỗi HTTP {exc.code}."
        )

    except (URLError, TimeoutError):
        raise HTTPException(
            status_code=504,
            detail="Không thể kết nối SaveAPI."
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Không đọc được phản hồi từ SaveAPI."
        )

    if not result.get("success"):
        error = result.get("error") or {}
        message = error.get("message") or "Không lấy được video."
        raise HTTPException(status_code=502, detail=message)

    medias = result.get("medias") or []
    video = next(
        (item for item in medias if item.get("type") == "video"),
        None
    )

    if not video or not video.get("url"):
        raise HTTPException(
            status_code=502,
            detail="API không trả về liên kết video."
        )

    meta = result.get("meta") or {}

    return {
        "title": meta.get("title") or meta.get("text") or "TikTok Video",
        "description": meta.get("text") or meta.get("description") or "",
        "uploader": meta.get("author") or meta.get("username") or "",
        "thumbnail": meta.get("thumbnail") or meta.get("cover") or "",
        "duration": meta.get("duration"),
        "webpage_url": result.get("source_url") or url,
        "video_url": video["url"],
    }


@app.get("/")
def home():
    return {
        "status": "ok",
        "message": "Chinh Video API is running."
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "saveapi_configured": bool(SAVEAPI_KEY)
    }


@app.post("/api/download")
def download_info(request: DownloadRequest):
    info = get_info(request.url.strip())

    return {
        "code": 0,
        "message": "success",
        "data": info
    }


def stream_video(video_url: str):
    request = Request(
        video_url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    try:
        with urlopen(request, timeout=60) as response:
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    except Exception:
        return


def video_response(url: str, filename: str):
    info = get_info(url)

    return StreamingResponse(
        stream_video(info["video_url"]),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        }
    )


@app.get("/api/video")
def get_video(url: str = Query(..., min_length=1)):
    info = get_info(url.strip())

    return StreamingResponse(
        stream_video(info["video_url"]),
        media_type="video/mp4",
        headers={
            "Content-Disposition": 'inline; filename="video.mp4"',
            "Cache-Control": "no-store",
        }
    )


@app.get("/api/download-file")
def download_file(url: str = Query(..., min_length=1)):
    return video_response(url.strip(), "video.mp4")
