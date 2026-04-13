
# Section 5: FastAPI 기반 Redis 실무 패턴 구현

> 이 섹션은 강의에서 다루는 9가지 Redis 실무 패턴을 FastAPI와 async redis-py로 구현한다. 각 패턴은 문제 상황 → 해결 전략 → 흐름도 → 코드 예시 → 주의사항 순으로 정리하며, 실제 서비스에서 마주치는 시나리오를 중심으로 설명한다.

---

## 24. FastAPI 개발 환경 준비

### 가상 환경 생성 및 패키지 설치

```bash
# 가상 환경 생성
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 핵심 패키지 설치
pip install fastapi uvicorn redis
```

- `fastapi` — 비동기 웹 프레임워크
- `uvicorn` — ASGI 서버
- `redis` — redis-py (4.x 이상에서 async 지원 내장)

### 프로젝트 구조

```
redis-patterns/
├── main.py              # FastAPI 앱 진입점, lifespan, Redis 연결
├── routers/
│   ├── cache.py         # 패턴 01: Cache-Aside
│   ├── recent.py        # 패턴 02: 최근 본 상품
│   ├── session.py       # 패턴 03: 분산 세션
│   ├── counter.py       # 패턴 04: 카운팅
│   ├── verification.py  # 패턴 05: 임시 인증번호
│   ├── lock.py          # 패턴 06: 분산 락
│   ├── ratelimit.py     # 패턴 07: Rate Limiting
│   ├── ranking.py       # 패턴 08: 랭킹
│   └── notification.py  # 패턴 09: 실시간 알림
├── dependencies.py      # Redis 의존성 주입
└── requirements.txt
```

### redis-py의 async 사용법

redis-py 4.x부터 `redis.asyncio` 모듈을 통해 비동기 클라이언트를 직접 제공한다. 별도의 `aioredis` 패키지 설치가 필요 없다.

```python
import redis.asyncio as aioredis

# 비동기 Redis 클라이언트 생성
client = aioredis.from_url("redis://localhost:6379", decode_responses=True)

# 사용
await client.set("key", "value")
value = await client.get("key")
```

`decode_responses=True`를 설정하면 반환값이 `bytes`가 아닌 `str`로 디코딩된다. 문자열 기반 작업이 대부분이므로 기본으로 켜는 것을 권장한다.

### 서버 실행

```bash
uvicorn main:app --reload --port 8000
```

---

## 25. FastAPI와 Redis 연동 기초

### 문제 상황

매 요청마다 Redis 연결을 새로 생성하면 연결 수립 오버헤드가 누적되고, 동시 요청이 많아지면 Redis 서버의 최대 연결 수를 초과할 수 있다.

### 해결 전략 — lifespan 이벤트 + Connection Pool

FastAPI의 `lifespan` 이벤트에서 애플리케이션 시작 시 Connection Pool을 생성하고, 종료 시 정리한다. `app.state`에 클라이언트를 저장하여 모든 엔드포인트에서 재사용한다.

```
┌─────────────────────────────────────────────────────┐
│                   애플리케이션 생명주기               │
│                                                     │
│   startup                                           │
│   ├── ConnectionPool 생성 (max_connections=20)       │
│   ├── Redis 클라이언트 생성                          │
│   └── app.state.redis에 저장                        │
│                                                     │
│   running                                           │
│   ├── 요청 A ──→ app.state.redis (풀에서 연결 대여)  │
│   ├── 요청 B ──→ app.state.redis (풀에서 연결 대여)  │
│   └── 요청 C ──→ app.state.redis (풀에서 연결 대여)  │
│                                                     │
│   shutdown                                          │
│   └── Redis 연결 풀 정리 (aclose)                    │
└─────────────────────────────────────────────────────┘
```

### 코드 예시: main.py

```python
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 시 Redis 연결 관리"""
    # startup: Connection Pool과 함께 Redis 클라이언트 생성
    pool = aioredis.ConnectionPool.from_url(
        "redis://localhost:6379",
        max_connections=20,
        decode_responses=True,
    )
    app.state.redis = aioredis.Redis(connection_pool=pool)

    yield  # 애플리케이션 실행 중

    # shutdown: 연결 풀 정리
    await app.state.redis.aclose()

app = FastAPI(lifespan=lifespan)


def get_redis(request: Request) -> aioredis.Redis:
    """의존성 주입용 헬퍼"""
    return request.app.state.redis


@app.get("/set/{key}/{value}")
async def set_value(request: Request, key: str, value: str):
    redis = get_redis(request)
    await redis.set(key, value)
    return {"message": f"SET {key} = {value}"}


@app.get("/get/{key}")
async def get_value(request: Request, key: str):
    redis = get_redis(request)
    value = await redis.get(key)
    if value is None:
        return {"message": "Key not found"}
    return {"key": key, "value": value}
```

### Connection Pool 설정 파라미터

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `max_connections` | 무제한 | 풀에서 유지할 최대 연결 수 |
| `socket_timeout` | None | 소켓 읽기/쓰기 타임아웃 (초) |
| `socket_connect_timeout` | None | 소켓 연결 타임아웃 (초) |
| `retry_on_timeout` | False | 타임아웃 시 자동 재시도 |
| `health_check_interval` | 0 | 연결 상태 확인 주기 (초) |

> **운영 팁**: `max_connections`는 서버의 동시 요청 수를 기준으로 설정한다. FastAPI 워커 수 x 예상 동시 Redis 호출 수로 산정하되, Redis 서버의 `maxclients` 설정(기본 10,000)을 초과하지 않도록 주의한다.

### 의존성 주입 패턴 (Depends 활용)

라우터에서 `Depends`로 Redis 클라이언트를 주입하면 코드가 깔끔해진다:

```python
from fastapi import Depends

async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis

@app.get("/example")
async def example(redis: aioredis.Redis = Depends(get_redis)):
    await redis.set("hello", "world")
    return {"result": await redis.get("hello")}
```

### 주의사항

- `on_event("startup")` / `on_event("shutdown")` 데코레이터는 **deprecated**다. 반드시 `lifespan` 패턴을 사용할 것.
- `decode_responses=True`를 설정하지 않으면 모든 반환값이 `bytes` 타입이므로 일일이 `.decode()` 호출이 필요하다.
- Connection Pool 없이 `aioredis.from_url()`만 사용해도 내부적으로 기본 풀이 생성되지만, `max_connections` 등을 명시적으로 제어하려면 직접 풀을 만드는 것이 좋다.

---

## 26. 패턴 01: 캐싱(Cache-Aside) — DB 부하를 줄이는 전략

### 문제 상황

상품 조회 API에 트래픽이 몰리면 매 요청이 DB를 직접 조회한다. 같은 상품을 1초에 1,000번 조회하면 동일 쿼리가 1,000번 실행되어 DB에 불필요한 부하가 발생한다.

```
문제: 동일 상품에 대한 반복 조회

Client ──→ API Server ──→ PostgreSQL
Client ──→ API Server ──→ PostgreSQL   ← 같은 쿼리 반복!
Client ──→ API Server ──→ PostgreSQL
         (초당 1,000회)
```

### 해결 전략 — Cache-Aside 패턴

Cache-Aside(Lazy Loading)는 가장 널리 쓰이는 캐싱 패턴이다. 애플리케이션이 캐시를 직접 관리하며, 캐시 미스가 발생할 때만 DB에서 읽고 캐시에 저장한다.

### 흐름도

