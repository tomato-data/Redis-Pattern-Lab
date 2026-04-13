
# Section 3: Redis 자료형과 필수 명령어

> Redis의 5대 핵심 자료형(String, List, Set, Hash, Sorted Set)과 각 자료형의 필수 명령어를 다룬다. 단순 문법 나열이 아니라, 각 자료형이 실무에서 어떤 문제를 해결하는지 맥락과 함께 학습한다.

---

## 11. String 타입: 가장 기본이 되는 데이터 타입

### 바이너리 세이프란?

Redis의 String은 일반적인 프로그래밍 언어의 "문자열"보다 훨씬 넓은 개념이다. **바이너리 세이프(Binary Safe)** 하므로 텍스트뿐 아니라 이미지, 직렬화된 객체, 정수 등 어떤 바이너리 데이터든 저장할 수 있다.

```
┌──────────────────────────────────────────────────┐
│              Redis String이 담을 수 있는 것         │
│                                                  │
│   "hello"           → 일반 텍스트                  │
│   "12345"           → 숫자 (내부적으로 정수 인코딩)   │
│   "{\"name\":\"A\"}" → JSON 문자열                 │
│   <JPEG binary>     → 이미지 바이너리               │
│   <serialized obj>  → 직렬화된 객체                 │
│                                                  │
│   최대 크기: 512MB                                 │
└──────────────────────────────────────────────────┘
```

### 기본 명령어: SET / GET / MSET / MGET

```redis
# 단일 키-값 설정 및 조회
SET user:1:name "Alice"
GET user:1:name
# → "Alice"

# 여러 키를 한 번에 설정 (네트워크 왕복 1회로 줄임)
MSET user:1:name "Alice" user:1:age "30" user:1:city "Seoul"

# 여러 키를 한 번에 조회
MGET user:1:name user:1:age user:1:city
# → 1) "Alice"
# → 2) "30"
# → 3) "Seoul"
```

> **MSET/MGET의 가치**: 키 3개를 개별 SET/GET으로 처리하면 네트워크 왕복 3회, MSET/MGET으로 처리하면 왕복 1회. 키가 많을수록 성능 차이가 극대화된다.

### 원자적 카운터: INCR / DECR / INCRBY / DECRBY

Redis가 단순 캐시를 넘어 **실시간 카운터**로 활용되는 핵심 기능이다. 이 명령어들은 **원자적(Atomic)** 으로 실행되므로, 여러 클라이언트가 동시에 호출해도 값이 정확하게 증감한다.

```redis
SET page:home:views 0

INCR page:home:views      # → 1
INCR page:home:views      # → 2
INCR page:home:views      # → 3

DECR page:home:views      # → 2

INCRBY page:home:views 10 # → 12
DECRBY page:home:views 5  # → 7
```

```
왜 원자적이어야 하는가?

비원자적 연산 (애플리케이션에서 직접 처리):
  Thread A: GET counter → 10
  Thread B: GET counter → 10       ← 같은 값을 읽음
  Thread A: SET counter 11
  Thread B: SET counter 11         ← 기대값 12인데 11!

원자적 연산 (Redis INCR):
  Thread A: INCR counter → 11
  Thread B: INCR counter → 12     ← 정확!
```

### 문자열 조작: APPEND / STRLEN

```redis
SET greeting "Hello"
APPEND greeting " World"
GET greeting
# → "Hello World"

STRLEN greeting
# → 11
```

### String 타입 실무 활용

| 활용 사례 | 패턴 | 예시 |
|-----------|------|------|
| **캐시** | SET + TTL | DB 쿼리 결과를 JSON으로 캐싱 |
| **카운터** | INCR / INCRBY | 페이지 조회수, API 호출 횟수 |
| **플래그** | SET + NX | 분산 락, 중복 요청 방지 |
| **세션 토큰** | SET + EX | 로그인 토큰 저장 (만료 포함) |
| **Rate Limiting** | INCR + EXPIRE | 분당 API 호출 제한 |

---

## 12. SET 명령어 핵심 옵션: EX/PX, NX/XX

### 만료 시간 옵션: EX / PX

SET 명령어 자체에 만료 시간을 지정할 수 있다. 별도의 EXPIRE 호출 없이 **한 번의 원자적 명령**으로 값 설정과 만료를 동시에 처리한다.

```redis
# EX: 초 단위 만료
SET session:abc123 "user:1" EX 3600
# → 3600초(1시간) 후 자동 삭제

# PX: 밀리초 단위 만료
SET rate:api:user1 "1" PX 1000
# → 1000밀리초(1초) 후 자동 삭제
```

| 옵션 | 단위 | 사용 예 |
|------|------|---------|
| **EX seconds** | 초 | 세션(3600), 캐시(300) |
| **PX milliseconds** | 밀리초 | Rate Limit(1000), 짧은 TTL |

### NX: 키가 존재하지 않을 때만 SET — 분산 락의 기초

NX 옵션은 Redis에서 가장 중요한 옵션 중 하나다. **키가 존재하지 않을 때만** 값을 설정하므로, 여러 클라이언트가 동시에 같은 키를 선점하려 할 때 **오직 하나만 성공**한다.

