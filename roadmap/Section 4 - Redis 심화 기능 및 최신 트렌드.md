
# Section 4: Redis 심화 기능 및 최신 트렌드

> Pub/Sub, Stream, Redis Stack, 트랜잭션/스크립팅 등 Redis의 심화 기능을 학습하고, Redis 7.x/8.0의 핵심 패러다임 변화를 이해한다. "단순 캐시"를 넘어 "데이터 플랫폼"으로 진화하는 Redis의 현재와 미래를 다룬다.

---

## 19. Pub/Sub: 실시간 메시지 브로커 활용하기

### Publish/Subscribe 패턴 개요

Pub/Sub는 **발행자(Publisher)** 와 **구독자(Subscriber)** 가 서로의 존재를 모른 채 **채널(Channel)** 을 통해 메시지를 주고받는 패턴이다. 발행자는 채널에 메시지를 보내고, 해당 채널을 구독 중인 모든 구독자가 실시간으로 메시지를 수신한다.

```
┌─────────────────────────────────────────────────────────┐
│                    Pub/Sub 동작 구조                       │
│                                                         │
│  Publisher A ──┐                  ┌── Subscriber 1       │
│                ├──→ Channel X ──→├── Subscriber 2       │
│  Publisher B ──┘                  └── Subscriber 3       │
│                                                         │
│  Publisher C ────→ Channel Y ────→── Subscriber 4       │
│                                                         │
│  * Publisher는 구독자가 누구인지 모른다                      │
│  * Subscriber는 발행자가 누구인지 모른다                     │
│  * Channel이 중간 매개체 역할                               │
└─────────────────────────────────────────────────────────┘
```

**핵심 특성**: 발행자와 구독자 간의 **느슨한 결합(Loose Coupling)**. 새로운 구독자를 추가하거나 제거해도 발행자의 코드를 변경할 필요가 없다.

### 핵심 명령어

#### SUBSCRIBE / PUBLISH / UNSUBSCRIBE

```bash
# 터미널 1: 구독자
SUBSCRIBE notifications
# Reading messages... (waiting for messages)

# 터미널 2: 발행자
PUBLISH notifications "새 주문이 접수되었습니다"
# (integer) 1    ← 메시지를 수신한 구독자 수

# 터미널 1 출력:
# 1) "message"
# 2) "notifications"
# 3) "새 주문이 접수되었습니다"
```

```bash
# 다중 채널 구독
SUBSCRIBE chat:room1 chat:room2 alerts

# 구독 해제
UNSUBSCRIBE chat:room1
```

#### PSUBSCRIBE — 패턴 매칭 구독

`PSUBSCRIBE`는 글로브(glob) 패턴을 사용하여 여러 채널을 한 번에 구독한다.

```bash
# chat: 으로 시작하는 모든 채널 구독
PSUBSCRIBE chat:*

# 위 명령으로 chat:room1, chat:room2, chat:vip 등 모두 수신

# 패턴 예시
PSUBSCRIBE user:*:events    # user:123:events, user:456:events 등
PSUBSCRIBE alert.[critical] # alert.c, alert.r, alert.i 등 (한 글자 매칭)
PSUBSCRIBE news.*           # news.sports, news.tech 등
```

```
패턴 매칭 구독 흐름:

Publisher                Redis                 Subscriber
   │                       │                       │
   │  PUBLISH chat:room1   │                       │
   │  "Hello"              │   PSUBSCRIBE chat:*   │
   │──────────────────────→│──────────────────────→│
   │                       │   match: chat:room1   │
   │                       │   ← chat:* 패턴에 해당  │
   │                       │                       │
   │  PUBLISH chat:room2   │                       │
   │  "World"              │                       │
   │──────────────────────→│──────────────────────→│
   │                       │   match: chat:room2   │
```

### Pub/Sub의 특성: Fire-and-Forget

Redis Pub/Sub의 가장 중요한 특성은 **Fire-and-Forget**이다. 이것은 장점이자 동시에 가장 큰 제약이다.

```
┌──────────────────────────────────────────────────┐
│              Fire-and-Forget 의미                  │
│                                                  │
│  1. 메시지 영속성 없음                               │
│     → Redis가 재시작되면 메시지 유실                  │
│     → 어떤 메시지가 발행되었는지 기록이 남지 않음       │
│                                                  │
│  2. 구독자 없으면 메시지 유실                         │
│     → PUBLISH 시점에 구독자가 0명이면 메시지 소멸      │
│     → 나중에 구독하더라도 과거 메시지 수신 불가         │
│                                                  │
│  3. 전달 보장 없음                                  │
│     → 구독자가 메시지를 처리했는지 확인 불가            │
│     → ACK 메커니즘 없음                             │
│                                                  │
│  4. 구독자 연결 끊김 시 메시지 유실                    │
│     → 네트워크 일시 장애 중 발행된 메시지는 소멸        │
│     → 재연결 후에도 복구 불가                         │
└──────────────────────────────────────────────────┘
```

```bash
# 구독자가 없는 상태에서 발행
PUBLISH chat:room1 "아무도 없나요?"
# (integer) 0    ← 수신자 0명, 메시지 영구 소멸
```

### Pub/Sub vs Stream vs 외부 MQ 비교

| 특성 | Redis Pub/Sub | Redis Stream | Kafka | RabbitMQ |
|------|--------------|-------------|-------|----------|
| **메시지 영속성** | 없음 | 있음 | 있음 (디스크) | 있음 |
| **과거 메시지 조회** | 불가 | 가능 | 가능 | 제한적 |
| **Consumer Group** | 없음 | 있음 | 있음 | 있음 |
| **전달 보장** | At-most-once | At-least-once | At-least-once | At-least-once |
| **처리량** | 매우 높음 | 높음 | 매우 높음 | 높음 |
| **운영 복잡도** | 매우 낮음 | 낮음 | 높음 | 중간 |
| **적합 시나리오** | 실시간 알림 | 이벤트 로그 | 대규모 스트리밍 | 작업 큐 |
| **메시지 순서 보장** | 채널 내 보장 | 보장 | 파티션 내 보장 | 큐 내 보장 |