```
┌──────────────────────────────────────────────────────────┐
│                  Cache-Aside 패턴 흐름                    │
│                                                          │
│   1. 클라이언트 요청                                      │
│      │                                                   │
│      ▼                                                   │
│   2. Redis에서 캐시 조회 (GET product:{id})               │
│      │                                                   │
│      ├── HIT (데이터 있음) ──→ 3a. 캐시 데이터 반환        │
│      │                                                   │
│      └── MISS (데이터 없음)                               │
│           │                                              │
│           ▼                                              │
│        3b. DB에서 조회                                    │
│           │                                              │
│           ▼                                              │
│        4. Redis에 캐시 저장 (SET product:{id} ... EX 300) │
│           │                                              │
│           ▼                                              │
│        5. 데이터 반환                                     │
└──────────────────────────────────────────────────────────┘
```

### TTL 설정 전략

| 데이터 유형 | 권장 TTL | 이유 |
|------------|---------|------|
| 상품 상세 | 5~10분 | 가격/재고 변경 가능 |
| 카테고리 목록 | 1~6시간 | 변경 빈도 낮음 |
| 사용자 프로필 | 5~30분 | 수정 빈도 중간 |
| 설정값 | 1~24시간 | 거의 변경 없음 |

### 캐시 무효화 — 데이터 변경 시 캐시 삭제

데이터가 변경되면 **즉시 캐시를 삭제**하여 다음 조회에서 DB의 최신 데이터를 가져오게 한다:

```
데이터 변경 흐름:

1. 상품 정보 수정 요청
2. DB UPDATE 실행
3. Redis DEL product:{id}  ← 캐시 무효화
4. 다음 조회 시 Cache Miss → DB에서 최신 데이터 조회 → 캐시 갱신
```

캐시를 **갱신(SET)**하지 않고 **삭제(DEL)**하는 이유: 갱신 시점에 DB와 캐시 사이의 일시적 불일치 가능성을 줄이기 위함이다. 삭제만 하면 다음 읽기에서 자연스럽게 최신 데이터가 캐시된다.

### 코드 예시: 상품 조회 API with Cache-Aside

```python
import json

from fastapi import APIRouter, Depends, HTTPException, Request

import redis.asyncio as aioredis

router = APIRouter(prefix="/products", tags=["products"])

CACHE_TTL = 300  # 5분


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


# 가상의 DB 조회 함수 (실제로는 SQLAlchemy, Tortoise 등 사용)
async def fetch_product_from_db(product_id: int) -> dict | None:
    """DB에서 상품 조회 (시뮬레이션)"""
    # 실제 구현에서는 async DB 쿼리
    fake_db = {
        1: {"id": 1, "name": "무선 키보드", "price": 59000, "stock": 120},
        2: {"id": 2, "name": "기계식 마우스", "price": 35000, "stock": 85},
    }
    return fake_db.get(product_id)


@router.get("/{product_id}")
async def get_product(product_id: int, redis: aioredis.Redis = Depends(get_redis)):
    cache_key = f"product:{product_id}"

    # 1. 캐시 조회
    cached = await redis.get(cache_key)
    if cached:
        return {"source": "cache", "data": json.loads(cached)}

    # 2. Cache Miss → DB 조회
    product = await fetch_product_from_db(product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="상품을 찾을 수 없습니다")

    # 3. 캐시에 저장 (TTL 설정)
    await redis.set(cache_key, json.dumps(product), ex=CACHE_TTL)

    return {"source": "db", "data": product}


@router.put("/{product_id}")
async def update_product(
    product_id: int,
    name: str,
    price: int,
    redis: aioredis.Redis = Depends(get_redis),
):
    cache_key = f"product:{product_id}"

    # 1. DB 업데이트 (시뮬레이션)
    # await db.execute("UPDATE products SET name=?, price=? WHERE id=?", ...)

    # 2. 캐시 무효화 — 갱신이 아닌 삭제
    await redis.delete(cache_key)

    return {"message": "상품 정보가 업데이트되었습니다"}
```

### 주의사항

- **Cache Stampede(Thunder Herd)**: TTL이 동시에 만료되면 수백 개의 요청이 동시에 DB를 조회한다. TTL에 랜덤 jitter를 추가하면 만료 시점을 분산시킬 수 있다: `ttl = CACHE_TTL + random.randint(0, 60)`.
- **Cold Start**: 서버 재시작 직후에는 캐시가 비어 있어 DB 부하가 급증한다. 자주 조회되는 데이터를 미리 워밍업하는 전략이 필요하다.
- **직렬화 비용**: `json.dumps` / `json.loads`는 간단하지만, 대용량 객체에서는 `msgpack`이나 `orjson`이 더 빠르다.

---

## 27. 패턴 02: 쇼핑몰의 최근 본 상품 리스트 (List 활용)

### 문제 상황

쇼핑몰에서 사용자별 "최근 본 상품" 기능을 구현해야 한다. DB에 매 조회를 INSERT하면 쓰기 부하가 크고, 최근 N개만 유지하려면 정리 쿼리도 필요하다.

```
요구사항:
- 사용자별 최근 본 상품을 최대 20개까지 유지
- 가장 최근에 본 상품이 맨 앞에 위치
- 같은 상품을 다시 보면 맨 앞으로 이동 (중복 방지)
- 조회는 빠르게 (실시간 UI 반영)
```

### 해결 전략 — Redis List (LPUSH + LTRIM)

Redis List를 Stack처럼 사용한다. `LPUSH`로 왼쪽에 추가하고 `LTRIM`으로 길이를 제한하면, 자동으로 오래된 항목이 제거된다.

### 흐름도

```
상품 조회 시:

1. LREM recent:{user_id} 0 {product_id}   ← 기존 중복 제거 (있으면)
2. LPUSH recent:{user_id} {product_id}     ← 맨 앞에 추가
3. LTRIM recent:{user_id} 0 19            ← 최대 20개 유지

조회 시:

LRANGE recent:{user_id} 0 19             ← 최근 20개 반환

┌─────────────────────────────────────────┐
│ recent:user:42                          │
│ [상품E, 상품D, 상품C, 상품B, 상품A, ...] │
│  ↑ 최신                       오래됨 ↑  │
│                                         │
│ 상품B를 다시 조회하면:                    │
│ 1. LREM → [상품E, 상품D, 상품C, 상품A]   │
│ 2. LPUSH → [상품B, 상품E, 상품D, 상품C, 상품A] │
└─────────────────────────────────────────┘
```

### 코드 예시

```python
from fastapi import APIRouter, Depends, Request

import redis.asyncio as aioredis

router = APIRouter(prefix="/recent", tags=["recent"])

MAX_RECENT_ITEMS = 20


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


@router.post("/{user_id}/view/{product_id}")
async def add_recently_viewed(
    user_id: int,
    product_id: int,
    redis: aioredis.Redis = Depends(get_redis),
):
    key = f"recent:{user_id}"

    # Pipeline으로 3개 명령을 한 번에 전송 (네트워크 왕복 1회)
    async with redis.pipeline(transaction=True) as pipe:
        pipe.lrem(key, 0, str(product_id))       # 1. 중복 제거
        pipe.lpush(key, str(product_id))          # 2. 맨 앞에 추가
        pipe.ltrim(key, 0, MAX_RECENT_ITEMS - 1)  # 3. 길이 제한
        pipe.expire(key, 60 * 60 * 24 * 30)       # 4. 30일 TTL
        await pipe.execute()

    return {"message": f"상품 {product_id} 조회 기록 저장"}


@router.get("/{user_id}")
async def get_recently_viewed(
    user_id: int,
    limit: int = 10,
    redis: aioredis.Redis = Depends(get_redis),
):
    key = f"recent:{user_id}"

    # 최근 본 상품 ID 목록 조회
    product_ids = await redis.lrange(key, 0, limit - 1)

    # 실제 서비스에서는 이 ID 목록으로 DB에서 상품 상세 정보를 조회
    return {
        "user_id": user_id,
        "recent_products": product_ids,
        "count": len(product_ids),
    }


@router.delete("/{user_id}")
async def clear_recently_viewed(
    user_id: int,
    redis: aioredis.Redis = Depends(get_redis),
):
    key = f"recent:{user_id}"
    await redis.delete(key)
    return {"message": "최근 본 상품 목록이 삭제되었습니다"}
```

