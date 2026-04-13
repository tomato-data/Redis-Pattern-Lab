
# Section 7: 대용량 서비스 설계 보너스 트랙

> 대규모 트래픽 환경에서의 캐시 무효화 전략, 캐시 스템피드 현상의 원인과 방어 패턴을 다룬다. 캐시를 "쓰는 것"보다 "지우는 것"이 어렵다는 사실을 체감하고, 실무에서 선택 가능한 전략의 트레이드오프를 이해한다.

---

## 41. 캐시 무효화(Cache Invalidation) 전략

### 캐시 무효화란?

> "There are only two hard things in Computer Science: cache invalidation and naming things."
> — Phil Karlton

캐시 무효화(Cache Invalidation)란, **원본 데이터가 변경되었을 때 캐시에 남아 있는 오래된 데이터를 어떻게 처리할 것인가**에 대한 문제다.

캐시를 도입하는 것 자체는 간단하다. 진짜 어려운 것은 **"언제, 어떻게 캐시를 지울 것인가"**다.

```
핵심 문제:

  시점 T1: DB = "Alice", Cache = "Alice"  ← 일치 ✅
  시점 T2: DB = "Bob"   (업데이트)
  시점 T3: DB = "Bob",  Cache = "Alice"   ← 불일치! ❌
                                              ↑
                                 캐시를 언제 지우거나 갱신할 것인가?
```

캐시가 오래된 데이터(Stale Data)를 반환하면, 사용자는 변경한 내용이 반영되지 않는 것처럼 느낀다. 반대로 캐시를 너무 공격적으로 무효화하면 캐시 히트율이 떨어져 성능 이점을 잃는다. 이 **일관성과 성능 사이의 균형**이 캐시 무효화의 본질이다.

---

### 전략 1: TTL 기반 (Time-based Expiration)

가장 단순한 전략. 캐시에 만료 시간(TTL)을 설정하고, 시간이 지나면 자동으로 삭제한다.

```
TTL 기반 무효화 흐름:

  Client → Cache 조회
             │
             ├─ Hit (TTL 내) → 캐시 데이터 반환 (최신이 아닐 수 있음)
             │
             └─ Miss (TTL 만료) → DB 조회 → 캐시에 저장 (새 TTL 설정)
```

```bash
# Redis에서 TTL 설정
SET user:1:profile '{"name":"Alice"}' EX 300    # 5분 후 자동 만료
```

**장점**:
- 구현이 가장 간단 — `SET key value EX seconds` 한 줄
- 별도의 무효화 로직이 불필요
- 최악의 경우에도 TTL 시간 후에는 최신 데이터로 갱신

**단점**:
- TTL 시간 동안은 오래된 데이터를 반환할 수 있음 (Eventual Consistency)
- TTL이 짧으면 캐시 히트율 하락, 길면 데이터 불일치 지속 시간 증가
- 데이터 변경 빈도와 무관하게 일률적으로 만료

**적합한 경우**: 약간의 데이터 불일치를 허용할 수 있는 경우 (랭킹, 통계, 추천 목록 등)

---

### 전략 2: Write-Through

데이터를 쓸 때 **DB와 캐시를 동시에 업데이트**하는 전략. 캐시가 항상 최신 상태를 유지한다.

```
Write-Through 흐름:

  쓰기 요청 (name = "Bob")
       │
       ▼
  ┌─────────────────────────────────────┐
  │         Application Server          │
  │                                     │
  │  1. DB에 쓰기  ──→  PostgreSQL      │
  │  2. 캐시 갱신  ──→  Redis           │
  │                                     │
  │  두 작업이 모두 완료되면 응답 반환     │
  └─────────────────────────────────────┘

  읽기 요청:
  Client → Cache 조회 → 항상 최신 데이터 반환 ✅
```

```python
# Write-Through 의사 코드
async def update_user(user_id: str, data: dict):
    # 1. DB 업데이트
    await db.execute("UPDATE users SET name = $1 WHERE id = $2", data["name"], user_id)

    # 2. 캐시도 즉시 갱신
    await redis.set(f"user:{user_id}:profile", json.dumps(data), ex=300)

    return {"status": "ok"}
```