### 활용 사례

**실시간 알림 시스템**

```bash
# 사용자별 알림 채널
SUBSCRIBE user:1234:notifications

# 알림 발행
PUBLISH user:1234:notifications '{"type":"order","message":"주문이 배송 시작되었습니다"}'
```

**채팅 시스템**

```bash
# 채팅방 참가
SUBSCRIBE chat:room:42

# 메시지 전송
PUBLISH chat:room:42 '{"user":"Alice","text":"안녕하세요!"}'
```

**설정 변경 전파**

```bash
# 모든 서버가 설정 변경 채널 구독
PSUBSCRIBE config:*

# 설정 변경 시 전파
PUBLISH config:rate_limit '{"max_requests":100,"window_seconds":60}'

# 모든 서버가 동시에 설정 변경을 수신하여 로컬 캐시 갱신
```

```
설정 변경 전파 흐름:

Admin API
   │
   │  PUBLISH config:rate_limit
   │  '{"max_requests":100}'
   │
   ▼
 Redis ──→ Server A (로컬 설정 갱신)
   │──→ Server B (로컬 설정 갱신)
   │──→ Server C (로컬 설정 갱신)
   │
   └── 모든 서버가 동시에 새 설정 적용
```

---

## 20. Stream: 로그 및 데이터 스트림 처리 기초

### Redis Stream이란?

Redis 5.0에서 도입된 **로그형(Append-only) 자료구조**다. Pub/Sub의 한계인 메시지 유실, 소비 이력 추적 불가 문제를 해결하면서도, Kafka처럼 무겁지 않은 **경량 메시지 스트림**을 제공한다.

```
┌────────────────────────────────────────────────────────┐
│                Redis Stream 구조                        │
│                                                        │
│  Stream Key: orders                                    │
│                                                        │
│  ┌──────────────┬──────────────┬──────────────┐        │
│  │ 1710000000-0 │ 1710000001-0 │ 1710000002-0 │ ...    │
│  │ user: Alice  │ user: Bob    │ user: Charlie│        │
│  │ item: book   │ item: phone  │ item: laptop │        │
│  │ qty: 2       │ qty: 1       │ qty: 1       │        │
│  └──────────────┴──────────────┴──────────────┘        │
│       ▲                                                │
│       │                                                │
│  Append-Only: 새 메시지는 항상 오른쪽에 추가              │
│  과거 메시지 조회 가능 (Pub/Sub과의 핵심 차이)             │
└────────────────────────────────────────────────────────┘
```

### Pub/Sub의 한계를 보완하는 Stream

| Pub/Sub의 한계 | Stream의 해결 |
|---------------|-------------|
| 메시지 영속성 없음 | 메시지가 Stream에 영구 저장 |
| 구독자 없으면 메시지 유실 | 나중에 구독해도 과거 메시지 조회 가능 |
| ACK 메커니즘 없음 | Consumer Group의 XACK으로 처리 확인 |
| 소비 이력 추적 불가 | 소비자별 마지막 읽은 위치 추적 |
| 재처리 불가 | 메시지 ID로 언제든 재조회 가능 |

### 핵심 명령어

#### XADD — 메시지 추가

```bash
# 자동 ID 생성 (* 사용)
XADD orders * user Alice item book qty 2
# "1710000000123-0"    ← 자동 생성된 메시지 ID

# 수동 ID 지정
XADD orders 1710000001000-0 user Bob item phone qty 1

# MAXLEN으로 스트림 크기 제한
XADD orders MAXLEN ~ 1000 * user Charlie item laptop qty 1
# ~ (근사치): 정확히 1000이 아닌 대략 1000개 유지 (성능 최적화)
```

#### XLEN — 스트림 길이 조회

```bash
XLEN orders
# (integer) 3
```

#### XRANGE / XREVRANGE — 범위 조회

```bash
# 전체 조회 (- 최소, + 최대)
XRANGE orders - +

# 특정 시간 범위 조회
XRANGE orders 1710000000000 1710000002000

# 최근 N개 조회 (COUNT 옵션)
XRANGE orders - + COUNT 10

# 역순 조회
XREVRANGE orders + - COUNT 5
```

#### XREAD — 실시간 읽기

```bash
# 특정 ID 이후의 메시지 읽기
XREAD COUNT 10 STREAMS orders 1710000000123-0

# 블로킹 읽기: 새 메시지가 올 때까지 대기 (최대 5000ms)
XREAD BLOCK 5000 COUNT 10 STREAMS orders $
# $ = 현재 시점 이후의 새 메시지만
```

### Consumer Group

Consumer Group은 **여러 소비자가 하나의 Stream을 분담 처리**하는 메커니즘이다. 같은 그룹 내에서 각 메시지는 **한 명의 소비자에게만** 전달된다.

```
┌───────────────────────────────────────────────────┐
│            Consumer Group 동작 구조                 │
│                                                   │
│  Stream: orders                                   │
│  ┌───┬───┬───┬───┬───┬───┬───┬───┐               │
│  │ 1 │ 2 │ 3 │ 4 │ 5 │ 6 │ 7 │ 8 │               │
│  └───┴───┴───┴───┴───┴───┴───┴───┘               │
│                                                   │
│  Consumer Group: order-processors                 │
│  ├── Consumer A: 메시지 1, 4, 7 처리               │
│  ├── Consumer B: 메시지 2, 5, 8 처리               │
│  └── Consumer C: 메시지 3, 6 처리                  │
│                                                   │
│  * 각 메시지는 그룹 내 한 소비자에게만 전달            │
│  * 소비자별 독립적인 처리 속도                        │
│  * ACK 전까지 Pending 상태 유지                     │
└───────────────────────────────────────────────────┘
```

#### Consumer Group 명령어