### 주의사항

- **Pipeline 사용 필수**: `LREM` → `LPUSH` → `LTRIM`을 개별 명령으로 보내면 네트워크 왕복이 3번 발생한다. Pipeline으로 묶으면 1번으로 줄어든다.
- **LREM의 O(N)**: 리스트 전체를 순회하므로, 리스트 길이가 수천 개로 커지면 성능에 영향을 준다. `LTRIM`으로 길이를 제한하는 것이 필수다.
- **List vs Sorted Set**: 시간순 정렬만 필요하면 List가 적합하다. 점수 기반 정렬이 필요하면 Sorted Set을 사용하고, `ZADD`로 타임스탬프를 점수로 넣는 방식을 고려할 수 있다.
- **TTL 설정**: 비활성 사용자의 데이터가 영구히 남지 않도록 적절한 TTL을 설정한다.

---

## 28. 패턴 03: 분산 세션 공유 (Session Store)

### 문제 상황 — 로드밸런서 환경에서의 세션 불일치

서버를 여러 대 운영할 때, 각 서버가 자체 메모리에 세션을 저장하면 사용자가 다른 서버로 라우팅될 때마다 세션이 유실된다.

```
문제: Sticky Session 없이 다중 서버 운영

사용자 로그인 → Server A (세션 생성: session_abc → user:42)
다음 요청    → Server B (session_abc를 모름 → 로그인 풀림!)

               ┌── Server A: {session_abc: user:42}  ← 여기만 알고 있음
Load Balancer ─┤
               └── Server B: {}                      ← 세션 없음
```

Sticky Session(세션 고정)은 해결책처럼 보이지만, 특정 서버에 트래픽이 쏠리는 문제와 서버 장애 시 세션 유실이라는 단점이 있다.

### 해결 전략 — Redis Hash로 세션 중앙 저장

모든 서버가 Redis를 세션 저장소로 공유하면, 어떤 서버로 라우팅되든 동일한 세션에 접근할 수 있다.

```
해결: Redis를 세션 저장소로 사용

               ┌── Server A ──┐
Load Balancer ─┤               ├──→ Redis
               └── Server B ──┘    session:abc → {user_id: 42, role: admin}

어떤 서버로 가든 Redis에서 세션을 조회하므로 일치 보장
```

### 흐름도

```
┌──────────────────────────────────────────────────────┐
│                  세션 기반 인증 흐름                   │
│                                                      │
│  로그인:                                              │
│  1. 아이디/비밀번호 검증                               │
│  2. session_id = uuid4() 생성                        │
│  3. HSET session:{session_id} user_id 42 role admin  │
│  4. EXPIRE session:{session_id} 1800 (30분)          │
│  5. 응답 쿠키에 session_id 저장                       │
│                                                      │
│  인증된 요청:                                         │
│  1. 쿠키에서 session_id 추출                          │
│  2. HGETALL session:{session_id}                     │
│  3. 세션 데이터 있으면 → 인증 성공                     │
│  4. 세션 데이터 없으면 → 401 Unauthorized              │
│                                                      │
│  로그아웃:                                            │
│  1. DEL session:{session_id}                         │
│  2. 응답에서 쿠키 삭제                                │
└──────────────────────────────────────────────────────┘
```

### 코드 예시: 세션 기반 인증

```python
import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response

import redis.asyncio as aioredis

router = APIRouter(prefix="/auth", tags=["auth"])

SESSION_TTL = 1800  # 30분


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


# 가상의 사용자 DB
USERS_DB = {
    "admin@test.com": {"id": 42, "password": "hashed_pw", "role": "admin"},
    "user@test.com": {"id": 99, "password": "hashed_pw", "role": "user"},
}


@router.post("/login")
async def login(
    email: str,
    password: str,
    response: Response,
    redis: aioredis.Redis = Depends(get_redis),
):
    # 1. 사용자 인증 (실제로는 비밀번호 해시 비교)
    user = USERS_DB.get(email)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="인증 실패")

    # 2. 세션 ID 생성
    session_id = str(uuid.uuid4())

    # 3. Redis Hash에 세션 데이터 저장
    session_key = f"session:{session_id}"
    await redis.hset(
        session_key,
        mapping={
            "user_id": str(user["id"]),
            "email": email,
            "role": user["role"],
        },
    )
    await redis.expire(session_key, SESSION_TTL)

    # 4. 쿠키에 세션 ID 저장
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,      # JavaScript에서 접근 불가
        secure=True,        # HTTPS에서만 전송
        samesite="lax",     # CSRF 방지
        max_age=SESSION_TTL,
    )

    return {"message": "로그인 성공"}


async def get_current_user(
    request: Request,
    session_id: str | None = Cookie(default=None),
) -> dict:
    """세션 기반 인증 의존성"""
    if not session_id:
        raise HTTPException(status_code=401, detail="세션이 없습니다")

    redis = request.app.state.redis
    session_key = f"session:{session_id}"

    # 세션 데이터 조회
    session_data = await redis.hgetall(session_key)
    if not session_data:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다")

    # 세션 연장 (Sliding Expiration)
    await redis.expire(session_key, SESSION_TTL)

    return session_data


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {"user": user}


@router.post("/logout")
async def logout(
    response: Response,
    session_id: str | None = Cookie(default=None),
    redis: aioredis.Redis = Depends(get_redis),
):
    if session_id:
        await redis.delete(f"session:{session_id}")

    response.delete_cookie("session_id")
    return {"message": "로그아웃 완료"}
```

### 주의사항

- **Sliding Expiration**: 매 요청마다 `EXPIRE`로 TTL을 갱신하면, 활동 중인 사용자의 세션이 자동으로 연장된다. 반면 **Absolute Expiration**은 로그인 시점부터 고정 시간 후 만료된다. 보안 요구사항에 따라 선택한다.
- **세션 ID 예측 불가능성**: `uuid4()`는 충분히 안전하지만, 보안이 중요한 환경에서는 `secrets.token_urlsafe(32)` 사용을 권장한다.
- **쿠키 보안**: `httponly`, `secure`, `samesite` 플래그를 반드시 설정하여 XSS, CSRF 공격을 방지한다.
- **세션 데이터 크기**: Redis Hash에 저장하는 세션 데이터는 최소한으로 유지한다. 대량의 사용자 정보는 DB에서 조회하고, 세션에는 `user_id`와 `role` 정도만 저장한다.

---

## 29. 패턴 04: 조회수/좋아요 카운팅 정합성 (INCR)

### 문제 상황 — RDB UPDATE의 동시성 문제

게시글 조회수를 RDB로 직접 관리하면 두 가지 문제가 발생한다:

```
문제 1: 동시성 (Lost Update)

시점 T1: 요청A가 count 읽음 → 100
시점 T2: 요청B가 count 읽음 → 100
시점 T3: 요청A가 count = 100 + 1 = 101 저장
시점 T4: 요청B가 count = 100 + 1 = 101 저장  ← 102여야 하는데 101!

문제 2: DB 부하
초당 10,000건의 UPDATE 쿼리 → DB Connection Pool 고갈
```