**장점**:
- 캐시가 항상 최신 상태 — 읽기 시 일관성 보장
- 읽기 시 Cache Miss가 거의 발생하지 않음

**단점**:
- **쓰기 지연 증가** — DB 쓰기 + 캐시 쓰기를 모두 기다려야 응답
- **읽히지 않는 데이터도 캐시**에 저장 — 메모리 낭비
- DB와 캐시 사이의 원자성 보장이 어려움 (DB 성공, 캐시 실패 시?)

**적합한 경우**: 읽기가 쓰기보다 훨씬 많고, 캐시 일관성이 중요한 경우 (사용자 프로필, 설정값)

---

### 전략 3: Write-Behind (Write-Back)

**캐시에 먼저 쓰고**, 일정 시간 후 비동기로 DB에 반영하는 전략. 쓰기 성능을 극대화한다.

```
Write-Behind 흐름:

  쓰기 요청 (name = "Bob")
       │
       ▼
  ┌──────────────────────────────────────────────┐
  │           Application Server                  │
  │                                               │
  │  1. 캐시에 즉시 쓰기 ──→ Redis (즉시 응답)     │
  │                                               │
  │  2. 비동기 워커가 주기적으로                     │
  │     캐시 변경분을 DB에 반영 ──→ PostgreSQL      │
  │                                               │
  │     ┌─────────────────────────────────┐       │
  │     │  변경 큐: user:1, user:5, ...   │       │
  │     │  매 1초마다 배치로 DB에 flush    │       │
  │     └─────────────────────────────────┘       │
  └──────────────────────────────────────────────┘
```

**장점**:
- **쓰기 성능 극대화** — 캐시 쓰기는 마이크로초 단위
- 여러 쓰기를 모아 배치 처리 가능 — DB 부하 감소
- 동일 키에 대한 연속 쓰기를 병합 가능

**단점**:
- **캐시 장애 시 데이터 유실 위험** — DB에 아직 반영되지 않은 변경이 소실
- 구현 복잡도 높음 — 비동기 워커, 변경 추적, 실패 재시도 로직 필요
- 캐시와 DB 사이의 일시적 불일치 발생

**적합한 경우**: 쓰기가 매우 빈번하고, 일부 데이터 유실이 허용되는 경우 (조회수, 좋아요, 실시간 로그)

---

### 전략 4: Cache-Aside + Event-based Invalidation

가장 견고한 전략. 데이터 변경 시 **이벤트를 발행하여 캐시를 삭제**하고, 다음 읽기에서 캐시를 재생성한다.

```
Cache-Aside + Event-based Invalidation 흐름:

  1. 쓰기 요청
       │
       ▼
  ┌──────────────────────────────────────────────┐
  │  Application Server                           │
  │                                               │
  │  ① DB에 쓰기 ──→ PostgreSQL                    │
  │  ② 이벤트 발행 ──→ Message Broker (Kafka 등)   │
  └──────────────────────────────────────────────┘

  2. 이벤트 소비
       │
       ▼
  ┌──────────────────────────────────────────────┐
  │  Cache Invalidation Worker                    │
  │                                               │
  │  ③ 이벤트 수신 ──→ "user:1 변경됨"             │
  │  ④ 캐시 삭제 ──→ DEL user:1:profile            │
  └──────────────────────────────────────────────┘

  3. 다음 읽기 요청
       │
       ▼
  ┌──────────────────────────────────────────────┐
  │  Application Server                           │
  │                                               │
  │  ⑤ Cache Miss → DB 조회 → 캐시 재생성          │
  └──────────────────────────────────────────────┘
```

**핵심 포인트**: 캐시를 "갱신"하는 것이 아니라 **"삭제"**한다. 갱신은 경합 조건이 발생할 수 있지만, 삭제 후 재생성은 항상 최신 데이터를 보장한다.

**장점**:
- 높은 일관성 — 데이터 변경 즉시 캐시 무효화
- 서비스 간 결합도 낮음 — 이벤트 기반으로 분리
- 읽히지 않는 데이터를 캐시하지 않음