```redis
# 첫 번째 클라이언트: 성공
SET lock:order:123 "worker-A" NX
# → OK

# 두 번째 클라이언트: 실패 (키가 이미 존재)
SET lock:order:123 "worker-B" NX
# → (nil)
```

### XX: 키가 존재할 때만 SET — 업데이트 전용

XX는 NX의 반대다. 키가 **이미 존재할 때만** 값을 갱신한다. 실수로 새 키를 생성하는 것을 방지하는 안전장치 역할을 한다.

```redis
# 키가 없으면 실패
SET user:1:status "active" XX
# → (nil)  (user:1:status가 없으므로)

# 먼저 키를 생성
SET user:1:status "inactive"

# 이제 XX로 업데이트 가능
SET user:1:status "active" XX
# → OK
```

### 분산 락 원자적 획득 패턴

실무에서 가장 많이 쓰이는 패턴이다. EX와 NX를 조합하면 **안전한 분산 락**을 구현할 수 있다.

```redis
# 분산 락 획득: "60초 동안 유효한 락을 원자적으로 획득"
SET lock:payment:order-789 "worker-A-uuid" EX 60 NX
```

```
분산 락 흐름:

  Worker A                          Redis                         Worker B
     │                                │                              │
     ├── SET lock EX 60 NX ──────────▶│                              │
     │                                │◀── SET lock EX 60 NX ───────┤
     │◀── OK (락 획득 성공) ───────────│                              │
     │                                │── (nil) (이미 존재) ─────────▶│
     │                                │                              │
     │   작업 수행 (최대 60초)          │           락 획득 실패,        │
     │                                │           재시도 또는 대기      │
     │                                │                              │
     ├── DEL lock ───────────────────▶│                              │
     │                                │   (락 해제, 60초 내 완료)      │
```

**왜 EX와 NX를 함께 써야 하는가?**

- NX만 사용: 워커가 크래시하면 락이 영원히 남아 **데드락** 발생
- EX만 사용: 여러 워커가 동시에 락을 획득하여 **경쟁 조건** 발생
- EX + NX: 원자적으로 "없으면 설정 + 자동 만료"를 보장

### SETNX vs SET ... NX

```redis
# 레거시 명령어 (별도의 만료 설정 필요)
SETNX lock:resource "owner-1"
EXPIRE lock:resource 60
# ⚠️ 문제: SETNX와 EXPIRE 사이에 크래시하면 만료 없는 락이 남음

# 권장 방식 (원자적 — 한 명령으로 모든 것 처리)
SET lock:resource "owner-1" EX 60 NX
# ✅ 설정과 만료가 원자적으로 처리됨
```

| 방식 | 원자성 | 안전성 | 권장 |
|------|--------|--------|------|
| `SETNX` + `EXPIRE` | 두 명령 분리 | 크래시 시 데드락 가능 | 비권장 |
| `SET ... EX ... NX` | 단일 명령 | 항상 안전 | 권장 |

---

## 13. 만료 시간 설정: EXPIRE와 TTL

### 만료 시간 설정 명령어

이미 존재하는 키에 만료 시간을 사후에 설정하거나 확인하는 명령어들이다.

```redis
SET user:1:cache '{"name":"Alice","age":30}'

# 초 단위 만료 설정
EXPIRE user:1:cache 300
# → 300초 후 자동 삭제

# 밀리초 단위 만료 설정
PEXPIRE user:1:cache 300000
# → 300,000밀리초(300초) 후 자동 삭제
```

### TTL / PTTL: 남은 시간 확인

```redis
SET session:xyz "data" EX 120

# 초 단위 남은 시간
TTL session:xyz
# → 118  (약 2초 경과)

# 밀리초 단위 남은 시간
PTTL session:xyz
# → 117500
```

**TTL 반환값의 의미**:

| 반환값 | 의미 |
|--------|------|
| **양수** | 남은 초(또는 밀리초) |
| **-1** | 키는 존재하지만 만료가 설정되지 않음 (영구) |
| **-2** | 키 자체가 존재하지 않음 |

```redis
SET permanent:key "forever"
TTL permanent:key
# → -1  (만료 없음)

TTL nonexistent:key
# → -2  (키 없음)
```

### PERSIST: 만료 제거

```redis
SET temp:data "value" EX 60
TTL temp:data
# → 60

PERSIST temp:data
TTL temp:data
# → -1  (만료가 제거되어 영구 키가 됨)
```

### Lazy Expiration vs Active Expiration

Redis는 만료된 키를 즉시 삭제하지 않는다. 두 가지 메커니즘을 조합하여 만료를 처리한다.

```
┌───────────────────────────────────────────────────────────────┐
│                    Redis 만료 처리 메커니즘                      │
│                                                               │
│   1. Lazy Expiration (수동적)                                  │
│   ──────────────────────────                                  │
│   클라이언트가 키에 접근할 때 만료 여부를 확인한다.                  │
│   만료되었으면 그때 삭제하고 nil을 반환한다.                       │
│                                                               │
│   GET expired:key                                             │
│     → Redis 내부: "이 키 만료됐네? 삭제하고 nil 반환"              │
│                                                               │
│   장점: CPU 부하 없음                                           │
│   단점: 아무도 접근하지 않는 키는 메모리에 계속 남음                 │
│                                                               │
│   2. Active Expiration (능동적)                                 │
│   ──────────────────────────                                  │
│   Redis가 초당 10회, 만료 키가 있는 공간에서 무작위로               │
│   20개 키를 샘플링하여 만료된 키를 삭제한다.                       │
│   만료 비율이 25% 이상이면 즉시 반복 실행한다.                     │
│                                                               │
│   장점: 아무도 접근하지 않는 만료 키도 정리됨                      │
│   단점: 약간의 CPU 사용                                         │
└───────────────────────────────────────────────────────────────┘
```