`UPDATE SET count = count + 1`은 행 잠금(Row Lock)으로 동시성은 해결하지만, 잠금 대기로 인한 성능 저하는 피할 수 없다.

### 해결 전략 — Redis INCR의 원자성

Redis의 `INCR` 명령은 **원자적(Atomic)**이다. 단일 스레드로 동작하는 Redis에서 `INCR`은 읽기-증가-쓰기가 하나의 명령으로 처리되므로 Lost Update가 발생하지 않는다.

```
Redis INCR의 원자성:

요청A: INCR post:1:views → 101
요청B: INCR post:1:views → 102   ← 순차 처리, 누락 없음
요청C: INCR post:1:views → 103
         (초당 수만 건도 거뜬)
```

### Write-Back 패턴 — Redis 카운터를 주기적으로 DB에 동기화

실시간 카운터는 Redis가 담당하고, DB에는 주기적으로 동기화한다:

```
┌─────────────────────────────────────────────────────┐
│              Write-Back 패턴 흐름                    │
│                                                     │
│   실시간 요청:                                       │
│   Client → API → Redis INCR post:{id}:views         │
│                   (즉시 응답, 지연 없음)              │
│                                                     │
│   주기적 동기화 (5분마다):                            │
│   Scheduler → Redis GET post:{id}:views              │
│            → DB UPDATE posts SET views = {count}     │
│            → Redis DEL post:{id}:views (또는 유지)    │
│                                                     │
│   조회 시:                                           │
│   Redis 값 존재 → Redis에서 반환                     │
│   Redis 값 없음 → DB에서 반환                        │
└─────────────────────────────────────────────────────┘
```

### 코드 예시

```python
from fastapi import APIRouter, Depends, Request

import redis.asyncio as aioredis

router = APIRouter(prefix="/posts", tags=["posts"])


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


@router.post("/{post_id}/view")
async def increment_view(
    post_id: int,
    redis: aioredis.Redis = Depends(get_redis),
):
    """조회수 증가 — Redis INCR (원자적)"""
    key = f"post:{post_id}:views"
    views = await redis.incr(key)
    return {"post_id": post_id, "views": views}


@router.post("/{post_id}/like")
async def toggle_like(
    post_id: int,
    user_id: int,
    redis: aioredis.Redis = Depends(get_redis),
):
    """좋아요 토글 — Set으로 중복 방지 + INCR로 카운팅"""
    like_set_key = f"post:{post_id}:liked_users"
    like_count_key = f"post:{post_id}:likes"

    # 이미 좋아요 했는지 확인
    already_liked = await redis.sismember(like_set_key, str(user_id))

    if already_liked:
        # 좋아요 취소
        async with redis.pipeline(transaction=True) as pipe:
            pipe.srem(like_set_key, str(user_id))
            pipe.decr(like_count_key)
            await pipe.execute()
        return {"action": "unliked"}
    else:
        # 좋아요 추가
        async with redis.pipeline(transaction=True) as pipe:
            pipe.sadd(like_set_key, str(user_id))
            pipe.incr(like_count_key)
            await pipe.execute()
        return {"action": "liked"}


@router.get("/{post_id}/stats")
async def get_post_stats(
    post_id: int,
    redis: aioredis.Redis = Depends(get_redis),
):
    """게시글 통계 조회"""
    views = await redis.get(f"post:{post_id}:views")
    likes = await redis.get(f"post:{post_id}:likes")

    return {
        "post_id": post_id,
        "views": int(views) if views else 0,
        "likes": int(likes) if likes else 0,
    }


# ─── Write-Back: 주기적 DB 동기화 (별도 스케줄러에서 실행) ───

async def sync_views_to_db(redis: aioredis.Redis):
    """
    5분마다 실행되는 동기화 작업 (APScheduler, Celery Beat 등에서 호출)
    """
    cursor = "0"
    while cursor != 0:
        cursor, keys = await redis.scan(
            cursor=cursor, match="post:*:views", count=100
        )
        for key in keys:
            post_id = key.split(":")[1]
            views = await redis.get(key)
            if views:
                # DB 업데이트 (실제로는 async DB 클라이언트 사용)
                # await db.execute(
                #     "UPDATE posts SET views = %s WHERE id = %s",
                #     (int(views), int(post_id)),
                # )
                pass
```

### 주의사항

- **INCR vs INCRBY**: 1씩 증가시킬 때는 `INCR`, N씩 증가시킬 때는 `INCRBY`를 사용한다.
- **좋아요 중복 방지**: `INCR`만으로는 같은 사용자의 중복 좋아요를 막을 수 없다. Redis Set(`SADD` + `SISMEMBER`)으로 사용자별 좋아요 여부를 관리해야 한다.
- **Write-Back의 데이터 유실 위험**: Redis가 장애로 죽으면 DB에 동기화되지 않은 카운터가 유실된다. 중요 데이터는 동기화 주기를 짧게 하거나 Redis 영속성(RDB/AOF)을 활성화한다.
- **SCAN 사용**: 동기화 시 `KEYS *`는 Redis를 블로킹하므로 절대 사용하지 않는다. 반드시 `SCAN`을 사용하여 점진적으로 키를 순회한다.

---

## 30. 패턴 05: TTL을 활용한 임시 인증번호 로직

### 문제 상황

휴대폰 본인인증, 이메일 인증 등에서 일정 시간 동안만 유효한 인증번호를 관리해야 한다. DB에 저장하면 만료 처리를 위한 별도 배치나 쿼리가 필요하다.

```
요구사항:
- 인증번호 6자리 발급
- 3분(180초) 후 자동 만료
- 검증 성공 시 즉시 삭제 (1회용)
- 30초 이내 재발송 방지
```

### 해결 전략 — Redis SET + EX (TTL 자동 만료)

Redis의 TTL은 별도 배치 없이 키를 자동으로 삭제한다. `SET key value EX seconds` 한 줄이면 "3분 후 자동 만료"가 구현된다.

### 흐름도

```
┌────────────────────────────────────────────────────────────┐
│                 인증번호 발급/검증 흐름                      │
│                                                            │
│   발급 요청:                                                │
│   1. TTL 확인 (재발송 방지)                                 │
│      └── TTL > 150초 → "30초 후 재발송 가능" 에러 반환       │
│   2. 6자리 랜덤 코드 생성                                   │
│   3. SET verification:{phone} {code} EX 180                │
│   4. SMS 발송 (비동기)                                      │
│                                                            │
│   검증 요청:                                                │
│   1. GET verification:{phone}                              │
│   2. 저장된 코드와 입력 코드 비교                            │
│      ├── 일치 → DEL verification:{phone} → 인증 성공        │
│      └── 불일치 → 인증 실패                                 │
│                                                            │
│   자동 만료:                                                │
│   3분(180초) 경과 → Redis가 자동으로 키 삭제                 │
└────────────────────────────────────────────────────────────┘
```

### 코드 예시

