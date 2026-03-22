"""
Step 07: 분산 락 (Section 5 - 패턴 06)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SET NX EX로 원자적 락 획득, Lua Script로 owner 확인 후 해제.
쿠폰 선착순 발급 시나리오로 동시성 제어를 체험.
"""

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis

from app.dependencies import get_redis

router = APIRouter(prefix="/step07", tags=["Step 07: 분산 락"])

LOCK_TTL = 30

# Lua Script: owner 확인 후 삭제 (원자적)
RELEASE_LOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


async def acquire_lock(redis: Redis, resource: str, owner: str, ttl: int = LOCK_TTL) -> bool:
    result = await redis.set(f"lock:{resource}", owner, nx=True, ex=ttl)
    return result is not None


async def release_lock(redis: Redis, resource: str, owner: str) -> bool:
    result = await redis.eval(RELEASE_LOCK_SCRIPT, 1, f"lock:{resource}", owner)
    return result == 1


@router.post("/coupon/setup/{coupon_id}")
async def setup_coupon(coupon_id: int, stock: int = 100, redis: Redis = Depends(get_redis)):
    """쿠폰 재고 초기화"""
    await redis.set(f"coupon:{coupon_id}:stock", stock)
    return {"coupon_id": coupon_id, "stock": stock, "message": "쿠폰 재고 설정 완료"}


@router.post("/coupon/{coupon_id}/issue")
async def issue_coupon(coupon_id: int, user_id: int, redis: Redis = Depends(get_redis)):
    """쿠폰 발급 (분산 락으로 동시성 제어)"""
    resource = f"coupon:{coupon_id}"
    owner = str(uuid.uuid4())

    # 1. 락 획득 시도
    locked = await acquire_lock(redis, resource, owner)
    if not locked:
        raise HTTPException(
            status_code=409,
            detail="다른 사용자가 쿠폰을 발급 중입니다. 잠시 후 다시 시도해주세요.",
        )

    try:
        # 2. 비즈니스 로직 (락 내부에서 실행)
        stock_key = f"coupon:{coupon_id}:stock"
        stock = await redis.get(stock_key)

        if stock is None:
            raise HTTPException(status_code=404, detail="쿠폰이 존재하지 않습니다")
        if int(stock) <= 0:
            raise HTTPException(status_code=410, detail="쿠폰이 모두 소진되었습니다")

        # 재고 차감
        remaining = await redis.decr(stock_key)

        # 발급 기록
        await redis.sadd(f"coupon:{coupon_id}:issued_users", str(user_id))

        return {
            "message": f"쿠폰 발급 성공! (user:{user_id})",
            "remaining_stock": remaining,
            "lock_owner": owner,
            "commands": [
                f"SET lock:{resource} {owner} NX EX {LOCK_TTL} ← 락 획득",
                f"GET {stock_key} ← 재고 확인",
                f"DECR {stock_key} ← 재고 차감",
                f"DEL lock:{resource} (Lua Script로 owner 확인 후) ← 락 해제",
            ],
        }
    finally:
        # 3. 락 해제 (성공/실패 무관)
        await release_lock(redis, resource, owner)


@router.post("/coupon/{coupon_id}/issue-unsafe")
async def issue_coupon_unsafe(coupon_id: int, user_id: int, redis: Redis = Depends(get_redis)):
    """쿠폰 발급 (락 없음 — 동시성 문제 발생 가능!)"""
    stock_key = f"coupon:{coupon_id}:stock"
    stock = await redis.get(stock_key)

    if stock is None:
        raise HTTPException(status_code=404, detail="쿠폰이 존재하지 않습니다")

    # 의도적으로 잠깐 지연 (동시성 문제 재현용)
    await asyncio.sleep(0.1)

    if int(stock) <= 0:
        raise HTTPException(status_code=410, detail="쿠폰이 모두 소진되었습니다")

    remaining = await redis.decr(stock_key)

    return {
        "message": f"쿠폰 발급 (락 없음) — user:{user_id}",
        "remaining_stock": remaining,
        "경고": "락 없이 처리되어 동시 요청 시 초과 발급 가능!",
    }


@router.get("/coupon/{coupon_id}/status")
async def coupon_status(coupon_id: int, redis: Redis = Depends(get_redis)):
    """쿠폰 상태 확인"""
    stock = await redis.get(f"coupon:{coupon_id}:stock")
    issued = await redis.smembers(f"coupon:{coupon_id}:issued_users")
    lock_exists = await redis.exists(f"lock:coupon:{coupon_id}")
    lock_ttl = await redis.ttl(f"lock:coupon:{coupon_id}")

    return {
        "coupon_id": coupon_id,
        "remaining_stock": int(stock) if stock else "미설정",
        "issued_users": list(issued),
        "issued_count": len(issued),
        "lock_active": bool(lock_exists),
        "lock_ttl": lock_ttl,
    }
