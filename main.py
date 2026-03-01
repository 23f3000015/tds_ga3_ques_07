import os
import re
import json
import tempfile
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

AI_PIPE_TOKEN = os.getenv("AI_PIPE_TOKEN")
AI_PIPE_URL = "https://aipipe.org/geminiv1beta/models/gemini-1.5-flash:generateContent"


class AskRequest(BaseModel):
    video_url: str
    topic: str


class AskResponse(BaseModel):
    timestamp: str
    video_url: str
    topic: str


def download_transcript(video_url: str) -> str:
    temp_dir = tempfile.mkdtemp()

    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en"],
        "outtmpl": os.path.join(temp_dir, "%(id)s"),
        "quiet": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        ydl.download([video_url])
        video_id = info["id"]

    # find subtitle file
    for file in os.listdir(temp_dir):
        if file.endswith(".vtt"):
            with open(os.path.join(temp_dir, file), "r", encoding="utf-8") as f:
                return f.read()

    raise Exception("Transcript not available")


def extract_first_timestamp_from_vtt(vtt_text, topic):
    blocks = vtt_text.split("\n\n")

    for block in blocks:
        if topic.lower() in block.lower():
            lines = block.split("\n")
            if len(lines) >= 2:
                timestamp_line = lines[0]
                start_time = timestamp_line.split(" --> ")[0]
                hhmmss = start_time.split(".")[0]
                return hhmmss

    return None


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):

    if not AI_PIPE_TOKEN:
        raise HTTPException(status_code=500, detail="AI_PIPE_TOKEN not set")

    try:
        # 1️⃣ Get transcript
        transcript = download_transcript(request.video_url)

        # 2️⃣ Try direct match first (fast)
        direct_timestamp = extract_first_timestamp_from_vtt(transcript, request.topic)
        if direct_timestamp:
            return AskResponse(
                timestamp=direct_timestamp,
                video_url=request.video_url,
                topic=request.topic,
            )

        # 3️⃣ If not found, ask Gemini
        prompt = f"""
        Below is a YouTube transcript.

        Find the FIRST timestamp where the topic "{request.topic}" is mentioned.

        Return ONLY JSON:
        {{
            "timestamp": "HH:MM:SS"
        }}

        Transcript:
        {transcript[:12000]}
        """

        headers = {
            "Authorization": f"Bearer {AI_PIPE_TOKEN}",
            "Content-Type": "application/json",
        }

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ]
        }

        response = requests.post(
            AI_PIPE_URL,
            headers=headers,
            json=payload
        )

        if response.status_code != 200:
            raise Exception(response.text)

        result = response.json()
        content = result["candidates"][0]["content"]["parts"][0]["text"]

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
