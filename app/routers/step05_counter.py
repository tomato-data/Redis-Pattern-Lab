"""
Step 05: 조회수/좋아요 카운팅 (Section 5 - 패턴 04)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Redis INCR의 원자성으로 동시성 문제를 해결하고,
Set으로 좋아요 중복을 방지한다.
SQLite UPDATE와 비교하여 성능 차이를 체감.
"""

import time

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Post
from app.dependencies import get_db, get_redis

router = APIRouter(prefix="/step05", tags=["Step 05: 카운팅"])


@router.post("/redis/{post_id}/view")
async def increment_view_redis(post_id: int, redis: Redis = Depends(get_redis)):
    """Redis INCR — 원자적 조회수 증가"""
    start = time.perf_counter()
    key = f"post:{post_id}:views"
    views = await redis.incr(key)
    elapsed = (time.perf_counter() - start) * 1000
    return {
        "method": "redis_incr",
        "post_id": post_id,
        "views": views,
        "elapsed_ms": round(elapsed, 3),
        "원자성": "INCR은 읽기-증가-쓰기가 하나의 명령. Lost Update 불가능.",
    }


@router.post("/sqlite/{post_id}/view")
async def increment_view_sqlite(post_id: int, db: AsyncSession = Depends(get_db)):
    """SQLite UPDATE — DB 직접 카운팅 (비교용)"""
    start = time.perf_counter()
    await db.execute(update(Post).where(Post.id == post_id).values(views=Post.views + 1))
    await db.commit()

    result = await db.execute(select(Post.views).where(Post.id == post_id))
    views = result.scalar()
    elapsed = (time.perf_counter() - start) * 1000
    return {
        "method": "sqlite_update",
        "post_id": post_id,
        "views": views,
        "elapsed_ms": round(elapsed, 3),
        "주의": "동시 요청 시 행 잠금(Row Lock) 경합 발생 가능",
    }


@router.post("/redis/{post_id}/like")
async def toggle_like(post_id: int, user_id: int, redis: Redis = Depends(get_redis)):
    """좋아요 토글 — Set(중복 방지) + INCR(카운팅)"""
    like_set_key = f"post:{post_id}:liked_users"
    like_count_key = f"post:{post_id}:likes"

    already_liked = await redis.sismember(like_set_key, str(user_id))

    if already_liked:
        # 좋아요 취소
        async with redis.pipeline(transaction=True) as pipe:
            pipe.srem(like_set_key, str(user_id))
            pipe.decr(like_count_key)
            await pipe.execute()
        action = "unliked"
    else:
        # 좋아요 추가
        async with redis.pipeline(transaction=True) as pipe:
            pipe.sadd(like_set_key, str(user_id))
            pipe.incr(like_count_key)
            await pipe.execute()
        action = "liked"

    likes = await redis.get(like_count_key)
    liked_users = await redis.smembers(like_set_key)

    return {
        "action": action,
        "post_id": post_id,
        "total_likes": int(likes) if likes else 0,
        "liked_users": list(liked_users),
        "로그": f"SISMEMBER로 중복 확인 O(1) → {'SREM+DECR' if action == 'unliked' else 'SADD+INCR'} (Pipeline)",
    }


@router.get("/{post_id}/stats")
async def get_stats(
    post_id: int,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """Redis 카운터 vs SQLite 카운터 비교"""
    redis_views = await redis.get(f"post:{post_id}:views")
    redis_likes = await redis.get(f"post:{post_id}:likes")

    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()

    return {
        "post_id": post_id,
        "redis": {
            "views": int(redis_views) if redis_views else 0,
            "likes": int(redis_likes) if redis_likes else 0,
        },
        "sqlite": {
            "views": post.views if post else 0,
            "likes": post.likes if post else 0,
        },
        "설명": "Redis 카운터는 실시간, SQLite는 동기화 전까지 차이 발생 가능",
    }