| 방식 | 트리거 | 장점 | 단점 |
|------|--------|------|------|
| **Lazy** | 클라이언트가 키 접근 시 | CPU 부하 없음 | 미접근 키 메모리 잔류 |
| **Active** | Redis 내부 주기적 샘플링 | 미접근 키도 정리 | 소량의 CPU 사용 |

두 방식을 조합하여, 접근되는 키는 Lazy로 즉시 처리하고 접근되지 않는 키는 Active로 점진적으로 정리한다.

### 주의: SET으로 값을 덮어쓰면 TTL이 초기화된다

이것은 실무에서 자주 발생하는 실수다.

```redis
SET mykey "value1" EX 300
TTL mykey
# → 300

# 200초 후...
TTL mykey
# → 100

# SET으로 값을 덮어쓰면?
SET mykey "value2"
TTL mykey
# → -1  ⚠️ 만료가 사라졌다!
```

**TTL을 유지하면서 값만 변경하려면**:

```redis
# 방법 1: SET에 다시 EX를 명시
SET mykey "value2" EX 300

# 방법 2: 남은 TTL을 읽고 다시 설정
# (애플리케이션 레벨에서 TTL 조회 후 SET EX)
```

---

## 14. List 타입: 데이터의 줄 세우기와 메시지 큐

### 내부 구조: Doubly Linked List

Redis의 List는 **양방향 연결 리스트(Doubly Linked List)** 로 구현되어 있다. 따라서 양쪽 끝에서의 삽입/삭제는 O(1)이지만, 중간 인덱스 접근은 O(N)이다.

```
┌──────────────────────────────────────────────────┐
│                 Redis List 내부 구조               │
│                                                  │
│   HEAD                                    TAIL   │
│    │                                        │    │
│    ▼                                        ▼    │
│   ┌───┐    ┌───┐    ┌───┐    ┌───┐    ┌───┐     │
│   │ A │◀──▶│ B │◀──▶│ C │◀──▶│ D │◀──▶│ E │     │
│   └───┘    └───┘    └───┘    └───┘    └───┘     │
│    ▲                                        ▲    │
│    │                                        │    │
│  LPUSH                                   RPUSH   │
│  LPOP                                    RPOP    │
│                                                  │
│   O(1)        O(N) 접근          O(1)            │
└──────────────────────────────────────────────────┘
```

### 기본 삽입/삭제: LPUSH / RPUSH / LPOP / RPOP

```redis
# 왼쪽(HEAD)에 삽입
LPUSH queue:tasks "task-3"
LPUSH queue:tasks "task-2"
LPUSH queue:tasks "task-1"
# 결과: [task-1, task-2, task-3]

# 오른쪽(TAIL)에 삽입
RPUSH queue:tasks "task-4"
# 결과: [task-1, task-2, task-3, task-4]

# 왼쪽에서 꺼내기 (FIFO 큐)
LPOP queue:tasks
# → "task-1"
# 결과: [task-2, task-3, task-4]

# 오른쪽에서 꺼내기
RPOP queue:tasks
# → "task-4"
# 결과: [task-2, task-3]
```

### 범위 조회: LRANGE

```redis
RPUSH fruits "apple" "banana" "cherry" "date" "elderberry"

# 전체 조회 (0부터 -1까지 = 처음부터 끝까지)
LRANGE fruits 0 -1
# → 1) "apple"
# → 2) "banana"
# → 3) "cherry"
# → 4) "date"
# → 5) "elderberry"

# 처음 3개만
LRANGE fruits 0 2
# → 1) "apple"
# → 2) "banana"
# → 3) "cherry"

# 마지막 2개
LRANGE fruits -2 -1
# → 1) "date"
# → 2) "elderberry"
```

### 보조 명령어: LLEN, LINDEX, LINSERT

```redis
# 리스트 길이
LLEN fruits
# → 5

# 특정 인덱스 조회 (O(N) — 주의!)
LINDEX fruits 2
# → "cherry"

# 특정 원소 앞/뒤에 삽입
LINSERT fruits BEFORE "cherry" "blueberry"
LRANGE fruits 0 -1
# → 1) "apple"
# → 2) "banana"
# → 3) "blueberry"
# → 4) "cherry"
# → 5) "date"
# → 6) "elderberry"
```

### 블로킹 팝: BLPOP / BRPOP — 메시지 큐의 기초

BLPOP/BRPOP은 리스트가 비어 있으면 **데이터가 들어올 때까지 대기**한다. 이것이 Redis로 간단한 메시지 큐를 구현할 수 있는 핵심이다.