**단점**:
- 구현 복잡도 높음 — 메시지 브로커, 이벤트 소비자 필요
- 이벤트 유실 시 캐시 불일치 가능 — 보완으로 TTL 병행 사용
- 삭제 직후 동시 읽기 시 Cache Stampede 발생 가능

**적합한 경우**: 마이크로서비스 아키텍처, 높은 일관성이 필요한 경우 (결제 정보, 재고, 사용자 권한)

---

### 전략 선택 가이드: 트레이드오프 비교

| 전략 | 일관성 | 쓰기 성능 | 읽기 성능 | 구현 복잡도 | 데이터 유실 위험 |
|------|--------|----------|----------|------------|----------------|
| **TTL 기반** | 낮음 (TTL 내 stale) | 높음 | 높음 | 매우 낮음 | 없음 |
| **Write-Through** | 높음 | 낮음 (동기 쓰기) | 매우 높음 | 낮음 | 없음 |
| **Write-Behind** | 중간 | 매우 높음 | 매우 높음 | 높음 | 있음 (캐시 장애) |
| **Event-based** | 높음 | 높음 | 높음 | 매우 높음 | 낮음 (이벤트 유실) |

```
전략 선택 판단 흐름:

  Q1: 데이터 불일치를 허용할 수 있는가?
       │
       ├─ Yes → TTL 기반 (가장 단순)
       │
       └─ No → Q2: 쓰기 성능이 중요한가?
                    │
                    ├─ Yes → Q3: 데이터 유실이 허용되는가?
                    │         │
                    │         ├─ Yes → Write-Behind
                    │         └─ No  → Event-based Invalidation
                    │
                    └─ No → Write-Through
```

> 실무에서는 하나의 전략만 쓰는 것이 아니라, **데이터 특성에 따라 전략을 조합**한다. 예: 사용자 프로필은 Event-based, 랭킹 데이터는 TTL 기반, 조회수는 Write-Behind.

---

## 42. 캐시 스템피드(Cache Stampede) 방어 전략

### Cache Stampede란?

Cache Stampede(= Thundering Herd, Cache Avalanche)는 **인기 키의 캐시가 만료되는 순간, 동시에 다수의 요청이 DB로 몰려 과부하를 일으키는 현상**이다.

```
정상 상태 (캐시 존재):

  요청 1 ──→ Cache Hit ──→ 즉시 응답 ✅
  요청 2 ──→ Cache Hit ──→ 즉시 응답 ✅
  요청 3 ──→ Cache Hit ──→ 즉시 응답 ✅
  ...
  요청 100 ──→ Cache Hit ──→ 즉시 응답 ✅

  DB 부하: 0  ← Redis가 모든 읽기를 흡수
```

```
TTL 만료 시점 (Cache Stampede 발생):

  요청 1 ──→ Cache Miss ──→ DB 조회 ──→ 캐시 저장
  요청 2 ──→ Cache Miss ──→ DB 조회 ──→ 캐시 저장 (중복!)
  요청 3 ──→ Cache Miss ──→ DB 조회 ──→ 캐시 저장 (중복!)
  요청 4 ──→ Cache Miss ──→ DB 조회 ──→ 캐시 저장 (중복!)
  ...
  요청 100 ──→ Cache Miss ──→ DB 조회 ──→ DB 과부하! 💥

  DB 부하: 100 동시 쿼리  ← 원래는 0이었는데!
```

### 왜 위험한가?

문제는 단순히 "DB 쿼리가 많아진다"가 아니다. **연쇄 장애(Cascading Failure)** 로 이어질 수 있다.

```
연쇄 장애 시나리오:

  ① 인기 키 TTL 만료
       │
       ▼
  ② 수백 요청이 동시에 DB로
       │
       ▼
  ③ DB 커넥션 풀 소진
       │
       ▼
  ④ 다른 정상 쿼리도 대기 (커넥션 부족)
       │
       ▼
  ⑤ API 타임아웃 → 사용자 재시도 → 부하 증가
       │
       ▼
  ⑥ 서비스 전체 장애
```

### 발생 조건

Cache Stampede는 다음 **세 가지 조건이 동시에 충족**될 때 발생한다:

| 조건 | 설명 |
|------|------|
| 높은 트래픽 | 해당 키에 대한 동시 요청이 많음 |
| TTL 만료 | 캐시가 만료되어 Miss 발생 |
| 높은 DB 조회 비용 | DB 쿼리 실행에 시간이 걸려 그 사이 추가 요청이 누적 |

트래픽이 적으면 Miss가 발생해도 1~2개 요청만 DB에 도달하므로 문제 없다. **초당 수천 요청이 몰리는 인기 키**에서만 위험하다.

---

### 방어 전략 개요

| 전략 | 핵심 아이디어 | 복잡도 |
|------|-------------|--------|
| **Locking** | 첫 번째 요청만 DB 조회, 나머지는 대기 | 중간 |
| **Probabilistic Early Expiration** | TTL 만료 전 확률적으로 미리 갱신 | 낮음 |
| **Background Refresh** | 백그라운드에서 주기적으로 캐시 갱신 | 중간 |

---

### 방어 전략 1: Locking (뮤텍스 방식)

첫 번째 요청만 DB에서 데이터를 가져오고, 나머지 요청은 캐시가 채워질 때까지 대기한다. 상세 구현은 다음 강의(43번)에서 다룬다.

```
Locking 방어 흐름:

  요청 1 ──→ Cache Miss ──→ 락 획득 ✅ ──→ DB 조회 ──→ 캐시 저장 ──→ 락 해제
  요청 2 ──→ Cache Miss ──→ 락 획득 ❌ ──→ 대기... ──→ 캐시 Hit ──→ 응답
  요청 3 ──→ Cache Miss ──→ 락 획득 ❌ ──→ 대기... ──→ 캐시 Hit ──→ 응답
  ...
  요청 100 ──→ Cache Miss ──→ 락 획득 ❌ ──→ 대기... ──→ 캐시 Hit ──→ 응답

  DB 부하: 1 쿼리  ← 100에서 1로 감소!
```

---

### 방어 전략 2: Probabilistic Early Expiration (확률적 조기 갱신)

TTL이 만료되기 **전에** 확률적으로 캐시를 미리 갱신한다. TTL 만료 시점에 Cache Miss가 발생하지 않으므로 Stampede 자체를 예방한다.

```
Probabilistic Early Expiration 개념:

  TTL 설정: 300초 (5분)

  시간 경과:
  0초 ──── 240초 ──── 270초 ──── 290초 ──── 300초 (만료)
  │         │          │          │          │
  │         │          │          ├─ 갱신 확률 80%
  │         │          ├─ 갱신 확률 30%
  │         ├─ 갱신 확률 5%
  ├─ 갱신 확률 ~0%
  │
  └── TTL이 얼마 남지 않을수록 갱신 확률 증가
```

#### 갱신 판단 공식

```
currentTime - (timeToCompute * beta * log(random())) > expiry
```

| 변수 | 의미 |
|------|------|
| `currentTime` | 현재 시각 |
| `timeToCompute` | DB에서 데이터를 가져오는 데 걸리는 시간 |
| `beta` | 확률 조정 파라미터 (기본값 1.0, 높을수록 조기 갱신 빈번) |
| `random()` | 0~1 사이의 랜덤 값 |
| `expiry` | 캐시 만료 시각 |

```python
# Probabilistic Early Expiration 의사 코드
import math
import random
import time

def should_refresh_early(expiry: float, time_to_compute: float, beta: float = 1.0) -> bool:
    """TTL 만료 전에 캐시를 갱신할지 확률적으로 판단"""
    now = time.time()
    random_value = random.random()

    # log(random())은 항상 음수 → - 를 붙여 양수로 만듦
    # TTL이 가까울수록, time_to_compute가 클수록 갱신 확률 증가
    threshold = now - (time_to_compute * beta * math.log(random_value))

    return threshold > expiry
```

**핵심 원리**: 트래픽이 많을수록 `should_refresh_early`를 호출하는 빈도가 높아지므로, **누군가 한 명이 만료 전에 갱신할 확률이 자연스럽게 높아진다**. TTL 만료 시점에는 이미 캐시가 새로운 데이터로 채워져 있을 가능성이 크다.

