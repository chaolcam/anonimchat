import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne
import sys
import codecs

# Windows konsolundaki emoji hatalarini onlemek icin
if sys.platform.startswith('win'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

MONGO_URI = "mongodb+srv://emre252687_db_user:lE5PZFfo5RJFnOC9@cluster0.1nrcqti.mongodb.net/?appName=Cluster0"

async def migrate():
    client = AsyncIOMotorClient(MONGO_URI)
    db = client['secret_lounge_db']
    
    print("Donusum (Sikistirma) baslatiliyor. Veriler indiriliyor...")
    
    # Adim 1: Verileri client tarafinda grupla (MongoDB limitlerine takilmamak icin)
    grouped = {}
    count = 0
    
    # Sadece eski kayitlari cekiyoruz
    cursor = db.messages.find({"target_user_id": {"$exists": True}})
    
    async for doc in cursor:
        key = (doc["original_user_id"], doc["original_message_id"])
        if key not in grouped:
            grouped[key] = {
                "content_type": doc.get("content_type", "text"),
                "timestamp": doc.get("timestamp"),
                "targets": []
            }
        grouped[key]["targets"].append({
            "user_id": doc["target_user_id"],
            "msg_id": doc["target_message_id"]
        })
        
        count += 1
        if count % 50000 == 0:
            print(f"{count} belge indirildi ve islendi...")
            
    print(f"Bitti! Toplam {count} eski belge indirildi ve {len(grouped)} orijinal mesaja sıkıştırıldı.")
    
    if len(grouped) == 0:
        print("Sikistirilacak eski belge bulunamadi. Islem iptal ediliyor.")
        return

    print("Veritabanina tek paket halinde (messages_new) yukleniyor...")
    
    # Adim 2: Yeni formati hazirla ve yukle
    operations = []
    for (orig_u, orig_m), data in grouped.items():
        operations.append(
            UpdateOne(
                {"original_user_id": orig_u, "original_message_id": orig_m},
                {
                    "$setOnInsert": {
                        "content_type": data["content_type"],
                        "timestamp": data["timestamp"]
                    },
                    "$addToSet": {
                        "targets": {"$each": data["targets"]}
                    }
                },
                upsert=True
            )
        )
        
    chunk_size = 20000
    for i in range(0, len(operations), chunk_size):
        chunk = operations[i:i + chunk_size]
        await db.messages_new.bulk_write(chunk)
        print(f"{i + len(chunk)} / {len(operations)} orjinal mesaj yazildi...")
        
    print("Mevcut yeni formatli veriler (varsa) aktariliyor...")
    new_format_docs_cursor = db.messages.find({"targets": {"$exists": True}})
    new_format_docs = await new_format_docs_cursor.to_list(None)
    if new_format_docs:
        await db.messages_new.insert_many(new_format_docs)
        print(f"{len(new_format_docs)} adet yeni formatli belge aktarildi.")

    print("Eski siskin veritabani siliniyor...")
    await db.messages.drop()
    
    print("Yeni koleksiyon devreye aliniyor...")
    await db.messages_new.rename("messages")
    
    print("MIGRASYON TAMAMLANDI! Veritabaniniz inanilmaz derecede kuculdu.")

if __name__ == "__main__":
    asyncio.run(migrate())