```redis
# Consumer: 데이터가 올 때까지 최대 30초 대기
BLPOP queue:jobs 30
# → (blocking... 데이터가 없으면 대기)

# Producer (다른 클라이언트에서):
RPUSH queue:jobs "send-email:user-42"
# → Consumer가 즉시 깨어나서 "send-email:user-42"를 받음
```

```
메시지 큐 패턴:

  Producer                    Redis List                Consumer
     │                           │                         │
     ├── RPUSH job ─────────────▶│                         │
     │                           │                         │
     │                           │◀── BLPOP (대기 중) ──────┤
     │                           │                         │
     │                           │── job 전달 ─────────────▶│
     │                           │                         │
     ├── RPUSH job ─────────────▶│                         │  처리 중...
     │                           │                         │
     │                           │◀── BLPOP (다시 대기) ────┤
     │                           │── job 전달 ─────────────▶│
```

> **BLPOP의 타임아웃**: 0을 지정하면 무한 대기한다. 실무에서는 적절한 타임아웃을 설정하여 커넥션이 영원히 점유되는 것을 방지한다.

### LTRIM: 고정 길이 리스트 유지 — "최근 N개" 패턴

LTRIM은 지정된 범위 밖의 원소를 모두 삭제한다. LPUSH와 조합하면 **최근 N개만 유지하는 리스트**를 만들 수 있다.

```redis
# "최근 본 상품 5개" 패턴
LPUSH recent:user:1 "product-A"
LTRIM recent:user:1 0 4    # 최근 5개만 유지

LPUSH recent:user:1 "product-B"
LTRIM recent:user:1 0 4

LPUSH recent:user:1 "product-C"
LTRIM recent:user:1 0 4

# ... 계속 추가해도 항상 최대 5개만 유지됨
```

### List 타입 실무 활용

| 활용 사례 | 패턴 | 핵심 명령어 |
|-----------|------|------------|
| **메시지 큐** | RPUSH + BLPOP | Producer-Consumer |
| **최근 본 상품** | LPUSH + LTRIM | 고정 길이 리스트 |
| **타임라인** | LPUSH + LRANGE | 최신 항목 조회 |
| **작업 큐** | RPUSH + LPOP | FIFO 처리 |
| **로그 수집** | LPUSH + LTRIM | 최근 N건 유지 |

---

## 15. Set 타입: 중복 제거와 소셜 네트워크 기능

### 순서 없는 고유 원소 집합

Set은 **중복을 허용하지 않는 순서 없는 집합**이다. 수학의 집합(Set)과 동일한 개념으로, 합집합/교집합/차집합 연산을 지원한다.

```
┌──────────────────────────────────────────────────┐
│                    Redis Set                     │
│                                                  │
│    ┌─────────────────────────────────┐            │
│    │  "Alice"  "Bob"  "Charlie"     │            │
│    │        "Diana"  "Eve"          │            │
│    └─────────────────────────────────┘            │
│                                                  │
│    - 순서 없음 (삽입 순서 보장 안 됨)                │
│    - 중복 불가 (같은 값을 여러 번 넣어도 1개)        │
│    - 원소 존재 여부 확인: O(1)                      │
│    - 집합 연산 지원                                 │
└──────────────────────────────────────────────────┘
```

### 기본 명령어: SADD / SREM / SMEMBERS / SISMEMBER

```redis
# 원소 추가
SADD team:backend "Alice" "Bob" "Charlie"
# → 3 (추가된 원소 수)

# 중복 추가 시도
SADD team:backend "Alice"
# → 0 (이미 존재하므로 추가되지 않음)

# 원소 제거
SREM team:backend "Charlie"
# → 1

# 모든 원소 조회
SMEMBERS team:backend
# → 1) "Alice"
# → 2) "Bob"

# 원소 존재 여부 확인 (O(1))
SISMEMBER team:backend "Alice"
# → 1 (존재)
SISMEMBER team:backend "Zoe"
# → 0 (없음)
```

### 보조 명령어: SCARD, SRANDMEMBER

```redis
SADD lottery:participants "user:1" "user:2" "user:3" "user:4" "user:5"

# 원소 수
SCARD lottery:participants
# → 5

# 랜덤으로 1개 추출 (제거하지 않음)
SRANDMEMBER lottery:participants
# → "user:3" (무작위)

# 랜덤으로 2개 추출
SRANDMEMBER lottery:participants 2
# → 1) "user:1"
# → 2) "user:5"

# SPOP: 랜덤으로 꺼내기 (제거됨)
SPOP lottery:participants
# → "user:4" (제거됨)
```

### 집합 연산: SUNION, SINTER, SDIFF

이것이 Set 타입의 진정한 강점이다. 애플리케이션 레벨에서 구현하면 복잡한 로직을 **한 줄의 명령어**로 처리할 수 있다.

```redis
SADD user:1:friends "Alice" "Bob" "Charlie" "Diana"
SADD user:2:friends "Bob" "Diana" "Eve" "Frank"

# 합집합: 두 사람의 친구 전체
SUNION user:1:friends user:2:friends
# → "Alice" "Bob" "Charlie" "Diana" "Eve" "Frank"

# 교집합: 공통 친구
SINTER user:1:friends user:2:friends
# → "Bob" "Diana"

# 차집합: user:1에만 있는 친구
SDIFF user:1:friends user:2:friends
# → "Alice" "Charlie"
```

