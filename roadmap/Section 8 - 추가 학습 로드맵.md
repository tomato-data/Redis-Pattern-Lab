# Section 8: 추가 학습 로드맵 (플러스 알파)

> Section 1~7에서 다룬 자료구조 + 명령어 + 실무 패턴 + 운영은 개발자가 Redis를 활용하는 데 필요한 80%를 커버한다. 아래는 서비스 규모가 커질 때 하나씩 필요해지는 주제들이다.

---

## 우선순위 1: 고가용성과 확장 (인프라/아키텍처)

### Replication + Sentinel

프로덕션에서 Redis 1대가 죽으면 서비스가 멈춘다. Replication과 Sentinel로 이를 방지한다.

```
Master (쓰기/읽기) → Replica 1 (읽기 전용)
                   → Replica 2 (읽기 전용)

Sentinel이 Master 장애 감지 → Replica를 자동으로 Master로 승격
```

**학습 포인트**:
- Master-Replica 복제 구성
- Sentinel의 자동 failover 동작 원리
- 읽기 부하 분산 (Read Replica)
- 복제 지연(Replication Lag) 이해

### Redis Cluster (수평 확장)

데이터가 한 대 메모리에 안 담길 때, 여러 노드에 자동 분산한다.

```
키 A → Node 1 (슬롯 0~5460)
키 B → Node 2 (슬롯 5461~10922)
키 C → Node 3 (슬롯 10923~16383)
```

16,384개 해시 슬롯에 키를 분배한다. Key 네이밍에서 `{}`가 안티패턴인 이유 — Cluster에서 해시 슬롯 지정에 쓰이는 문법이기 때문.

**학습 포인트**:
- 해시 슬롯 기반 데이터 분배
- 노드 추가/제거 시 리밸런싱
- 클러스터 모드에서 MULTI/EXEC, Lua Script 제약 (같은 슬롯의 키만 가능)
- Hash Tag `{user}:profile`, `{user}:session` — 같은 슬롯에 배치하는 기법

### Redis Transactions (MULTI/EXEC)

Lua Script보다 가벼운 원자성 보장 방법.

```redis
MULTI
SET user:1:name "Alice"
INCR user:1:login_count
EXEC    ← 두 명령이 원자적으로 실행
```

**학습 포인트**:
- MULTI/EXEC로 명령 묶기
- WATCH로 낙관적 락 구현 (CAS — Check And Set)
- Lua Script와의 사용처 차이

---

## 우선순위 2: 보안과 최적화

### 보안 (AUTH, ACL, TLS)

프로덕션에서는 필수.

```redis
# 비밀번호 설정
CONFIG SET requirepass "your-password"

# ACL: 사용자별 명령어/키 접근 제한
ACL SETUSER readonly ~cache:* +GET +MGET -@write
```

**학습 포인트**:
- requirepass로 기본 인증
- ACL v2로 사용자별 권한 분리 (읽기 전용 유저, 특정 prefix만 접근 등)
- TLS 암호화 (외부 네트워크 노출 시)
- bind 설정으로 접근 IP 제한

### 메모리 최적화 (내부 인코딩)

Redis는 데이터 크기에 따라 내부 인코딩을 자동 전환한다.

```redis
# 작은 Hash → ziplist (메모리 효율적)
# 큰 Hash → hashtable (성능 우선)
OBJECT ENCODING key
```

**학습 포인트**:
- ziplist, listpack, skiplist 등 내부 자료구조
- `hash-max-ziplist-entries`, `hash-max-ziplist-value` 등 임계값 설정
- `OBJECT ENCODING`, `MEMORY USAGE` 명령으로 키별 메모리 분석
- 대규모 서비스에서 메모리 비용 절감 기법

### Redis 기반 메시지 큐 vs 전용 MQ

| | Redis Stream | Kafka | RabbitMQ |
|---|---|---|---|
| 설치/운영 | 간단 | 복잡 | 중간 |
| 처리량 | 수십만/초 | 수백만/초 | 수만/초 |
| 메시지 보존 | 메모리 (MAXLEN) | 디스크 (일/주) | 디스크 (ACK까지) |
| 라우팅 | 단순 | 파티션 기반 | Exchange 기반 (유연) |
| 적합 규모 | 소~중규모 | 대규모 파이프라인 | 중규모 비동기 처리 |

**학습 포인트**:
- 각 MQ의 보장 수준 (at-most-once, at-least-once, exactly-once)
- 서비스 규모에 따른 선택 기준
- Redis Stream에서 Kafka로의 마이그레이션 시점

---

## 우선순위 3: 클라우드 매니지드 서비스

직접 운영하지 않고 클라우드에 맡기는 옵션.

| 서비스 | 제공자 | 특징 |
|--------|--------|------|
| **ElastiCache** | AWS | Redis/Valkey 호환, 자동 failover |
| **MemoryDB** | AWS | Redis 호환 + 내구성 보장 (Multi-AZ) |
| **Memorystore** | GCP | Redis 호환, VPC 내 자동 관리 |
| **Azure Cache** | Azure | Redis 호환, Enterprise 티어 |

**학습 포인트**:
- 매니지드 vs 자체 운영 트레이드오프
- 클라우드별 제약 사항 (일부 명령어 제한, CONFIG 변경 불가 등)
- 비용 최적화 (인스턴스 크기, Reserved 할인)

---

## 학습 단계 요약

```
✅ 완료 (Section 1~7):
   자료구조 + 명령어 + 실무 패턴 + 운영
   → 개발자가 Redis를 활용하는 데 충분

📌 다음 단계 (우선순위 1):
   Replication + Cluster + Transactions
   → 서비스가 장애 대응/확장이 필요해질 때

📌 그 다음 (우선순위 2):
   보안 + 메모리 최적화 + MQ 비교
   → 프로덕션 보안 강화, 대규모 비용 최적화

📌 필요 시 (우선순위 3):
   클라우드 매니지드 서비스
   → 직접 운영 대신 클라우드에 맡길 때
```
