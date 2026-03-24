from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "cravecall_engine"
    RESTAURANT_ID: str = "rest_001"

    class Config:
        env_file = ".env"


settings = Settings()


class Database:
    client: AsyncIOMotorClient = None
    db = None


db_instance = Database()


async def connect_db():
    db_instance.client = AsyncIOMotorClient(settings.MONGODB_URL)
    db_instance.db = db_instance.client[settings.DATABASE_NAME]
    print(f"Connected to MongoDB: {settings.DATABASE_NAME}")


async def close_db():
    if db_instance.client:
        db_instance.client.close()
        print("MongoDB connection closed")


def get_db():
    return db_instance.db
