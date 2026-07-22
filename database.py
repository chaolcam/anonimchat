import logging
from motor.motor_asyncio import AsyncIOMotorClient
import config
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# MongoDB Client
client = AsyncIOMotorClient(config.MONGO_URI)
db = client['secret_lounge_db']

users_collection = db['users']
messages_collection = db['messages']
bans_collection = db['bans']

async def init_db():
    """Veritabanı indekslerini oluşturur."""
    await users_collection.create_index("user_id", unique=True)
    # Her kullanıcının kendi sohbetindeki mesaj id'si o chat için benzersizdir
    await messages_collection.create_index([("target_user_id", 1), ("target_message_id", 1)], unique=True)
    await bans_collection.create_index("user_id", unique=True)
    logger.info("MongoDB indexleri güncellendi.")

async def add_or_update_user(user_id: int, username: str, full_name: str):
    """Kullanıcıyı veritabanına ekler veya aktifliğini günceller."""
    now = datetime.now(timezone.utc)
    
    banned = await is_banned(user_id)
    if banned:
        return False

    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {
            "username": username,
            "full_name": full_name,
            "is_active": True,
            "last_active": now
        }, "$setOnInsert": {
            "joined_at": now
        }},
        upsert=True
    )
    return True

async def set_user_inactive(user_id: int):
    await users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"is_active": False}}
    )

async def get_active_users():
    cursor = users_collection.find({"is_active": True})
    users = await cursor.to_list(length=None)
    return [u["user_id"] for u in users]

async def log_message(original_user_id: int, original_message_id: int, target_user_id: int, target_message_id: int, content_type: str):
    """
    Gönderilen her kopyayı ve asıl mesajı veritabanına loglar.
    original_*: Mesajı atan kişi ve o kişinin kendi chatindeki mesaj ID'si
    target_*: Mesajın iletildiği kişi ve o kişinin chatinde oluşan yeni mesajın ID'si
    """
    await messages_collection.insert_one({
        "original_user_id": original_user_id,
        "original_message_id": original_message_id,
        "target_user_id": target_user_id,
        "target_message_id": target_message_id,
        "content_type": content_type,
        "timestamp": datetime.now(timezone.utc)
    })

async def get_message_info(target_user_id: int, target_message_id: int):
    """Bir kullanıcının sohbetindeki bir mesajın kimden geldiğini bulur."""
    msg = await messages_collection.find_one({
        "target_user_id": target_user_id,
        "target_message_id": target_message_id
    })
    if msg:
        user = await users_collection.find_one({"user_id": msg["original_user_id"]})
        return {
            "original_user_id": msg["original_user_id"],
            "original_message_id": msg["original_message_id"],
            "username": user.get("username") if user else None,
            "full_name": user.get("full_name") if user else None,
            "timestamp": msg["timestamp"]
        }
    return None

async def get_target_message_id(original_user_id: int, original_message_id: int, target_user_id: int):
    """
    Belirli bir orijinal mesajın (örn: Ali'nin 100 ID'li mesajı), 
    diğer kullanıcının (örn: Ayşe) sohbetinde hangi ID'ye sahip olduğunu bulur (reply yapabilmek için).
    """
    msg = await messages_collection.find_one({
        "original_user_id": original_user_id,
        "original_message_id": original_message_id,
        "target_user_id": target_user_id
    })
    if msg:
        return msg["target_message_id"]
    return None

async def ban_user(user_id: int, reason: str = ""):
    await bans_collection.update_one(
        {"user_id": user_id},
        {"$set": {"reason": reason, "banned_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    await set_user_inactive(user_id)

async def unban_user(user_id: int):
    await bans_collection.delete_one({"user_id": user_id})

async def is_banned(user_id: int) -> bool:
    doc = await bans_collection.find_one({"user_id": user_id})
    return bool(doc)

async def get_stats():
    total_users = await users_collection.count_documents({})
    active_users = await users_collection.count_documents({"is_active": True})
    total_messages = await messages_collection.count_documents({})
    total_banned = await bans_collection.count_documents({})
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_messages": total_messages,
        "total_banned": total_banned
    }
