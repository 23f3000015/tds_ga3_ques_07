import os
import re
import string
import requests
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

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
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def seconds_to_hhmmss(seconds: float) -> str:
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02}:{m:02}:{s:02}"


def get_caption_entries(video_url: str):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

    subtitles = info.get("subtitles") or info.get("automatic_captions")
    if not subtitles:
        raise Exception("No subtitles available")

    if "en" in subtitles:
        subtitle_url = subtitles["en"][0]["url"]
    else:
        lang = list(subtitles.keys())[0]
        subtitle_url = subtitles[lang][0]["url"]

    response = requests.get(subtitle_url)
    if response.status_code != 200:
        raise Exception("Failed to fetch subtitles")

    vtt = response.text
    blocks = vtt.split("\n\n")

    entries = []

    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 2:
            continue

        timestamp_line = lines[0]
        caption_text = " ".join(lines[1:])

        start = timestamp_line.split(" --> ")[0]
        start = start.split(".")[0]

        if re.match(r"^\d{2}:\d{2}:\d{2}$", start):
            entries.append({
                "time": start,
                "text": normalize(caption_text)
            })

    return entries


def find_phrase(entries, topic):
    normalized_topic = normalize(topic)

    # Combine sliding window across captions
    combined_text = ""
    time_map = []

    for entry in entries:
        combined_text += " " + entry["text"]
        time_map.append(entry["time"])

    combined_text = combined_text.strip()

    index = combined_text.find(normalized_topic)
    if index == -1:
        raise Exception("Topic not found")

    # Estimate which caption index this corresponds to
    word_position = len(combined_text[:index].split())

    word_count = 0
    for i, entry in enumerate(entries):
        word_count += len(entry["text"].split())
        if word_count >= word_position:
            return entry["time"]

    raise Exception("Timestamp not resolved")


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    try:
        entries = get_caption_entries(request.video_url)
        timestamp = find_phrase(entries, request.topic)

        return AskResponse(
            timestamp=timestamp,
            video_url=request.video_url,
            topic=request.topic
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
