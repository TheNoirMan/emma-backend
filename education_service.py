from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import time


# ============================================================
# EMMA EDUCATION SERVICE
# SIH26042
# ============================================================

router = APIRouter(
    prefix="/education",
    tags=["EMMA Education - SIH26042"],
)


# ============================================================
# STORAGE
# ============================================================

BASE_DIR = Path.cwd()
OFFLINE_DIR = BASE_DIR / "offline_lessons"

OFFLINE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# SUPPORTED LANGUAGES
# ============================================================

SUPPORTED_LANGUAGES = {

    "hindi": {
        "name": "Hindi",
        "code": "hi-IN",
        "script": "Devanagari",
    },

    "santhali": {
        "name": "Santhali",
        "code": "sat-IN",
        "script": "Ol Chiki",
        "sih_primary": True,
    },

    "tamil": {
        "name": "Tamil",
        "code": "ta-IN",
        "script": "Tamil",
    },

    "telugu": {
        "name": "Telugu",
        "code": "te-IN",
        "script": "Telugu",
    },

    "bengali": {
        "name": "Bengali",
        "code": "bn-IN",
        "script": "Bengali",
    },

    "kannada": {
        "name": "Kannada",
        "code": "kn-IN",
        "script": "Kannada",
    },

    "malayalam": {
        "name": "Malayalam",
        "code": "ml-IN",
        "script": "Malayalam",
    },

    "marathi": {
        "name": "Marathi",
        "code": "mr-IN",
        "script": "Devanagari",
    },

    "gujarati": {
        "name": "Gujarati",
        "code": "gu-IN",
        "script": "Gujarati",
    },

    "odia": {
        "name": "Odia",
        "code": "or-IN",
        "script": "Odia",
    },

    "punjabi": {
        "name": "Punjabi",
        "code": "pa-IN",
        "script": "Gurmukhi",
    },

    "assamese": {
        "name": "Assamese",
        "code": "as-IN",
        "script": "Bengali-Assamese",
    },

    "english": {
        "name": "English",
        "code": "en-IN",
        "script": "Latin",
    },
}


# ============================================================
# REQUEST MODELS
# ============================================================

class TranslationRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source_language: str = "hindi"
    target_language: str = "santhali"


class LessonRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    class_level: str = "Class 1"
    source_language: str = "hindi"
    target_language: str = "santhali"


class WorksheetRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    class_level: str = "Class 1"
    source_language: str = "hindi"
    target_language: str = "santhali"
    question_count: int = Field(
        default=5,
        ge=1,
        le=20,
    )


class FlashcardRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    class_level: str = "Class 1"
    source_language: str = "hindi"
    target_language: str = "santhali"
    card_count: int = Field(
        default=5,
        ge=1,
        le=20,
    )


# ============================================================
# PROTOTYPE TRANSLATION DATA
# ============================================================