```
집합 연산 시각화:

  user:1:friends          user:2:friends
  ┌────────────┐          ┌────────────┐
  │ Alice      │          │            │
  │ Charlie    │          │       Eve  │
  │      ┌─────┼──────────┼────┐ Frank │
  │      │ Bob │          │    │       │
  │      │Diana│          │    │       │
  └──────┼─────┘          └────┼───────┘
         │    SINTER           │
         └─────────────────────┘

  SDIFF(1,2) = {Alice, Charlie}    — 1에만 있는 것
  SDIFF(2,1) = {Eve, Frank}        — 2에만 있는 것
  SINTER     = {Bob, Diana}        — 공통
  SUNION     = {Alice, Bob, Charlie, Diana, Eve, Frank}  — 전체
```

### Set 타입 실무 활용

| 활용 사례 | 패턴 | 핵심 명령어 |
|-----------|------|------------|
| **친구 목록** | SADD + SMEMBERS | 중복 없는 관계 |
| **공통 관심사** | SINTER | 두 사용자의 교집합 |
| **중복 방문 체크** | SISMEMBER | 이미 방문했는지 O(1) 확인 |
| **태그 시스템** | SADD + SINTER | 특정 태그 조합의 게시물 |
| **온라인 사용자** | SADD + SREM | 접속/해제 시 추가/제거 |
| **추첨/랜덤 선택** | SRANDMEMBER / SPOP | 랜덤 추출 |

---

## 16. Hash 타입: 객체를 저장하는 가장 깔끔한 방법

### Key-Field-Value 구조

Hash는 하나의 Redis 키 안에 **여러 개의 필드-값 쌍**을 저장할 수 있다. 프로그래밍 언어의 Dictionary/Map과 유사하며, 객체를 저장하기에 가장 자연스러운 자료형이다.

```
┌──────────────────────────────────────────────────┐
│              Redis Hash 구조                      │
│                                                  │
│   Key: "user:1"                                  │
│   ┌────────────┬──────────────────┐              │
│   │   Field    │      Value      │              │
│   ├────────────┼──────────────────┤              │
│   │   name     │   "Alice"       │              │
│   │   age      │   "30"          │              │
│   │   email    │   "a@test.com"  │              │
│   │   city     │   "Seoul"       │              │
│   │   score    │   "1500"        │              │
│   └────────────┴──────────────────┘              │
│                                                  │
│   vs String 방식:                                 │
│   user:1:name  → "Alice"   (키 5개 필요)          │
│   user:1:age   → "30"                            │
│   user:1:email → "a@test.com"                    │
│   user:1:city  → "Seoul"                         │
│   user:1:score → "1500"                          │
└──────────────────────────────────────────────────┘
```

### 기본 명령어: HSET / HGET / HMSET / HMGET / HGETALL

```redis
# 단일 필드 설정
HSET user:1 name "Alice"
HSET user:1 age "30"
HSET user:1 email "alice@example.com"

# 여러 필드를 한 번에 설정 (Redis 4.0+ 에서는 HSET으로도 가능)
HMSET user:1 city "Seoul" score "1500"

# 단일 필드 조회
HGET user:1 name
# → "Alice"

# 여러 필드 조회
HMGET user:1 name age city
# → 1) "Alice"
# → 2) "30"
# → 3) "Seoul"

# 모든 필드-값 조회
HGETALL user:1
# → 1) "name"
# → 2) "Alice"
# → 3) "age"
# → 4) "30"
# → 5) "email"
# → 6) "alice@example.com"
# → 7) "city"
# → 8) "Seoul"
# → 9) "score"
# → 10) "1500"
```

### 보조 명령어: HDEL, HEXISTS, HLEN

```redis
# 필드 삭제
HDEL user:1 city
# → 1

# 필드 존재 여부
HEXISTS user:1 name
# → 1 (존재)
HEXISTS user:1 city
# → 0 (삭제됨)

# 필드 개수
HLEN user:1
# → 4
```

### HINCRBY: 특정 필드만 원자적 증가

Hash의 강력한 기능 중 하나다. 객체의 **특정 필드만** 원자적으로 증감할 수 있어, 전체 객체를 읽고-수정하고-쓰는 과정이 필요 없다.

```redis
HSET product:1 name "Widget" price "10000" views "0" stock "100"

# 조회수만 증가
HINCRBY product:1 views 1
# → 1

# 재고 감소
HINCRBY product:1 stock -1
# → 99

# 가격 인상
HINCRBY product:1 price 500
# → 10500
```

### String(JSON) vs Hash 비교: 언제 어떤 걸 쓸까

```redis
# 방식 1: String에 JSON 저장
SET user:1 '{"name":"Alice","age":30,"email":"a@test.com","score":1500}'

# 방식 2: Hash에 필드별 저장
HSET user:1 name "Alice" age "30" email "a@test.com" score "1500"
```

