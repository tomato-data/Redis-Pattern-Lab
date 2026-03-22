"""
Step 09: 실시간 랭킹 시스템 (Section 5 - 패턴 08)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Redis Sorted Set으로 O(log N) 실시간 리더보드 구현.
SQLite ORDER BY와 성능 비교.
"""

import time

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import User
from app.dependencies import get_db, get_redis

router = APIRouter(prefix="/step09", tags=["Step 09: 랭킹"])


@router.post("/setup")
async def setup_leaderboard(redis: Redis = Depends(get_redis), db: AsyncSession = Depends(get_db)):
    """리더보드 초기 데이터 설정 (DB에서 Redis Sorted Set으로 로드)"""
    result = await db.execute(select(User))
    users = result.scalars().all()

    members = {u.name: u.score for u in users}
    if members:
        await redis.zadd("leaderboard", members)

    ranking = await redis.zrevrange("leaderboard", 0, -1, withscores=True)
    return {
        "message": "리더보드 초기화 완료",
        "loaded_users": len(members),
        "ranking": [{"rank": i + 1, "name": name, "score": int(score)} for i, (name, score) in enumerate(ranking)],
    }


@router.post("/score")
async def update_score(name: str, points: int, redis: Redis = Depends(get_redis)):
    """점수 업데이트 — ZINCRBY (원자적)"""
    start = time.perf_counter()
    new_score = await redis.zincrby("leaderboard", points, name)
    rank = await redis.zrevrank("leaderboard", name)
    elapsed = (time.perf_counter() - start) * 1000

    return {
        "command": f"ZINCRBY leaderboard {points} {name}",
        "player": name,
        "new_score": int(new_score),
        "rank": rank + 1 if rank is not None else None,
        "elapsed_ms": round(elapsed, 3),
        "설명": "O(log N) — 점수 변경과 동시에 자동 재정렬",
    }


@router.get("/top")
async def get_top_redis(limit: int = 10, redis: Redis = Depends(get_redis)):
    """Redis 리더보드 Top N (Sorted Set)"""
    start = time.perf_counter()
    ranking = await redis.zrevrange("leaderboard", 0, limit - 1, withscores=True)
    elapsed = (time.perf_counter() - start) * 1000

    return {
        "method": "redis_sorted_set",
        "command": f"ZREVRANGE leaderboard 0 {limit - 1} WITHSCORES",
        "elapsed_ms": round(elapsed, 3),
        "complexity": "O(log N + M) where M = limit",
        "ranking": [
            {"rank": i + 1, "name": name, "score": int(score)}
            for i, (name, score) in enumerate(ranking)
        ],
    }


@router.get("/top-sqlite")
async def get_top_sqlite(limit: int = 10, db: AsyncSession = Depends(get_db)):
    """SQLite 리더보드 Top N (ORDER BY — 비교용)"""
    start = time.perf_counter()
    result = await db.execute(select(User).order_by(User.score.desc()).limit(limit))
    users = result.scalars().all()
    elapsed = (time.perf_counter() - start) * 1000

    return {
        "method": "sqlite_order_by",
        "elapsed_ms": round(elapsed, 3),
        "complexity": "O(N log N) — 매 조회마다 정렬",
        "ranking": [
            {"rank": i + 1, "name": u.name, "score": u.score}
            for i, u in enumerate(users)
        ],
        "vs_redis": "데이터가 많아질수록 Redis Sorted Set의 O(log N) 이점이 커짐",
    }


@router.get("/rank/{name}")
async def get_player_rank(name: str, redis: Redis = Depends(get_redis)):
    """특정 플레이어 순위/점수 조회"""
    score = await redis.zscore("leaderboard", name)
    rank = await redis.zrevrank("leaderboard", name)
    total = await redis.zcard("leaderboard")

    if score is None:
        return {"error": f"'{name}' 없음"}

    return {
        "player": name,
        "score": int(score),
        "rank": rank + 1,
        "total_players": total,
        "commands": [
            f"ZSCORE leaderboard {name} → {int(score)}",
            f"ZREVRANK leaderboard {name} → {rank}",
            f"ZCARD leaderboard → {total}",
        ],
    }


@router.get("/range-by-score")
async def range_by_score(min_score: int = 0, max_score: int = 10000, redis: Redis = Depends(get_redis)):
    """점수 범위로 조회 — ZRANGEBYSCORE"""
    members = await redis.zrangebyscore("leaderboard", min_score, max_score, withscores=True)
    return {
        "command": f"ZRANGEBYSCORE leaderboard {min_score} {max_score} WITHSCORES",
        "count": len(members),
        "members": [{"name": name, "score": int(score)} for name, score in members],
    }
