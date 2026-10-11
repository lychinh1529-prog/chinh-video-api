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

app = FastAPI(title="Chinh Video API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://chinh-video-downloader.pages.dev",
    ],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


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


def get_info(url: str):
    check_url(url)

    options = {
        "format": "best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30