| 기준 | String (JSON) | Hash |
|------|---------------|------|
| **부분 읽기** | 전체 JSON을 읽고 파싱해야 함 | HGET으로 필요한 필드만 조회 |
| **부분 수정** | 전체를 읽고-수정-쓰기 (비효율) | HSET/HINCRBY로 필드만 수정 |
| **원자적 증감** | 불가능 (읽기-수정-쓰기 필요) | HINCRBY로 가능 |
| **네스팅 구조** | JSON 중첩 가능 | 1단계 필드만 가능 (플랫) |
| **직렬화 비용** | 매번 JSON 파싱/직렬화 필요 | 없음 |
| **메모리** | 큰 JSON은 비효율적 | 작은 Hash는 ziplist로 최적화 |
| **적합한 경우** | 중첩 구조, 항상 전체를 읽는 경우 | 플랫 구조, 부분 읽기/수정이 잦은 경우 |

> **실무 규칙**: 필드를 개별적으로 읽거나 수정하는 빈도가 높다면 Hash, 항상 전체 객체를 한 번에 읽고 쓰면 String(JSON)이 유리하다.

### Hash 타입 실무 활용

| 활용 사례 | 패턴 | 핵심 명령어 |
|-----------|------|------------|
| **사용자 프로필** | 필드별 저장/조회 | HSET / HGET / HGETALL |
| **상품 정보** | 조회수/재고 원자적 증감 | HINCRBY |
| **세션 데이터** | 부분 업데이트 | HSET + EXPIRE |
| **설정값 관리** | 카테고리별 그룹핑 | HSET / HMGET |
| **쇼핑 카트** | 상품ID:수량 저장 | HINCRBY / HDEL |

---

## 17. Sorted Set 타입: 실시간 랭킹과 스코어링

### Set + Score = 자동 정렬

Sorted Set(ZSet)은 Set의 모든 특성(고유 원소, 중복 불가)에 **score(점수)** 가 추가된 자료형이다. 원소는 score에 의해 자동으로 오름차순 정렬되며, 같은 score를 가진 원소는 사전순으로 정렬된다.

```
┌──────────────────────────────────────────────────┐
│              Redis Sorted Set                    │
│                                                  │
│   Key: "leaderboard:game1"                       │
│                                                  │
│   Score     Member                               │
│   ───────   ──────────                           │
│   2500      "player:alice"     ← Rank 0 (최저)   │
│   3200      "player:bob"       ← Rank 1          │
│   4100      "player:charlie"   ← Rank 2          │
│   4800      "player:diana"     ← Rank 3          │
│   5500      "player:eve"       ← Rank 4 (최고)   │
│                                                  │
│   자동 정렬: score 기준 오름차순                     │
│   시간 복잡도: O(log N) — Skip List 기반            │
└──────────────────────────────────────────────────┘
```

### 기본 명령어: ZADD / ZREM / ZSCORE / ZRANK

```redis
# 원소 추가 (score와 함께)
ZADD leaderboard 2500 "alice"
ZADD leaderboard 3200 "bob"
ZADD leaderboard 4100 "charlie"
ZADD leaderboard 4800 "diana"
ZADD leaderboard 5500 "eve"

# 특정 멤버의 점수 조회
ZSCORE leaderboard "charlie"
# → "4100"

# 순위 조회 (0부터 시작, 오름차순)
ZRANK leaderboard "charlie"
# → 2

# 역순위 (내림차순 — 리더보드에서 주로 사용)
ZREVRANK leaderboard "charlie"
# → 2  (5명 중 3등)

# 원소 제거
ZREM leaderboard "bob"
# → 1
```

### 순위별 조회: ZRANGE / ZREVRANGE

```redis
# 오름차순으로 전체 조회
ZRANGE leaderboard 0 -1
# → 1) "alice"
# → 2) "charlie"
# → 3) "diana"
# → 4) "eve"

# 점수와 함께 조회
ZRANGE leaderboard 0 -1 WITHSCORES
# → 1) "alice"
# → 2) "2500"
# → 3) "charlie"
# → 4) "4100"
# → 5) "diana"
# → 6) "4800"
# → 7) "eve"
# → 8) "5500"

# 내림차순 (리더보드 Top 3)
ZREVRANGE leaderboard 0 2 WITHSCORES
# → 1) "eve"
# → 2) "5500"
# → 3) "diana"
# → 4) "4800"
# → 5) "charlie"
# → 6) "4100"
```

### 점수 증가: ZINCRBY

기존 멤버의 점수를 원자적으로 증감한다. 리더보드에서 실시간으로 점수가 변하는 시나리오에 핵심이 되는 명령어다.

```redis
# alice에게 500점 추가
ZINCRBY leaderboard 500 "alice"
# → "3000"

# 점수가 변하면 자동으로 순위가 재정렬됨
ZREVRANGE leaderboard 0 -1 WITHSCORES
# → 1) "eve"       5500
# → 2) "diana"     4800
# → 3) "charlie"   4100
# → 4) "alice"     3000   ← 2500에서 3000으로, 순위 자동 갱신
```

### 점수 범위 조회: ZRANGEBYSCORE

```redis
# 점수 3000~5000 사이의 멤버 조회
ZRANGEBYSCORE leaderboard 3000 5000
# → 1) "alice"
# → 2) "charlie"
# → 3) "diana"

# 점수 3000 초과 ~ 5000 이하 (괄호로 초과 표현)
ZRANGEBYSCORE leaderboard (3000 5000
# → 1) "charlie"
# → 2) "diana"

# 무한대 범위
ZRANGEBYSCORE leaderboard -inf +inf
# → 전체 멤버 (오름차순)
```

