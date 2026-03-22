"""
Step 08: API Rate Limiting (Section 5 - 패턴 07)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
고정 윈도우 방식과 슬라이딩 윈도우 방식 두 가지 구현.
Lua Script로 원자적 처리.
"""

import time

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis

from app.dependencies import get_redis

router = APIRouter(prefix="/step08", tags=["Step 08: Rate Limiting"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 방식 1: 고정 윈도우 (Fixed Window)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/fixed-window/request")
async def fixed_window_request(
    user_id: int,
    limit: int = 10,
    window: int = 60,
    redis: Redis = Depends(get_redis),
):
    """고정 윈도우 Rate Limiting — INCR + EXPIRE"""
    key = f"ratelimit:fixed:{user_id}:{int(time.time()) // window}"

    current = await redis.incr(key)
    if current == 1:
        # 첫 요청이면 윈도우 TTL 설정
        await redis.expire(key, window)

    ttl = await redis.ttl(key)

    if current > limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "요청 한도 초과",
                "limit": limit,
                "current": current,
                "retry_after": ttl,
            },
        )

    return {
        "method": "fixed_window",
        "allowed": True,
        "current_count": current,
        "limit": limit,
        "remaining": limit - current,
        "window_ttl": ttl,
        "commands": [
            f"INCR {key} → {current}",
            f"EXPIRE {key} {window} (첫 요청시에만)",
        ],
        "설명": f"{window}초 윈도우 내 {current}/{limit} 요청 사용",
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 방식 2: 슬라이딩 윈도우 (Sliding Window) — Lua Script
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local unique_id = ARGV[4]

-- 윈도우 밖의 오래된 요청 제거
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- 현재 윈도우 내 요청 수
local current = redis.call('ZCARD', key)

if current < limit then
    -- 허용: 현재 요청을 Sorted Set에 추가
    redis.call('ZADD', key, now, unique_id)
    redis.call('EXPIRE', key, window)
    return {1, current + 1, limit - current - 1}
else
    -- 거부
    return {0, current, 0}
end
"""


@router.get("/sliding-window/request")
async def sliding_window_request(
    user_id: int,
    limit: int = 10,
    window: int = 60,
    redis: Redis = Depends(get_redis),
):
    """슬라이딩 윈도우 Rate Limiting — Sorted Set + Lua Script"""
    key = f"ratelimit:sliding:{user_id}"
    now = time.time()
    unique_id = f"{now}-{id(now)}"

    result = await redis.eval(
        SLIDING_WINDOW_SCRIPT,
        1,
        key,
        str(limit),
        str(window),
        str(now),
        unique_id,
    )

    allowed, current, remaining = result

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "요청 한도 초과 (슬라이딩 윈도우)",
                "limit": limit,
                "current": current,
                "remaining": 0,
            },
        )

    return {
        "method": "sliding_window",
        "allowed": True,
        "current_count": current,
        "limit": limit,
        "remaining": remaining,
        "설명": "Sorted Set의 score=타임스탬프. 윈도우 밖 요청은 자동 제거. Lua Script로 원자적 처리.",
        "vs_고정윈도우": "경계 시점의 burst 문제를 해결. 더 정확한 Rate Limiting.",
    }


@router.get("/status/{user_id}")
async def rate_limit_status(user_id: int, redis: Redis = Depends(get_redis)):
    """Rate Limit 상태 확인"""
    # 고정 윈도우 현재 키
    window = 60
    fixed_key = f"ratelimit:fixed:{user_id}:{int(time.time()) // window}"
    fixed_count = await redis.get(fixed_key)
    fixed_ttl = await redis.ttl(fixed_key)

    # 슬라이딩 윈도우
    sliding_key = f"ratelimit:sliding:{user_id}"
    now = time.time()
    # 윈도우 내 요청만 카운트
    await redis.zremrangebyscore(sliding_key, 0, now - window)
    sliding_count = await redis.zcard(sliding_key)

    return {
        "user_id": user_id,
        "fixed_window": {
            "current_count": int(fixed_count) if fixed_count else 0,
            "window_ttl": fixed_ttl,
        },
        "sliding_window": {
            "current_count": sliding_count,
        },
    }
