"""
Step 02: Cache-Aside 패턴 (Section 5 - 패턴 01)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DB 조회 결과를 Redis에 캐싱하고, Cache Hit/Miss를
비교하여 성능 차이를 체감한다.
"""

import json
import random
import time

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Product
from app.dependencies import get_db, get_redis

router = APIRouter(prefix="/step02", tags=["Step 02: Cache-Aside"])

CACHE_TTL = 300  # 5분


@router.get("/products/{product_id}")
async def get_product_cached(
    product_id: int,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """Cache-Aside: 캐시 조회 → Miss시 DB 조회 → 캐시 저장"""
    cache_key = f"product:{product_id}"
    start = time.perf_counter()

    # 1. Redis 캐시 조회
    cached = await redis.get(cache_key)
    if cached:
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "source": "redis_cache",
            "elapsed_ms": round(elapsed, 3),
            "data": json.loads(cached),
            "로그": f"Cache HIT! {elapsed:.3f}ms 소요",
        }

    # 2. Cache Miss → DB 조회
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="상품 없음")

    product_data = {
        "id": product.id,
        "name": product.name,
        "price": product.price,
        "stock": product.stock,
        "description": product.description,
    }

    # 3. 캐시에 저장 (TTL + jitter로 Cache Stampede 방지)
    jitter = random.randint(0, 60)
    await redis.set(cache_key, json.dumps(product_data), ex=CACHE_TTL + jitter)

    elapsed = (time.perf_counter() - start) * 1000
    return {
        "source": "database",
        "elapsed_ms": round(elapsed, 3),
        "data": product_data,
        "cache_ttl": CACHE_TTL + jitter,
        "로그": f"Cache MISS → DB 조회 후 캐시 저장. {elapsed:.3f}ms 소요",
    }


@router.get("/products/{product_id}/no-cache")
async def get_product_no_cache(
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    """캐시 없이 DB 직접 조회 (비교용)"""
    start = time.perf_counter()

    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="상품 없음")

    elapsed = (time.perf_counter() - start) * 1000
    return {
        "source": "database_only",
        "elapsed_ms": round(elapsed, 3),
        "data": {
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "stock": product.stock,
        },
        "로그": f"DB 직접 조회. {elapsed:.3f}ms 소요 (캐시 없음)",
    }


@router.put("/products/{product_id}")
async def update_product(
    product_id: int,
    name: str | None = None,
    price: int | None = None,
    redis: Redis = Depends(get_redis),
    db: AsyncSession = Depends(get_db),
):
    """상품 수정 → 캐시 무효화 (갱신이 아닌 삭제!)"""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="상품 없음")

    if name:
        product.name = name
    if price:
        product.price = price
    await db.commit()

    # 캐시 무효화 — "갱신"이 아닌 "삭제"
    cache_key = f"product:{product_id}"
    deleted = await redis.delete(cache_key)

    return {
        "message": "상품 수정 완료",
        "cache_invalidated": bool(deleted),
        "로그": "DB 업데이트 후 캐시 DEL. 다음 조회 시 DB에서 최신 데이터를 가져와 캐시 갱신됨.",
    }


@router.get("/cache-status/{product_id}")
async def cache_status(product_id: int, redis: Redis = Depends(get_redis)):
    """캐시 상태 확인 (TTL, 존재 여부)"""
    cache_key = f"product:{product_id}"
    exists = await redis.exists(cache_key)
    ttl = await redis.ttl(cache_key)
    value = await redis.get(cache_key)

    return {
        "cache_key": cache_key,
        "exists": bool(exists),
        "ttl": ttl,
        "ttl_설명": {-2: "키 없음", -1: "만료 없음(영구)"}.get(ttl, f"{ttl}초 후 만료"),
        "cached_data": json.loads(value) if value else None,
    }
