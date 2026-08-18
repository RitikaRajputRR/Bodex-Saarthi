import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

# MongoDB settings
MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "bodex_saarthi")

# Knowledge file
KNOWLEDGE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "bodex_knowledge.txt"
)

try:
    # Connect MongoDB
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=10000
    )

    db = client[MONGO_DB]
    knowledge_collection = db["knowledge"]

    # Test connection
    client.admin.command("ping")

    print("MongoDB connected successfully.")
    print("Database:", MONGO_DB)

    # Read knowledge file
    with open(
        KNOWLEDGE_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        knowledge_text = file.read()

    if not knowledge_text.strip():
        print("ERROR: bodex_knowledge.txt is empty.")
        exit()

    # Remove old knowledge
    knowledge_collection.delete_many({})

    # Insert BODEX knowledge
    result = knowledge_collection.insert_one({
        "source": "bodex_knowledge.txt",
        "content": knowledge_text,
        "type": "bodex_knowledge"
    })

    print("BODEX knowledge inserted successfully.")
    print("Document ID:", result.inserted_id)
    print("Characters:", len(knowledge_text))

except FileNotFoundError:
    print("ERROR: bodex_knowledge.txt not found.")

except Exception as e:
    print("ERROR:", e)

finally:
    try:
        client.close()
    except:
        pass