```bash
# 그룹 생성 ($ = 지금부터의 새 메시지만, 0 = 처음부터)
XGROUP CREATE orders order-processors $ MKSTREAM

# 그룹으로 메시지 읽기
XREADGROUP GROUP order-processors consumer-A COUNT 5 STREAMS orders >
# > = 아직 이 그룹에 전달되지 않은 새 메시지

# 처리 완료 확인 (ACK)
XACK orders order-processors 1710000000123-0

# Pending 메시지 조회 (ACK되지 않은 메시지)
XPENDING orders order-processors - + 10
```

```
Consumer Group 메시지 흐름:

Producer         Redis Stream        Consumer Group
   │                  │                    │
   │  XADD orders     │                    │
   │  * user Alice     │                    │
   │─────────────────→│                    │
   │                  │  XREADGROUP >      │
   │                  │←───────────────────│ Consumer A
   │                  │  (메시지 전달)       │
   │                  │                    │
   │                  │  XACK              │
   │                  │←───────────────────│ Consumer A
   │                  │  (처리 완료 확인)    │
   │                  │                    │
   │                  │ Pending에서 제거     │
```

### 메시지 ID 구조

Redis Stream의 메시지 ID는 `<millisecondsTime>-<sequenceNumber>` 형식이다.

```
메시지 ID: 1710000000123-0
           ─────────────  ─
                │          │
       Unix timestamp(ms)  시퀀스 번호

같은 밀리초에 여러 메시지가 추가되면:
  1710000000123-0
  1710000000123-1
  1710000000123-2

특수 ID:
  -  : 가능한 가장 작은 ID
  +  : 가능한 가장 큰 ID
  $  : 현재 시점의 마지막 ID (XREAD에서 사용)
  >  : 아직 전달되지 않은 메시지 (XREADGROUP에서 사용)
  0  : 처음부터 (XREADGROUP에서 Pending 재조회 시 사용)
```

### Stream vs Pub/Sub vs Kafka 비교표

| 특성 | Redis Pub/Sub | Redis Stream | Apache Kafka |
|------|--------------|-------------|--------------|
| **저장 방식** | 저장 안 함 | 메모리 + AOF | 디스크 (로그) |
| **메시지 보존** | 발행 즉시 소멸 | MAXLEN으로 제어 | 보존 기간 설정 |
| **Consumer Group** | 미지원 | 지원 | 지원 |
| **ACK 메커니즘** | 없음 | XACK | Offset Commit |
| **메시지 재처리** | 불가 | 가능 | 가능 |
| **처리량 (초당)** | ~100만+ | ~10만+ | ~100만+ |
| **운영 난이도** | 매우 쉬움 | 쉬움 | 어려움 (ZooKeeper/KRaft) |
| **파티셔닝** | 없음 | 없음 (단일 키) | 토픽 파티셔닝 |
| **적합 규모** | 소규모 실시간 | 중소규모 이벤트 | 대규모 데이터 파이프라인 |

### 활용 사례

**이벤트 소싱**

```bash
# 주문 이벤트를 Stream에 기록
XADD order:1234:events * type created status pending total 50000
XADD order:1234:events * type paid status paid payment_method card
XADD order:1234:events * type shipped status shipped tracking_no ABC123

# 주문의 전체 이력 조회
XRANGE order:1234:events - +
```

**활동 로그**

```bash
# 사용자 활동 기록
XADD user:activity * user_id 1234 action page_view page /products
XADD user:activity * user_id 1234 action add_cart product_id 567

# Consumer Group으로 분석 워커가 분담 처리
XGROUP CREATE user:activity analytics-workers $
XREADGROUP GROUP analytics-workers worker-1 COUNT 100 STREAMS user:activity >
```

**경량 메시지 큐**

```bash
# 작업 큐에 작업 추가
XADD task:queue * type email to user@example.com subject "가입 환영"

# 워커가 작업을 가져와 처리
XREADGROUP GROUP task-workers worker-1 BLOCK 5000 COUNT 1 STREAMS task:queue >

# 처리 완료 후 ACK
XACK task:queue task-workers 1710000000123-0
```

---

## 21. Redis Stack: JSON 저장과 고속 검색 (FullText Search)

### Redis Stack이란?

Redis Stack은 **Redis 코어 + 추가 모듈**을 번들로 제공하는 확장 패키지다. 기존 Redis의 단순 자료구조를 넘어 JSON 문서 저장, 전문 검색, 그래프 쿼리 등 고급 기능을 추가한다.

```
┌────────────────────────────────────────────────────┐
│                  Redis Stack 구성                    │
│                                                    │
│  ┌──────────────────────────────────────────┐      │
│  │              Redis Core                  │      │
│  │   String, Hash, List, Set, Sorted Set,   │      │
│  │   Stream, HyperLogLog, Bitmap, Geo       │      │
│  └──────────────────────────────────────────┘      │
│           +                                        │
│  ┌──────────────┐  ┌──────────────┐                │
│  │  RedisJSON   │  │  RediSearch  │                │
│  │  JSON 문서   │  │  전문 검색    │                │
│  │  저장/조회    │  │  인덱싱      │                │
│  └──────────────┘  └──────────────┘                │
│  ┌──────────────┐  ┌──────────────┐                │
│  │  RedisGraph  │  │  RedisTimeSeries │            │
│  │  그래프 DB    │  │  시계열 데이터    │            │
│  └──────────────┘  └──────────────┘                │
│  ┌──────────────┐                                  │
│  │ RedisBloom   │                                  │
│  │ 확률적 자료구조│                                  │
│  └──────────────┘                                  │
└────────────────────────────────────────────────────┘
```

### RedisJSON

RedisJSON은 Redis에서 **JSON 문서를 네이티브로 저장/조회/수정**할 수 있게 해주는 모듈이다. JSONPath 표현식으로 중첩된 필드에 직접 접근할 수 있다.

#### 핵심 명령어

