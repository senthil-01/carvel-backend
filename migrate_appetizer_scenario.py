"""
Migration: rename scenario key "four" to "4 appetizer"
Condition: category=Appetizer, sellByCount=false
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI     = "mongodb://localhost:27017"
DB_NAME       = "cravecall_engine"
RESTAURANT_ID = "rest_001"


async def migrate():
    client = AsyncIOMotorClient(MONGO_URI)
    db     = client[DB_NAME]

    cursor = db["menu_item_rules"].find({
        "restaurantId":   RESTAURANT_ID,
        "category":       "Appetizer",
        "sellByCount":    False,
        "scenarios.four": {"$exists": True}
    })

    count = 0
    async for doc in cursor:
        item_code  = doc["itemCode"]
        four_value = doc["scenarios"]["four"]

        # Step 1 — add "4 appetizer" key
        await db["menu_item_rules"].update_one(
            {"_id": doc["_id"]},
            {"$set": {"scenarios.4 appetizer": four_value}}
        )

        # Step 2 — remove "four" key
        await db["menu_item_rules"].update_one(
            {"_id": doc["_id"]},
            {"$unset": {"scenarios.four": ""}}
        )

        print(f"✅ Updated {item_code} — 'four' → '4 appetizer'")
        count += 1

    print(f"\nDone — {count} items updated.")
    client.close()


if __name__ == "__main__":
    asyncio.run(migrate())