**장점**:
- 락 없이 구현 가능 — 경합 없음
- 구현 코드 단순

**단점**:
- 100% 보장은 아님 — 운이 나쁘면 갱신 없이 만료될 수 있음
- 불필요한 조기 갱신이 발생할 수 있음

---

### 방어 전략 3: Background Refresh (백그라운드 갱신)

애플리케이션 요청과 무관하게 **백그라운드 워커가 주기적으로 인기 키를 갱신**한다.

```
Background Refresh 흐름:

  ┌─────────────────────────────────┐
  │     Background Worker           │
  │                                 │
  │  매 TTL/2 마다:                  │
  │  ① 인기 키 목록 순회             │
  │  ② DB에서 최신 데이터 조회        │
  │  ③ 캐시 갱신 (새 TTL 설정)       │
  │                                 │
  │  → TTL이 만료될 일 자체가 없음    │
  └─────────────────────────────────┘

  Client 요청:
  요청 1 ──→ Cache Hit ──→ 항상 즉시 응답 ✅
  요청 2 ──→ Cache Hit ──→ 항상 즉시 응답 ✅
```

**장점**:
- Cache Miss 자체가 발생하지 않음 — Stampede 원천 차단
- 클라이언트 요청 경로에 추가 로직 없음

**단점**:
- 인기 키 목록을 관리해야 함
- 읽히지 않는 키도 갱신할 수 있음 — 자원 낭비
- 워커 장애 시 갱신 중단 위험

---

### 세 가지 전략 비교

| 비교 항목 | Locking | Probabilistic Early Expiration | Background Refresh |
|----------|---------|-------------------------------|-------------------|
| **Cache Miss 발생** | 있음 (첫 요청) | 거의 없음 | 없음 |
| **DB 동시 쿼리** | 1개로 제한 | 1~2개 (확률적) | 워커만 조회 |
| **클라이언트 지연** | 대기 시간 있음 | 없음 | 없음 |
| **구현 복잡도** | 중간 (락 관리) | 낮음 (수식만) | 중간 (워커 관리) |
| **100% 방어 보장** | 예 | 아니오 (확률적) | 예 (워커 정상 시) |
| **적합한 경우** | 범용, 가장 일반적 | 단순 구현 원할 때 | 인기 키가 명확할 때 |

---

## 43. 캐시 스템피드 방어 — Locking

### Locking 전략 상세

Locking(뮤텍스 방식)은 Cache Stampede 방어의 **가장 일반적이고 확실한 전략**이다. 핵심 아이디어는 단순하다: **첫 번째 요청만 DB에서 데이터를 가져오고, 나머지 요청은 캐시가 채워질 때까지 대기한다.**

Redis의 `SET NX` 명령어를 분산 락으로 활용한다.

```bash
# 락 획득 시도
SET lock:user:1:profile 1 NX EX 5
# NX: 키가 존재하지 않을 때만 설정 (= 락 획득)
# EX 5: 5초 후 자동 만료 (= 데드락 방지)
```

| 옵션 | 역할 |
|------|------|
| `NX` | 이미 락이 존재하면 실패 반환 — 첫 번째 요청만 성공 |
| `EX 5` | 락 소유자가 장애로 해제하지 못해도 5초 후 자동 해제 |

---

### 구현 흐름

```
Locking 기반 Cache-Aside 전체 흐름:

  요청 도착
       │
       ▼
  ┌─────────────┐
  │ 캐시 조회    │
  └──────┬──────┘
         │
    ┌────┴────┐
    │         │
  Hit       Miss
    │         │
    ▼         ▼
  응답    ┌──────────────┐
  반환    │ 락 획득 시도   │
          │ SET NX EX 5  │
          └──────┬───────┘
                 │
           ┌─────┴─────┐
           │           │
         성공         실패
           │           │
           ▼           ▼
    ┌────────────┐  ┌───────────────┐
    │ DB 조회    │  │ sleep(0.05~   │
    │ 캐시 저장  │  │       0.1초)   │
    │ 락 해제    │  │               │
    └─────┬──────┘  └───────┬───────┘
          │                 │
          ▼                 └──→ 처음으로 (캐시 재조회)
        응답 반환
```