```bash
# JSON 문서 저장
JSON.SET product:1001 $ '{
  "name": "무선 키보드",
  "brand": "LogiTech",
  "price": 89000,
  "category": "electronics",
  "specs": {
    "weight": "450g",
    "connectivity": "Bluetooth 5.0",
    "battery": "AAA x 2"
  },
  "tags": ["keyboard", "wireless", "bluetooth"],
  "in_stock": true
}'

# 전체 문서 조회
JSON.GET product:1001
# 특정 필드만 조회
JSON.GET product:1001 $.name
# → "무선 키보드"

# 중첩 필드 접근 (JSONPath)
JSON.GET product:1001 $.specs.weight
# → "450g"

# 배열 요소 접근
JSON.GET product:1001 $.tags[0]
# → "keyboard"

# 여러 필드 동시 조회
JSON.GET product:1001 $.name $.price $.specs.connectivity
```

```bash
# 다중 키 조회
JSON.MGET product:1001 product:1002 product:1003 $.name
# → ["무선 키보드", "기계식 키보드", "트랙패드"]
```

```bash
# 부분 업데이트 (전체 문서 교체 없이)
JSON.SET product:1001 $.price 79000
JSON.SET product:1001 $.specs.weight "420g"

# 숫자 필드 증감
JSON.NUMINCRBY product:1001 $.price -5000
# → 74000

# 배열에 요소 추가
JSON.ARRAPPEND product:1001 $.tags '"ergonomic"'

# 필드 삭제
JSON.DEL product:1001 $.specs.battery
```

### RediSearch

RediSearch는 Redis에 저장된 Hash 또는 JSON 문서에 대해 **전문 검색(Full-Text Search)** 과 **보조 인덱스**를 제공하는 모듈이다.

#### 인덱스 생성: FT.CREATE

```bash
# Hash 기반 인덱스
FT.CREATE idx:products
  ON HASH
  PREFIX 1 product:
  SCHEMA
    name TEXT WEIGHT 5.0        # 전문 검색, 가중치 5배
    brand TEXT
    price NUMERIC SORTABLE      # 숫자 범위 검색 + 정렬
    category TAG                # 정확한 값 필터링
    in_stock TAG                # boolean을 TAG로 처리

# JSON 기반 인덱스
FT.CREATE idx:products_json
  ON JSON
  PREFIX 1 product:
  SCHEMA
    $.name AS name TEXT WEIGHT 5.0
    $.brand AS brand TEXT
    $.price AS price NUMERIC SORTABLE
    $.category AS category TAG
    $.tags AS tags TAG SEPARATOR ","
```

#### 스키마 필드 타입

| 타입 | 용도 | 검색 방식 | 예시 |
|------|------|----------|------|
| **TEXT** | 전문 검색 대상 | 형태소 분석, 부분 매칭 | 상품명, 설명 |
| **NUMERIC** | 숫자 범위 검색 | 범위 쿼리 (`[min max]`) | 가격, 수량 |
| **TAG** | 정확한 값 필터링 | 정확한 매칭 (OR 가능) | 카테고리, 상태 |
| **GEO** | 위치 기반 검색 | 반경 쿼리 | 좌표 |
| **VECTOR** | 벡터 유사도 검색 | KNN, Range | 임베딩 |

#### 전문 검색: FT.SEARCH

```bash
# 기본 검색 (TEXT 필드 대상)
FT.SEARCH idx:products "키보드"

# 특정 필드에서 검색
FT.SEARCH idx:products "@name:무선 키보드"

# 숫자 범위 필터
FT.SEARCH idx:products "@price:[50000 100000]"

# TAG 필터 (정확한 값)
FT.SEARCH idx:products "@category:{electronics}"

# 복합 조건
FT.SEARCH idx:products "@name:키보드 @price:[0 100000] @category:{electronics}"

# 정렬
FT.SEARCH idx:products "@category:{electronics}" SORTBY price ASC

# 페이지네이션
FT.SEARCH idx:products "*" LIMIT 0 10    # 첫 10개
FT.SEARCH idx:products "*" LIMIT 10 10   # 다음 10개

# 반환 필드 지정
FT.SEARCH idx:products "키보드" RETURN 3 name price brand
```

### Hash vs RedisJSON 비교

```
┌─────────────────────────────────────────────────────────┐
│              Hash vs RedisJSON 구조 차이                  │
│                                                         │
│  Hash (평면 구조):                                       │
│  ┌──────────────────────────────────────┐               │
│  │ product:1001                         │               │
│  │   name       = "무선 키보드"           │               │
│  │   price      = "89000"               │               │
│  │   spec_weight = "450g"       ← 평면화 │               │
│  │   spec_conn   = "Bluetooth"  ← 필요  │               │
│  │   tags        = "kb,wireless" ← CSV  │               │
│  └──────────────────────────────────────┘               │
│                                                         │
│  RedisJSON (중첩 구조):                                   │
│  ┌──────────────────────────────────────┐               │
│  │ product:1001                         │               │
│  │   name: "무선 키보드"                  │               │
│  │   price: 89000          ← 숫자 타입   │               │
│  │   specs:                             │               │
│  │     weight: "450g"      ← 중첩 객체   │               │
│  │     connectivity: "Bluetooth"        │               │
│  │   tags: ["kb", "wireless"] ← 배열    │               │
│  └──────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────┘
```

| 특성 | Hash | RedisJSON |
|------|------|-----------|
| **구조** | 평면(flat) key-value | 중첩(nested) JSON |
| **데이터 타입** | 모든 값이 문자열 | 숫자, 불리언, 배열, 객체 |
| **중첩 객체** | 키 이름 규칙으로 평면화 필요 | 네이티브 지원 |
| **배열** | CSV 문자열로 처리 | 네이티브 배열 |
| **부분 업데이트** | HSET으로 필드 단위 | JSONPath로 깊은 필드까지 |
| **메모리 효율** | 더 효율적 | 약간 더 많이 사용 |
| **직렬화 비용** | 없음 (이미 문자열) | JSON 파싱 필요 |
| **적합 시나리오** | 단순한 평면 데이터 | 복잡한 중첩 구조 |

### 활용 사례

**상품 검색 시스템**

