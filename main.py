import os
import re
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AI_PIPE_TOKEN = os.getenv("AI_PIPE_TOKEN")
AI_PIPE_URL = "https://aipipe.org/openrouter/v1/chat/completions"


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


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    try:
        if not AI_PIPE_TOKEN:
            raise Exception("AI_PIPE_TOKEN not set")

        prompt = f"""
        In the YouTube video {request.video_url},
        at what timestamp (HH:MM:SS) is the topic
        "{request.topic}" first discussed?

        Return ONLY the timestamp in HH:MM:SS format.
        """

        headers = {
            "Authorization": f"Bearer {AI_PIPE_TOKEN}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": "openai/gpt-4.1-nano",
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        response = requests.post(AI_PIPE_URL, headers=headers, json=payload)

        if response.status_code != 200:
            raise Exception(response.text)

        content = response.json()["choices"][0]["message"]["content"].strip()

        # Extract HH:MM:SS safely
        match = re.search(r"\d{2}:\d{2}:\d{2}", content)
        if not match:
            raise Exception("Invalid timestamp format")

        timestamp = match.group(0)

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