단계별 정리:

```
1. 캐시 조회 → Miss 확인
2. 락 획득 시도 (SET lock:{key} 1 NX EX 5)
3-A. 락 성공:
     → DB에서 데이터 조회
     → 결과를 캐시에 저장 (SET key value EX TTL)
     → 락 해제 (DEL lock:{key})
     → 데이터 반환

3-B. 락 실패:
     → sleep(0.05 ~ 0.1초)
     → 1번으로 돌아감 (캐시 재조회)
     → 이 시점에서 캐시가 채워져 있으면 Hit → 응답
```

---

### Python/FastAPI 코드 예시

```python
import asyncio
import json
from redis.asyncio import Redis

redis = Redis(host="localhost", port=6379, decode_responses=True)

CACHE_TTL = 300        # 캐시 TTL: 5분
LOCK_TTL = 5           # 락 TTL: 5초 (DB 조회보다 넉넉하게)
RETRY_DELAY = 0.05     # 재시도 대기: 50ms
MAX_RETRIES = 100      # 최대 재시도 횟수


async def get_user_profile(user_id: str) -> dict:
    cache_key = f"user:{user_id}:profile"
    lock_key = f"lock:{cache_key}"

    for attempt in range(MAX_RETRIES):
        # 1. 캐시 조회
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # 2. Cache Miss → 락 획득 시도
        lock_acquired = await redis.set(lock_key, "1", nx=True, ex=LOCK_TTL)

        if lock_acquired:
            try:
                # 3-A. 락 성공 → DB에서 데이터 조회
                profile = await fetch_from_db(user_id)

                # 캐시에 저장
                await redis.set(cache_key, json.dumps(profile), ex=CACHE_TTL)

                return profile
            finally:
                # 락 해제 (성공이든 실패든)
                await redis.delete(lock_key)
        else:
            # 3-B. 락 실패 → 짧은 대기 후 재시도
            await asyncio.sleep(RETRY_DELAY)

    # 모든 재시도 실패 → fallback
    raise Exception("Cache stampede: max retries exceeded")


async def fetch_from_db(user_id: str) -> dict:
    """실제 DB 조회 (의사 코드)"""
    # await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    return {"id": user_id, "name": "Alice", "email": "alice@example.com"}
```

---

### 주의사항

#### 1. 락 TTL 설정

락 TTL은 **DB 조회 시간보다 넉넉하게** 설정해야 한다. DB 조회에 2초 걸리는데 락 TTL이 1초면, 락이 먼저 풀려 다른 요청이 중복 조회한다.

```
잘못된 설정:
  DB 조회 시간: ~2초
  락 TTL: 1초

  요청 1 ──→ 락 획득 ──→ DB 조회 시작...
                                   │
  1초 후: 락 자동 만료!              │  ← 아직 DB 조회 중
                                   │
  요청 2 ──→ 락 획득(!) ──→ DB 조회  │  ← 중복 조회 발생!
                                   │
  요청 1 ──→ ... ──→ DB 조회 완료 ──→ 캐시 저장


올바른 설정:
  DB 조회 시간: ~2초
  락 TTL: 5초 (2~3배 여유)
```

#### 2. 데드락 방지

`NX` + `EX` 조합이 데드락을 방지한다:
- **`NX`**: 이미 락이 존재하면 다른 요청이 획득 불가 — 동시 접근 차단
- **`EX`**: 락 소유자가 크래시하거나 `DEL`을 실행하지 못해도 일정 시간 후 자동 해제

```
데드락 방지 시나리오:

  요청 1 ──→ 락 획득 ──→ DB 조회 중 서버 크래시 💥
                         │
                         └─ 락 해제 코드 실행 안 됨!

  BUT: EX 5 설정 → 5초 후 락 자동 만료

  요청 2 ──→ (5초 후) 락 획득 성공 ──→ 정상 처리
```

#### 3. Stale Cache Fallback

락 대기 중인 요청에게 **이전 캐시 데이터(stale cache)를 반환하는 전략**도 고려할 수 있다. 약간 오래된 데이터라도 응답하는 것이 대기하는 것보다 나은 경우가 많다.