### 보조 명령어: ZCARD, ZCOUNT

```redis
# 전체 멤버 수
ZCARD leaderboard
# → 4

# 특정 점수 범위 내 멤버 수
ZCOUNT leaderboard 3000 5000
# → 3
```

### 시간 복잡도: Skip List 기반 O(log N)

Sorted Set이 실시간 랭킹에 적합한 이유는 내부적으로 **Skip List**를 사용하기 때문이다.

```
Skip List 개념:

Level 4:  HEAD ──────────────────────────────────────▶ 5500(eve)
Level 3:  HEAD ─────────────────▶ 4100(charlie) ─────▶ 5500(eve)
Level 2:  HEAD ───▶ 3000(alice) ─▶ 4100(charlie) ────▶ 5500(eve)
Level 1:  HEAD ───▶ 3000(alice) ─▶ 4100 ─▶ 4800 ────▶ 5500(eve)
Level 0:  HEAD ───▶ 3000 ───▶ 4100 ───▶ 4800 ───▶ 5500
          (alice)  (charlie)  (diana)     (eve)
```

| 연산 | 시간 복잡도 | 설명 |
|------|-----------|------|
| ZADD | O(log N) | 삽입 + 정렬 위치 탐색 |
| ZREM | O(log N) | 삭제 + 정렬 유지 |
| ZSCORE | O(1) | 해시 테이블로 직접 접근 |
| ZRANK | O(log N) | Skip List 순회 |
| ZRANGE | O(log N + M) | M = 반환 원소 수 |
| ZINCRBY | O(log N) | 점수 변경 + 재정렬 |

### Sorted Set 타입 실무 활용

| 활용 사례 | Score 활용 | 핵심 명령어 |
|-----------|-----------|------------|
| **리더보드** | 게임 점수 | ZADD / ZINCRBY / ZREVRANGE |
| **인기 검색어** | 검색 횟수 | ZINCRBY / ZREVRANGE 0 9 |
| **예약 시스템** | Unix Timestamp | ZADD / ZRANGEBYSCORE |
| **Rate Limiting** | 요청 시간 | ZADD / ZRANGEBYSCORE / ZREMRANGEBYSCORE |
| **지연 큐** | 실행 예정 시간 | ZADD / ZRANGEBYSCORE |
| **트렌딩 콘텐츠** | 가중 점수 | ZINCRBY / ZREVRANGE |

---

## 18. 자료형 정리: 어떤 자료형을 선택해야 할까?

### 자료형 선택 Decision Tree

```
요구사항을 분석하라
       │
       ▼
   단순한 값 하나?
   (문자열, 숫자, JSON)
       │
    ┌──┴──┐
   Yes    No
    │      │
    ▼      ▼
 String   순서가 있는 목록?
          (큐, 스택, 타임라인)
              │
           ┌──┴──┐
          Yes    No
           │      │
           ▼      ▼
         List   고유한 값들의 집합?
                (중복 제거, 멤버십 확인)
                    │
                 ┌──┴──┐
                Yes    No
                 │      │
                 ▼      ▼
               Set    객체의 필드-값 쌍?
                      (프로필, 설정)
                          │
                       ┌──┴──┐
                      Yes    No
                       │      │
                       ▼      ▼
                     Hash   정렬/순위가 필요?
                            (랭킹, 스코어)
                                │
                             ┌──┴──┐
                            Yes    No
                             │      │
                             ▼      ▼
                        Sorted   복합 자료형
                         Set     검토 필요
```

### 요구사항별 자료형 매핑

| 요구사항 | 자료형 | 대표 패턴 | 예시 |
|----------|--------|-----------|------|
| 단순 값 저장/캐싱 | **String** | SET/GET + EX | 세션 토큰, JSON 캐시 |
| 원자적 카운터 | **String** | INCR/DECR | 조회수, API 호출 횟수 |
| 분산 락 | **String** | SET NX EX | 동시성 제어 |
| 순서 있는 목록 | **List** | LPUSH/RPOP | 작업 큐, 타임라인 |
| 메시지 큐 | **List** | RPUSH/BLPOP | Producer-Consumer |
| 최근 N개 유지 | **List** | LPUSH + LTRIM | 최근 본 상품, 로그 |
| 중복 제거 집합 | **Set** | SADD/SISMEMBER | 온라인 유저, 태그 |
| 집합 연산 | **Set** | SINTER/SUNION | 공통 친구, 추천 |
| 객체/프로필 | **Hash** | HSET/HGET | 사용자 정보, 상품 |
| 부분 필드 수정 | **Hash** | HSET/HINCRBY | 재고 감소, 점수 증가 |
| 랭킹/리더보드 | **Sorted Set** | ZADD/ZREVRANGE | 게임 순위, 인기순 |
| 시간 기반 정렬 | **Sorted Set** | ZADD (timestamp) | 예약, 지연 큐 |
| 범위 점수 조회 | **Sorted Set** | ZRANGEBYSCORE | 가격 범위 필터 |

### 시간 복잡도 비교표

