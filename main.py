import os
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi

app = FastAPI()

# Enable CORS (safe for validator)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


def extract_video_id(url: str) -> str:
    if "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    if "watch?v=" in url:
        return url.split("watch?v=")[1].split("&")[0]
    raise Exception("Invalid YouTube URL")


def seconds_to_hhmmss(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    try:
        video_id = extract_video_id(request.video_url)

        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)

        for entry in transcript:
            if request.topic.lower() in entry.text.lower():
                timestamp = seconds_to_hhmmss(entry.start)

                return AskResponse(
                    timestamp=timestamp,
                    video_url=request.video_url,
                    topic=request.topic,
                )

        raise Exception("Topic not found in transcript")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Railway dynamic port binding
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
