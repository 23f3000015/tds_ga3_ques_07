import os
import re
import time
import json
import tempfile
import yt_dlp
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = FastAPI()

# CORS (safe for validator)
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


def download_audio(video_url: str) -> str:
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "audio.%(ext)s")

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio",
        "outtmpl": output_path,
        "quiet": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    # Find downloaded file
    for file in os.listdir(temp_dir):
        if file.endswith(".m4a") or file.endswith(".webm"):
            return os.path.join(temp_dir, file)

    raise Exception("Audio download failed")


def wait_until_active(file):
    while True:
        file = genai.get_file(file.name)
        if file.state.name == "ACTIVE":
            return file
        if file.state.name == "FAILED":
            raise Exception("File processing failed")
        time.sleep(2)


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    audio_path = None

    try:
        if not os.getenv("GEMINI_API_KEY"):
            raise Exception("GEMINI_API_KEY not set")

        # 1️⃣ Download audio only
        audio_path = download_audio(request.video_url)

        # 2️⃣ Upload to Gemini Files API
        uploaded_file = genai.upload_file(audio_path)

        # 3️⃣ Wait until file becomes ACTIVE
        uploaded_file = wait_until_active(uploaded_file)

        # 4️⃣ Use structured output schema
        model = genai.GenerativeModel(
            model_name="gemini-1.5-pro",
            generation_config={
                "response_mime_type": "application/json",
                "response_schema": {
                    "type": "object",
                    "properties": {
                        "timestamp": {
                            "type": "string",
                            "pattern": "^[0-9]{2}:[0-9]{2}:[0-9]{2}$"
                        }
                    },
                    "required": ["timestamp"]
                },
            },
        )

        prompt = f"""
        Analyze the uploaded audio file.
        Find the FIRST moment the following exact phrase appears:

        "{request.topic}"

        Return ONLY JSON:
        {{
          "timestamp": "HH:MM:SS"
        }}

        Ensure the timestamp is the exact first spoken occurrence.
        """

        response = model.generate_content([uploaded_file, prompt])

        parsed = json.loads(response.text)
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
