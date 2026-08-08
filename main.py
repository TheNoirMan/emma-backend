from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel
from groq import Groq
import os
import base64

app = FastAPI()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


class ChatRequest(BaseModel):
    message: str
    history: list = []


SYSTEM_PROMPT = """
You are EMMA, a personal AI assistant.

You have access to the current conversation history.
Use it to understand what the user previously asked or told you.

Do not say that you have never talked to the user if the information
is present in the conversation history.

Reply naturally and conversationally.

Reply in Tamil if the user speaks Tamil.
Reply in English if the user speaks English.

Remember information from the conversation while it is provided
in the history.
"""


@app.get("/")
def home():
    return {
        "assistant": "EMMA",
        "status": "Online"
    }


@app.post("/chat")
def chat(request: ChatRequest):

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    # Add previous conversation
    for item in request.history:

        role = item.get("role")
        content = item.get("content")

        if role in ["user", "assistant"] and content:
            messages.append({
                "role": role,
                "content": content
            })

    # Add current message
    messages.append({
        "role": "user",
        "content": request.message
    })

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.7,
    )

    return {
        "reply": response.choices[0].message.content
    }


@app.post("/vision")
async def vision(file: UploadFile = File(...)):

    image_bytes = await file.read()

    image_base64 = base64.b64encode(
        image_bytes
    ).decode()

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Describe this image in detail."
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]
    )

    return {
        "description": response.choices[0].message.content
    }
