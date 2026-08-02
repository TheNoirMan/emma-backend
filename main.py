import os
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

class ChatRequest(BaseModel):
    message: str

SYSTEM_PROMPT = """
You are EMMA, a personal AI assistant.

Rules:
- Speak naturally.
- Reply in Tamil if the user speaks Tamil.
- Reply in English if the user speaks English.
- Be friendly, concise, and helpful.
"""

@app.get("/")
def home():
    return {"assistant": "EMMA", "status": "Online"}

@app.post("/chat")
def chat(request: ChatRequest):
    response = client.responses.create(
        model="gpt-5.5",
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": request.message,
            },
        ],
    )

    return {
        "reply": response.output_text
    }