TRANSLATION_DICTIONARY = {

    # ========================================================
    # GREETINGS
    # ========================================================

    "hello": "ᱡᱚᱦᱟᱨ",
    "namaste": "ᱡᱚᱦᱟᱨ",

    # ========================================================
    # NUMBERS
    # ========================================================

    "one": "ᱮᱠᱚ",
    "two": "ᱵᱟᱨ",
    "three": "ᱯᱮ",
    "four": "ᱯᱳᱱ",
    "five": "ᱢᱚᱬᱮ",
    "six": "ᱛᱩᱨᱩᱭ",
    "seven": "ᱮᱭᱟᱭ",
    "eight": "ᱤᱨᱟᱹᱞ",
    "nine": "ᱟᱨᱮ",
    "ten": "ᱜᱮᱞ",

    # ========================================================
    # BASIC PEOPLE / PRONOUNS
    # ========================================================

    "i": "ᱤᱧ",
    "you": "ᱟᱢ",
    "he": "ᱟᱡ",
    "she": "ᱟᱡ",
    "we": "ᱟᱵᱚ",
    "child": "ᱦᱚᱱ",
    "children": "ᱦᱚᱱ ᱠᱚ",

    # ========================================================
    # BASIC PLACES / OBJECTS
    # ========================================================

    "house": "ᱚᱲᱟᱜ",
    "home": "ᱚᱲᱟᱜ",
    "school": "ᱤᱥᱠᱩᱞ",
    "book": "ᱯᱩᱛᱷᱤ",
    "name": "ᱧᱩᱛᱩᱢ",
    "water": "ᱫᱟᱜ",
    "land": "ᱚᱛ",
    "earth": "ᱚᱛ",
    "bamboo": "ᱢᱟᱴ",
    "hair": "ᱩᱯ",
    "mouth": "ᱢᱚᱪᱟ",
    "head": "ᱵᱚᱦᱚᱠ",
    "tooth": "ᱫᱟᱴᱟ",
    "ear": "ᱞᱩᱛᱩᱨ",
    "eye": "ᱢᱮᱫ",
    "hand": "ᱛᱤ",
    "foot": "ᱡᱟᱝᱜᱟ",

    # ========================================================
    # ANIMALS
    # ========================================================

    "dog": "ᱥᱮᱛᱟ",
    "tiger": "ᱠᱩᱞ",
    "bear": "ᱵᱟᱱᱟ",
    "ox": "ᱫᱷᱟᱱᱜᱽᱨᱟ",

    # ========================================================
    # CLASSROOM ACTIONS
    # ========================================================

    "write": "ᱚᱞ",
    "see": "ᱧᱮᱞ",
    "go": "ᱪᱟᱞᱟᱜ",
    "listen": "ᱟᱧᱡᱚᱢ",
    "speak": "ᱨᱚᱲ",
    "read": "ᱯᱟᱲᱦᱟᱣ",
    "learn": "ᱥᱤᱠᱷᱟᱣ",
    "teach": "ᱥᱤᱠᱷᱟᱣ",
    "come": "ᱦᱤᱡᱩ",
    "sit": "ᱫᱚᱦᱚ",
    "stand": "ᱛᱤᱝ",
    "look": "ᱧᱮᱞ",
    "answer": "ᱡᱚᱵᱟᱵ",

    # ========================================================
    # BASIC CLASSROOM WORDS
    # ========================================================

    "teacher": "ᱪᱮᱫᱟᱠ",
    "student": "ᱪᱮᱫᱟᱠ ᱠᱚ",
    "lesson": "ᱯᱟᱲᱦᱟᱣ",
    "question": "ᱡᱚᱵᱟᱵ",
    "answer": "ᱡᱚᱵᱟᱵ",
    "book": "ᱯᱩᱛᱷᱤ",

    # ========================================================
    # YES / NO / HELP
    # ========================================================

    "yes": "ᱦᱚᱸ",
    "no": "ᱵᱟᱝ",
    "help": "ᱥᱟᱦᱟᱭ",
    "please": "ᱫᱚᱭᱟ ᱠᱟᱛᱮ",
    "thank you": "ᱵᱤᱨ ᱵᱟᱨᱟᱭ",

    # ========================================================
    # COMMON CLASSROOM PHRASES
    # ========================================================

    "come here": "ᱱᱚᱸᱰᱮ ᱦᱤᱡᱩ ᱢᱮ",
    "sit down": "ᱫᱚᱦᱚ ᱢᱮ",
    "listen carefully": "ᱥᱟᱹᱜᱟᱹᱭ ᱟᱧᱡᱚᱢ ᱢᱮ",
    "look here": "ᱱᱚᱸᱰᱮ ᱧᱮᱞ ᱢᱮ",
    "read this": "ᱱᱚᱶᱟ ᱯᱟᱲᱦᱟᱣ ᱢᱮ",
    "write this": "ᱱᱚᱶᱟ ᱚᱞ ᱢᱮ",
    "come to school": "ᱤᱥᱠᱩᱞ ᱛᱮ ᱦᱤᱡᱩ ᱢᱮ",

    # ========================================================
    # BASIC QUESTION PHRASES
    # ========================================================

    "what is your name": "ᱟᱢ ᱨᱮᱱ ᱧᱩᱛᱩᱢ ᱪᱮᱫ?",
    "how are you": "ᱪᱮᱫ ᱞᱮᱠᱟ ᱢᱮᱱᱟᱢᱟ?",
    "how much": "ᱚᱱᱛᱮ?",
    "i do not understand": "ᱟᱤᱧ ᱵᱩᱡᱷᱤ ᱵᱟᱝ",
    "please help me": "ᱟᱤᱧ ᱥᱟᱦᱟᱭ ᱢᱮ",

    # ========================================================
    # BASIC COLOURS
    # ========================================================

    "red": "ᱞᱟᱞ",
    "green": "ᱦᱟᱨᱤᱭᱟᱹ",
    "blue": "ᱱᱤᱞ",
    "yellow": "ᱦᱮᱸᱫᱮ",
    "black": "ᱦᱮᱸᱫᱮ",

    # ========================================================
    # BASIC FOOD / DAILY LIFE
    # ========================================================

    "rice": "ᱡᱚᱢ",
    "food": "ᱡᱚᱢ",
    "drink": "ᱧᱩ",
    "eat": "ᱡᱚᱢ",
    "water": "ᱫᱟᱜ",

    # ========================================================
    # NATURE
    # ========================================================

    "sun": "ᱥᱤᱝᱜᱤ",
    "moon": "ᱪᱟᱹᱸᱫᱚ",
    "star": "ᱤᱯᱤᱞ",
    "tree": "ᱫᱟᱨᱮ",
    "forest": "ᱵᱤᱨ",
    "rain": "ᱡᱚᱞ",

    # ========================================================
    # TIME / DAILY ROUTINE
    # ========================================================

    "today": "ᱛᱤᱦᱤᱧ",
    "tomorrow": "ᱜᱟᱯᱟ",
    "day": "ᱢᱟᱦᱟ",
    "morning": "ᱥᱟᱛ",
    "night": "ᱧᱤᱫ",

    # ========================================================
    # USEFUL ADJECTIVES
    # ========================================================

    "good": "ᱵᱮᱥ",
    "bad": "ᱵᱟᱹᱝ",
    "big": "ᱢᱟᱨᱟᱝ",
    "small": "ᱦᱩᱰᱤᱧ",
    "new": "ᱱᱟᱣᱟ",
    "old": "ᱢᱟᱨᱟᱝ",

}
REVERSE_TRANSLATION_DICTIONARY = {
    value: key
    for key, value in TRANSLATION_DICTIONARY.items()
}


