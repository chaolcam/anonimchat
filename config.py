import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# Admin ID'lerini liste haline getiriyoruz
admin_env = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in admin_env.split(",") if x.strip().isdigit()]

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables.")
if not MONGO_URI:
    raise ValueError("MONGO_URI is not set in environment variables.")
