import os
import re
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import google.generativeai as genai

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

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


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    try:
        if not os.getenv("GEMINI_API_KEY"):
            raise Exception("GEMINI_API_KEY not set")

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
        Analyze the YouTube video at this URL:

        {request.video_url}

        Find the FIRST moment when the following exact phrase is spoken:

        "{request.topic}"

        Return ONLY JSON:
        {{
            "timestamp": "HH:MM:SS"
        }}

        The timestamp must be the first spoken occurrence.
        """

        response = model.generate_content(prompt)

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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
