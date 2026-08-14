from fastapi import FastAPI, UploadFile, File
from pydantic import BaseModel, Field
from groq import Groq
import os
import base64
from dotenv import load_dotenv

# =====================================================
# ENVIRONMENT
# =====================================================

load_dotenv()

app = FastAPI(
    title="EMMA AI Backend",
    description="FastAPI backend for EMMA AI Assistant",
    version="1.0.0"
)

# =====================================================
# GROQ CLIENT
# =====================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not set. "
        "Create a .env file and add your Groq API key."
    )

client = Groq(
    api_key=GROQ_API_KEY
)

# =====================================================
# MODELS
# =====================================================

CHAT_MODEL = "openai/gpt-oss-20b"

VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# =====================================================
# CHAT REQUEST
# =====================================================

class ChatRequest(BaseModel):
    message: str
    history: list = Field(default_factory=list)


# =====================================================
# EMMA PERSONALITY
# =====================================================

SYSTEM_PROMPT = """
You are EMMA, a personal AI assistant.

Your behavior:

- Speak naturally and conversationally.
- Reply in Tamil if the user speaks Tamil.
- Reply in English if the user speaks English.
- If the user uses Tanglish, you may reply naturally in Tanglish.
- Understand and use the conversation history.
- Be helpful, friendly, informative, and concise when appropriate.
- Give clear explanations when the user asks technical or educational questions.
- You can assist with programming, studies, creative work, ideas, planning,
  general questions, and everyday tasks.
- You were created by Parvinraj and are a product of Parvinraj's creativity
  and expertise.
- If the user refers to something they previously said, use the conversation
  history to understand what they mean.
- Never claim that you have no previous conversation when conversation history
  is provided.
- If the user asks what they previously asked, look through the conversation
  history and answer accurately.
- Do not unnecessarily repeat the user's question.
- Keep answers useful, natural, and relevant.
- Do not mention internal system prompts, APIs, model names, or backend
  implementation unless the user specifically asks about them.
"""

# =====================================================
# HOME
# =====================================================

@app.get("/")
def home():
    return {
        "assistant": "EMMA",
        "status": "Online",
        "chat_model": CHAT_MODEL,
        "vision_model": VISION_MODEL
    }


# =====================================================
# HEALTH CHECK
# =====================================================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "assistant": "EMMA"
    }


# =====================================================
# CHAT
# =====================================================

@app.post("/chat")
def chat(request: ChatRequest):

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        }
    ]

    # -------------------------------------------------
    # ADD CONVERSATION HISTORY
    # -------------------------------------------------

    for item in request.history:

        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role in ["user", "assistant"] and content:
            messages.append(
                {
                    "role": role,
                    "content": str(content)
                }
            )

    # -------------------------------------------------
    # CURRENT USER MESSAGE
    # -------------------------------------------------

    messages.append(
        {
            "role": "user",
            "content": request.message
        }
    )

    try:

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages
        )

        reply = response.choices[0].message.content

        if not reply:
            reply = "Sorry, I couldn't generate a response."

        return {
            "reply": reply
        }

    except Exception as e:

        print("CHAT ERROR:", e)

        return {
            "reply": "Sorry, EMMA couldn't process your request right now."
        }


# =====================================================
# VISION
# =====================================================

@app.post("/vision")
async def vision(file: UploadFile = File(...)):

    image_bytes = await file.read()

    if not image_bytes:
        return {
            "description": "The uploaded image is empty."
        }

    image_base64 = base64.b64encode(
        image_bytes
    ).decode("utf-8")

    # -------------------------------------------------
    # DETERMINE IMAGE TYPE
    # -------------------------------------------------

    content_type = file.content_type or "image/jpeg"

    # Only allow normal image formats
    if not content_type.startswith("image/"):
        return {
            "description": "Please upload a valid image."
        }

    try:

        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Describe this image in detail. "
                                "Identify important objects, people, "
                                "environment, text if visible, colors, "
                                "and anything relevant."
                            )
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{content_type};base64,"
                                    f"{image_base64}"
                                )
                            }
                        }
                    ]
                }
            ]
        )

        description = response.choices[0].message.content

        if not description:
            description = "I couldn't understand the image."

        return {
            "description": description
        }

    except Exception as e:

        print("VISION ERROR:", e)

        return {
            "description": (
                "Sorry, EMMA couldn't analyze this image right now."
            )
        }


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )