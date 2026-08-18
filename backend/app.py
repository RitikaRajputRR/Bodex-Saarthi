from flask import Flask, request, Response, jsonify, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
from pypdf import PdfReader
from bs4 import BeautifulSoup
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timezone

import os
import requests
import json
import time
import base64
import io
import re

from urllib.parse import urlparse


# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

CORS(
    app,
    expose_headers=["X-Chat-Id"]
)


# =========================================================
# UPLOAD SETTINGS
# =========================================================

app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024


# =========================================================
# GROQ CONFIG
# =========================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


# =========================================================
# MONGODB
# =========================================================

MONGO_URI = os.getenv("MONGO_URI")

MONGO_DB = os.getenv(
    "MONGO_DB",
    "bodex_saarthi"
)

mongo_client = None
mongo_db = None

chat_collection = None
knowledge_collection = None
urls_collection = None


try:

    if not MONGO_URI:

        print("WARNING: MONGO_URI is missing.")

    else:

        mongo_client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=10000
        )

        mongo_db = mongo_client[MONGO_DB]

        chat_collection = mongo_db["chats"]
        knowledge_collection = mongo_db["knowledge"]
        urls_collection = mongo_db["urls"]

        mongo_client.admin.command("ping")

        print("MongoDB Atlas connected successfully.")
        print("MongoDB database:", MONGO_DB)
        print("MongoDB collections: chats, knowledge, urls")


except Exception as e:

    print("MongoDB Atlas connection error:", e)


# =========================================================
# MODELS
# =========================================================

TEXT_MODEL = "openai/gpt-oss-20b"

VISION_MODEL = "qwen/qwen3.6-27b"


# =========================================================
# SESSION
# =========================================================

session = requests.Session()


# =========================================================
# LIMITS
# =========================================================

MAX_PDF_TEXT_CHARS = 60000

MAX_PDF_CONTEXT_CHARS = 20000

PDF_CHUNK_SIZE = 3000

MAX_URL_CONTEXT_CHARS = 12000

FINAL_RESPONSE_TOKENS = 1200

MAX_KNOWLEDGE_CONTEXT_CHARS = 12000


# =========================================================
# EXACT OUT OF SCOPE MESSAGE
# =========================================================

OUT_OF_SCOPE_MESSAGE = (
    "I'm Saarthi, BODEX's knowledge assistant. "
    "I can only answer questions related to BODEX, its services, "
    "products, technologies, culture, careers, and related company information."
)


# =========================================================
# SYSTEM PROMPT
# =========================================================

SYSTEM_PROMPT = f"""
You are Saarthi, BODEX's knowledge assistant.

Your ONLY job is to answer questions and analyze content related
to BODEX.

IMPORTANT SCOPE RULE:

You may answer ONLY if the user's question, uploaded image,
uploaded PDF, uploaded document, or webpage is related to BODEX.

BODEX-related content includes:

- BODEX company information
- BODEX products
- BODEX services
- BODEX technologies
- BODEX AI solutions
- BODEX data management
- BODEX analytics
- BODEX custom software
- BODEX SaaS
- BODEX Custom LLM
- BODEX consulting
- BODEX careers
- BODEX jobs
- BODEX employees
- BODEX work culture
- BODEX benefits
- BODEX security
- BODEX privacy
- BODEX governance
- BODEX methodology
- BODEX process automation
- BODEX real-time analytics
- BODEX legacy modernization
- BODEX products such as RecordEX, SIS, BSA, KPI-Dash,
  UtahData and other products explicitly present in the
  supplied BODEX knowledge or uploaded BODEX document.

=========================================================
NON-BODEX CONTENT
=========================================================

If the user asks something unrelated to BODEX,
DO NOT answer the question.

Respond EXACTLY with:

{OUT_OF_SCOPE_MESSAGE}

The same rule applies to uploaded images and PDFs.

For example:

- Random photo -> do NOT describe it.
- Random person photo -> do NOT identify the person.
- Random temple photo -> do NOT analyze the temple.
- Random general PDF -> do NOT summarize it.
- Random educational PDF -> do NOT answer it.
- Random resume -> do NOT analyze it unless it is explicitly
  related to BODEX.
- General programming question -> do NOT answer it.
- General geography question -> do NOT answer it.

=========================================================
BODEX PDF RULE
=========================================================

If the uploaded PDF contains BODEX information, you MAY answer
questions about that PDF.

The uploaded BODEX PDF is an allowed source of information.

Use the uploaded PDF content as the source for the answer.

Do NOT refuse a BODEX PDF merely because the information is not
present in the MongoDB BODEX Knowledge Base.

=========================================================
BODEX IMAGE RULE
=========================================================

If the uploaded image is clearly related to BODEX, you MAY analyze it.

Examples:

- BODEX product screenshot
- BODEX dashboard screenshot
- BODEX website screenshot
- BODEX document screenshot
- BODEX presentation slide
- BODEX logo
- BODEX UI
- BODEX architecture diagram
- BODEX product image

If the image is not BODEX-related, respond with the exact
out-of-scope message.

Do not describe a random image.

=========================================================
SOURCE OF TRUTH
=========================================================

For BODEX company facts:

1. BODEX Knowledge Base is authoritative.
2. An uploaded BODEX PDF/document is an authoritative source
   for information contained inside that document.
3. A BODEX-related image can be analyzed for information visible
   in the image.
4. A BODEX-related webpage can be used for information contained
   on that webpage.

NEVER invent information.

NEVER add unsupported technical details.

NEVER assume a technology, certification, client, security feature,
framework, cloud platform or capability unless it is explicitly
visible in the supplied source.

If a BODEX question asks for a detail that is not available in the
provided BODEX source, say:

"The available BODEX information does not specify this detail."

=========================================================
IDENTITY
=========================================================

Your name is Saarthi.

If asked your name, respond:

"My name is Saarthi. How can I help you?"

Never say your name is ChatGPT.

=========================================================
RESPONSE STYLE
=========================================================

- Answer only the exact BODEX-related question.
- Be concise.
- Use Markdown when useful.
- Do not add unrelated information.
- Do not repeat the question.
- Do not invent information.
- Do not answer non-BODEX questions.
- Do not analyze non-BODEX images.
- Do not summarize non-BODEX PDFs.

=========================================================
FINAL SCOPE CHECK
=========================================================

Before answering ANY request, silently determine:

Is this related to BODEX?

If NO:
return exactly:

{OUT_OF_SCOPE_MESSAGE}

If YES:
answer using only the supplied BODEX sources.
"""


# =========================================================
# LOAD BODEX KNOWLEDGE FROM MONGODB
# =========================================================

def load_bodex_knowledge_from_mongodb():

    if knowledge_collection is None:

        print("Knowledge collection is not available.")

        return ""

    try:

        document = knowledge_collection.find_one(
            {
                "type": "bodex_knowledge"
            },
            sort=[
                ("_id", -1)
            ]
        )

        if not document:

            print("No BODEX knowledge found in MongoDB.")

            return ""

        knowledge_text = document.get(
            "content",
            ""
        )

        if not knowledge_text:

            print("BODEX knowledge document is empty.")

            return ""

        print(
            "BODEX knowledge loaded from MongoDB:",
            len(knowledge_text),
            "characters"
        )

        return knowledge_text

    except Exception as e:

        print(
            "MongoDB knowledge loading error:",
            e
        )

        return ""


# =========================================================
# BODEX KNOWLEDGE
# =========================================================

BODEX_KNOWLEDGE = load_bodex_knowledge_from_mongodb()


# =========================================================
# LOCAL KNOWLEDGE FALLBACK
# =========================================================

if not BODEX_KNOWLEDGE:

    KNOWLEDGE_FILE = os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)
        ),
        "bodex_knowledge.txt"
    )

    try:

        with open(
            KNOWLEDGE_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            BODEX_KNOWLEDGE = f.read()

        print(
            "BODEX knowledge loaded from local file:",
            len(BODEX_KNOWLEDGE),
            "characters"
        )

    except Exception as e:

        print(
            "Local BODEX knowledge file error:",
            e
        )

        BODEX_KNOWLEDGE = ""


# =========================================================
# KNOWLEDGE SECTIONS
# =========================================================

def split_knowledge_sections(text):

    if not text:

        return []

    pattern = r"(?m)(?=^\s*\d+\.\s*)"

    parts = re.split(
        pattern,
        text
    )

    sections = []

    for part in parts:

        part = part.strip()

        if part:

            sections.append(part)

    return sections


KNOWLEDGE_SECTIONS = split_knowledge_sections(
    BODEX_KNOWLEDGE
)

print(
    "BODEX knowledge sections:",
    len(KNOWLEDGE_SECTIONS)
)


# =========================================================
# STOP WORDS
# =========================================================

STOP_WORDS = {

    "the",
    "and",
    "for",
    "are",
    "this",
    "that",
    "with",
    "from",
    "what",
    "when",
    "where",
    "which",
    "about",
    "please",
    "tell",
    "give",
    "does",
    "how",
    "can",
    "you",
    "is",
    "was",
    "were",
    "will",
    "would",
    "could",
    "should",
    "into",
    "their",
    "they",
    "them",
    "have",
    "has",
    "been",
    "being",
    "also",
    "than",
    "then",
    "its",
    "it",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "or",
    "by",
    "as",
    "at",
    "be",
    "do",
    "did",
    "user",
    "company"
}


# =========================================================
# EXTRACT KEYWORDS
# =========================================================

def extract_keywords(text):

    if not text:

        return []

    words = re.findall(
        r"\b[a-zA-Z0-9][a-zA-Z0-9\-\.]{2,}\b",
        text.lower()
    )

    result = []

    seen = set()

    for word in words:

        word = word.strip(
            ".,!?;:()[]{}\"'"
        )

        if word in STOP_WORDS:

            continue

        if len(word) < 3:

            continue

        if word not in seen:

            seen.add(word)

            result.append(word)

    return result


# =========================================================
# GET RELEVANT BODEX KNOWLEDGE
# =========================================================

def get_relevant_bodex_knowledge(
    user_question,
    max_chars=MAX_KNOWLEDGE_CONTEXT_CHARS
):

    if not BODEX_KNOWLEDGE:

        return ""

    if not KNOWLEDGE_SECTIONS:

        return BODEX_KNOWLEDGE[:max_chars]

    question_lower = (
        user_question or ""
    ).lower()

    keywords = extract_keywords(
        user_question
    )

    topic_aliases = {

        "recordex": [
            "recordex",
            "record",
            "records",
            "document",
            "archival",
            "ocr"
        ],

        "kpi": [
            "kpi",
            "kpi-dash",
            "dashboard",
            "analytics",
            "visual",
            "insight"
        ],

        "sis": [
            "sis",
            "secure info share",
            "password",
            "pin",
            "sensitive information"
        ],

        "utahdata": [
            "utahdata",
            "utahdata.org",
            "utah",
            "growth",
            "diversity"
        ],

        "bsa": [
            "bsa",
            "baseline",
            "baseline saas"
        ],

        "privacy": [
            "privacy",
            "security",
            "compliance",
            "governance",
            "data security"
        ],

        "ai_governance": [
            "responsible ai",
            "rai",
            "ai governance",
            "ai safety",
            "governance"
        ],

        "etl": [
            "etl",
            "extract",
            "transform",
            "load",
            "pipeline",
            "real-time"
        ],

        "culture": [
            "culture",
            "employee",
            "employees",
            "work",
            "teamwork",
            "collaboration"
        ],

        "philanthropy": [
            "philanthropy",
            "charity",
            "community",
            "school",
            "children"
        ],

        "careers": [
            "career",
            "careers",
            "job",
            "jobs",
            "apply",
            "candidate",
            "application"
        ],

        "benefits": [
            "benefits",
            "perks",
            "employee benefits"
        ],

        "infrastructure": [
            "infrastructure",
            "cloud",
            "architecture",
            "optimization"
        ],

        "legacy": [
            "legacy",
            "modernization",
            "upgrade",
            "old system"
        ]
    }

    expanded_keywords = set(
        keywords
    )

    for aliases in topic_aliases.values():

        if any(
            alias in question_lower
            for alias in aliases
        ):

            expanded_keywords.update(
                aliases
            )

    scored_sections = []

    for index, section in enumerate(
        KNOWLEDGE_SECTIONS
    ):

        lower_section = section.lower()

        score = 0

        for aliases in topic_aliases.values():

            for alias in aliases:

                if alias in question_lower:

                    if alias in lower_section:

                        score += 8

        for keyword in expanded_keywords:

            if keyword in lower_section:

                score += 1

                if keyword in {
                    "recordex",
                    "kpi-dash",
                    "kpi",
                    "sis",
                    "utahdata",
                    "bsa",
                    "privacy",
                    "security",
                    "compliance",
                    "philanthropy",
                    "benefits",
                    "careers",
                    "etl",
                    "responsible",
                    "governance"
                }:

                    score += 4

        scored_sections.append(
            (
                score,
                index,
                section
            )
        )

    scored_sections.sort(
        key=lambda item: item[0],
        reverse=True
    )

    selected = []

    current_length = 0

    for score, index, section in scored_sections:

        if score <= 0:

            continue

        remaining = (
            max_chars
            - current_length
        )

        if remaining <= 0:

            break

        selected.append(
            (
                index,
                section[:remaining]
            )
        )

        current_length += min(
            len(section),
            remaining
        )

        if len(selected) >= 5:

            break

    if not selected:

        for index, section in enumerate(
            KNOWLEDGE_SECTIONS
        ):

            if index < 4:

                selected.append(
                    (
                        index,
                        section
                    )
                )

    selected.sort(
        key=lambda item: item[0]
    )

    result = "\n\n".join(
        section
        for index, section in selected
    )

    return result[:max_chars]


# =========================================================
# URL
# =========================================================

def extract_url(text):

    if not text:

        return None

    pattern = r'https?://[^\s<>"\']+'

    match = re.search(
        pattern,
        text
    )

    if not match:

        return None

    return match.group(0).rstrip(
        ".,;:!?)]}"
    )


def is_valid_url(url):

    try:

        parsed = urlparse(url)

        return (
            parsed.scheme in (
                "http",
                "https"
            )
            and bool(parsed.netloc)
        )

    except Exception:

        return False


# =========================================================
# EXTRACT WEBPAGE
# =========================================================

def extract_url_text(url):

    try:

        if not is_valid_url(url):

            return (
                "",
                "",
                "Invalid URL."
            )

        headers = {

            "User-Agent":
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/143.0 Safari/537.36"
        }

        response = session.get(
            url,
            headers=headers,
            timeout=(10, 20),
            allow_redirects=True
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get(
                "Content-Type",
                ""
            )
            .lower()
        )

        if "text/html" not in content_type:

            return (
                "",
                "",
                "This URL does not contain a normal HTML webpage."
            )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        title = ""

        if soup.title:

            title = soup.title.get_text(
                " ",
                strip=True
            )

        for element in soup(
            [
                "script",
                "style",
                "noscript",
                "iframe",
                "svg",
                "canvas",
                "nav",
                "footer",
                "form",
                "aside"
            ]
        ):

            element.decompose()

        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.body
            or soup
        )

        text = main_content.get_text(
            separator="\n",
            strip=True
        )

        lines = []

        for line in text.splitlines():

            line = re.sub(
                r"\s+",
                " ",
                line
            ).strip()

            if line:

                lines.append(line)

        clean_text = "\n".join(
            lines
        )

        return (
            clean_text[:MAX_URL_CONTEXT_CHARS],
            title,
            ""
        )

    except requests.exceptions.Timeout:

        return (
            "",
            "",
            "The website took too long to respond."
        )

    except requests.exceptions.RequestException as e:

        return (
            "",
            "",
            f"Could not open this URL: {str(e)}"
        )

    except Exception as e:

        return (
            "",
            "",
            f"Could not analyze this webpage: {str(e)}"
        )


# =========================================================
# PDF EXTRACTION
# =========================================================

def extract_pdf_text(file):

    try:

        file_bytes = file.read()

        if not file_bytes:

            return ""

        reader = PdfReader(
            io.BytesIO(file_bytes)
        )

        pages = []

        current_chars = 0

        for page_number, page in enumerate(
            reader.pages,
            start=1
        ):

            try:

                text = page.extract_text()

                if text:

                    text = text.strip()

                    if text:

                        page_text = (
                            f"\n--- Page {page_number} ---\n"
                            f"{text}"
                        )

                        pages.append(
                            page_text
                        )

                        current_chars += len(
                            page_text
                        )

                if current_chars >= MAX_PDF_TEXT_CHARS:

                    break

            except Exception as page_error:

                print(
                    f"PDF page {page_number} error:",
                    page_error
                )

        return "\n\n".join(
            pages
        ).strip()[:MAX_PDF_TEXT_CHARS]

    except Exception as e:

        print(
            "PDF extraction error:",
            e
        )

        return ""


# =========================================================
# PDF RELEVANT CONTEXT
# =========================================================

def split_pdf_text(
    text,
    chunk_size=PDF_CHUNK_SIZE
):

    if not text:

        return []

    chunks = []

    start = 0

    while start < len(text):

        end = start + chunk_size

        chunk = text[start:end]

        if end < len(text):

            newline_index = chunk.rfind("\n")

            if newline_index > chunk_size * 0.5:

                end = start + newline_index

                chunk = text[start:end]

        chunk = chunk.strip()

        if chunk:

            chunks.append(chunk)

        start = end

    return chunks


def select_relevant_pdf_text(
    pdf_text,
    user_message
):

    if not pdf_text:

        return ""

    chunks = split_pdf_text(
        pdf_text
    )

    if not chunks:

        return ""

    keywords = extract_keywords(
        user_message
    )

    if not keywords:

        return pdf_text[:MAX_PDF_CONTEXT_CHARS]

    scored = []

    for index, chunk in enumerate(chunks):

        lower = chunk.lower()

        score = 0

        for keyword in keywords:

            score += lower.count(keyword)

        scored.append(
            (
                score,
                index,
                chunk
            )
        )

    scored.sort(
        key=lambda x: x[0],
        reverse=True
    )

    selected = []

    total = 0

    for score, index, chunk in scored:

        if score <= 0:

            continue

        remaining = (
            MAX_PDF_CONTEXT_CHARS
            - total
        )

        if remaining <= 0:

            break

        piece = chunk[:remaining]

        selected.append(
            (
                index,
                piece
            )
        )

        total += len(piece)

        if total >= MAX_PDF_CONTEXT_CHARS:

            break

    if not selected:

        return pdf_text[:MAX_PDF_CONTEXT_CHARS]

    selected.sort(
        key=lambda x: x[0]
    )

    return "\n\n".join(
        item[1]
        for item in selected
    )[:MAX_PDF_CONTEXT_CHARS]


# =========================================================
# CHECK BODEX CONTENT
# =========================================================

def contains_bodex_content(text):

    if not text:

        return False

    lower = text.lower()

    strong_terms = [

        "bodex",
        "recordex",
        "kpi-dash",
        "kpi dash",
        "secure info share",
        "baseline saas",
        "utahdata",
        "utahdata.org",
        "bodex technologies",
        "bodex solutions",
        "bodex ai",
        "bodex software",
        "bodex llm",
        "bodex analytics"
    ]

    for term in strong_terms:

        if term in lower:

            return True

    # Additional BODEX combinations
    bodex_words = [
        "bodeX",
        "record",
        "analytics",
        "custom software",
        "saas",
        "custom llm",
        "ai solutions",
        "data management"
    ]

    score = 0

    for word in bodex_words:

        if word.lower() in lower:

            score += 1

    # At least 2 BODEX-specific concepts
    return score >= 2


# =========================================================
# AI SCOPE CHECK
# =========================================================

def ai_check_bodex_content(
    content,
    is_image=False
):

    if not content and not is_image:

        return False

    try:

        if is_image:

            messages = [

                {
                    "role": "system",
                    "content": """
Determine whether this image is related to BODEX.

Return ONLY one word:

BODEX

or

OTHER

An image is BODEX-related if it visibly contains or represents
BODEX branding, BODEX products, BODEX dashboards, BODEX documents,
BODEX website, BODEX presentations, BODEX UI, or other clearly
BODEX-specific content.
"""
                },

                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Classify this image."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": content
                            }
                        }
                    ]
                }
            ]

            model = VISION_MODEL

        else:

            sample = content[:12000]

            messages = [

                {
                    "role": "system",
                    "content": """
Determine whether this document is related to BODEX.

Return ONLY one word:

BODEX

or

OTHER

BODEX-related documents may contain:
BODEX, RecordEX, KPI-Dash, SIS, Baseline SaaS,
UtahData, BODEX AI, BODEX services, BODEX products,
BODEX company information, BODEX careers, BODEX technologies,
or other clearly BODEX-specific information.
"""
                },

                {
                    "role": "user",
                    "content":
                        "Classify this document:\n\n" + sample
                }
            ]

            model = TEXT_MODEL

        headers = {

            "Authorization":
                f"Bearer {GROQ_API_KEY}",

            "Content-Type":
                "application/json"
        }

        payload = {

            "model":
                model,

            "messages":
                messages,

            "temperature":
                0,

            "max_tokens":
                5,

            "stream":
                False
        }

        response = session.post(

            GROQ_API_URL,

            headers=headers,

            json=payload,

            timeout=(10, 60)
        )

        if response.status_code != 200:

            print(
                "Scope check error:",
                response.text
            )

            return False

        data = response.json()

        result = (
            data["choices"][0]["message"]["content"]
            .strip()
            .upper()
        )

        print(
            "BODEX scope check:",
            result
        )

        return result == "BODEX"

    except Exception as e:

        print(
            "BODEX scope check exception:",
            e
        )

        return False


# =========================================================
# BUILD PDF CONTENT
# =========================================================

def build_pdf_content(
    user_message,
    pdf_text
):

    relevant = select_relevant_pdf_text(
        pdf_text,
        user_message
    )

    question = (
        user_message
        or
        "Please analyze this BODEX PDF."
    )

    return f"""
The user uploaded a BODEX-related PDF.

PDF CONTENT:

--- BEGIN BODEX PDF ---
{relevant}
--- END BODEX PDF ---

USER QUESTION:

{question}

Answer using the BODEX PDF content and BODEX Knowledge Base.

Do not invent information.
"""


# =========================================================
# BUILD URL CONTENT
# =========================================================

def build_url_content(
    user_message,
    url,
    title,
    webpage_text
):

    question = (
        user_message
        or
        "Please analyze this BODEX webpage."
    )

    return f"""
The user provided a BODEX-related webpage.

URL:
{url}

Title:
{title}

WEBPAGE CONTENT:

--- BEGIN BODEX WEBPAGE ---
{webpage_text}
--- END BODEX WEBPAGE ---

USER QUESTION:

{question}

Answer only using the BODEX webpage and BODEX Knowledge Base.
Do not invent information.
"""


# =========================================================
# CREATE CHAT
# =========================================================

def create_chat(
    title="New Chat"
):

    if chat_collection is None:

        return None

    now = datetime.now(
        timezone.utc
    )

    chat = {

        "title":
            title,

        "messages":
            [],

        "createdAt":
            now,

        "updatedAt":
            now
    }

    try:

        result = chat_collection.insert_one(
            chat
        )

        return str(
            result.inserted_id
        )

    except Exception as e:

        print(
            "Create chat error:",
            e
        )

        return None


# =========================================================
# SAVE MESSAGE
# =========================================================

def save_message(
    chat_id,
    role,
    content
):

    try:

        if (
            chat_collection is None
            or not chat_id
            or not ObjectId.is_valid(chat_id)
            or not content
        ):

            return False

        now = datetime.now(
            timezone.utc
        )

        chat_collection.update_one(

            {
                "_id":
                    ObjectId(chat_id)
            },

            {

                "$push": {

                    "messages": {

                        "role":
                            role,

                        "content":
                            content,

                        "createdAt":
                            now
                    }
                },

                "$set": {

                    "updatedAt":
                        now
                }
            }
        )

        return True

    except Exception as e:

        print(
            "Save message error:",
            e
        )

        return False


# =========================================================
# UPDATE TITLE
# =========================================================

def update_chat_title(
    chat_id,
    title
):

    try:

        if (
            chat_collection is None
            or not chat_id
            or not ObjectId.is_valid(chat_id)
        ):

            return False

        chat_collection.update_one(

            {
                "_id":
                    ObjectId(chat_id)
            },

            {
                "$set": {

                    "title":
                        title,

                    "updatedAt":
                        datetime.now(
                            timezone.utc
                        )
                }
            }
        )

        return True

    except Exception as e:

        print(
            "Update title error:",
            e
        )

        return False


# =========================================================
# CHAT
# =========================================================

@app.route(
    "/chat",
    methods=["POST"]
)
def chat():

    try:

        # -------------------------------------------------
        # USER MESSAGE
        # -------------------------------------------------

        user_message = request.form.get(
            "message",
            ""
        ).strip()


        # -------------------------------------------------
        # CHAT ID
        # -------------------------------------------------

        chat_id = request.form.get(
            "chat_id",
            ""
        ).strip()


        # -------------------------------------------------
        # CREATE CHAT
        # -------------------------------------------------

        if not chat_id:

            title = (
                user_message[:40]
                if user_message
                else
                "New Chat"
            )

            chat_id = create_chat(
                title
            )

        elif not ObjectId.is_valid(
            chat_id
        ):

            return jsonify({
                "error":
                    "Invalid chat_id."
            }), 400


        # -------------------------------------------------
        # DOCUMENT CONTEXT
        # -------------------------------------------------

        document_context = request.form.get(
            "document_context",
            ""
        ).strip()


        # -------------------------------------------------
        # FILE
        # -------------------------------------------------

        uploaded_file = request.files.get(
            "file"
        )


        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if (
            not user_message
            and not uploaded_file
            and not document_context
        ):

            return jsonify({
                "error":
                    "Message, document or image is required."
            }), 400


        # -------------------------------------------------
        # GROQ KEY
        # -------------------------------------------------

        if not GROQ_API_KEY:

            return jsonify({
                "error":
                    "GROQ_API_KEY is missing."
            }), 500


        # -------------------------------------------------
        # SAVE USER MESSAGE
        # -------------------------------------------------

        if user_message and chat_id:

            save_message(
                chat_id,
                "user",
                user_message
            )


        # -------------------------------------------------
        # VARIABLES
        # -------------------------------------------------

        pdf_text = ""

        image_base64 = None

        image_mime_type = None

        webpage_text = ""

        webpage_title = ""

        detected_url = None

        selected_model = TEXT_MODEL

        uploaded_bodex_content = False


        # =================================================
        # FILE PROCESSING
        # =================================================

        if uploaded_file:

            filename = (
                uploaded_file.filename
                or ""
            ).lower()

            content_type = (
                uploaded_file.content_type
                or ""
            ).lower()


            # =============================================
            # PDF
            # =============================================

            if (
                filename.endswith(".pdf")
                or content_type == "application/pdf"
            ):

                print(
                    "\nChecking uploaded PDF for BODEX content..."
                )

                pdf_text = extract_pdf_text(
                    uploaded_file
                )

                if not pdf_text:

                    return jsonify({
                        "error":
                            "Could not extract text from this PDF. "
                            "The PDF may be scanned or image-based."
                    }), 400


                # First local check
                uploaded_bodex_content = contains_bodex_content(
                    pdf_text
                )


                # If local check fails, use AI classifier
                if not uploaded_bodex_content:

                    uploaded_bodex_content = ai_check_bodex_content(
                        pdf_text,
                        is_image=False
                    )


                print(
                    "Uploaded PDF BODEX:",
                    uploaded_bodex_content
                )


                if not uploaded_bodex_content:

                    # IMPORTANT:
                    # Do not send random PDF to answer model.
                    return Response(

                        OUT_OF_SCOPE_MESSAGE,

                        content_type=
                            "text/plain; charset=utf-8",

                        headers={
                            "X-Chat-Id":
                                chat_id or ""
                        }
                    )


                selected_model = TEXT_MODEL


            # =============================================
            # IMAGE
            # =============================================

            elif (
                content_type.startswith("image/")
                or filename.endswith(
                    (
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp"
                    )
                )
            ):

                raw_image = uploaded_file.read()

                if not raw_image:

                    return jsonify({
                        "error":
                            "The uploaded image is empty."
                    }), 400


                if len(raw_image) > (
                    3 * 1024 * 1024
                ):

                    return jsonify({
                        "error":
                            "Please upload an image smaller than 3 MB."
                    }), 400


                image_base64 = base64.b64encode(
                    raw_image
                ).decode("utf-8")


                image_mime_type = (
                    content_type
                    or
                    "image/jpeg"
                )


                # =========================================
                # AI IMAGE SCOPE CHECK
                # =========================================

                image_data_url = (
                    f"data:"
                    f"{image_mime_type}"
                    f";base64,"
                    f"{image_base64}"
                )


                print(
                    "\nChecking uploaded image for BODEX content..."
                )


                uploaded_bodex_content = ai_check_bodex_content(
                    image_data_url,
                    is_image=True
                )


                print(
                    "Uploaded image BODEX:",
                    uploaded_bodex_content
                )


                if not uploaded_bodex_content:

                    return Response(

                        OUT_OF_SCOPE_MESSAGE,

                        content_type=
                            "text/plain; charset=utf-8",

                        headers={
                            "X-Chat-Id":
                                chat_id or ""
                        }
                    )


                selected_model = VISION_MODEL


            # =============================================
            # UNSUPPORTED
            # =============================================

            else:

                return jsonify({
                    "error":
                        "Only PDF, JPG, JPEG, PNG and WEBP files are supported."
                }), 400


        # =================================================
        # URL PROCESSING
        # =================================================

        detected_url = extract_url(
            user_message
        )


        if (
            detected_url
            and not image_base64
            and not pdf_text
        ):

            (
                webpage_text,
                webpage_title,
                url_error
            ) = extract_url_text(
                detected_url
            )


            if url_error:

                return jsonify({
                    "error":
                        url_error
                }), 400


            if not webpage_text:

                return jsonify({
                    "error":
                        "No readable webpage content was found."
                }), 400


            # ---------------------------------------------
            # BODEX URL CHECK
            # ---------------------------------------------

            if not contains_bodex_content(
                webpage_text
            ):

                bodex_url_check = ai_check_bodex_content(
                    webpage_text,
                    is_image=False
                )

                if not bodex_url_check:

                    return Response(

                        OUT_OF_SCOPE_MESSAGE,

                        content_type=
                            "text/plain; charset=utf-8",

                        headers={
                            "X-Chat-Id":
                                chat_id or ""
                        }
                    )


            selected_model = TEXT_MODEL


        # =================================================
        # NORMAL QUESTION SCOPE
        # =================================================

        if (
            not uploaded_file
            and not detected_url
            and not document_context
        ):

            question_is_bodex = contains_bodex_content(
                user_message
            )


            # BODEX-specific keywords
            bodex_question_words = [

                "bodex",
                "recordex",
                "kpi",
                "kpi-dash",
                "sis",
                "utahdata",
                "baseline",
                "saas",
                "custom llm",
                "ai solutions",
                "data management",
                "analytics",
                "bodeX",
                "bode x"
            ]


            if any(
                word in user_message.lower()
                for word in bodex_question_words
            ):

                question_is_bodex = True


            if not question_is_bodex:

                # Let exact BODEX refusal happen immediately.
                return Response(

                    OUT_OF_SCOPE_MESSAGE,

                    content_type=
                        "text/plain; charset=utf-8",

                    headers={
                        "X-Chat-Id":
                            chat_id or ""
                    }
                )


        # =================================================
        # RELEVANT BODEX KNOWLEDGE
        # =================================================

        relevant_knowledge = (
            get_relevant_bodex_knowledge(
                user_message
            )
        )


        print(
            "\nRelevant BODEX knowledge:",
            len(relevant_knowledge),
            "characters"
        )


        # =================================================
        # USER CONTENT
        # =================================================

        if image_base64:

            image_question = (
                user_message
                or
                "Please analyze this BODEX image."
            )


            user_content = [

                {
                    "type":
                        "text",

                    "text":
                        image_question
                },

                {
                    "type":
                        "image_url",

                    "image_url": {

                        "url":
                            (
                                f"data:"
                                f"{image_mime_type}"
                                f";base64,"
                                f"{image_base64}"
                            )
                    }
                }

            ]


        elif pdf_text:

            user_content = build_pdf_content(

                user_message,

                pdf_text
            )


        elif detected_url:

            user_content = build_url_content(

                user_message,

                detected_url,

                webpage_title,

                webpage_text
            )


        elif document_context:

            limited_context = (
                document_context[
                    :MAX_PDF_CONTEXT_CHARS
                ]
            )

            user_content = f"""

The user provided BODEX-related document context:

--- BEGIN DOCUMENT ---
{limited_context}
--- END DOCUMENT ---

User question:

{user_message}

Answer only using this BODEX document context
and the BODEX Knowledge Base.

Do not invent information.
"""


        else:

            user_content = user_message


        # =================================================
        # HEADERS
        # =================================================

        headers = {

            "Authorization":
                f"Bearer {GROQ_API_KEY}",

            "Content-Type":
                "application/json"
        }


        # =================================================
        # PAYLOAD
        # =================================================

        payload = {

            "model":
                selected_model,

            "messages": [

                {
                    "role":
                        "system",

                    "content":
                        SYSTEM_PROMPT
                },

                {
                    "role":
                        "system",

                    "content":
                        (
                            "BODEX KNOWLEDGE BASE\n\n"
                            + relevant_knowledge
                            + "\n\n"
                            "END BODEX KNOWLEDGE BASE\n\n"
                            "IMPORTANT:\n"
                            "Use the uploaded BODEX document/image/webpage "
                            "when it is provided.\n"
                            "Use the BODEX Knowledge Base for BODEX facts.\n"
                            "Never invent information.\n"
                            "Never answer non-BODEX content.\n"
                            "If the requested BODEX detail is not available, say:\n"
                            "\"The available BODEX information does not specify this detail.\""
                        )
                },

                {
                    "role":
                        "user",

                    "content":
                        user_content
                }

            ],

            "temperature":
                0.1,

            "max_tokens":
                FINAL_RESPONSE_TOKENS,

            "stream":
                True
        }


        # =================================================
        # REQUEST
        # =================================================

        start_time = time.time()


        print(
            "\n================================"
        )

        print(
            "SENDING REQUEST TO GROQ"
        )

        print(
            "Model:",
            selected_model
        )

        print(
            "Question:",
            user_message
        )

        print(
            "BODEX FILE:",
            uploaded_bodex_content
        )

        print(
            "Knowledge chars:",
            len(relevant_knowledge)
        )

        print(
            "================================"
        )


        response = session.post(

            GROQ_API_URL,

            headers=headers,

            json=payload,

            stream=True,

            timeout=(10, 180)
        )


        response.encoding = "utf-8"


        # =================================================
        # GROQ ERROR
        # =================================================

        if response.status_code != 200:

            try:

                error_data = response.json()

            except Exception:

                error_data = response.text


            print(
                "Groq Error:",
                error_data
            )


            return jsonify({
                "error":
                    error_data
            }), response.status_code


        # =================================================
        # STREAM
        # =================================================

        @stream_with_context
        def generate():

            assistant_response = ""


            try:

                for line in response.iter_lines(
                    decode_unicode=True
                ):

                    if not line:

                        continue


                    if not line.startswith(
                        "data:"
                    ):

                        continue


                    data = line[5:].strip()


                    if data == "[DONE]":

                        break


                    try:

                        chunk = json.loads(
                            data
                        )

                    except json.JSONDecodeError:

                        continue


                    choices = chunk.get(
                        "choices",
                        []
                    )


                    if not choices:

                        continue


                    delta = choices[0].get(
                        "delta",
                        {}
                    )


                    content = delta.get(
                        "content"
                    )


                    if content:

                        assistant_response += content

                        yield content


                # -----------------------------------------
                # SAVE ASSISTANT RESPONSE
                # -----------------------------------------

                if (
                    assistant_response
                    and chat_id
                ):

                    save_message(

                        chat_id,

                        "assistant",

                        assistant_response
                    )


                # -----------------------------------------
                # TIME
                # -----------------------------------------

                elapsed = (
                    time.time()
                    - start_time
                )


                print(
                    f"Response time: {elapsed:.2f}s"
                )


                yield (
                    f"\n__TIME__:"
                    f"{elapsed:.2f}"
                )


            except Exception as e:

                print(
                    "Streaming error:",
                    e
                )


                if (
                    assistant_response
                    and chat_id
                ):

                    save_message(

                        chat_id,

                        "assistant",

                        assistant_response
                    )


                yield (
                    f"\n__ERROR__:"
                    f"{str(e)}"
                )


            finally:

                response.close()


        # =================================================
        # RETURN STREAM
        # =================================================

        return Response(

            generate(),

            content_type=
                "text/plain; charset=utf-8",

            headers={

                "Cache-Control":
                    "no-cache, no-transform",

                "X-Accel-Buffering":
                    "no",

                "Connection":
                    "keep-alive",

                "X-Chat-Id":
                    chat_id or ""
            }
        )


    # =====================================================
    # TIMEOUT
    # =====================================================

    except requests.exceptions.Timeout:

        return jsonify({
            "error":
                "AI server took too long to respond."
        }), 504


    # =====================================================
    # REQUEST ERROR
    # =====================================================

    except requests.exceptions.RequestException as e:

        print(
            "Request error:",
            e
        )

        return jsonify({
            "error":
                f"Connection error: {str(e)}"
        }), 503


    # =====================================================
    # GENERAL ERROR
    # =====================================================

    except Exception as e:

        print(
            "General chat error:",
            e
        )

        return jsonify({
            "error":
                str(e)
        }), 500


# =========================================================
# GET ALL CHATS
# =========================================================

@app.route(
    "/chats",
    methods=["GET"]
)
def get_all_chats():

    try:

        if chat_collection is None:

            return jsonify({
                "error":
                    "MongoDB is not connected."
            }), 500


        chats = chat_collection.find(
            {},
            {
                "messages": 0
            }
        ).sort(
            "updatedAt",
            -1
        )


        result = []


        for chat_item in chats:

            result.append({

                "id":
                    str(
                        chat_item["_id"]
                    ),

                "title":
                    chat_item.get(
                        "title",
                        "New Chat"
                    ),

                "createdAt":
                    chat_item.get(
                        "createdAt"
                    ),

                "updatedAt":
                    chat_item.get(
                        "updatedAt"
                    )
            })


        return jsonify({
            "chats":
                result
        })


    except Exception as e:

        print(
            "Get all chats error:",
            e
        )

        return jsonify({
            "error":
                str(e)
        }), 500


# =========================================================
# GET SINGLE CHAT
# =========================================================

@app.route(
    "/chats/<chat_id>",
    methods=["GET"]
)
def get_single_chat(chat_id):

    try:

        if chat_collection is None:

            return jsonify({
                "error":
                    "MongoDB is not connected."
            }), 500


        if not ObjectId.is_valid(
            chat_id
        ):

            return jsonify({
                "error":
                    "Invalid chat ID."
            }), 400


        chat_item = chat_collection.find_one({

            "_id":
                ObjectId(chat_id)

        })


        if not chat_item:

            return jsonify({
                "error":
                    "Chat not found."
            }), 404


        chat_item["_id"] = str(
            chat_item["_id"]
        )


        return jsonify(
            chat_item
        )


    except Exception as e:

        print(
            "Get single chat error:",
            e
        )

        return jsonify({
            "error":
                str(e)
        }), 500


