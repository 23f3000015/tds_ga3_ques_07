import os
import re
import string
import requests
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Enable CORS (safe)
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


def normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("\n", " ")
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_captions(video_url: str) -> str:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    subtitles = info.get("subtitles") or info.get("automatic_captions")
    if not subtitles:
        raise Exception("No subtitles available")

    # Prefer English
    if "en" in subtitles:
        subtitle_url = subtitles["en"][0]["url"]
    else:
        lang = list(subtitles.keys())[0]
        subtitle_url = subtitles[lang][0]["url"]

    response = requests.get(subtitle_url)
    if response.status_code != 200:
        raise Exception("Failed to fetch subtitles")

    return response.text


def parse_vtt(vtt_text: str, topic: str) -> str:
    blocks = vtt_text.split("\n\n")
    normalized_topic = normalize(topic)

    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 2:
            continue

        timestamp_line = lines[0]
        caption_text = " ".join(lines[1:])

        normalized_caption = normalize(caption_text)

        if normalized_topic in normalized_caption:
            start = timestamp_line.split(" --> ")[0]
            start = start.split(".")[0]

            if re.match(r"^\d{2}:\d{2}:\d{2}$", start):
                return start

    raise Exception("Topic not found")


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    try:
        captions = get_captions(request.video_url)
        timestamp = parse_vtt(captions, request.topic)

        return AskResponse(
            timestamp=timestamp,
            video_url=request.video_url,
            topic=request.topic
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Railway dynamic port
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
