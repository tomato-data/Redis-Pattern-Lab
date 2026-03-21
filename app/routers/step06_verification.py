"""
Step 06: TTL 기반 임시 인증번호 (Section 5 - 패턴 05)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Redis SET + EX로 3분 후 자동 만료되는 인증번호를 구현.
TTL로 재발송 쿨다운 시간도 계산.
"""

import random
import string

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis

from app.dependencies import get_redis

router = APIRouter(prefix="/step06", tags=["Step 06: 인증번호"])

CODE_TTL = 180       # 인증번호 유효 시간: 3분
RESEND_COOLDOWN = 30  # 재발송 대기 시간: 30초


def generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


@router.post("/send")
async def send_verification(phone: str, redis: Redis = Depends(get_redis)):
    """인증번호 발급 — SET + EX (자동 만료)"""
    key = f"verification:{phone}"

    # 1. 재발송 방지: TTL 확인
    ttl = await redis.ttl(key)
    if ttl > CODE_TTL - RESEND_COOLDOWN:
        remaining = ttl - (CODE_TTL - RESEND_COOLDOWN)
        raise HTTPException(
            status_code=429,
            detail=f"{remaining}초 후에 재발송할 수 있습니다",
        )

    # 2. 인증번호 생성 및 저장
    code = generate_code()
    await redis.set(key, code, ex=CODE_TTL)

    return {
        "message": "인증번호가 발송되었습니다",
        "phone": phone,
        "code_for_testing": code,  # 실제 서비스에서는 절대 응답에 포함하면 안 됨!
        "expires_in": CODE_TTL,
        "commands": [
            f"SET {key} {code} EX {CODE_TTL}",
        ],
        "로그": f"인증번호 {code} 생성. {CODE_TTL}초(3분) 후 자동 만료. 별도 배치 불필요.",
    }


@router.post("/verify")
async def verify_code(phone: str, code: str, redis: Redis = Depends(get_redis)):
    """인증번호 검증 → 성공 시 즉시 삭제 (1회용)"""
    key = f"verification:{phone}"
    stored_code = await redis.get(key)

    if stored_code is None:
        raise HTTPException(status_code=400, detail="인증번호가 만료되었거나 발급되지 않았습니다")

    if stored_code != code:
        # 시도 횟수 제한 (실무에서는 필수)
        attempt_key = f"verification:attempts:{phone}"
        attempts = await redis.incr(attempt_key)
        await redis.expire(attempt_key, CODE_TTL)

        if attempts >= 5:
            await redis.delete(key)
            await redis.delete(attempt_key)
            raise HTTPException(status_code=429, detail="시도 횟수 초과. 인증번호를 다시 발급받으세요.")

        raise HTTPException(
            status_code=400,
            detail=f"인증번호 불일치 (시도 {attempts}/5)",
        )

    # 인증 성공 → 즉시 삭제
    await redis.delete(key)
    await redis.delete(f"verification:attempts:{phone}")

    return {
        "message": "인증 성공",
        "verified": True,
        "로그": f"코드 일치 → DEL {key} (1회용이므로 즉시 삭제)",
    }


@router.get("/status/{phone}")
async def verification_status(phone: str, redis: Redis = Depends(get_redis)):
    """인증번호 상태 확인"""
    key = f"verification:{phone}"
    exists = await redis.exists(key)
    ttl = await redis.ttl(key)
    attempts_key = f"verification:attempts:{phone}"
    attempts = await redis.get(attempts_key)

    resend_available = ttl <= (CODE_TTL - RESEND_COOLDOWN) if ttl > 0 else True

    return {
        "phone": phone,
        "code_exists": bool(exists),
        "ttl": ttl,
        "ttl_설명": f"{ttl}초 후 만료" if ttl > 0 else "인증번호 없음",
        "attempts": int(attempts) if attempts else 0,
        "resend_available": resend_available,
    }
