import os
import re
import time
import json
import tempfile
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

AI_PIPE_TOKEN = os.getenv("AI_PIPE_TOKEN")
AI_PIPE_URL = "https://api.aipipe.ai/v1/chat/completions"  # OpenAI compatible endpoint


class AskRequest(BaseModel):
    video_url: str
    topic: str


class AskResponse(BaseModel):
    timestamp: str
    video_url: str
    topic: str


def download_audio(video_url: str) -> str:
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "audio.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    return os.path.join(temp_dir, "audio.mp3")


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):

    if not AI_PIPE_TOKEN:
        raise HTTPException(status_code=500, detail="AI_PIPE_TOKEN not set")

    audio_path = None

    try:
        # 1️⃣ Download audio
        audio_path = download_audio(request.video_url)

        # 2️⃣ Prepare prompt
        prompt = f"""
        Analyze the provided audio file.
        Find the FIRST timestamp where the topic "{request.topic}" is spoken.

        Return ONLY valid JSON in this format:
        {{
            "timestamp": "HH:MM:SS"
        }}

        The timestamp MUST be in HH:MM:SS format.
        """

        headers = {
            "Authorization": f"Bearer {AI_PIPE_TOKEN}",
        }

        files = {
            "file": open(audio_path, "rb"),
        }

        data = {
            "model": "gemini-1.5-pro",
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }

        response = requests.post(
            AI_PIPE_URL,
            headers=headers,
            data={"payload": json.dumps(data)},
            files=files,
        )

        if response.status_code != 200:
            raise Exception(response.text)

        result = response.json()

        content = result["choices"][0]["message"]["content"]

        parsed = json.loads(content)
        timestamp = parsed["timestamp"]

        if not re.match(r"^\d{2}:\d{2}:\d{2}$", timestamp):
            raise Exception("Invalid timestamp format")

        return AskResponse(
            timestamp=timestamp,
            video_url=request.video_url,
            topic=request.topic,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
