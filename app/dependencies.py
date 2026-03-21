"""Redis & DB 의존성 주입"""

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
