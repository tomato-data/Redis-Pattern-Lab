"""
Step 12: Redis vs SQLite 성능 비교 (종합)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
동일 작업을 Redis와 SQLite로 수행하여
응답 시간, 처리량 차이를 직접 측정.
"""

import asyncio
import json
import time

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Post, Product, User
from app.dependencies import get_db, get_redis

router = APIRouter(prefix="/step12", tags=["Step 12: Redis vs SQLite 비교"])


@router.get("/read-single")
async def compare_read_single(
    product_id: int = 1,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """단일 읽기 성능 비교: Redis GET vs SQLite SELECT"""
    # Redis
    cache_key = f"bench:product:{product_id}"
    # 먼저 데이터를 넣어둠
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product:
        await redis.set(cache_key, json.dumps({
            "id": product.id, "name": product.name, "price": product.price,
        }))

    # Redis 읽기
    start = time.perf_counter()
    redis_data = await redis.get(cache_key)
    redis_elapsed = (time.perf_counter() - start) * 1000

    # SQLite 읽기
    start = time.perf_counter()
    result = await db.execute(select(Product).where(Product.id == product_id))
    _ = result.scalar_one_or_none()
    sqlite_elapsed = (time.perf_counter() - start) * 1000

    return {
        "operation": "단일 레코드 읽기",
        "redis": {"elapsed_ms": round(redis_elapsed, 3), "method": "GET"},
        "sqlite": {"elapsed_ms": round(sqlite_elapsed, 3), "method": "SELECT ... WHERE id = ?"},
        "speedup": f"Redis가 {sqlite_elapsed / redis_elapsed:.1f}배 빠름" if redis_elapsed > 0 else "측정 불가",
    }


@router.get("/read-batch")
async def compare_read_batch(
    iterations: int = 100,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """반복 읽기 성능 비교: N회 반복 조회"""
    # 준비
    await redis.set("bench:key", "benchmark_value")

    # Redis N회 읽기
    start = time.perf_counter()
    for _ in range(iterations):
        await redis.get("bench:key")
    redis_elapsed = (time.perf_counter() - start) * 1000

    # SQLite N회 읽기
    start = time.perf_counter()
    for _ in range(iterations):
        await db.execute(select(Product).where(Product.id == 1))
    sqlite_elapsed = (time.perf_counter() - start) * 1000

    return {
        "operation": f"{iterations}회 반복 읽기",
        "redis": {
            "total_ms": round(redis_elapsed, 3),
            "avg_ms": round(redis_elapsed / iterations, 3),
        },
        "sqlite": {
            "total_ms": round(sqlite_elapsed, 3),
            "avg_ms": round(sqlite_elapsed / iterations, 3),
        },
        "speedup": f"Redis가 {sqlite_elapsed / redis_elapsed:.1f}배 빠름" if redis_elapsed > 0 else "N/A",
    }


@router.get("/write-counter")
async def compare_write_counter(
    iterations: int = 100,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """카운터 증가 성능 비교: INCR vs UPDATE SET col = col + 1"""
    counter_key = "bench:counter"
    await redis.set(counter_key, 0)

    # Redis INCR
    start = time.perf_counter()
    for _ in range(iterations):
        await redis.incr(counter_key)
    redis_elapsed = (time.perf_counter() - start) * 1000

    # SQLite UPDATE
    start = time.perf_counter()
    for _ in range(iterations):
        await db.execute(update(Post).where(Post.id == 1).values(views=Post.views + 1))
        await db.commit()
    sqlite_elapsed = (time.perf_counter() - start) * 1000

    # 정리
    await redis.delete(counter_key)

    return {
        "operation": f"카운터 {iterations}회 증가",
        "redis": {
            "total_ms": round(redis_elapsed, 3),
            "avg_ms": round(redis_elapsed / iterations, 3),
            "method": "INCR (원자적, 락 불필요)",
        },
        "sqlite": {
            "total_ms": round(sqlite_elapsed, 3),
            "avg_ms": round(sqlite_elapsed / iterations, 3),
            "method": "UPDATE SET col = col + 1 (행 잠금 발생)",
        },
        "speedup": f"Redis가 {sqlite_elapsed / redis_elapsed:.1f}배 빠름" if redis_elapsed > 0 else "N/A",
    }


@router.get("/pipeline-vs-individual")
async def compare_pipeline(
    count: int = 100,
    redis: Redis = Depends(get_redis),
):
    """Redis Pipeline vs 개별 명령어 성능 비교"""
    # 개별 명령어
    start = time.perf_counter()
    for i in range(count):
        await redis.set(f"bench:individual:{i}", f"value-{i}")
    individual_elapsed = (time.perf_counter() - start) * 1000

    # Pipeline
    start = time.perf_counter()
    async with redis.pipeline(transaction=False) as pipe:
        for i in range(count):
            pipe.set(f"bench:pipeline:{i}", f"value-{i}")
        await pipe.execute()
    pipeline_elapsed = (time.perf_counter() - start) * 1000

    # 정리
    keys = [f"bench:individual:{i}" for i in range(count)] + [f"bench:pipeline:{i}" for i in range(count)]
    await redis.delete(*keys)

    return {
        "operation": f"SET {count}회",
        "individual": {
            "total_ms": round(individual_elapsed, 3),
            "avg_ms": round(individual_elapsed / count, 3),
            "network_roundtrips": count,
        },
        "pipeline": {
            "total_ms": round(pipeline_elapsed, 3),
            "avg_ms": round(pipeline_elapsed / count, 3),
            "network_roundtrips": 1,
        },
        "speedup": f"Pipeline이 {individual_elapsed / pipeline_elapsed:.1f}배 빠름" if pipeline_elapsed > 0 else "N/A",
        "설명": f"Pipeline은 {count}개 명령을 네트워크 왕복 1회로 전송. 개별은 {count}회 왕복.",
    }


@router.get("/ranking")
async def compare_ranking(
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """랭킹 조회 비교: ZREVRANGE vs ORDER BY"""
    # Redis Sorted Set에 데이터 준비
    result = await db.execute(select(User))
    users = result.scalars().all()
    members = {u.name: u.score for u in users}
    if members:
        await redis.zadd("bench:ranking", members)

    # Redis
    start = time.perf_counter()
    redis_result = await redis.zrevrange("bench:ranking", 0, 9, withscores=True)
    redis_elapsed = (time.perf_counter() - start) * 1000

    # SQLite
    start = time.perf_counter()
    db_result = await db.execute(select(User).order_by(User.score.desc()).limit(10))
    _ = db_result.scalars().all()
    sqlite_elapsed = (time.perf_counter() - start) * 1000

    await redis.delete("bench:ranking")

    return {
        "operation": "Top 10 랭킹 조회",
        "redis": {
            "elapsed_ms": round(redis_elapsed, 3),
            "method": "ZREVRANGE (O(log N + M), Skip List)",
        },
        "sqlite": {
            "elapsed_ms": round(sqlite_elapsed, 3),
            "method": "SELECT ... ORDER BY score DESC LIMIT 10",
        },
        "설명": "소규모 데이터에서는 차이 미미. 수십만 건 이상에서 Redis Sorted Set의 O(log N) 이점이 극대화.",
    }
