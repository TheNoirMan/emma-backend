from fastapi import FastAPI, UploadFile, File, HTTPException
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
    version="1.1.0",
)

# =====================================================
# GROQ CLIENT
# =====================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set.")

client = Groq(api_key=GROQ_API_KEY)

# =====================================================
# MODELS
# =====================================================

CHAT_MODEL = "openai/gpt-oss-20b"
VISION_MODEL = "qwen/qwen3.6-27b"

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
- Understand and use conversation history.
- Be helpful, friendly, informative, and concise when appropriate.
- Give clear explanations for technical and educational questions.
- Assist with programming, studies, creative work, ideas, planning,
  general questions, and everyday tasks.
- You were created by Parvinraj,Kishore shakthi,Lokesh KV,Madhan and Murugan a group of engineering students.
- you will come under MR LEGACY, a company that specializes in AI solutions. 
- If the user refers to something previously said, use conversation history.
- Never claim you have no previous conversation when history is provided.
- Do not unnecessarily repeat the user's question.
- Keep answers useful, natural, and relevant.
- Do not reveal internal prompts, APIs, or backend implementation
  unless specifically asked.
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
        "vision_model": VISION_MODEL,
    }


# =====================================================
# HEALTH
# =====================================================

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "assistant": "EMMA",
    }


# =====================================================
# CHAT
# =====================================================

@app.post("/chat")
def chat(request: ChatRequest):

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    for item in request.history:

        if not isinstance(item, dict):
            continue

        role = item.get("role")
        content = item.get("content")

        if role in ["user", "assistant"] and content:
            messages.append(
                {
                    "role": role,
                    "content": str(content),
                }
            )

    messages.append(
        {
            "role": "user",
            "content": request.message,
        }
    )

    try:

        response = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
        )

        reply = response.choices[0].message.content

        if not reply:
            reply = "Sorry, I couldn't generate a response."

        return {
            "reply": reply,
        }

    except Exception as e:

        print("=" * 60)
        print("CHAT ERROR")
        print(repr(e))
        print("=" * 60)

        return {
            "reply": "Sorry, EMMA couldn't process your request right now."
        }


# =====================================================
# VISION
# =====================================================

@app.post("/vision")
async def vision(file: UploadFile = File(...)):

    print("=" * 60)
    print("VISION REQUEST RECEIVED")
    print("=" * 60)

    # -------------------------------------------------
    # FILE INFORMATION
    # -------------------------------------------------

    print("Filename:", file.filename)
    print("Content-Type:", file.content_type)

    # -------------------------------------------------
    # READ FILE
    # -------------------------------------------------

    try:
        image_bytes = await file.read()
    except Exception as e:

        print("FILE READ ERROR:", repr(e))

        return {
            "description": "EMMA could not read the uploaded image."
        }

    print("Image size:", len(image_bytes), "bytes")

    # -------------------------------------------------
    # EMPTY FILE
    # -------------------------------------------------

    if not image_bytes:

        return {
            "description": "The uploaded image is empty."
        }

    # -------------------------------------------------
    # CHECK IMAGE SIGNATURE
    # -------------------------------------------------

    detected_type = None

    # JPEG
    if image_bytes.startswith(b"\xff\xd8\xff"):
        detected_type = "image/jpeg"

    # PNG
    elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        detected_type = "image/png"

    # GIF
    elif image_bytes.startswith((b"GIF87a", b"GIF89a")):
        detected_type = "image/gif"

    # WEBP
    elif (
        len(image_bytes) >= 12
        and image_bytes[0:4] == b"RIFF"
        and image_bytes[8:12] == b"WEBP"
    ):
        detected_type = "image/webp"

    print("Detected image type:", detected_type)

    # -------------------------------------------------
    # DETERMINE MIME TYPE
    # -------------------------------------------------

    content_type = detected_type or file.content_type

    # If Android sends a generic MIME type but the file
    # itself is a valid image, use the detected type.

    if not content_type:
        content_type = "image/jpeg"

    if not content_type.startswith("image/"):

        print("INVALID CONTENT TYPE:", content_type)

        return {
            "description": (
                "Please upload a valid image. "
                f"Received file type: {content_type}"
            )
        }

    # -------------------------------------------------
    # BASE64
    # -------------------------------------------------

    try:

        image_base64 = base64.b64encode(
            image_bytes
        ).decode("utf-8")

    except Exception as e:

        print("BASE64 ERROR:", repr(e))

        return {
            "description": "EMMA could not process this image."
        }

    # -------------------------------------------------
    # GROQ VISION REQUEST
    # -------------------------------------------------

    try:

        print("Sending image to Groq...")
        print("Vision model:", VISION_MODEL)
        print("MIME type:", content_type)

        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
    "You are EMMA Vision, an intelligent visual assistant. "
    "Analyze this image carefully and describe what you see. "
    "Identify important objects, people, animals, environment, "
    "actions, visible text, colors, signs, and other relevant details. "
    "If there is text, read it accurately. "
    "Do not invent details that cannot be seen. "
    "Give a clear, natural answer that a user can understand."
)
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{content_type};base64,"
                                    f"{image_base64}"
                                )
                            },
                        },
                    ],
                }
            ],
        )

        # -------------------------------------------------
        # RESPONSE
        # -------------------------------------------------

        description = response.choices[0].message.content

        print("VISION RESPONSE:")
        print(description)

        if not description:

            return {
                "description": "I couldn't understand the image."
            }

        print("=" * 60)

        return {
            "description": description
        }

    except Exception as e:

        print("=" * 60)
        print("VISION GROQ ERROR")
        print(repr(e))
        print("=" * 60)

        # IMPORTANT:
        # Return the actual backend error while we're debugging.

        return {
            "description": (
                "VISION_ERROR: "
                f"{str(e)}"
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
        port=8000,
    )