# =========================================================
# DELETE CHAT
# =========================================================

@app.route(
    "/chats/<chat_id>",
    methods=["DELETE"]
)
def delete_chat(chat_id):

    try:

        if chat_collection is None:

            return jsonify({
                "error":
                    "MongoDB is not connected."
            }), 500


        if not ObjectId.is_valid(
            chat_id
        ):

            return jsonify({
                "error":
                    "Invalid chat ID."
            }), 400


        result = chat_collection.delete_one({

            "_id":
                ObjectId(chat_id)

        })


        if result.deleted_count == 0:

            return jsonify({
                "error":
                    "Chat not found."
            }), 404


        return jsonify({

            "success":
                True,

            "message":
                "Chat deleted successfully."

        })


    except Exception as e:

        print(
            "Delete chat error:",
            e
        )

        return jsonify({
            "error":
                str(e)
        }), 500


# =========================================================
# KNOWLEDGE STATUS
# =========================================================

@app.route(
    "/knowledge/status",
    methods=["GET"]
)
def knowledge_status():

    try:

        if knowledge_collection is None:

            return jsonify({

                "connected":
                    False,

                "message":
                    "Knowledge collection is not connected."

            }), 500


        document = knowledge_collection.find_one(
            {
                "type":
                    "bodex_knowledge"
            }
        )


        if not document:

            return jsonify({

                "connected":
                    True,

                "knowledge_found":
                    False,

                "message":
                    "No BODEX knowledge found."

            })


        content = document.get(
            "content",
            ""
        )


        return jsonify({

            "connected":
                True,

            "knowledge_found":
                True,

            "database":
                MONGO_DB,

            "collection":
                "knowledge",

            "characters":
                len(content)

        })


    except Exception as e:

        return jsonify({

            "connected":
                False,

            "error":
                str(e)

        }), 500


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    mongo_status = (
        mongo_client is not None
        and knowledge_collection is not None
    )


    return jsonify({

        "status":
            "ok",

        "service":
            "Saarthi AI Backend",

        "mongodb":
            mongo_status,

        "database":
            MONGO_DB

    })


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return "Saarthi AI Backend is Running!"


# =========================================================
# 413
# =========================================================

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({

        "error":
            "File is too large. Maximum file size is 25 MB."

    }), 413


# =========================================================
# 504
# =========================================================

@app.errorhandler(504)
def timeout_error(error):

    return jsonify({

        "error":
            "AI server took too long to respond."

    }), 504


# =========================================================
# GENERAL ERROR
# =========================================================

@app.errorhandler(Exception)
def handle_exception(error):

    print(
        "Unhandled error:",
        error
    )

    return jsonify({

        "error":
            str(error)

    }), 500


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=False,

        threaded=True
    )