```bash
# 상품 데이터 저장 (JSON)
JSON.SET product:2001 $ '{
  "name": "맥북 프로 14인치",
  "brand": "Apple",
  "price": 2390000,
  "category": "laptop",
  "specs": {"cpu": "M3 Pro", "ram": "18GB", "ssd": "512GB"}
}'

# 인덱스 생성
FT.CREATE idx:shop ON JSON PREFIX 1 product:
  SCHEMA
    $.name AS name TEXT
    $.brand AS brand TAG
    $.price AS price NUMERIC SORTABLE
    $.category AS category TAG

# 검색: "프로" 키워드 + 가격 200만 이상 + 노트북 카테고리
FT.SEARCH idx:shop "@name:프로 @price:[2000000 +inf] @category:{laptop}"
```

**로그 검색**

```bash
# 로그 저장
HSET log:20240301:001 level ERROR service auth message "인증 토큰 만료" timestamp 1710000000
HSET log:20240301:002 level INFO service api message "요청 처리 완료" timestamp 1710000001

# 인덱스 생성
FT.CREATE idx:logs ON HASH PREFIX 1 log:
  SCHEMA
    level TAG
    service TAG
    message TEXT
    timestamp NUMERIC SORTABLE

# ERROR 로그만 검색
FT.SEARCH idx:logs "@level:{ERROR}" SORTBY timestamp DESC
```

---

## 22. 최신 트렌드: Redis 7.x & 8.0 핵심 패러다임 변화

### Redis 7.0 주요 변경점

Redis 7.0(2022년 4월)은 서버 측 스크립팅, 보안, 멀티테넌시 측면에서 대규모 업데이트가 이루어진 버전이다.

#### Redis Functions

Lua Script의 진화형으로, **서버에 함수를 영구 등록**하여 재사용할 수 있다. (자세한 내용은 23강 참조)

```bash
# 함수 라이브러리 로드
FUNCTION LOAD "#!lua name=mylib\nredis.register_function('myfunc', function(keys, args) return redis.call('GET', keys[1]) end)"

# 함수 호출
FCALL myfunc 1 user:1234
```

#### ACL v2 — 세분화된 접근 제어

Redis 7.0에서는 **셀렉터(Selector)** 기반의 다중 권한 규칙을 지원한다.

```bash
# Redis 6.x ACL (단일 규칙)
ACL SETUSER readonly ~cache:* +GET +MGET

# Redis 7.0 ACL v2 (다중 규칙 - Selector)
ACL SETUSER app_user ON >password
  ~cache:* +GET +MGET +SET
  (~session:* +GET +DEL)       # 추가 Selector: session 키에는 GET, DEL만
```

#### Sharded Pub/Sub

기존 Pub/Sub는 클러스터 환경에서 **모든 노드에 메시지를 브로드캐스트**하여 불필요한 네트워크 트래픽이 발생했다. Sharded Pub/Sub는 채널을 특정 슬롯에 매핑하여 **해당 샤드의 노드에만 메시지를 전달**한다.

```
기존 Pub/Sub (클러스터):

  PUBLISH channel:1 "msg"
     │
     ▼
  ┌────────┐   브로드캐스트   ┌────────┐   브로드캐스트   ┌────────┐
  │ Node A │ ──────────────→│ Node B │ ──────────────→│ Node C │
  │ shard1 │                │ shard2 │                │ shard3 │
  └────────┘                └────────┘                └────────┘
  모든 노드에 전달 (비효율적)


Sharded Pub/Sub (Redis 7.0):

  SPUBLISH channel:1 "msg"
     │
     ▼
  ┌────────┐                ┌────────┐                ┌────────┐
  │ Node A │                │ Node B │                │ Node C │
  │ shard1 │                │ shard2 │                │ shard3 │
  │ ← 전달 │                │        │                │        │
  └────────┘                └────────┘                └────────┘
  해당 샤드만 처리 (효율적)
```

```bash
# Sharded Pub/Sub 명령어
SSUBSCRIBE channel:1
SPUBLISH channel:1 "메시지"
SUNSUBSCRIBE channel:1
```

#### Client-side Caching

서버 Push 기반의 **캐시 무효화(Invalidation)** 메커니즘이다. 클라이언트가 로컬에 캐시한 키가 서버에서 변경되면, Redis가 **능동적으로 무효화 알림을 전송**한다.

```
Client-side Caching 흐름:

Client                    Redis Server
  │                            │
  │  GET user:1234             │
  │  (+ CLIENT TRACKING ON)    │
  │───────────────────────────→│
  │                            │
  │  ← "Alice"                 │
  │←───────────────────────────│
  │                            │
  │  [로컬 캐시 저장]            │
  │  user:1234 = "Alice"       │
  │                            │
  │        ... 시간 경과 ...     │
  │                            │
  │                  다른 클라이언트가
  │                  SET user:1234 "Bob"
  │                            │
  │  ← INVALIDATE user:1234    │  ← 서버가 능동적으로 통지
  │←───────────────────────────│
  │                            │
  │  [로컬 캐시 삭제]            │
  │  user:1234 제거             │
  │                            │
  │  GET user:1234             │  ← 다음 요청 시 서버에서 재조회
  │───────────────────────────→│
  │  ← "Bob"                   │
  │←───────────────────────────│
```

```bash
# Client-side Caching 활성화 (RESP3 프로토콜 필요)
CLIENT TRACKING ON

# Broadcasting 모드: 특정 접두사의 키 변경만 추적
CLIENT TRACKING ON BCAST PREFIX user: PREFIX session:
```

**Client-side Caching의 장점**:
- 네트워크 왕복 제거로 **로컬 캐시 수준의 속도** 달성
- 서버 Push 기반이므로 **폴링 불필요**
- TTL 기반보다 **정확한 무효화** (변경 즉시 알림)

### Redis 8.0 핵심 변화

Redis 8.0(2025년)은 기술적 변화보다 **라이선스와 아키텍처 패러다임**에서 큰 전환점이다.

#### 라이선스 변경

