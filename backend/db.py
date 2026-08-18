import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB", "bodex_saarthi")

client = MongoClient(
    MONGO_URI,
    serverSelectionTimeoutMS=10000
)

db = client[MONGO_DB]

knowledge_collection = db["knowledge"]
urls_collection = db["urls"]
chats_collection = db["chats"]

try:
    client.admin.command("ping")
    print("MongoDB connected successfully.")
    print("MongoDB database:", MONGO_DB)

except Exception as e:
    print("MongoDB connection error:", e)