# ============================================================
# OFFLINE CURRICULUM
# ============================================================

OFFLINE_LESSONS = {
    "numbers": {
        "topic": "Numbers 1-10",
        "class_level": "Class 1",
        "learning_outcome": "Foundational Numeracy",
        "hindi": {
            "title": "संख्या 1 से 10",
            "lesson": (
                "आज हम 1 से 10 तक की संख्याएँ सीखेंगे। "
                "बच्चे प्रत्येक संख्या को पहचानेंगे और गिनेंगे।"
            ),
        },
        "santhali": {
            "title": "᱑ ᱟᱨ ᱥᱮ ᱑᱐",
            "lesson": (
                "EMMA prototype multilingual numeracy lesson."
            ),
        },
    },
    "letters": {
        "topic": "Basic Letters",
        "class_level": "Class 1",
        "learning_outcome": "Foundational Literacy",
        "hindi": {
            "title": "मूल अक्षर",
            "lesson": (
                "आज हम कुछ मूल अक्षरों को "
                "पहचानना और बोलना सीखेंगे।"
            ),
        },
        "santhali": {
            "title": "ᱪᱤᱠᱤ ᱚᱞ",
            "lesson": (
                "EMMA prototype multilingual literacy lesson."
            ),
        },
    },
    "colors": {
        "topic": "Basic Colors",
        "class_level": "Class 1",
        "learning_outcome": "Foundational Learning",
        "hindi": {
            "title": "मूल रंग",
            "lesson": (
                "आज हम लाल, नीला, हरा और पीला "
                "रंग पहचानना सीखेंगे।"
            ),
        },
        "santhali": {
            "title": "ᱨᱚᱝ",
            "lesson": (
                "EMMA prototype multilingual colour lesson."
            ),
        },
    },
}


# ============================================================
# LANGUAGE VALIDATION
# ============================================================

def validate_language(language: str) -> str:
    language = language.strip().lower()

    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {language}",
        )

    return language


# ============================================================
# TRANSLATION ENGINE
# ============================================================

def translate_text(
    text: str,
    source_language: str,
    target_language: str,
) -> Dict[str, Any]:

    source_language = validate_language(
        source_language
    )

    target_language = validate_language(
        target_language
    )

    text = text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Text cannot be empty.",
        )

    if source_language == target_language:
        return {
            "success": True,
            "input": text,
            "translation": text,
            "source_language": source_language,
            "target_language": target_language,
            "offline": True,
            "prototype": False,
            "method": "identity",
        }

    # Hindi -> Santhali
    if (
        source_language == "hindi"
        and target_language == "santhali"
    ):
        translated = TRANSLATION_DICTIONARY.get(
            text.lower()
        )

        if translated:
            return {
                "success": True,
                "input": text,
                "translation": translated,
                "source_language": source_language,
                "target_language": target_language,
                "offline": True,
                "prototype": True,
                "method": "prototype_dictionary",
            }

        return {
            "success": True,
            "input": text,
            "translation": (
                "[Prototype] Translation not available "
                "for this phrase yet."
            ),
            "source_language": source_language,
            "target_language": target_language,
            "offline": True,
            "prototype": True,
            "method": "prototype_fallback",
        }

    # Santhali -> Hindi
    if (
        source_language == "santhali"
        and target_language == "hindi"
    ):
        translated = REVERSE_TRANSLATION_DICTIONARY.get(
            text
        )

        if translated:
            return {
                "success": True,
                "input": text,
                "translation": translated,
                "source_language": source_language,
                "target_language": target_language,
                "offline": True,
                "prototype": True,
                "method": "prototype_dictionary",
            }

        return {
            "success": True,
            "input": text,
            "translation": (
                "[Prototype] Translation not available "
                "for this phrase yet."
            ),
            "source_language": source_language,
            "target_language": target_language,
            "offline": True,
            "prototype": True,
            "method": "prototype_fallback",
        }

    raise HTTPException(
        status_code=400,
        detail="Language pair is not available.",
    )


# ============================================================
# LANGUAGES
# ============================================================

@router.get("/languages")
def get_languages():

    return {
        "success": True,
        "module": "EMMA Education",
        "problem_statement": "SIH26042",
        "primary_sih_language": "Santhali",
        "languages": SUPPORTED_LANGUAGES,
        "language_count": len(SUPPORTED_LANGUAGES),
    }


# ============================================================
# TRANSLATION API
# ============================================================

@router.post("/translate")
def education_translate(
    request: TranslationRequest,
):
    return translate_text(
        text=request.text,
        source_language=request.source_language,
        target_language=request.target_language,
    )


# ============================================================
# LESSON API
# ============================================================

@router.post("/lesson")
def generate_lesson(
    request: LessonRequest,
):

    topic_key = (
        request.topic
        .strip()
        .lower()
        .replace(" ", "_")
    )

    lesson = OFFLINE_LESSONS.get(topic_key)

    if lesson:
        source_language = validate_language(
            request.source_language
        )

        target_language = validate_language(
            request.target_language
        )

        source_content = lesson.get(
            source_language,
            {},
        )

        target_content = lesson.get(
            target_language,
            {},
        )

        return {
            "success": True,
            "mode": "offline_curriculum",
            "topic": lesson["topic"],
            "class_level": lesson["class_level"],
            "learning_outcome": lesson[
                "learning_outcome"
            ],
            "source_language": source_language,
            "target_language": target_language,
            "source_content": source_content,
            "target_content": target_content,
            "offline_ready": True,
        }

    return {
        "success": True,
        "mode": "education_prototype",
        "topic": request.topic,
        "class_level": request.class_level,
        "learning_outcome": "Foundational Learning",
        "source_language": request.source_language,
        "target_language": request.target_language,
        "source_content": {
            "title": request.topic,
            "lesson": (
                f"Prototype lesson for {request.topic}."
            ),
        },
        "target_content": {
            "title": request.topic,
            "lesson": (
                "Target-language curriculum content "
                "will be provided by the synchronized "
                "EMMA language pack."
            ),
        },
        "offline_ready": True,
    }


