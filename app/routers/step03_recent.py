"""
Step 03: 최근 본 상품 리스트 (Section 5 - 패턴 02)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Redis List로 "최근 본 상품" 구현.
LREM → LPUSH → LTRIM 패턴으로 중복 제거 + 최대 N개 유지.
Pipeline으로 네트워크 왕복 1회로 최적화.
"""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.dependencies import get_redis

router = APIRouter(prefix="/step03", tags=["Step 03: 최근 본 상품"])

MAX_RECENT = 20


@router.post("/{user_id}/view/{product_id}")
async def add_recently_viewed(
    user_id: int,
    product_id: int,
    redis: Redis = Depends(get_redis),
):
    """상품 조회 기록 — LREM + LPUSH + LTRIM (Pipeline)"""
    key = f"recent:{user_id}"

    # Pipeline: 3개 명령을 네트워크 왕복 1회로 전송
    async with redis.pipeline(transaction=True) as pipe:
        pipe.lrem(key, 0, str(product_id))       # 1. 기존 중복 제거
        pipe.lpush(key, str(product_id))           # 2. 맨 앞에 추가
        pipe.ltrim(key, 0, MAX_RECENT - 1)         # 3. 최대 20개 유지
        pipe.expire(key, 60 * 60 * 24 * 30)        # 4. 30일 TTL
        await pipe.execute()

    items = await redis.lrange(key, 0, -1)
    return {
        "commands": [
            f"LREM {key} 0 {product_id}  ← 중복 제거",
            f"LPUSH {key} {product_id}   ← 맨 앞에 추가",
            f"LTRIM {key} 0 {MAX_RECENT - 1}       ← 최대 {MAX_RECENT}개 유지",
        ],
        "pipeline": "네트워크 왕복 1회로 3개 명령 전송",
        "recent_products": items,
        "count": len(items),
    }


@router.get("/{user_id}")
async def get_recently_viewed(
    user_id: int,
    limit: int = 10,
    redis: Redis = Depends(get_redis),
):
    """최근 본 상품 목록 조회"""
    key = f"recent:{user_id}"
    items = await redis.lrange(key, 0, limit - 1)
    total = await redis.llen(key)
    return {
        "command": f"LRANGE {key} 0 {limit - 1}",
        "user_id": user_id,
        "recent_products": items,
        "showing": len(items),
        "total": total,
    }


@router.delete("/{user_id}")
async def clear_recently_viewed(
    user_id: int,
    redis: Redis = Depends(get_redis),
):
    """최근 본 상품 목록 삭제"""
    key = f"recent:{user_id}"
    await redis.delete(key)
    return {"message": "최근 본 상품 목록 삭제 완료"}
