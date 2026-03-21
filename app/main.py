"""
Redis 마스터 로드맵 — 실습 환경
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FastAPI + Redis + SQLite

Swagger UI: http://localhost:8000/docs
Redis Insight: http://localhost:5540
"""

import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.database import init_db
from app.routers import (
    step01_basics,
    step02_cache,
    step03_recent,
    step04_session,
    step05_counter,
    step06_verification,
    step07_lock,
    step08_ratelimit,
    step09_ranking,
    step10_pubsub,
    step11_stream,
    step12_comparison,
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──
    pool = aioredis.ConnectionPool.from_url(
        REDIS_URL,
        max_connections=20,
        decode_responses=True,
    )
    app.state.redis = aioredis.Redis(connection_pool=pool)

    # Redis 연결 확인
    pong = await app.state.redis.ping()
    print(f"  Redis 연결: {'OK' if pong else 'FAIL'} ({REDIS_URL})")

    # SQLite 초기화
    await init_db()
    print("  SQLite 초기화 완료")

    print("  Swagger UI → http://localhost:8000/docs")
    print("  Redis Insight → http://localhost:5540")

    yield

    # ── shutdown ──
    await app.state.redis.aclose()


app = FastAPI(
    title="Redis 마스터 로드맵 실습",
    description="""
## 12 Step 실습 환경

| Step | 주제 | Section |
|------|------|---------|
| 01 | 기본 자료형 (String, List, Set, Hash, Sorted Set) | 3 |
| 02 | Cache-Aside 패턴 | 5 |
| 03 | 최근 본 상품 (List) | 5 |
| 04 | 분산 세션 (Hash + TTL) | 5 |
| 05 | 조회수/좋아요 (INCR + Set) | 5 |
| 06 | 임시 인증번호 (TTL) | 5 |
| 07 | 분산 락 (SET NX EX + Lua) | 5 |
| 08 | Rate Limiting (고정/슬라이딩 윈도우) | 5 |
| 09 | 실시간 랭킹 (Sorted Set) | 5 |
| 10 | Pub/Sub 실시간 알림 | 4, 5 |
| 11 | Stream + Consumer Group | 4 |
| 12 | Redis vs SQLite 성능 비교 | 종합 |
""",
    version="1.0.0",
    lifespan=lifespan,
)

# ── 라우터 등록 ──
app.include_router(step01_basics.router)
app.include_router(step02_cache.router)
app.include_router(step03_recent.router)
app.include_router(step04_session.router)
app.include_router(step05_counter.router)
app.include_router(step06_verification.router)
app.include_router(step07_lock.router)
app.include_router(step08_ratelimit.router)
app.include_router(step09_ranking.router)
app.include_router(step10_pubsub.router)
app.include_router(step11_stream.router)
app.include_router(step12_comparison.router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    r = app.state.redis
    pong = await r.ping()
    info = await r.info("server")
    return {
        "status": "ok",
        "redis": {
            "connected": pong,
            "version": info.get("redis_version"),
        },
    }