```python
import random
import string

from fastapi import APIRouter, Depends, HTTPException, Request

import redis.asyncio as aioredis

router = APIRouter(prefix="/verification", tags=["verification"])

CODE_TTL = 180         # 인증번호 유효 시간: 3분
RESEND_COOLDOWN = 30   # 재발송 대기 시간: 30초


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def generate_code(length: int = 6) -> str:
    """6자리 숫자 인증번호 생성"""
    return "".join(random.choices(string.digits, k=length))


@router.post("/send")
async def send_verification(
    phone: str,
    redis: aioredis.Redis = Depends(get_redis),
):
    key = f"verification:{phone}"

    # 1. 재발송 방지: 남은 TTL 확인
    ttl = await redis.ttl(key)
    if ttl > CODE_TTL - RESEND_COOLDOWN:
        remaining = ttl - (CODE_TTL - RESEND_COOLDOWN)
        raise HTTPException(
            status_code=429,
            detail=f"{remaining}초 후에 재발송할 수 있습니다",
        )

    # 2. 인증번호 생성
    code = generate_code()

    # 3. Redis에 저장 (3분 TTL)
    await redis.set(key, code, ex=CODE_TTL)

    # 4. SMS 발송 (실제로는 외부 API 호출)
    # await sms_client.send(phone, f"인증번호: {code}")

    return {"message": "인증번호가 발송되었습니다", "expires_in": CODE_TTL}


@router.post("/verify")
async def verify_code(
    phone: str,
    code: str,
    redis: aioredis.Redis = Depends(get_redis),
):
    key = f"verification:{phone}"

    # 1. 저장된 인증번호 조회
    stored_code = await redis.get(key)

    if stored_code is None:
        raise HTTPException(
            status_code=400,
            detail="인증번호가 만료되었거나 발급되지 않았습니다",
        )

    # 2. 코드 비교
    if stored_code != code:
        raise HTTPException(status_code=400, detail="인증번호가 일치하지 않습니다")

    # 3. 인증 성공 → 즉시 삭제 (1회용)
    await redis.delete(key)

    return {"message": "인증 성공", "verified": True}
```

### 주의사항

- **재발송 방지 로직**: `TTL` 값으로 마지막 발송 시점을 역산한다. TTL이 `180 - 30 = 150초` 이상 남아 있으면 아직 30초가 지나지 않은 것이다.
- **인증 시도 횟수 제한**: 코드 예시에는 생략되었지만, 실제 서비스에서는 별도의 카운터(`verification:attempts:{phone}`)로 시도 횟수를 제한해야 무차별 대입 공격을 방지할 수 있다.
- **TTL 반환값 의미**: `TTL` 명령은 키가 없으면 `-2`, TTL이 설정되지 않은 키는 `-1`, TTL이 있으면 남은 초를 반환한다.
- **코드 보안**: 인증번호를 응답으로 직접 반환하면 안 된다. SMS/이메일 채널을 통해서만 전달한다. 코드 예시에서 응답에 코드를 포함하지 않은 것에 주목할 것.

---

## 31. 패턴 06: 분산 락(Distributed Lock) — 동시성 문제 해결

### 문제 상황 — 분산 환경의 동시성 문제

쿠폰 100장을 선착순 발급할 때, 여러 서버에서 동시에 재고를 확인하고 차감하면 초과 발급이 발생한다.

```
문제: 쿠폰 100장, 서버 3대, 동시 요청

시점 T1: Server A — 남은 쿠폰 조회 → 1장
시점 T1: Server B — 남은 쿠폰 조회 → 1장   ← 동시에 읽음!
시점 T2: Server A — 쿠폰 발급 → 남은 0장
시점 T2: Server B — 쿠폰 발급 → 남은 -1장  ← 초과 발급!
```

Python의 `threading.Lock`은 **단일 프로세스** 내에서만 동작한다. 분산 환경(여러 서버, 여러 컨테이너)에서는 Redis 기반 분산 락이 필요하다.

### 해결 전략 — Redis SET NX EX로 원자적 락 획득

```
분산 락의 3단계:

1. 락 획득 시도
   SET lock:coupon:{id} {owner_id} NX EX 30
   ├── NX: 키가 없을 때만 설정 (이미 락이 있으면 실패)
   └── EX 30: 30초 후 자동 해제 (데드락 방지)

2. 비즈니스 로직 실행
   재고 확인 → 쿠폰 발급

3. 락 해제
   owner_id 확인 → DEL (Lua Script로 원자적 처리)
```

### 흐름도

```
┌─────────────────────────────────────────────────────────┐
│                  분산 락 흐름도                           │
│                                                         │
│  Server A                       Redis                   │
│  │                               │                      │
│  ├─ SET lock:coupon NX EX 30 ──→ │ (키 없음 → 성공)     │
│  │                               │ lock:coupon = "A"    │
│  ├─ 재고 확인 (1장)               │                      │
│  ├─ 쿠폰 발급                     │                      │
│  ├─ DEL lock:coupon ──────────→  │ (락 해제)            │
│  │                               │                      │
│  Server B                        │                      │
│  │                               │                      │
│  ├─ SET lock:coupon NX EX 30 ──→ │ (키 있음 → 실패)     │
│  ├─ 재시도 또는 "잠시 후 시도" 반환 │                      │
│                                                         │
│  ⚠️ 만약 Server A가 죽으면?                              │
│  EX 30으로 30초 후 자동 해제 → 데드락 방지                │
└─────────────────────────────────────────────────────────┘
```

### 락 해제 시 owner 확인이 필요한 이유

```
위험한 시나리오 (owner 미확인):

T1: Server A — 락 획득 (EX 30초)
T31: 락 자동 만료 (Server A는 아직 작업 중)
T32: Server B — 락 획득 (새로운 락)
T33: Server A — DEL lock:coupon  ← Server B의 락을 삭제!
T34: Server C — 락 획득          ← 동시에 2개 프로세스가 실행!
```

따라서 락 해제 시 **자신이 설정한 락인지 확인한 후** 삭제해야 한다. 이 확인과 삭제는 원자적이어야 하므로 Lua Script를 사용한다.

### 코드 예시: 쿠폰 발급 동시성 제어

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

import redis.asyncio as aioredis

router = APIRouter(prefix="/coupons", tags=["coupons"])

LOCK_TTL = 30  # 락 만료 시간 (초)

# Lua Script: owner 확인 후 삭제 (원자적)
RELEASE_LOCK_SCRIPT = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


async def acquire_lock(
    redis: aioredis.Redis,
    resource: str,
    owner: str,
    ttl: int = LOCK_TTL,
) -> bool:
    """분산 락 획득 시도"""
    result = await redis.set(
        f"lock:{resource}",
        owner,
        nx=True,   # 키가 없을 때만 설정
        ex=ttl,    # TTL 설정 (데드락 방지)
    )
    return result is not None


async def release_lock(
    redis: aioredis.Redis,
    resource: str,
    owner: str,
) -> bool:
    """분산 락 해제 (Lua Script로 원자적 처리)"""
    result = await redis.eval(
        RELEASE_LOCK_SCRIPT,
        1,                    # KEYS 개수
        f"lock:{resource}",   # KEYS[1]
        owner,                # ARGV[1]
    )
    return result == 1


@router.post("/{coupon_id}/issue")
async def issue_coupon(
    coupon_id: int,
    user_id: int,
    redis: aioredis.Redis = Depends(get_redis),
):
    resource = f"coupon:{coupon_id}"
    owner = str(uuid.uuid4())  # 이 요청의 고유 식별자

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

        # 재고 차감 + 발급 기록
        async with redis.pipeline(transaction=True) as pipe:
            pipe.decr(stock_key)
            pipe.sadd(f"coupon:{coupon_id}:issued_users", str(user_id))
            await pipe.execute()

        return {"message": "쿠폰 발급 성공", "coupon_id": coupon_id}

    finally:
        # 3. 반드시 락 해제 (예외 발생 시에도)
        await release_lock(redis, resource, owner)
```

### Redlock 알고리즘 개요

단일 Redis 인스턴스에서의 분산 락은 Redis 자체가 장애를 일으키면 무력화된다. Redlock은 **N개(보통 5개)의 독립적인 Redis 인스턴스**에서 과반수 이상의 락을 획득해야 성공으로 판단하는 알고리즘이다.

```
Redlock 흐름:

1. 5개 Redis 인스턴스에 순서대로 SET NX EX 시도
2. 과반수(3개 이상) 성공 + 총 소요 시간 < TTL → 락 획득 성공
3. 실패 시 → 이미 획득한 모든 인스턴스에서 DEL

실무에서는 redis-py-cluster나 별도 라이브러리(pottery 등)가 Redlock을 구현해 제공한다.
```

### 주의사항

- **TTL 설정**: 비즈니스 로직 실행 시간보다 충분히 길게 설정한다. 너무 짧으면 작업 중에 락이 풀려 동시성 문제가 재발한다.
- **try/finally 필수**: 비즈니스 로직에서 예외가 발생해도 반드시 락을 해제해야 한다. `finally` 블록을 사용한다.
- **Lua Script 필수**: GET과 DEL을 따로 실행하면 그 사이에 다른 프로세스가 끼어들 수 있다. Lua Script로 원자적으로 처리한다.
- **재시도 전략**: 락 획득 실패 시 일정 간격을 두고 재시도하는 로직(Exponential Backoff)을 추가하면 사용자 경험이 개선된다.

---

## 32. 패턴 07: API Rate Limiting — 서버 과부하 방지

### 문제 상황

특정 사용자나 IP에서 과도한 API 호출이 발생하면 서버 자원이 고갈되어 정상 사용자에게 영향을 미친다. 악의적인 크롤링, DDoS, 또는 버그 있는 클라이언트에 의한 반복 호출을 제한해야 한다.

### 해결 전략 1 — Fixed Window 카운터

가장 단순한 방식이다. 고정된 시간 윈도우(예: 1분) 내에서 요청 횟수를 카운팅한다.

```
Fixed Window 카운터:

시간:  00:00 ─────────────── 01:00 ─────────────── 02:00
윈도우:    [       윈도우 1       ] [       윈도우 2       ]
요청:   ■■■■■■■■■■                ■■■■
카운터: 10/100 (통과)             4/100 (통과)

키: ratelimit:{ip}:{분}
값: 요청 횟수 (INCR)
TTL: 60초 (윈도우가 끝나면 자동 삭제)
```

```python
async def fixed_window_check(
    redis: aioredis.Redis,
    identifier: str,
    limit: int = 100,
    window: int = 60,
) -> tuple[bool, int]:
    """
    Fixed Window Rate Limiter.
    Returns: (allowed: bool, remaining: int)
    """
    import time

    current_window = int(time.time()) // window
    key = f"ratelimit:{identifier}:{current_window}"

    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window)
        results = await pipe.execute()

    current_count = results[0]
    remaining = max(0, limit - current_count)

    return current_count <= limit, remaining
```

### Fixed Window의 경계 문제

```
경계 문제 (Burst at window edge):

    윈도우 1            윈도우 2
... ──────|── 100건 ──|── 100건 ──|──────── ...
          59초  60초  61초

00:59에 100건 + 01:01에 100건 = 2초 사이에 200건!
제한은 분당 100건인데, 경계에서 사실상 2배가 통과됨.
```

### 해결 전략 2 — Sliding Window Log

Sorted Set에 각 요청의 타임스탬프를 기록하고, 현재 시점 기준으로 윈도우 내의 요청만 카운팅한다. 경계 문제를 완전히 해결한다.

```
Sliding Window Log:

현재 시각: 12:01:30
윈도우: 60초
→ 12:00:30 ~ 12:01:30 사이의 요청만 카운팅

Sorted Set: ratelimit:{ip}
score = 타임스탬프, member = 유니크 ID

┌─────────────────────────────────────────────┐
│  12:00:15 ──── 제거 (윈도우 밖)              │
│  12:00:25 ──── 제거 (윈도우 밖)              │
│  12:00:45 ──── 카운팅 ✓                     │
│  12:01:10 ──── 카운팅 ✓                     │
│  12:01:28 ──── 카운팅 ✓                     │
│                                             │
│  3건 < 100건 제한 → 통과                     │
└─────────────────────────────────────────────┘
```

```python
import time
import uuid


async def sliding_window_check(
    redis: aioredis.Redis,
    identifier: str,
    limit: int = 100,
    window: int = 60,
) -> tuple[bool, int]:
    """
    Sliding Window Log Rate Limiter.
    Returns: (allowed: bool, remaining: int)
    """
    key = f"ratelimit:sw:{identifier}"
    now = time.time()
    window_start = now - window

    async with redis.pipeline(transaction=True) as pipe:
        # 1. 윈도우 밖의 오래된 요청 제거
        pipe.zremrangebyscore(key, 0, window_start)
        # 2. 현재 요청 추가 (유니크 member 필요)
        pipe.zadd(key, {f"{now}:{uuid.uuid4().hex[:8]}": now})
        # 3. 윈도우 내 요청 수 카운팅
        pipe.zcard(key)
        # 4. TTL 설정 (메모리 정리)
        pipe.expire(key, window)
        results = await pipe.execute()

    current_count = results[2]
    remaining = max(0, limit - current_count)

    if current_count > limit:
        # 초과한 요청은 제거
        await redis.zrem(key, f"{now}:{uuid.uuid4().hex[:8]}")
        return False, 0

    return True, remaining
```

### 두 방식 비교

| 특성 | Fixed Window | Sliding Window Log |
|------|-------------|-------------------|
| **구현 복잡도** | 간단 (INCR + EXPIRE) | 중간 (Sorted Set + ZRANGEBYSCORE) |
| **메모리 사용** | O(1) per key | O(N) per key (각 요청 기록) |
| **정확도** | 경계 문제 있음 | 정확함 |
| **Redis 명령 수** | 2개 (INCR, EXPIRE) | 4개 (ZREMRANGEBYSCORE, ZADD, ZCARD, EXPIRE) |
| **적합한 경우** | 대략적 제한 충분 | 정확한 제한 필요 |

### 코드 예시: IP 기반 Rate Limiter 미들웨어

```python
import time

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

