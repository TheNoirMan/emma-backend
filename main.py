from fastapi import FastAPI
from pydantic import BaseModel
import ollama

app = FastAPI()

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
    response = ollama.chat(
        model="qwen3:8b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": request.message},
        ],
    )

    return {
        "reply": response["message"]["content"]
    }