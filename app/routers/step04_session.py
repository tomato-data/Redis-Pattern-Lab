"""
Step 04: 분산 세션 공유 (Section 5 - 패턴 03)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Redis Hash로 세션을 중앙 관리하여 다중 서버에서
동일한 세션에 접근 가능하게 한다.
Sliding Expiration으로 활동 중 세션 자동 연장.
"""

import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from redis.asyncio import Redis

from app.dependencies import get_redis

router = APIRouter(prefix="/step04", tags=["Step 04: 분산 세션"])

SESSION_TTL = 1800  # 30분

# 가상 사용자 DB
USERS_DB = {
    "admin@test.com": {"id": 42, "password": "password123", "role": "admin", "name": "Admin"},
    "user@test.com": {"id": 99, "password": "password123", "role": "user", "name": "User"},
}


@router.post("/login")
async def login(
    email: str,
    password: str,
    response: Response,
    redis: Redis = Depends(get_redis),
):
    """로그인 → 세션 생성 (Redis Hash + TTL)"""
    user = USERS_DB.get(email)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="이메일 또는 비밀번호가 올바르지 않습니다")

    session_id = str(uuid.uuid4())
    session_key = f"session:{session_id}"

    # Redis Hash에 세션 데이터 저장
    await redis.hset(session_key, mapping={
        "user_id": str(user["id"]),
        "email": email,
        "role": user["role"],
        "name": user["name"],
    })
    await redis.expire(session_key, SESSION_TTL)

    # 쿠키에 세션 ID 저장
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=SESSION_TTL)

    return {
        "message": "로그인 성공",
        "session_id": session_id,
        "commands": [
            f"HSET {session_key} user_id {user['id']} email {email} role {user['role']}",
            f"EXPIRE {session_key} {SESSION_TTL}",
        ],
        "로그": f"세션 생성됨. TTL={SESSION_TTL}초 (30분). 쿠키에 session_id 저장.",
    }


@router.get("/me")
async def get_me(
    session_id: str | None = Cookie(default=None),
    redis: Redis = Depends(get_redis),
):
    """현재 세션 정보 조회 + Sliding Expiration"""
    if not session_id:
        raise HTTPException(status_code=401, detail="세션이 없습니다. 로그인해주세요.")

    session_key = f"session:{session_id}"
    session_data = await redis.hgetall(session_key)

    if not session_data:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다.")

    # Sliding Expiration: 매 요청마다 TTL 리셋
    await redis.expire(session_key, SESSION_TTL)
    ttl = await redis.ttl(session_key)

    return {
        "user": session_data,
        "session_ttl_remaining": ttl,
        "로그": f"HGETALL {session_key} → 세션 조회. EXPIRE로 TTL 리셋 (Sliding Expiration)",
    }


@router.get("/session-info/{session_id}")
async def session_info(session_id: str, redis: Redis = Depends(get_redis)):
    """세션 상세 정보 직접 조회 (디버깅용)"""
    session_key = f"session:{session_id}"
    data = await redis.hgetall(session_key)
    ttl = await redis.ttl(session_key)
    key_type = await redis.type(session_key)
    return {
        "session_key": session_key,
        "type": key_type,
        "data": data if data else "세션 없음 또는 만료됨",
        "ttl": ttl,
    }


@router.post("/logout")
async def logout(
    response: Response,
    session_id: str | None = Cookie(default=None),
    redis: Redis = Depends(get_redis),
):
    """로그아웃 → 세션 삭제"""
    if session_id:
        session_key = f"session:{session_id}"
        await redis.delete(session_key)

    response.delete_cookie("session_id")
    return {"message": "로그아웃 완료", "로그": "DEL session:{id} → 세션 즉시 삭제"}