| 연산 유형 | String | List | Set | Hash | Sorted Set |
|-----------|--------|------|-----|------|------------|
| **추가** | O(1) | O(1) 양끝 | O(1) | O(1) | O(log N) |
| **조회 (단일)** | O(1) | O(N) 인덱스 | O(1) | O(1) | O(1) score |
| **삭제 (단일)** | O(1) | O(N) | O(1) | O(1) | O(log N) |
| **범위 조회** | — | O(S+N) | — | — | O(log N + M) |
| **전체 조회** | O(1) | O(N) | O(N) | O(N) | O(N) |
| **존재 확인** | O(1) EXISTS | O(N) | O(1) | O(1) | O(1) |
| **길이/크기** | O(1) | O(1) | O(1) | O(1) | O(1) |
| **집합 연산** | — | — | O(N*M) | — | O(N*K log N) |

### 메모리 효율 비교

Redis는 원소 수가 적을 때 **메모리 최적화 인코딩**을 사용한다.

| 자료형 | 소량 데이터 인코딩 | 대량 데이터 인코딩 | 전환 기준 (기본값) |
|--------|-------------------|-------------------|-------------------|
| **String** | int / embstr | raw | 44바이트 초과 시 |
| **List** | listpack | quicklist | 128개 또는 64바이트 초과 시 |
| **Set** | listpack | hashtable | 128개 또는 64바이트 초과 시 |
| **Hash** | listpack | hashtable | 128개 필드 또는 64바이트 초과 시 |
| **Sorted Set** | listpack | skiplist + hashtable | 128개 또는 64바이트 초과 시 |

> **핵심**: 소량 데이터에서는 listpack(구 ziplist) 인코딩이 사용되어 메모리를 크게 절약한다. Hash 128개 필드 이내, Set 128개 원소 이내에서는 메모리 효율이 매우 높으므로, 적은 필드의 객체를 Hash로 저장하는 것은 String(JSON)보다 메모리 효율적이다.

### 자료형별 핵심 명령어 치트시트

```
┌────────────────────────────────────────────────────────────────────┐
│                    Redis 자료형 핵심 명령어                          │
├────────────┬───────────────────────────────────────────────────────┤
│  String    │  SET  GET  MSET  MGET  INCR  DECR  APPEND  STRLEN   │
│            │  SET key val EX 60 NX  (분산 락)                      │
├────────────┼───────────────────────────────────────────────────────┤
│  List      │  LPUSH  RPUSH  LPOP  RPOP  LRANGE  LLEN             │
│            │  BLPOP  BRPOP  LTRIM  LINDEX  LINSERT                │
├────────────┼───────────────────────────────────────────────────────┤
│  Set       │  SADD  SREM  SMEMBERS  SISMEMBER  SCARD             │
│            │  SRANDMEMBER  SPOP  SUNION  SINTER  SDIFF            │
├────────────┼───────────────────────────────────────────────────────┤
│  Hash      │  HSET  HGET  HMSET  HMGET  HGETALL                  │
│            │  HDEL  HEXISTS  HLEN  HINCRBY                        │
├────────────┼───────────────────────────────────────────────────────┤
│  Sorted    │  ZADD  ZREM  ZSCORE  ZRANK  ZREVRANK                 │
│  Set       │  ZRANGE  ZREVRANGE  ZINCRBY  ZRANGEBYSCORE           │
│            │  ZCARD  ZCOUNT                                       │
├────────────┼───────────────────────────────────────────────────────┤
│  공통      │  DEL  EXISTS  TYPE  EXPIRE  TTL  PERSIST  RENAME     │
└────────────┴───────────────────────────────────────────────────────┘
```

---

## 핵심 요약

1. **String**: 가장 기본적인 자료형이자 가장 다재다능한 자료형. 캐시, 카운터, 분산 락의 기초이며 INCR의 원자성이 핵심 강점이다.
2. **SET 옵션 (EX/NX/XX)**: `SET key value EX 60 NX`는 분산 락의 표준 패턴이다. SETNX + EXPIRE를 분리하면 안전하지 않다.
3. **만료 메커니즘**: Lazy + Active 두 가지 방식으로 동작하며, SET으로 덮어쓰면 TTL이 사라지는 점을 반드시 기억하라.
4. **List**: 양방향 연결 리스트 기반. RPUSH + BLPOP으로 메시지 큐, LPUSH + LTRIM으로 "최근 N개" 패턴을 구현한다.
5. **Set**: 중복 제거와 집합 연산(교집합/합집합/차집합)이 핵심. 소셜 네트워크의 공통 친구 같은 기능을 한 줄로 해결한다.
6. **Hash**: 객체를 필드 단위로 읽기/수정할 수 있어, JSON String보다 부분 업데이트가 잦은 경우에 유리하다.
7. **Sorted Set**: Skip List 기반 O(log N)으로 실시간 랭킹을 지원한다. score를 timestamp로 활용하면 시간 기반 정렬에도 쓸 수 있다.
8. **자료형 선택**: "단순 값 → String, 순서 목록 → List, 고유 집합 → Set, 객체 → Hash, 정렬 랭킹 → Sorted Set"으로 판단한다.

---

**다음**: [[Section 4 - Redis 심화 기능 및 최신 트렌드]]
