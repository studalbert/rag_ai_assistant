from redis.asyncio import Redis

from app.core.config import settings

# decode_responses=True — получаем строки, а не bytes, из всех операций get/set
redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
