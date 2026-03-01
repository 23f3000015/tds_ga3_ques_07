import os
import re
import tempfile
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yt_dlp

app = FastAPI()


class AskRequest(BaseModel):
    video_url: str
    topic: str


class AskResponse(BaseModel):
    timestamp: str
    video_url: str
    topic: str


@app.get("/")
def health():
    return {"status": "alive"}


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

    # Find .vtt subtitle file
    for file in os.listdir(temp_dir):
        if file.endswith(".vtt"):
            with open(os.path.join(temp_dir, file), "r", encoding="utf-8") as f:
                return f.read()

    raise Exception("Transcript not available")


def extract_timestamp(vtt_text: str, topic: str) -> str:
    blocks = vtt_text.split("\n\n")

    for block in blocks:
        if topic.lower() in block.lower():
            lines = block.split("\n")
            if len(lines) >= 2:
                timestamp_line = lines[0]
                start_time = timestamp_line.split(" --> ")[0]
                hhmmss = start_time.split(".")[0]

                # Ensure HH:MM:SS format
                if re.match(r"^\d{2}:\d{2}:\d{2}$", hhmmss):
                    return hhmmss

    raise Exception("Topic not found in transcript")


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    try:
        transcript = download_transcript(request.video_url)
        timestamp = extract_timestamp(transcript, request.topic)

        return AskResponse(
            timestamp=timestamp,
            video_url=request.video_url,
            topic=request.topic,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