```python
async def get_user_profile_with_fallback(user_id: str) -> dict:
    cache_key = f"user:{user_id}:profile"
    stale_key = f"stale:{cache_key}"
    lock_key = f"lock:{cache_key}"

    # 1. 캐시 조회
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 2. 락 획득 시도
    lock_acquired = await redis.set(lock_key, "1", nx=True, ex=LOCK_TTL)

    if lock_acquired:
        try:
            profile = await fetch_from_db(user_id)
            await redis.set(cache_key, json.dumps(profile), ex=CACHE_TTL)
            # stale cache도 함께 저장 (TTL을 더 길게)
            await redis.set(stale_key, json.dumps(profile), ex=CACHE_TTL * 2)
            return profile
        finally:
            await redis.delete(lock_key)
    else:
        # 3. 락 실패 → stale cache 반환 (대기 대신)
        stale = await redis.get(stale_key)
        if stale:
            return json.loads(stale)  # 오래된 데이터라도 응답

        # stale cache도 없으면 대기
        await asyncio.sleep(RETRY_DELAY)
        return await get_user_profile_with_fallback(user_id)
```

---

### Locking vs Probabilistic Early Expiration 비교

| 비교 항목 | Locking | Probabilistic Early Expiration |
|----------|---------|-------------------------------|
| **방어 보장** | 100% (락으로 차단) | 확률적 (높은 트래픽에서 거의 100%) |
| **구현 복잡도** | 중간 (락 관리, 재시도 로직) | 낮음 (수식 한 줄) |
| **클라이언트 지연** | 락 대기 시간 발생 | 없음 |
| **추가 Redis 부하** | 락 키 SET/DEL | 없음 (기존 로직에 수식만 추가) |
| **Cache Miss** | 첫 요청만 발생 | 이론상 발생 안 함 (사전 갱신) |
| **적합한 트래픽** | 모든 규모 | 높은 트래픽 (확률이 작동하려면) |
| **실무 채택** | 가장 일반적 | 보조 전략으로 병행 |

**실무 권장 조합**: Probabilistic Early Expiration으로 대부분의 Stampede를 사전에 방지하고, 만약 만료가 발생하더라도 Locking으로 DB 동시 접근을 차단한다. 두 전략을 **레이어링**하면 가장 견고하다.

```
레이어링 방어:

  Layer 1 — Probabilistic Early Expiration
  → TTL 만료 전에 확률적으로 갱신하여 만료 자체를 방지

  Layer 2 — Locking
  → 만약 Layer 1을 뚫고 만료가 발생하면
     락으로 DB 동시 접근을 1개로 제한
```

---

## 핵심 요약

1. **캐시 무효화의 본질**: 캐시를 도입하는 것보다 "언제, 어떻게 지울 것인가"가 진짜 어려운 문제. 일관성, 성능, 복잡도 사이의 트레이드오프를 이해하고 데이터 특성에 맞는 전략을 선택해야 한다.
2. **4가지 무효화 전략**: TTL 기반(단순), Write-Through(일관성), Write-Behind(쓰기 성능), Event-based(견고함). 실무에서는 데이터별로 조합하여 사용한다.
3. **Cache Stampede**: 인기 키 만료 시 동시 요청이 DB로 쏠리는 현상. 높은 트래픽 + TTL 만료 + 높은 DB 비용이 동시에 충족되면 발생하며, 연쇄 장애로 이어질 수 있다.
4. **Stampede 방어 3종**: Locking(확실한 차단), Probabilistic Early Expiration(사전 예방), Background Refresh(원천 차단). Locking이 가장 일반적이며, Probabilistic과 레이어링하면 가장 견고하다.
5. **Locking 구현 핵심**: `SET lock:{key} 1 NX EX 5`로 첫 요청만 통과시키고, 나머지는 짧은 sleep + 재시도로 캐시가 채워지기를 기다린다. 락 TTL은 DB 조회 시간의 2~3배로 설정한다.

---

**로드맵으로 돌아가기**: [[Redis 마스터 로드맵]]