# ============================================================
# WORKSHEET API
# ============================================================

@router.post("/worksheet")
def generate_worksheet(
    request: WorksheetRequest,
):

    questions = []

    for number in range(
        1,
        request.question_count + 1,
    ):
        questions.append(
            {
                "number": number,
                "hindi": (
                    f"{number}. {request.topic} "
                    "से संबंधित प्रश्न का उत्तर दें।"
                ),
                "santhali": (
                    f"{number}. {request.topic} "
                    " - target-language learning question"
                ),
            }
        )

    return {
        "success": True,
        "type": "bilingual_worksheet",
        "topic": request.topic,
        "class_level": request.class_level,
        "source_language": request.source_language,
        "target_language": request.target_language,
        "question_count": request.question_count,
        "questions": questions,
        "offline_ready": True,
        "generated_at": time.time(),
    }


# ============================================================
# FLASHCARD API
# ============================================================

@router.post("/flashcards")
def generate_flashcards(
    request: FlashcardRequest,
):

    cards = []

    for number in range(
        1,
        request.card_count + 1,
    ):
        cards.append(
            {
                "id": number,
                "topic": request.topic,
                "class_level": request.class_level,
                "front": (
                    f"{request.topic} #{number}"
                ),
                "hindi": (
                    f"{request.topic} सीखें"
                ),
                "santhali": (
                    f"Santhali learning card {number}"
                ),
            }
        )

    return {
        "success": True,
        "type": "visual_flashcards",
        "topic": request.topic,
        "class_level": request.class_level,
        "source_language": request.source_language,
        "target_language": request.target_language,
        "cards": cards,
        "offline_ready": True,
    }


# ============================================================
# OFFLINE LESSONS
# ============================================================

@router.get("/offline-lessons")
def get_offline_lessons():

    lessons = []

    for lesson_id, lesson in OFFLINE_LESSONS.items():
        lessons.append(
            {
                "id": lesson_id,
                "topic": lesson["topic"],
                "class_level": lesson["class_level"],
                "learning_outcome": lesson[
                    "learning_outcome"
                ],
            }
        )

    return {
        "success": True,
        "offline": True,
        "lesson_count": len(lessons),
        "lessons": lessons,
    }


# ============================================================
# EDUCATION STATUS
# ============================================================

@router.get("/status")
def education_status():

    return {
        "success": True,
        "module": "EMMA Education",
        "problem_statement": "SIH26042",
        "prototype_language": "Santhali",
        "translation": True,
        "voice_translation": True,
        "offline_curriculum": True,
        "bilingual_worksheets": True,
        "visual_flashcards": True,
        "curriculum_sync": True,
        "status": "prototype_ready",
    }


# ============================================================
# SYNC MANIFEST
# ============================================================

@router.get("/sync-manifest")
def sync_manifest():

    return {
        "success": True,
        "application": "EMMA",
        "module": "Education",
        "problem_statement": "SIH26042",
        "version": "1.0.0",
        "language_packs": [
            {
                "language": "Hindi",
                "code": "hi-IN",
                "status": "available",
            },
            {
                "language": "Santhali",
                "code": "sat-IN",
                "status": "prototype",
            },
        ],
        "offline_content": {
            "lessons": len(OFFLINE_LESSONS),
            "translation_entries": len(
                TRANSLATION_DICTIONARY
            ),
        },
        "sync_required": False,
        "generated_at": time.time(),
    }


# ============================================================
# HEALTH
# ============================================================

@router.get("/health")
def education_health():

    return {
        "success": True,
        "service": "education",
        "status": "online",
        "problem_statement": "SIH26042",
    }