```
┌────────────────────────────────────────────────────────┐
│              Redis 라이선스 변천사                        │
│                                                        │
│  Redis ≤ 7.2:  BSD 3-Clause (완전 오픈소스)              │
│       │                                                │
│       ▼                                                │
│  Redis 7.4+:   RSALv2 + SSPLv1 (듀얼 라이선스)           │
│                                                        │
│  RSALv2 (Redis Source Available License v2):            │
│    → 소스 코드 열람 가능                                  │
│    → 자체 서비스에 사용 가능                               │
│    → 단, Redis를 "경쟁 제품"으로 제공하는 것은 금지         │
│                                                        │
│  SSPLv1 (Server Side Public License v1):                │
│    → MongoDB가 처음 도입한 라이선스                        │
│    → 서비스로 제공 시 전체 스택 소스 공개 의무              │
│                                                        │
│  영향:                                                   │
│    → AWS ElastiCache, GCP Memorystore 등                │
│      클라우드 벤더가 Redis를 그대로 서비스로 제공하기 어려움  │
│    → 자체 서버에서 Redis를 사용하는 일반 기업은 영향 없음    │
└────────────────────────────────────────────────────────┘
```

#### 멀티스레딩 I/O 개선

Redis는 전통적으로 **싱글스레드 이벤트 루프**로 동작해왔다. Redis 8.0에서는 I/O 처리에 멀티스레딩을 더 적극적으로 활용한다.

```
Redis 전통 모델 (싱글스레드):

  Client A ──┐
  Client B ──┼──→ [단일 이벤트 루프] ──→ 명령 실행 (순차)
  Client C ──┘         │
                       │
              네트워크 I/O + 명령 실행
              모두 한 스레드에서 처리


Redis 8.0 모델 (I/O 멀티스레딩):

  Client A ──→ [I/O Thread 1] ──┐
  Client B ──→ [I/O Thread 2] ──┼──→ [메인 스레드: 명령 실행]
  Client C ──→ [I/O Thread 3] ──┘         │
                                          │
              네트워크 I/O는 멀티스레드    명령 실행은 여전히 싱글스레드
              (읽기/쓰기 병렬화)          (원자성 보장)
```

**핵심**: 명령 실행 자체는 여전히 싱글스레드로 원자성이 보장되지만, 네트워크 I/O(소켓 읽기/쓰기)를 멀티스레드로 처리하여 **대규모 연결 처리 성능**이 향상된다.

### Redis vs Valkey (Fork)

라이선스 변경에 대한 대응으로, Linux Foundation 주도로 Redis의 오픈소스 포크인 **Valkey**가 등장했다.

| 특성 | Redis 8.0+ | Valkey |
|------|-----------|--------|
| **라이선스** | RSALv2 + SSPLv1 | BSD 3-Clause (오픈소스) |
| **주도** | Redis Ltd. | Linux Foundation |
| **지원 기업** | Redis Ltd. | AWS, Google, Oracle 등 |
| **호환성** | — | Redis 7.2 기반 포크, API 호환 |
| **클라우드 서비스** | Redis Cloud | AWS ElastiCache, GCP 등에서 채택 |
| **커뮤니티** | 기존 Redis 커뮤니티 | 오픈소스 커뮤니티 |
| **새 기능** | Redis Ltd. 주도 개발 | 독립적 로드맵 |

**실무 관점**: 자체 서버에서 Redis를 사용하는 대부분의 기업에게 라이선스 변경은 직접적 영향이 없다. 다만 클라우드 서비스를 이용하는 경우 AWS ElastiCache가 Valkey로 전환되는 등의 변화를 인지해야 한다.

### 핵심 트렌드: "단순 캐시"에서 "데이터 플랫폼"으로

```
┌────────────────────────────────────────────────────────────┐
│                Redis 진화 방향                               │
│                                                            │
│  2009        2015         2018          2022        2025    │
│   │           │            │             │           │      │
│   ▼           ▼            ▼             ▼           ▼      │
│  캐시       Pub/Sub     Stream       Redis Stack   AI/ML   │
│  세션       Lua Script  모듈 시스템    JSON 검색    Vector   │
│  카운터     Cluster     ACL          Functions    Search   │
│                                                            │
│  ─────────────────────────────────────────────────────→     │
│  "캐시 서버"              →            "데이터 플랫폼"        │
│                                                            │
│  단순 key-value 저장     →    문서 저장, 전문 검색, 벡터 검색, │
│                               스트리밍, 그래프, 시계열        │
└────────────────────────────────────────────────────────────┘
```

Redis는 더 이상 "빠른 캐시"가 아니다. JSON 문서 저장, 전문 검색, 벡터 유사도 검색, 시계열 데이터, 그래프 쿼리까지 지원하는 **다목적 실시간 데이터 플랫폼**으로 진화하고 있다.

---

## 23. 트랜잭션과 스크립팅: Lua Script와 Redis Functions

### MULTI / EXEC — 기본 트랜잭션

Redis의 트랜잭션은 `MULTI`로 시작하여 `EXEC`로 실행한다. 큐에 쌓인 명령어들이 **원자적으로 순차 실행**된다.

```bash
# 기본 트랜잭션: 계좌 이체
MULTI
DECRBY account:alice 50000    # Alice 계좌에서 차감
INCRBY account:bob 50000      # Bob 계좌에 입금
EXEC
# 1) (integer) 950000
# 2) (integer) 1050000
```

```
MULTI/EXEC 실행 흐름:

Client                     Redis
  │                          │
  │  MULTI                   │
  │─────────────────────────→│  트랜잭션 시작 (큐잉 모드)
  │  ← OK                   │
  │                          │
  │  DECRBY account:alice    │
  │─────────────────────────→│  큐에 저장 (아직 미실행)
  │  ← QUEUED               │
  │                          │
  │  INCRBY account:bob      │
  │─────────────────────────→│  큐에 저장 (아직 미실행)
  │  ← QUEUED               │
  │                          │
  │  EXEC                    │
  │─────────────────────────→│  큐의 명령 원자적 순차 실행
  │  ← [결과1, 결과2]        │  다른 클라이언트 명령 끼어들기 불가
  │                          │
```

