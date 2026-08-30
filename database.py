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
    # Yeni yapıya göre indeksler (dizi içindeki verilere hızlı erişim)
    await messages_collection.create_index([("targets.user_id", 1), ("targets.msg_id", 1)])
    await messages_collection.create_index([("original_user_id", 1), ("original_message_id", 1)], unique=True)
    
    # 1 haftadan (604800 saniye) eski mesajları MongoDB'nin otomatik silmesi için TTL index
    await messages_collection.create_index("timestamp", expireAfterSeconds=604800)
    
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
    Gönderilen mesajı veritabanına loglar. Orijinal mesaja ait tek bir döküman (JSON) tutulur 
    ve diğer hedefler (targets) dizisine eklenir.
    """
    await messages_collection.update_one(
        {
            "original_user_id": original_user_id,
            "original_message_id": original_message_id
        },
        {
            "$setOnInsert": {
                "content_type": content_type,
                "timestamp": datetime.now(timezone.utc)
            },
            "$push": {
                "targets": {
                    "user_id": target_user_id,
                    "msg_id": target_message_id
                }
            }
        },
        upsert=True
    )

async def get_message_info(target_user_id: int, target_message_id: int):
    """Bir kullanıcının sohbetindeki bir mesajın kimden geldiğini bulur."""
    # Eski formattaki mesajları da bulabilmesi için $or kullanıyoruz
    msg = await messages_collection.find_one({
        "$or": [
            {
                "targets": {
                    "$elemMatch": {
                        "user_id": target_user_id,
                        "msg_id": target_message_id
                    }
                }
            },
            {
                "target_user_id": target_user_id,
                "target_message_id": target_message_id
            }
        ]
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
    # Önce yeni formatta veya eski formatta dokümanı bulalım
    msg = await messages_collection.find_one({
        "original_user_id": original_user_id,
        "original_message_id": original_message_id,
        "$or": [
            {"targets.user_id": target_user_id},
            {"target_user_id": target_user_id}
        ]
    })
    
    if msg:
        # Eski format (hedef direkt ana belgedeyse)
        if "target_message_id" in msg and msg.get("target_user_id") == target_user_id:
            return msg["target_message_id"]
            
        # Yeni format (hedef targets dizisindeyse)
        for t in msg.get("targets", []):
            if t["user_id"] == target_user_id:
                return t["msg_id"]
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

async def get_all_copies(original_user_id: int, original_message_id: int):
    """Bir orijinal mesajın kopyalandığı tüm hedefleri (target_user_id, target_message_id) listeler."""
    # 1. Eski formattaki ayrı ayrı belgeleri bulalım
    cursor = messages_collection.find({
        "original_user_id": original_user_id,
        "original_message_id": original_message_id,
        "target_user_id": {"$exists": True}
    })
    old_copies_docs = await cursor.to_list(length=None)
    
    # 2. Yeni formattaki tek belgeyi bulalım
    new_doc = await messages_collection.find_one({
        "original_user_id": original_user_id,
        "original_message_id": original_message_id,
        "targets": {"$exists": True}
    })
    
    results = []
    # Eski kayıtları listeye ekle
    for doc in old_copies_docs:
        results.append({
            "target_user_id": doc["target_user_id"],
            "target_message_id": doc["target_message_id"]
        })
        
    # Yeni kayıtları listeye ekle
    if new_doc:
        for t in new_doc.get("targets", []):
            results.append({
                "target_user_id": t["user_id"],
                "target_message_id": t["msg_id"]
            })
            
    return results

async def get_top_users(limit: int = 10):
    """En çok mesaj atan kullanıcıları sıralar."""
    pipeline = [
        {
            "$group": {
                "_id": {
                    "user_id": "$original_user_id",
                    "msg_id": "$original_message_id"
                }
            }
        },
        {
            "$group": {
                "_id": "$_id.user_id",
                "message_count": {"$sum": 1}
            }
        },
        {
            "$sort": {"message_count": -1}
        },
        {
            "$limit": limit
        },
        {
            "$lookup": {
                "from": "users",
                "localField": "_id",
                "foreignField": "user_id",
                "as": "user_info"
            }
        },
        {
            "$unwind": {
                "path": "$user_info",
                "preserveNullAndEmptyArrays": True
            }
        },
        {
            "$project": {
                "user_id": "$_id",
                "message_count": 1,
                "full_name": {"$ifNull": ["$user_info.full_name", "Bilinmeyen"]},
                "username": "$user_info.username"
            }
        }
    ]
    
    cursor = messages_collection.aggregate(pipeline)
    return await cursor.to_list(length=limit)