import redis.asyncio as aioredis


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP 기반 Fixed Window Rate Limiter"""

    def __init__(self, app: FastAPI, limit: int = 100, window: int = 60):
        super().__init__(app)
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next) -> Response:
        redis: aioredis.Redis = request.app.state.redis

        # 클라이언트 IP 추출 (프록시 환경에서는 X-Forwarded-For 사용)
        client_ip = request.client.host
        current_window = int(time.time()) // self.window
        key = f"ratelimit:{client_ip}:{current_window}"

        # 원자적으로 카운트 증가 + TTL 설정
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, self.window)
            results = await pipe.execute()

        current_count = results[0]
        remaining = max(0, self.limit - current_count)

        # Rate Limit 헤더 추가 (표준 관례)
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str((current_window + 1) * self.window),
        }

        if current_count > self.limit:
            return Response(
                content='{"detail": "요청 횟수를 초과했습니다"}',
                status_code=429,
                headers={
                    **headers,
                    "Retry-After": str(self.window),
                    "Content-Type": "application/json",
                },
            )

        response = await call_next(request)
        for header_name, header_value in headers.items():
            response.headers[header_name] = header_value

        return response


# 미들웨어 등록
# app.add_middleware(RateLimitMiddleware, limit=100, window=60)
```

### 주의사항

- **X-Forwarded-For**: 리버스 프록시(Nginx, ALB) 뒤에서 운영할 때는 `request.client.host`가 프록시의 IP가 된다. `X-Forwarded-For` 헤더에서 실제 클라이언트 IP를 추출해야 한다.
- **Rate Limit 헤더**: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `Retry-After`를 응답에 포함하면 클라이언트가 적절히 대응할 수 있다.
- **엔드포인트별 차등 적용**: 로그인 API는 분당 5회, 조회 API는 분당 100회 등 엔드포인트별로 다른 제한을 적용하는 것이 실무적이다.
- **분산 환경에서의 정확성**: 여러 서버가 같은 Redis를 바라보므로, 서버가 몇 대든 전체 합산 카운트가 적용된다. 이것이 Redis Rate Limiting의 핵심 장점이다.

---

## 33. 패턴 08: 실시간 랭킹 시스템 — 부하 없는 리더보드

### 문제 상황

게임 점수, 매출 순위, 인기 상품 등의 랭킹을 실시간으로 제공해야 한다. RDB에서 `ORDER BY score DESC LIMIT 10`을 매번 실행하면 데이터가 많아질수록 쿼리 비용이 급증한다.

```
RDB 방식의 문제:

SELECT * FROM leaderboard ORDER BY score DESC LIMIT 10;

데이터 10만 건 → 인덱스 있어도 부하 상당
실시간 갱신 + 초당 수천 조회 → DB가 감당 불가
```

### 해결 전략 — Redis Sorted Set

Sorted Set은 **삽입 시점에 자동 정렬**된다. 점수 업데이트와 순위 조회 모두 O(log N)으로 처리되어 데이터가 수백만 건이어도 빠르다.

```
Sorted Set 핵심 명령:

ZADD leaderboard 1500 "playerA"   — 점수 설정/갱신
ZINCRBY leaderboard 100 "playerA" — 점수 증가
ZREVRANGE leaderboard 0 9 WITHSCORES — 상위 10명 (내림차순)
ZREVRANK leaderboard "playerA"    — playerA의 순위 (0-based)
ZCARD leaderboard                 — 전체 참가자 수
ZSCORE leaderboard "playerA"     — playerA의 점수
```

### 흐름도

```
┌──────────────────────────────────────────────────────┐
│              실시간 랭킹 시스템 구조                   │
│                                                      │
│   점수 업데이트:                                      │
│   Client → API → ZINCRBY leaderboard {delta} {user}  │
│                  (O(log N), 자동 정렬)                │
│                                                      │
│   Top N 조회:                                        │
│   Client → API → ZREVRANGE leaderboard 0 N-1         │
│                  (O(log N + N), 즉시 반환)            │
│                                                      │
│   내 순위 조회:                                       │
│   Client → API → ZREVRANK leaderboard {user}          │
│                  (O(log N), 즉시 반환)                │
│                                                      │
│   ┌──────────────────────────────────┐               │
│   │  Sorted Set: leaderboard        │               │
│   │                                  │               │
│   │  Score    Member                 │               │
│   │  2500     playerC   ← 1위       │               │
│   │  2100     playerA   ← 2위       │               │
│   │  1800     playerF   ← 3위       │               │
│   │  ...                             │               │
│   └──────────────────────────────────┘               │
└──────────────────────────────────────────────────────┘
```

### 코드 예시

```python
from fastapi import APIRouter, Depends, HTTPException, Request

import redis.asyncio as aioredis

router = APIRouter(prefix="/rank", tags=["ranking"])

LEADERBOARD_KEY = "leaderboard"


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


@router.post("/score")
async def update_score(
    user_id: str,
    score: float,
    redis: aioredis.Redis = Depends(get_redis),
):
    """점수 증가 (ZINCRBY로 누적 가산)"""
    new_score = await redis.zincrby(LEADERBOARD_KEY, score, user_id)
    rank = await redis.zrevrank(LEADERBOARD_KEY, user_id)

    return {
        "user_id": user_id,
        "new_score": new_score,
        "rank": rank + 1 if rank is not None else None,  # 1-based 순위
    }


@router.get("/top10")
async def get_top10(redis: aioredis.Redis = Depends(get_redis)):
    """상위 10명 조회"""
    # ZREVRANGE: 점수 내림차순으로 0번째부터 9번째까지
    results = await redis.zrevrange(
        LEADERBOARD_KEY, 0, 9, withscores=True
    )

    leaderboard = [
        {"rank": idx + 1, "user_id": member, "score": score}
        for idx, (member, score) in enumerate(results)
    ]

    return {"leaderboard": leaderboard}


@router.get("/me/{user_id}")
async def get_my_rank(
    user_id: str,
    redis: aioredis.Redis = Depends(get_redis),
):
    """내 순위와 점수 조회"""
    # Pipeline으로 순위와 점수를 한 번에 조회
    async with redis.pipeline(transaction=False) as pipe:
        pipe.zrevrank(LEADERBOARD_KEY, user_id)
        pipe.zscore(LEADERBOARD_KEY, user_id)
        results = await pipe.execute()

    rank, score = results

    if rank is None:
        raise HTTPException(status_code=404, detail="랭킹에 등록되지 않은 사용자입니다")

    total = await redis.zcard(LEADERBOARD_KEY)

    return {
        "user_id": user_id,
        "rank": rank + 1,      # 1-based 순위
        "score": score,
        "total_players": total,
        "top_percent": round((rank + 1) / total * 100, 1) if total > 0 else 0,
    }


@router.get("/range")
async def get_rank_range(
    start: int = 1,
    end: int = 50,
    redis: aioredis.Redis = Depends(get_redis),
):
    """순위 범위 조회 (페이지네이션)"""
    results = await redis.zrevrange(
        LEADERBOARD_KEY, start - 1, end - 1, withscores=True
    )

    leaderboard = [
        {"rank": start + idx, "user_id": member, "score": score}
        for idx, (member, score) in enumerate(results)
    ]

    return {"leaderboard": leaderboard, "range": f"{start}-{end}"}
```

### 주의사항

- **ZREVRANK는 0-based**: Redis의 순위는 0부터 시작한다. 사용자에게 보여줄 때는 `+1`하여 1-based로 변환한다.
- **동점 처리**: Sorted Set에서 동점인 멤버는 **사전순(lexicographic)**으로 정렬된다. 동점 시 먼저 도달한 사람을 상위로 하려면 점수에 타임스탬프를 소수점 이하에 인코딩하는 트릭을 쓸 수 있다: `score = base_score + (1 - timestamp / max_timestamp)`.
- **대용량 랭킹**: 수백만 유저의 랭킹도 Sorted Set으로 충분히 처리할 수 있다. `ZREVRANGE`는 O(log N + M)이고, `ZREVRANK`는 O(log N)이다.
- **일별/주별 리더보드**: 키에 날짜를 포함하여(`leaderboard:2026-03-14`) 기간별 랭킹을 관리하고, `ZUNIONSTORE`로 통합 랭킹을 생성할 수 있다.

---

## 34. 패턴 09: 실시간 시스템 알림 — FastAPI와 Pub/Sub 연동

### 문제 상황

관리자가 공지사항을 등록하면 현재 접속 중인 모든 사용자에게 실시간으로 알림을 보내야 한다. 폴링(주기적 API 호출)은 서버 부하와 지연이 크고, WebSocket은 인프라 복잡도가 높다.

```
폴링 방식의 문제:
- 1초마다 GET /notifications → 서버에 초당 사용자 수만큼 요청
- 새 알림이 없어도 요청 발생 (낭비)
- 실시간이 아니라 "거의 실시간" (최대 1초 지연)
```

### 해결 전략 — Redis Pub/Sub + SSE(Server-Sent Events)

Redis Pub/Sub으로 메시지를 발행하면, 구독 중인 모든 서버가 즉시 수신한다. FastAPI의 SSE(Server-Sent Events)로 이 메시지를 클라이언트에 스트리밍한다.

### 흐름도

```
┌──────────────────────────────────────────────────────────┐
│           Pub/Sub + SSE 실시간 알림 아키텍처              │
│                                                          │
│  관리자                                                   │
│  │                                                       │
│  ├─ POST /notify {message: "서버 점검 안내"}              │
│  │                                                       │
│  ▼                                                       │
│  Server A → PUBLISH notifications "서버 점검 안내"         │
│                │                                         │
│                ▼                                         │
│              Redis Pub/Sub                               │
│                │                                         │
│         ┌──────┼──────┐                                  │
│         ▼      ▼      ▼                                  │
│  Server A   Server B   Server C   (SUBSCRIBE 중)         │
│    │           │          │                               │
│    ▼           ▼          ▼                               │
│  SSE ──→   SSE ──→    SSE ──→    (각 서버의 연결된 클라이언트) │
│  User1     User2      User3                              │
│  User4     User5      User6                              │
│                                                          │
│  모든 사용자가 즉시 알림 수신 (폴링 없음)                   │
└──────────────────────────────────────────────────────────┘
```

### Pub/Sub 핵심 개념

```
SUBSCRIBE channel          — 채널 구독 (메시지 대기)
PUBLISH channel message    — 채널에 메시지 발행
UNSUBSCRIBE channel        — 구독 해제

특징:
- Fire-and-forget: 구독자가 없으면 메시지 소멸 (저장 안 됨)
- 1:N 브로드캐스트: 하나의 PUBLISH가 모든 구독자에게 전달
- 패턴 구독: PSUBSCRIBE notifications:* (와일드카드)
```

### 코드 예시: SSE 엔드포인트

```python
import asyncio
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

import redis.asyncio as aioredis

router = APIRouter(prefix="/notifications", tags=["notifications"])


async def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


@router.post("/publish")
async def publish_notification(
    channel: str = "notifications",
    title: str = "알림",
    message: str = "",
    redis: aioredis.Redis = Depends(get_redis),
):
    """알림 발행 (관리자용)"""
    payload = json.dumps(
        {"title": title, "message": message},
        ensure_ascii=False,
    )

    # 현재 구독자 수 반환
    subscriber_count = await redis.publish(channel, payload)

    return {
        "published": True,
        "channel": channel,
        "subscribers_notified": subscriber_count,
    }


@router.get("/stream")
async def stream_notifications(request: Request):
    """SSE 스트림 (클라이언트용) — Redis Pub/Sub 구독"""

    async def event_generator():
        # Pub/Sub 전용 연결 생성 (기존 연결과 분리 필수)
        redis = aioredis.from_url(
            "redis://localhost:6379", decode_responses=True
        )
        pubsub = redis.pubsub()

        try:
            await pubsub.subscribe("notifications")

            while True:
                # 클라이언트 연결 끊김 확인
                if await request.is_disconnected():
                    break

                # 메시지 대기 (1초 타임아웃)
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )

                if message and message["type"] == "message":
                    data = message["data"]
                    # SSE 형식: "data: {json}\n\n"
                    yield f"data: {data}\n\n"

                # 연결 유지를 위한 heartbeat (15초마다)
                # 실제로는 별도 타이머로 관리
                await asyncio.sleep(0.1)

        finally:
            await pubsub.unsubscribe("notifications")
            await pubsub.aclose()
            await redis.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 버퍼링 비활성화
        },
    )


@router.get("/stream/{channel}")
async def stream_channel(channel: str, request: Request):
    """특정 채널의 SSE 스트림 (채널별 알림)"""

    async def event_generator():
        redis = aioredis.from_url(
            "redis://localhost:6379", decode_responses=True
        )
        pubsub = redis.pubsub()

        try:
            await pubsub.subscribe(channel)

            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break

                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await redis.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

### 클라이언트 측 SSE 연결 (JavaScript)

```javascript
// 브라우저에서 SSE 연결
const eventSource = new EventSource("/notifications/stream");

eventSource.onmessage = (event) => {
    const notification = JSON.parse(event.data);
    console.log("알림 수신:", notification.title, notification.message);
    // UI에 알림 표시
    showNotificationBanner(notification);
};

eventSource.onerror = (error) => {
    console.error("SSE 연결 오류:", error);
    // 자동 재연결됨 (EventSource 기본 동작)
};
```

### 주의사항

- **Pub/Sub 전용 연결**: Pub/Sub 모드에 들어간 Redis 연결은 `SUBSCRIBE`, `UNSUBSCRIBE`, `PING` 외의 명령을 실행할 수 없다. 반드시 일반 연결과 **별도의 연결**을 사용해야 한다.
- **메시지 유실**: Pub/Sub은 **Fire-and-Forget**이다. 구독자가 없는 시점에 발행된 메시지는 영구히 유실된다. 메시지 유실이 허용되지 않는 경우 Redis Streams(`XADD` / `XREAD`)를 사용한다.
- **Nginx 버퍼링**: Nginx가 SSE 응답을 버퍼링하면 실시간성이 깨진다. `X-Accel-Buffering: no` 헤더 또는 Nginx 설정(`proxy_buffering off`)으로 비활성화한다.
- **연결 정리**: 클라이언트가 연결을 끊으면 Pub/Sub 구독도 해제하고 Redis 연결도 닫아야 한다. `finally` 블록에서 반드시 정리한다.
- **확장성**: 수천 명이 동시 접속하면 서버당 수천 개의 SSE 연결이 유지된다. FastAPI(uvicorn)는 비동기이므로 연결 수 자체는 잘 견디지만, 메모리 사용량을 모니터링해야 한다.

---

## 핵심 요약

| 패턴 | Redis 자료형 | 핵심 명령 | 해결하는 문제 |
|------|------------|----------|-------------|
| **Cache-Aside** | String | SET EX, GET, DEL | DB 반복 조회 부하 |
| **최근 본 상품** | List | LPUSH, LTRIM, LRANGE, LREM | 고정 길이 이력 관리 |
| **분산 세션** | Hash | HSET, HGETALL, EXPIRE | 로드밸런서 환경 세션 불일치 |
| **카운팅** | String | INCR, DECR | 동시성 안전한 카운터 + DB 부하 감소 |
| **임시 인증번호** | String | SET EX, GET, DEL, TTL | 시간 제한 데이터 자동 만료 |
| **분산 락** | String | SET NX EX, DEL (Lua) | 분산 환경 동시성 제어 |
| **Rate Limiting** | String / Sorted Set | INCR EXPIRE / ZADD ZCARD | API 과부하 방지 |
| **실시간 랭킹** | Sorted Set | ZINCRBY, ZREVRANGE, ZREVRANK | 실시간 정렬 + 순위 조회 |
| **실시간 알림** | Pub/Sub | SUBSCRIBE, PUBLISH | 폴링 없는 즉시 알림 브로드캐스트 |

모든 패턴에서 공통적으로 중요한 원칙:

1. **Pipeline 활용**: 여러 명령을 묶어 네트워크 왕복을 줄인다.
2. **TTL 설정 필수**: 메모리는 유한하다. 모든 키에 적절한 만료 시간을 설정한다.
3. **원자성 활용**: `INCR`, `SET NX`, Lua Script 등 Redis의 원자적 연산으로 동시성 문제를 해결한다.
4. **Connection Pool 관리**: 연결을 재사용하고, 앱 종료 시 반드시 정리한다.

---

**다음**: [[Section 6 - Redis 운영 및 장애 대응]]
