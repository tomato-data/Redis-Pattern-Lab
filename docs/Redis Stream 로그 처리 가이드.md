#Projects/Redis-Study #Stack/Redis

# Redis Stream 로그 처리 가이드

실시간 로그 수집/처리에 Redis Stream을 활용하는 패턴을 정리한다. 실제 프로젝트 도입 시 참고용.

---

## 왜 Redis Stream인가

| | RDB (PostgreSQL) | Redis Stream |
|---|---|---|
| 쓰기 속도 | INSERT + 디스크 I/O → 초당 수천 건 | XADD + 메모리 → 초당 수십만 건 |
| 실시간 소비 | 폴링 필요 (SELECT ... WHERE id > ?) | Consumer Group으로 푸시형 읽기 |
| 분담 처리 | 직접 구현 필요 | Consumer Group 내장 |
| 처리 확인 | 직접 구현 필요 | XACK 내장 |
| 영구 보관 | O | X (메모리 기반, MAXLEN으로 크기 제한) |

핵심: Redis Stream은 **실시간 버퍼 + 분배기** 역할이지, 영구 저장소가 아니다.

---

## 활용 패턴 3가지

### 1. 이벤트 소싱 — 상태 변화 이력 기록

DB에는 현재 상태만, Stream에는 과정을 기록한다.

```redis
XADD order:1234:events * type created status pending total 50000
XADD order:1234:events * type paid status paid payment_method card
XADD order:1234:events * type shipped status shipped tracking_no ABC123

# 주문의 전체 이력을 시간순으로 조회
XRANGE order:1234:events - +
```

활용: "이 주문이 언제 결제됐고, 언제 배송됐는지" 추적. CS 대응, 감사 로그.

### 2. 활동 로그 — 유저 행동 수집 + 실시간 분석

```redis
XADD user:activity * user_id 1234 action page_view page /products
XADD user:activity * user_id 1234 action add_cart product_id 567
XADD user:activity * user_id 1234 action checkout total 35000

# Consumer Group으로 분석 워커가 분담 처리
XGROUP CREATE user:activity analytics-workers $
XREADGROUP GROUP analytics-workers worker-1 COUNT 100 STREAMS user:activity >
```

활용: "장바구니에 넣고 결제 안 한 유저" 탐지 → 푸시 알림. 실시간 대시보드.

### 3. 경량 작업 큐 — 비동기 처리

```redis
XADD task:queue * type email to user@example.com subject "가입 환영"
XADD task:queue * type sms phone 010-1234-5678 message "인증번호 123456"

# 워커가 작업을 가져와 처리
XREADGROUP GROUP task-workers worker-1 BLOCK 5000 COUNT 1 STREAMS task:queue >

# 처리 완료 후 ACK
XACK task:queue task-workers 1710000000123-0
```

활용: 이메일 발송, SMS, 이미지 리사이즈 등 즉시 응답 불필요한 작업.

---

## 실무 아키텍처

```
애플리케이션 → Redis Stream (실시간 버퍼, MAXLEN으로 크기 제한)
                  │
                  ├─ Consumer Group "analyzers"
                  │   ├─ worker-1 → DB/Elasticsearch (영구 저장)
                  │   └─ worker-2 → DB/Elasticsearch
                  │
                  ├─ Consumer Group "notifiers"
                  │   └─ worker-1 → 푸시 알림 발송
                  │
                  └─ Consumer Group "dashboard"
                      └─ worker-1 → 실시간 대시보드 업데이트
```

하나의 Stream에 여러 Consumer Group을 붙일 수 있다. 각 그룹은 **독립적으로** 모든 메시지를 소비한다. 같은 그룹 내 워커들은 메시지를 **분담**한다.

---

## Python (FastAPI) 구현 예시

### Producer (로그 기록)

```python
async def log_activity(redis: Redis, user_id: int, action: str, **extra):
    await redis.xadd(
        "user:activity",
        {"user_id": str(user_id), "action": action, **extra},
        maxlen=100000,    # 최대 10만 건 유지
        approximate=True,  # 정확히 10만이 아닌 근사치 (성능 최적화)
    )
```

### Consumer (워커)

```python
async def consume_activities(redis: Redis, group: str, consumer: str):
    while True:
        messages = await redis.xreadgroup(
            group, consumer,
            {"user:activity": ">"},
            count=100,
            block=5000,  # 5초간 새 메시지 대기
        )
        for stream_name, stream_messages in messages:
            for msg_id, data in stream_messages:
                # 처리 로직
                await process_activity(data)
                # 처리 완료 확인
                await redis.xack("user:activity", group, msg_id)
```

---

## 도입 판단 기준

### 도입하면 좋은 경우

- 실시간으로 대량의 이벤트/로그가 발생 (초당 수백 건 이상)
- 여러 소비자가 같은 이벤트를 각자 다른 목적으로 처리해야 함
- 비동기 작업 큐가 필요하지만 Kafka/RabbitMQ는 과한 경우
- 이미 Redis를 쓰고 있어서 추가 인프라 없이 도입 가능

### 굳이 안 써도 되는 경우

- 이벤트가 하루 수백 건 수준 → DB INSERT로 충분
- 영구 보관 + 복잡한 검색이 주 목적 → DB나 Elasticsearch가 적합
- 이미 Kafka/RabbitMQ가 있음 → 중복 인프라
- 메시지 순서 보장이 파티션 단위로 필요 → Kafka가 더 적합

### 주의 사항

- MAXLEN을 반드시 설정할 것 (안 하면 메모리 무한 증가)
- Stream은 메모리에 존재 — 서버 장애 시 AOF/RDB로 복구하지만, 유실 가능성 존재
- 영구 보관이 필요한 데이터는 Consumer에서 DB로 반드시 옮길 것
- Consumer가 장시간 죽어있으면 Pending 메시지가 쌓임 → 모니터링 필요

---

## Kafka vs Redis Stream 간단 비교

| | Redis Stream | Kafka |
|---|---|---|
| 설치/운영 | 간단 (Redis에 내장) | 복잡 (ZooKeeper/KRaft + 브로커) |
| 처리량 | 초당 수십만 건 | 초당 수백만 건 |
| 메시지 보존 | 메모리 (MAXLEN 제한) | 디스크 (일/주 단위 보존) |
| 적합 규모 | 중소규모 | 대규모 데이터 파이프라인 |
| Consumer Group | 지원 | 지원 (더 성숙) |

규모가 작~중간이고 이미 Redis를 쓰고 있다면 Stream, 대규모 데이터 파이프라인이면 Kafka.
