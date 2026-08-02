from fastapi import FastAPI
from pydantic import BaseModel
from groq import Groq
import os

app = FastAPI()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

class ChatRequest(BaseModel):
    message: str

SYSTEM_PROMPT = """
You are EMMA, a personal AI assistant.
Speak naturally.
Reply in Tamil if the user speaks Tamil.
Reply in English if the user speaks English.
"""

@app.get("/")
def home():
    return {"assistant": "EMMA", "status": "Online"}

@app.post("/chat")
def chat(request: ChatRequest):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": request.message}
        ]
    )

    return {
        "reply": response.choices[0].message.content
    }