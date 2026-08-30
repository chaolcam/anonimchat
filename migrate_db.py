import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

# LÜTFEN AŞAĞIDAKİ TİRNAK İÇİNE MONGODB BAĞLANTI LİNKİNİZİ (MONGO_URI) YAPIŞTIRIN
MONGO_URI = "mongodb+srv://emre252687_db_user:lE5PZFfo5RJFnOC9@cluster0.1nrcqti.mongodb.net/?appName=Cluster0"

async def migrate():


    client = AsyncIOMotorClient(MONGO_URI)
    db = client['secret_lounge_db']
    
    print("Dönüşüm (Sıkıştırma) başlatılıyor. Bu işlem veritabanı boyutuna göre biraz sürebilir...")
    
    # Tüm eski kayıtları bulup yeni formata (Array) çevirecek ve 'messages_new' adlı yeni koleksiyona kaydedecek olan sorgu
    pipeline = [
        # Sadece eski düzendeki (hedefi ayrı kaydedilmiş) belgeleri al
        { "$match": { "target_user_id": { "$exists": True } } },
        
        # Orijinal mesaja göre grupla
        {
            "$group": {
                "_id": {
                    "original_user_id": "$original_user_id",
                    "original_message_id": "$original_message_id"
                },
                "content_type": { "$first": "$content_type" },
                "timestamp": { "$first": "$timestamp" },
                "targets": {
                    "$push": {
                        "user_id": "$target_user_id",
                        "msg_id": "$target_message_id"
                    }
                }
            }
        },
        
        # Alan isimlerini ana formata uygun hale getir
        {
            "$project": {
                "_id": 0,
                "original_user_id": "$_id.original_user_id",
                "original_message_id": "$_id.original_message_id",
                "content_type": 1,
                "timestamp": 1,
                "targets": 1
            }
        },
        
        # Sonuçları geçici yeni bir koleksiyona (messages_new) kaydet
        { "$out": "messages_new" }
    ]
    
    try:
        # Sorguyu çalıştır
        await db.messages.aggregate(pipeline).to_list(None)
        print("✅ Veriler başarıyla yeni 'messages_new' koleksiyonuna sıkıştırıldı!")
        
        # Zaten yeni formatta olan (eğer varsa) mesajları da bulup yeni koleksiyona ekleyelim
        print("Mevcut yeni formatlı veriler aktarılıyor...")
        new_format_docs_cursor = db.messages.find({"targets": {"$exists": True}})
        new_format_docs = await new_format_docs_cursor.to_list(None)
        if new_format_docs:
            await db.messages_new.insert_many(new_format_docs)
            print(f"✅ {len(new_format_docs)} adet yeni formatlı belge aktarıldı.")
        
        # Artık eski şişkin koleksiyonu silebiliriz
        print("Eski şişkin veritabanı siliniyor...")
        await db.messages.drop()
        
        # Yeni koleksiyonun adını 'messages' olarak değiştirelim
        print("Yeni koleksiyon devreye alınıyor...")
        await db.messages_new.rename("messages")
        
        print("🎉 MİGRASYON TAMAMLANDI! Veritabanınız inanılmaz derecede küçüldü.")
        print("Artık bu dosyayı silebilir ve botunuzu başlatabilirsiniz.")
        
    except Exception as e:
        print(f"❌ Bir hata oluştu: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