```bash
# 트랜잭션 취소
MULTI
SET key1 "value1"
DISCARD           # 큐에 쌓인 명령 모두 폐기, 트랜잭션 종료
```

### WATCH — 낙관적 락 (Optimistic Locking)

`WATCH`는 특정 키를 감시하여, `EXEC` 시점까지 해당 키가 변경되었으면 **트랜잭션 전체를 취소**한다.

```bash
WATCH account:alice         # 키 감시 시작
GET account:alice           # 현재 잔액 확인: 1000000

MULTI
DECRBY account:alice 50000
INCRBY account:bob 50000
EXEC
# 감시 중 account:alice가 변경되지 않았으면 → 실행
# 감시 중 account:alice가 변경되었으면 → (nil) 반환, 트랜잭션 취소
```

```
WATCH + MULTI/EXEC 낙관적 락 흐름:

Client A                   Redis                   Client B
  │                          │                        │
  │  WATCH account:alice     │                        │
  │─────────────────────────→│                        │
  │                          │                        │
  │  GET account:alice       │                        │
  │  ← 1000000              │                        │
  │                          │                        │
  │  MULTI                   │                        │
  │─────────────────────────→│                        │
  │                          │                        │
  │                          │  SET account:alice 999  │ ← 다른 클라이언트가 변경!
  │                          │←───────────────────────│
  │                          │                        │
  │  DECRBY account:alice    │                        │
  │  INCRBY account:bob      │                        │
  │  EXEC                    │                        │
  │─────────────────────────→│                        │
  │  ← (nil)                 │  ← WATCH 키 변경 감지!   │
  │                          │     트랜잭션 전체 취소     │
  │                          │                        │
  │  [재시도 로직 필요]        │                        │
```

### MULTI/EXEC의 한계

MULTI/EXEC는 **조건부 실행이 불가능**하다. 큐에 명령을 넣는 시점에는 이전 명령의 결과를 알 수 없기 때문이다.

```bash
# 원하는 로직: "잔액이 50000 이상일 때만 차감"
# MULTI/EXEC로는 불가능!

MULTI
GET account:alice           # → QUEUED (결과를 모름)
# 여기서 GET 결과를 확인하고 조건 분기를 할 수 없다
DECRBY account:alice 50000  # → QUEUED (무조건 큐에 들어감)
EXEC
# 잔액이 부족해도 차감이 실행되어 버린다
```

이 한계를 해결하는 것이 바로 **Lua Script**와 **Redis Functions**이다.

### Lua Script: EVAL 명령어

Lua Script는 Redis 서버 내부에서 **원자적으로 실행되는 스크립트**다. 스크립트 실행 중에는 다른 어떤 Redis 명령도 끼어들 수 없다.

#### 기본 문법

```bash
EVAL "스크립트" numkeys key1 key2 ... arg1 arg2 ...
```

- `numkeys`: KEYS 배열의 크기
- `KEYS[1]`, `KEYS[2]`, ...: Redis 키 (클러스터 환경에서 라우팅에 사용)
- `ARGV[1]`, `ARGV[2]`, ...: 추가 인자

```bash
# 단순 예시: 키 값 가져오기
EVAL "return redis.call('GET', KEYS[1])" 1 user:1234

# 두 키의 값을 합산
EVAL "
  local a = tonumber(redis.call('GET', KEYS[1]))
  local b = tonumber(redis.call('GET', KEYS[2]))
  return a + b
" 2 counter:a counter:b
```

#### 실무 예시: "재고가 0 이상일 때만 감소"

```bash
# MULTI/EXEC로는 불가능한 조건부 원자적 처리
EVAL "
  local stock = tonumber(redis.call('GET', KEYS[1]))
  if stock == nil then
    return redis.error_reply('KEY_NOT_FOUND')
  end
  local amount = tonumber(ARGV[1])
  if stock >= amount then
    redis.call('DECRBY', KEYS[1], amount)
    return stock - amount
  else
    return redis.error_reply('INSUFFICIENT_STOCK')
  end
" 1 product:1001:stock 3
```

```
Lua Script 원자적 실행 보장:

Client A                  Redis                    Client B
  │                         │                         │
  │  EVAL "재고 차감 스크립트"  │                         │
  │────────────────────────→│                         │
  │                         │                         │
  │                    ┌────┴────┐                    │
  │                    │ Lua VM  │                    │
  │                    │         │                    │
  │                    │ GET stock│   GET stock       │
  │                    │ = 5     │←──────────────────│
  │                    │         │   ← 대기 (블로킹)  │
  │                    │ stock≥3?│                    │
  │                    │ YES     │                    │
  │                    │ DECRBY 3│                    │
  │                    │ → 2     │                    │
  │                    └────┬────┘                    │
  │                         │                         │
  │  ← 2                   │  ← 이제 실행 가능         │
  │                         │  GET stock → 2          │
  │                         │────────────────────────→│
```

#### Lua Script 주의사항

```
┌──────────────────────────────────────────────────────┐
│              Lua Script 사용 시 주의점                  │
│                                                      │
│  1. 실행 시간 제한                                     │
│     → 기본 5초 (lua-time-limit 설정)                   │
│     → 초과 시 SCRIPT KILL로 강제 종료 가능              │
│     → 쓰기 명령 실행 후에는 SHUTDOWN NOSAVE만 가능      │
│                                                      │
│  2. KEYS 배열에 접근할 키를 명시해야 함                  │
│     → 클러스터 환경에서 올바른 노드 라우팅을 위해 필수    │
│     → KEYS를 사용하지 않고 키를 하드코딩하면 안 됨       │
│                                                      │
│  3. 순수 함수여야 함                                    │
│     → 같은 입력에 같은 결과 (결정적)                     │
│     → 랜덤, 시간 함수 사용 시 복제 문제 발생 가능        │
│                                                      │
│  4. 블로킹                                            │
│     → 스크립트 실행 중 다른 모든 명령이 대기              │
│     → 긴 스크립트는 전체 서버 성능에 영향                │
└──────────────────────────────────────────────────────┘
```

