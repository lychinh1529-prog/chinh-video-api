from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp

app = FastAPI(title="Chinh Video Private API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/download")
def get_video_info(url: str):
    if not url:
        return {"code": -1, "msg": "Thiếu liên kết video"}
    
    try:
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_url = info.get('url')
            title = info.get('title', 'Video không tiêu đề')
            uploader = info.get('uploader', 'Tác giả')
            thumbnail = info.get('thumbnail', '')
            
            if not video_url:
                return {"code": -1, "msg": "Không thể trích xuất đường dẫn video"}

            return {
                "code": 0,
                "data": {
                    "play": video_url,
                    "hdplay": video_url,
                    "music": video_url,
                    "cover": thumbnail,
                    "title": title,
                    "author": {
                        "nickname": uploader,
                        "avatar": ""
                    }
                }
            }
    except Exception as e:
        return {"code": -1, "msg": f"Lỗi xử lý: {str(e)}"}

@app.get("/")
def root():
    return {"status": "API is running successfully!"}
  
