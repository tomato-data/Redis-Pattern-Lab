# 캐시 무효화와 Cache Stampede 방어

대규모 트래픽 환경에서의 캐시 전략. 캐시를 "쓰는 것"보다 "지우는 것"이 어렵다.

---

## 1. 캐시 무효화 (Cache Invalidation)

### 핵심 문제

```
시점 T1: DB = "Alice", Cache = "Alice"  ← 일치
시점 T2: DB = "Bob"   (업데이트)
시점 T3: DB = "Bob",  Cache = "Alice"   ← 불일치! 언제 어떻게 처리할 것인가?
```

### 4가지 전략

#### 전략 1: TTL 기반

가장 단순. 시간이 지나면 자동 만료.

```redis
SET user:1:profile '{"name":"Alice"}' EX 300   # 5분 후 만료
```

- 장점: 구현 한 줄, 별도 무효화 로직 불필요
- 단점: TTL 동안 오래된 데이터 반환 가능
- 적합: 약간의 불일치 OK (랭킹, 통계, 추천 목록)

#### 전략 2: Write-Through

DB와 캐시를 **동시에** 갱신.

```python
async def update_user(user_id, data):
    await db.execute("UPDATE users SET ...")   # 1. DB 쓰기
    await redis.set(f"user:{user_id}", ...)    # 2. 캐시 쓰기
```

- 장점: 캐시가 항상 최신
- 단점: 쓰기 지연 증가 (DB + 캐시 모두 기다림)
- 적합: 읽기 >> 쓰기, 일관성 중요 (프로필, 설정값)

#### 전략 3: Write-Behind (Write-Back)

캐시에 먼저 쓰고, DB는 **비동기로 나중에** 반영.

```
쓰기 → Redis (즉시 응답) → 비동기 워커가 주기적으로 DB에 flush
```

- 장점: 쓰기 성능 극대화
- 단점: 캐시 장애 시 데이터 유실 위험
- 적합: 쓰기 빈번 + 유실 OK (조회수, 좋아요, 실시간 로그)
- 실습 연관: Step 05 (조회수 카운팅) — Redis INCR로 실시간 처리, DB는 동기화 전이라 0이었던 것

#### 전략 4: Cache-Aside + Event-based Invalidation

변경 시 **이벤트를 발행하여 캐시를 삭제**하고, 다음 읽기에서 재생성.

```
1. DB 쓰기 → 이벤트 발행 (Kafka 등)
2. 이벤트 소비자 → DEL cache:key (캐시 삭제)
3. 다음 읽기 → Cache Miss → DB 조회 → 캐시 재생성
```

- 핵심: 캐시를 **"갱신"이 아니라 "삭제"**한다
- 장점: 높은 일관성, 서비스 간 결합도 낮음
- 단점: 구현 복잡 (메시지 브로커 필요)
- 적합: 마이크로서비스, 높은 일관성 (결제, 재고, 권한)
- 실습 연관: Step 02에서 `update_product` 시 `redis.delete(cache_key)`한 것이 이 원칙

### 전략 선택 판단

```
데이터 불일치 허용 가능?
  ├─ Yes → TTL 기반
  └─ No → 쓰기 성능 중요?
           ├─ Yes → 데이터 유실 허용?
           │         ├─ Yes → Write-Behind
           │         └─ No  → Event-based
           └─ No → Write-Through
```

실무에서는 하나만 쓰지 않고 **데이터별로 조합**한다:

- 사용자 프로필 → Event-based
- 랭킹 데이터 → TTL 기반
- 조회수 → Write-Behind

### 전략 비교표

| 전략          | 일관성 | 쓰기 성능 | 구현 복잡도 | 데이터 유실 |
| ------------- | ------ | --------- | ----------- | ----------- |
| TTL 기반      | 낮음   | 높음      | 매우 낮음   | 없음        |
| Write-Through | 높음   | 낮음      | 낮음        | 없음        |
| Write-Behind  | 중간   | 매우 높음 | 높음        | 있음        |
| Event-based   | 높음   | 높음      | 매우 높음   | 낮음        |

---

## 2. Cache Stampede 방어

### Cache Stampede란?

인기 키의 캐시가 만료되는 순간, 동시에 다수의 요청이 DB로 몰려 과부하를 일으키는 현상.

```
정상: 요청 100개 → Cache Hit  → DB 부하 0
만료: 요청 100개 → Cache Miss → DB에 100개 동시 쿼리 → 장애!
```

### 발생 조건 (3가지 동시 충족)

| 조건         | 설명                               |
| ------------ | ---------------------------------- |
| 높은 트래픽  | 해당 키에 동시 요청이 많음         |
| TTL 만료     | 캐시 미스 발생                     |
| 높은 DB 비용 | 쿼리 시간이 걸려 그 사이 요청 누적 |

### 연쇄 장애 시나리오

```
인기 키 TTL 만료
→ 수백 요청이 동시에 DB로
→ DB 커넥션 풀 소진
→ 다른 정상 쿼리도 대기
→ API 타임아웃 → 사용자 재시도 → 부하 증가
→ 서비스 전체 장애
```

### 방어 전략 3가지

#### 전략 1: Locking (가장 일반적)

첫 번째 요청만 DB 조회, 나머지는 대기.

```python
lock_acquired = await redis.set(lock_key, "1", nx=True, ex=5)

if lock_acquired:
    profile = await fetch_from_db(user_id)
    await redis.set(cache_key, json.dumps(profile), ex=300)
    await redis.delete(lock_key)
else:
    await asyncio.sleep(0.05)  # 대기 후 캐시 재조회
```

- DB 동시 쿼리: 100 → **1개로 감소**
- 실습 연관: Step 07의 `SET NX EX`가 이 패턴

주의: 락 TTL은 DB 조회 시간의 **2~3배**로 설정할 것.

#### 전략 2: Probabilistic Early Expiration

TTL 만료 전 **확률적으로 미리 갱신**. 만료 시점에는 이미 캐시가 새 데이터로 채워져 있음.

```
TTL 300초:
  0초   → 갱신 확률 ~0%
  240초 → 갱신 확률 5%
  270초 → 갱신 확률 30%
  290초 → 갱신 확률 80%
```

- 장점: 락 없이 구현, 경합 없음
- 단점: 100% 보장 아님 (확률적)

#### 전략 3: Background Refresh

백그라운드 워커가 인기 키를 **주기적으로 갱신**. Cache Miss 자체가 발생하지 않음.

- 장점: Stampede 원천 차단
- 단점: 인기 키 목록 관리 필요

### 전략 비교

|                 | Locking        | Probabilistic | Background |
| --------------- | -------------- | ------------- | ---------- |
| Cache Miss      | 있음 (첫 요청) | 거의 없음     | 없음       |
| DB 동시 쿼리    | 1개            | 1~2개         | 워커만     |
| 클라이언트 지연 | 대기 있음      | 없음          | 없음       |
| 100% 방어       | O              | X (확률적)    | O          |

### 실무 권장: 레이어링

```
Layer 1 — Probabilistic Early Expiration
→ TTL 만료 전에 확률적으로 갱신하여 만료 자체를 방지

Layer 2 — Locking
→ 만약 Layer 1을 뚫고 만료가 발생하면 락으로 DB 동시 접근 1개로 제한
```

### TTL jitter도 방어 수단

Step 02 코드의 `jitter = random.randint(0, 60)`는 모든 캐시가 동시에 만료되는 것을 방지하는 장치다.

```python
await redis.set(cache_key, data, ex=CACHE_TTL + jitter)
# 300초 ~ 360초 사이로 분산되어 동시 만료 방지
```