### Redis Functions (7.0+)

Redis Functions는 Lua Script의 진화형이다. 핵심 차이는 **서버에 영구 등록**되어 재시작 후에도 유지되며, **라이브러리 단위로 관리**된다는 점이다.

#### 기본 사용법

```bash
# 함수 라이브러리 로드
FUNCTION LOAD "#!lua name=inventory
  local function check_and_decrement(keys, args)
    local stock = tonumber(redis.call('GET', keys[1]))
    if stock == nil then
      return redis.error_reply('KEY_NOT_FOUND')
    end
    local amount = tonumber(args[1])
    if stock >= amount then
      redis.call('DECRBY', keys[1], amount)
      return stock - amount
    else
      return redis.error_reply('INSUFFICIENT_STOCK')
    end
  end

  redis.register_function('decrement_stock', check_and_decrement)
"

# 함수 호출
FCALL decrement_stock 1 product:1001:stock 3

# 읽기 전용 함수 호출 (레플리카에서도 실행 가능)
FCALL_RO get_stock 1 product:1001:stock
```

```bash
# 등록된 함수 목록 확인
FUNCTION LIST

# 특정 라이브러리 삭제
FUNCTION DELETE inventory

# 모든 함수 삭제
FUNCTION FLUSH
```

### Lua Script vs Redis Functions 비교

| 특성 | Lua Script (EVAL) | Redis Functions (FCALL) |
|------|-------------------|------------------------|
| **도입 시점** | Redis 2.6 | Redis 7.0 |
| **등록 방식** | 호출 시마다 스크립트 전송 | 사전 등록 (FUNCTION LOAD) |
| **영속성** | 없음 (SCRIPT FLUSH 시 소멸) | 있음 (AOF/RDB에 저장) |
| **관리 단위** | 개별 스크립트 | 라이브러리 (여러 함수 묶음) |
| **호출 방식** | EVAL / EVALSHA | FCALL / FCALL_RO |
| **캐싱** | EVALSHA로 SHA1 해시 캐싱 | 서버에 영구 저장 |
| **읽기 전용 구분** | 없음 | FCALL_RO (레플리카 실행 가능) |
| **권장 사용** | 단순/임시 스크립트 | 프로덕션 비즈니스 로직 |

```
EVAL vs FCALL 사용 흐름 비교:

EVAL 방식:
  Client ──→ EVAL "local stock = ..." 1 key arg
             (매 호출마다 스크립트 전체 전송)
             (또는 EVALSHA + SHA1 해시)

FCALL 방식:
  1회: Client ──→ FUNCTION LOAD "라이브러리 코드"
                  (서버에 영구 등록)

  N회: Client ──→ FCALL decrement_stock 1 key arg
                  (함수 이름만으로 호출, 코드 전송 불필요)
```

### 실무 종합 예시: Rate Limiter

```bash
# Lua Script로 구현하는 슬라이딩 윈도우 Rate Limiter
EVAL "
  local key = KEYS[1]
  local limit = tonumber(ARGV[1])
  local window = tonumber(ARGV[2])     -- 윈도우 크기(초)
  local now = tonumber(ARGV[3])        -- 현재 타임스탬프

  -- 윈도우 밖의 오래된 요청 제거
  redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

  -- 현재 윈도우 내 요청 수 확인
  local current = redis.call('ZCARD', key)

  if current < limit then
    -- 요청 허용: 현재 타임스탬프를 Sorted Set에 추가
    redis.call('ZADD', key, now, now .. '-' .. math.random(1000000))
    redis.call('EXPIRE', key, window)
    return 1    -- 허용
  else
    return 0    -- 거부
  end
" 1 ratelimit:user:1234 100 60 1710000000
-- KEYS[1] = ratelimit:user:1234
-- ARGV[1] = 100 (최대 요청 수)
-- ARGV[2] = 60 (윈도우: 60초)
-- ARGV[3] = 1710000000 (현재 타임스탬프)
```

```
Rate Limiter 동작 흐름:

  요청 도착
     │
     ▼
  ┌─────────────────────────────────┐
  │  Sorted Set: ratelimit:user:1234│
  │  Score = 타임스탬프               │
  │                                 │
  │  1. 윈도우(60초) 밖 제거          │
  │     ZREMRANGEBYSCORE 0 (now-60) │
  │                                 │
  │  2. 현재 개수 확인                │
  │     ZCARD → 현재 요청 수          │
  │                                 │
  │  3-a. 개수 < 100                │
  │       → ZADD (요청 기록)         │
  │       → return 1 (허용)          │
  │                                 │
  │  3-b. 개수 >= 100               │
  │       → return 0 (거부)          │
  └─────────────────────────────────┘
```

---

## 핵심 요약

1. **Pub/Sub**: Fire-and-forget 방식의 실시간 메시지 브로커. 메시지 영속성이 없으므로 유실 가능성을 허용하는 시나리오(알림, 설정 전파)에 적합하다.
2. **Stream**: Pub/Sub의 한계를 보완하는 로그형 자료구조. Consumer Group, ACK, 메시지 영속성을 지원하여 이벤트 소싱과 경량 메시지 큐로 활용한다.
3. **Redis Stack**: RedisJSON과 RediSearch를 통해 JSON 문서 저장과 전문 검색이 가능하다. Redis가 "캐시"를 넘어 "데이터 플랫폼"으로 진화하는 핵심 축이다.
4. **Redis 7.x/8.0 트렌드**: Functions, Sharded Pub/Sub, Client-side Caching 등 서버 기능이 강화되었고, 라이선스 변경(RSALv2+SSPLv1)으로 Valkey 포크가 등장했다.
5. **트랜잭션과 스크립팅**: MULTI/EXEC의 조건부 실행 한계를 Lua Script/Redis Functions가 해결한다. 원자적 조건 분기가 필요한 비즈니스 로직(재고 차감, Rate Limiting)에 필수적이다.

---

**다음**: [[Section 5 - FastAPI 기반 Redis 실무 패턴 구현]]
