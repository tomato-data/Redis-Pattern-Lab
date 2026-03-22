
# Section 6: Redis 운영 및 장애 대응

> Key 네이밍, 메모리 관리, 영속성 설정, 모니터링 등 프로덕션 환경에서 Redis를 안정적으로 운영하기 위한 핵심 지식을 다룬다. 실무에서 가장 많이 발생하는 장애 유형과 대응 방법을 중심으로 설명한다.

---

## 35. Key 네이밍 전략: 효율적인 데이터 관리의 시작

### 왜 네이밍 전략이 중요한가?

Redis에는 테이블이나 스키마가 없다. **Key 이름이 곧 데이터 구조**다. 수십만 개의 키가 뒤섞인 상태에서 체계 없이 키를 만들면, 어떤 데이터가 어디에 있는지 파악할 수 없게 된다.

### 네이밍 컨벤션: 콜론(:) 구분자 표준

Redis 커뮤니티에서 사실상 표준으로 사용하는 형식은 다음과 같다:

```
{서비스}:{도메인}:{식별자}
```

```redis
# 좋은 예시
SET app:user:1234 '{"name":"Alice","email":"alice@example.com"}'
SET shop:product:5678:stock 42
SET auth:session:abc-def-ghi '{"user_id":1234,"role":"admin"}'
SET cache:api:user-profile:1234 '...'

# 더 구체적인 계층 예시
SET app:user:1234:profile '...'
SET app:user:1234:settings '...'
SET app:order:9999:items '...'
```

### 네임스페이스 설계 예시

| 도메인 | Key 패턴 | 자료형 | TTL |
|--------|----------|--------|-----|
| 사용자 프로필 캐시 | `cache:user:{user_id}` | String (JSON) | 5분 |
| 세션 | `session:{session_id}` | Hash | 30분 |
| 장바구니 | `cart:{user_id}` | Hash | 24시간 |
| 실시간 랭킹 | `rank:daily:{date}` | Sorted Set | 48시간 |
| 최근 본 상품 | `recent:{user_id}` | List | 7일 |
| Rate Limit | `ratelimit:{user_id}:{endpoint}` | String (INCR) | 1분 |
| 분산 락 | `lock:{resource_name}` | String (NX) | 10초 |
| 임시 인증번호 | `otp:{phone_number}` | String | 3분 |

### Key 길이 vs 가독성 트레이드오프

```
┌─────────────────────────────────────────────────────────────────┐
│                    Key 길이 트레이드오프                          │
│                                                                 │
│   짧은 키              적정 키                   긴 키           │
│   u:1234              user:1234              application:       │
│                                              service:user:      │
│   ✅ 메모리 절약       ✅ 가독성 + 효율         profile:data:1234│
│   ❌ 의미 파악 불가    ✅ 디버깅 용이           ❌ 메모리 낭비    │
│   ❌ 디버깅 어려움     ✅ 팀 협업 가능          ❌ 네트워크 비용   │
│                                                                 │
│         ◀──── 메모리 효율 ────── 가독성 ────▶                    │
│                       ↑                                         │
│                   권장 지점                                      │
└─────────────────────────────────────────────────────────────────┘
```

**키 하나당 수 바이트 차이**지만, 수백만~수천만 개의 키가 존재하면 누적 차이는 상당하다. 그러나 대부분의 경우 **가독성을 우선**하는 것이 올바른 선택이다. 메모리 최적화가 필요한 극단적 상황에서만 짧은 키를 고려한다.

### 안티패턴

```redis
# ❌ 안티패턴 1: 너무 긴 키
SET my-awesome-application:user-management-service:user-profile-data:user-id-1234 '...'

# ❌ 안티패턴 2: 공백 포함
SET "user profile 1234" '...'    # 따옴표 필수, 실수 유발

# ❌ 안티패턴 3: 예약어/특수문자 사용
SET user{1234} '...'             # Cluster 환경에서 {} 는 해시 슬롯 지정에 사용됨
SET user\n1234 '...'             # 개행 문자 포함

# ❌ 안티패턴 4: 구분자 불일치
SET user:1234 '...'
SET user-5678 '...'              # 같은 서비스에서 구분자 혼용
SET user.9999 '...'

# ✅ 올바른 패턴: 일관된 구분자, 적절한 길이
SET user:1234 '...'
SET user:5678 '...'
SET user:9999 '...'
```

**핵심 규칙 정리**:
1. 구분자는 **콜론(:)** 으로 통일
2. 키 길이는 의미를 전달할 수 있는 **최소한의 길이**
3. 공백, 개행, 특수문자 사용 금지
4. 팀 내 네이밍 컨벤션 문서화 필수

---

## 36. O(N)의 공포: KEYS * 금지와 SCAN 활용

### KEYS * 가 위험한 이유

Redis는 **싱글 스레드**로 명령어를 처리한다. `KEYS *`는 전체 키 공간을 한 번에 스캔하는 O(N) 연산이다. 이 명령이 실행되는 동안 **다른 모든 명령어는 대기 상태**가 된다.

```
┌─────────────────────────────────────────────────────────────┐
│              KEYS * 실행 시 Redis 내부 동작                   │
│                                                             │
│   시간 ──────────────────────────────────────────────▶       │
│                                                             │
│   명령 큐:  GET  SET  INCR  [KEYS *]  GET  SET  GET  SET   │
│                              │                              │
│                    ┌─────────┘                              │
│                    ▼                                        │
│            ┌──────────────────┐                             │
│            │  전체 키 스캔     │                             │
│            │  O(N) 연산       │  ← 키 100만개 = 수 초 블로킹 │
│            │  블로킹 중...    │                              │
│            └──────────────────┘                             │
│                    │                                        │
│            뒤에 대기 중인 모든 명령어 처리 불가                 │
│            → 클라이언트 타임아웃 → 서비스 장애                  │
└─────────────────────────────────────────────────────────────┘
```

### 실무 사고 사례

```
시나리오: 프로덕션 Redis에 키 500만 개 존재

1. 개발자가 디버깅 목적으로 redis-cli 접속
2. KEYS user:* 실행 (매칭 키 조회 의도)
3. Redis가 500만 개 키를 전수 스캔 시작
4. 약 3~5초간 Redis 완전 블로킹
5. 이 시간 동안 모든 요청 타임아웃
6. API 서버 → Redis 연결 풀 고갈
7. 서비스 전체 장애 발생
```

**키 100만 개 기준 KEYS * 소요 시간**: 약 1~2초. 이 시간 동안 Redis는 어떤 요청도 처리하지 못한다.

### SCAN: 커서 기반 점진적 스캔

`SCAN`은 커서를 사용하여 **조금씩 나누어** 키를 스캔한다. 각 호출 사이에 다른 명령어가 처리될 수 있으므로 서버를 블로킹하지 않는다.

```redis
# 기본 사용법
SCAN 0 MATCH user:* COUNT 100
# 반환: 1) "17592"     ← 다음 커서
#       2) 1) "user:1234"
#          2) "user:5678"
#          3) ...

# 다음 페이지 조회 (반환된 커서를 사용)
SCAN 17592 MATCH user:* COUNT 100
# 반환: 1) "28401"     ← 다음 커서
#       2) 1) "user:9012"
#          ...

# 커서가 0을 반환하면 스캔 완료
SCAN 28401 MATCH user:* COUNT 100
# 반환: 1) "0"         ← 스캔 완료
#       2) 1) "user:3456"
```

```
┌─────────────────────────────────────────────────────────────┐
│              SCAN 실행 시 Redis 내부 동작                     │
│                                                             │
│   시간 ──────────────────────────────────────────────▶       │
│                                                             │
│   [SCAN 0]  GET  SET  [SCAN 17592]  GET  INCR  [SCAN 28401]│
│      │                    │                        │        │
│   100개씩 스캔         100개씩 스캔             100개씩 스캔   │
│   (매우 짧음)          (매우 짧음)              (매우 짧음)    │
│                                                             │
│   → 각 SCAN 사이에 다른 명령어 정상 처리 가능                  │
│   → 서버 블로킹 없음                                         │
└─────────────────────────────────────────────────────────────┘
```

### 자료형별 SCAN 명령어

| 명령어 | 대상 | 사용법 |
|--------|------|--------|
| `SCAN` | 전체 키 공간 | `SCAN 0 MATCH pattern COUNT 100` |
| `HSCAN` | Hash 필드 | `HSCAN myhash 0 MATCH field* COUNT 100` |
| `SSCAN` | Set 멤버 | `SSCAN myset 0 MATCH member* COUNT 100` |
| `ZSCAN` | Sorted Set 멤버 | `ZSCAN myzset 0 MATCH member* COUNT 100` |

### KEYS 명령어 비활성화

프로덕션 환경에서는 실수로라도 `KEYS`를 실행할 수 없도록 비활성화하는 것이 안전하다.

```bash
# redis.conf 에서 설정
rename-command KEYS ""

# 또는 런타임에 설정 (Redis 6.2+ 에서는 ACL 사용 권장)
# redis.conf
rename-command KEYS "KEYS_DISABLED_DO_NOT_USE"
```

```redis
# ACL을 사용한 방식 (Redis 6.0+)
ACL SETUSER default -keys
```

**핵심**: 프로덕션에서 `KEYS *`는 절대 사용하지 않는다. 대신 `SCAN`을 사용하여 점진적으로 키를 조회한다.

---

## 37. 메모리 관리: Maxmemory 설정과 데이터 삭제 정책(Eviction)

### Redis의 메모리 한계

Redis는 메모리 기반이므로, 물리 메모리를 초과하면 OS의 swap이 발생하거나 OOM(Out of Memory)으로 프로세스가 종료될 수 있다. 이를 방지하기 위해 **maxmemory**를 설정하고, 한도에 도달했을 때의 동작을 **Eviction 정책**으로 결정한다.

### maxmemory 설정

```redis
# 현재 설정 확인
CONFIG GET maxmemory

# 2GB로 설정
CONFIG SET maxmemory 2gb

# redis.conf에서 설정 (영구)
# maxmemory 2gb
```

```
권장 설정:
- 물리 메모리의 60~70% 를 maxmemory로 설정
- 나머지 30~40%: OS, 포크 프로세스(BGSAVE), 연결 버퍼 등

예시: 서버 RAM 8GB
  → maxmemory 5gb (약 62%)
```

### Eviction 정책 종류 (8가지)

maxmemory에 도달했을 때 Redis가 취하는 행동을 결정한다.

```redis
# Eviction 정책 설정
CONFIG SET maxmemory-policy allkeys-lru
```

| 정책 | 대상 범위 | 삭제 기준 | 설명 |
|------|----------|----------|------|
| **noeviction** | — | 삭제 안 함 | 메모리 초과 시 쓰기 명령에 에러 반환 |
| **allkeys-lru** | 모든 키 | LRU | 가장 오래 사용되지 않은 키 삭제 |
| **volatile-lru** | TTL 설정된 키만 | LRU | TTL 키 중 가장 오래 사용되지 않은 키 삭제 |
| **allkeys-lfu** | 모든 키 | LFU | 가장 적게 사용된 키 삭제 |
| **volatile-lfu** | TTL 설정된 키만 | LFU | TTL 키 중 가장 적게 사용된 키 삭제 |
| **volatile-ttl** | TTL 설정된 키만 | TTL 임박 순 | 만료가 가장 임박한 키부터 삭제 |
| **volatile-random** | TTL 설정된 키만 | 무작위 | TTL 키 중 무작위 삭제 |
| **allkeys-random** | 모든 키 | 무작위 | 모든 키 중 무작위 삭제 |

```
LRU vs LFU 차이:

LRU (Least Recently Used) — 마지막 접근 시점 기준
  Key A: 10초 전 접근  ← 가장 최근 → 유지
  Key B: 5분 전 접근   ← 오래됨 → 삭제 대상

LFU (Least Frequently Used) — 접근 빈도 기준
  Key A: 총 3회 접근   ← 적게 사용 → 삭제 대상
  Key B: 총 1000회 접근 ← 자주 사용 → 유지
```

### 용도별 권장 정책

```
┌─────────────────────────────────────────────────────────┐
│                   Eviction 정책 선택 가이드               │
│                                                         │
│   캐시 용도 (Cache)                                      │
│   └─ allkeys-lru  : 범용 캐시, 대부분의 경우 적합         │
│   └─ allkeys-lfu  : 인기 있는 데이터를 더 오래 유지        │
│                     (핫/콜드 데이터 차이가 클 때)           │
│                                                         │
│   세션 저장소 (Session Store)                             │
│   └─ volatile-ttl : TTL이 짧은(= 곧 만료될) 세션부터 삭제 │
│                                                         │
│   데이터 저장소 (영구 보관 의도)                           │
│   └─ noeviction   : 삭제 없이 에러 반환                   │
│                     → 애플리케이션에서 에러 핸들링 필요      │
└─────────────────────────────────────────────────────────┘
```

### INFO memory로 메모리 사용량 확인

```redis
INFO memory
```

| 필드 | 의미 | 확인 포인트 |
|------|------|------------|
| `used_memory` | Redis가 할당한 메모리 총량 | maxmemory 대비 비율 확인 |
| `used_memory_human` | 사람이 읽기 쉬운 형태 | — |
| `used_memory_peak` | 최대 메모리 사용량 | 피크 시 메모리 부족 여부 |
| `used_memory_rss` | OS가 보고하는 실제 메모리 | used_memory와 큰 차이 → 단편화 |
| `mem_fragmentation_ratio` | RSS / used_memory | 1.0~1.5 정상, >2.0 단편화 심각 |
| `maxmemory` | 설정된 최대 메모리 | 0이면 제한 없음 (위험) |
| `maxmemory_policy` | 현재 Eviction 정책 | 의도한 정책인지 확인 |

```redis
# 실무에서 자주 확인하는 패턴
127.0.0.1:6379> INFO memory
# Memory
used_memory:1234567
used_memory_human:1.18M
used_memory_peak:2345678
used_memory_peak_human:2.24M
mem_fragmentation_ratio:1.12
maxmemory:2147483648
maxmemory_human:2.00G
maxmemory_policy:allkeys-lru
```

---

## 38. 영속성(Persistence): RDB와 AOF의 동작원리와 백업/복구 실습

### Redis의 영속성 딜레마

Redis는 메모리 기반이므로, 프로세스가 종료되면 데이터가 사라진다. 이를 방지하기 위해 두 가지 영속성 메커니즘을 제공한다.

```
┌─────────────────────────────────────────────────────────────────┐
│                     Redis 영속성 옵션                             │
│                                                                 │
│   ┌──────────────┐              ┌──────────────┐                │
│   │     RDB      │              │     AOF      │                │
│   │  (Snapshot)  │              │ (Write Log)  │                │
│   │              │              │              │                │
│   │  주기적으로   │              │  모든 쓰기    │                │
│   │  전체 메모리  │              │  명령어를     │                │
│   │  스냅샷 저장  │              │  순서대로     │                │
│   │              │              │  로그에 기록  │                │
│   │  dump.rdb    │              │  appendonly.aof│               │
│   └──────────────┘              └──────────────┘                │
│                                                                 │
│   빠른 복구                      데이터 유실 최소화               │
│   컴팩트한 파일                  파일 크기 큼                     │
│   데이터 유실 가능               복구 속도 느림                   │
└─────────────────────────────────────────────────────────────────┘
```

### RDB (Redis Database): 주기적 스냅샷

특정 시점의 전체 메모리 데이터를 바이너리 파일(`dump.rdb`)로 저장한다.

#### SAVE vs BGSAVE

```
SAVE (동기 방식):
  메인 스레드가 직접 스냅샷 생성
  → 스냅샷 완료까지 모든 명령어 블로킹
  → 프로덕션에서 절대 사용 금지

BGSAVE (비동기 방식):
  1. Redis가 자식 프로세스를 fork()
  2. 자식 프로세스가 백그라운드에서 스냅샷 생성
  3. 메인 프로세스는 정상적으로 명령어 처리 계속
  4. 스냅샷 완료 후 자식 프로세스 종료
```

```
┌─────────────────────────────────────────────────────┐
│                 BGSAVE 동작 과정                     │
│                                                     │
│   Main Process                                      │
│   ├─ 명령 처리 중...                                 │
│   ├─ BGSAVE 트리거 → fork()                         │
│   ├─ 명령 처리 계속 (GET, SET, INCR...)             │
│   ├─ 명령 처리 계속...                               │
│   └─ 자식 프로세스 완료 알림 수신                     │
│                                                     │
│   Child Process (fork된 복제본)                      │
│   ├─ 메모리 데이터를 dump.rdb에 기록                 │
│   ├─ Copy-on-Write: 변경된 페이지만 복사             │
│   └─ 기록 완료 → 종료                               │
└─────────────────────────────────────────────────────┘
```

#### redis.conf RDB 설정

```bash
# redis.conf
# save <seconds> <changes>
# "N초 동안 M개 이상의 키가 변경되면 자동으로 BGSAVE 실행"

save 900 1      # 900초(15분) 동안 1개 이상 변경 시
save 300 10     # 300초(5분) 동안 10개 이상 변경 시
save 60 10000   # 60초(1분) 동안 10,000개 이상 변경 시

# RDB 파일 이름
dbfilename dump.rdb

# RDB 파일 저장 경로
dir /var/lib/redis/
```

#### RDB 장단점

| 장점 | 단점 |
|------|------|
| 복구 속도 빠름 (바이너리 로딩) | 마지막 스냅샷 이후 데이터 유실 가능 |
| 파일 크기 컴팩트 | fork() 시 메모리 사용량 일시적 증가 |
| 백업/이전이 간편 (파일 하나) | 데이터셋이 크면 fork() 시간 증가 |

### AOF (Append Only File): 모든 쓰기 명령 로그

모든 쓰기 명령어를 순서대로 로그 파일에 기록한다. 서버 재시작 시 이 로그를 처음부터 재실행하여 데이터를 복구한다.

#### AOF 설정

```bash
# redis.conf
appendonly yes
appendfilename "appendonly.aof"

# fsync 정책
appendfsync always    # 매 명령마다 디스크에 동기화 (가장 안전, 가장 느림)
appendfsync everysec  # 1초마다 동기화 (권장, 최대 1초 유실)
appendfsync no        # OS에 위임 (가장 빠름, 유실 범위 불확실)
```

```
appendfsync 정책 비교:

always     ■■■■■■■■■■ 안전성
           ■■         성능
           최대 유실: 0건 (이론적)

everysec   ■■■■■■■■   안전성     ← 권장
           ■■■■■■■    성능
           최대 유실: 1초 분량

no         ■■■        안전성
           ■■■■■■■■■■ 성능
           최대 유실: OS 버퍼 크기만큼 (불확실)
```

#### AOF Rewrite: 로그 압축

AOF 파일은 시간이 지남에 따라 계속 커진다. `AOF Rewrite`는 현재 메모리 상태를 기준으로 새로운 최소 명령 세트를 생성하여 파일 크기를 줄인다.

```
AOF Rewrite 전:
  SET counter 1
  INCR counter
  INCR counter
  INCR counter
  INCR counter          ← 5개 명령어

AOF Rewrite 후:
  SET counter 5          ← 1개 명령어로 압축
```

```redis
# 수동 Rewrite
BGREWRITEAOF

# 자동 Rewrite 조건 (redis.conf)
auto-aof-rewrite-percentage 100   # AOF 파일이 이전 대비 100% 이상 커지면
auto-aof-rewrite-min-size 64mb    # 최소 64MB 이상일 때만
```

#### AOF 장단점

| 장점 | 단점 |
|------|------|
| 데이터 유실 최소화 (최대 1초) | RDB 대비 파일 크기 큼 |
| 사람이 읽을 수 있는 텍스트 형식 | 복구 속도 느림 (명령 재실행) |
| 실수로 `FLUSHALL` 시 복구 가능 | 쓰기 성능에 영향 (always 모드) |

### RDB + AOF 혼합 전략 (Redis 4.0+)

Redis 4.0부터 두 방식을 결합할 수 있다. AOF Rewrite 시 RDB 형식의 프리앰블을 AOF 파일 앞에 삽입하여, **빠른 로딩(RDB) + 최소 유실(AOF)** 의 장점을 모두 취한다.

```bash
# redis.conf
aof-use-rdb-preamble yes   # Redis 4.0+ 기본값: yes
```

```
혼합 모드 AOF 파일 구조:

┌─────────────────────────────┐
│  RDB 프리앰블 (바이너리)     │ ← 마지막 Rewrite 시점의 스냅샷
│  빠르게 로딩                 │
├─────────────────────────────┤
│  AOF 인크리멘탈 로그 (텍스트)│ ← Rewrite 이후 추가된 명령들
│  순서대로 재실행             │
└─────────────────────────────┘
```

### 백업/복구 절차 실습

#### 백업

```bash
# 1. BGSAVE로 최신 스냅샷 생성
redis-cli BGSAVE

# 2. 스냅샷 완료 확인
redis-cli LASTSAVE

# 3. dump.rdb 파일 복사
cp /var/lib/redis/dump.rdb /backup/redis/dump_$(date +%Y%m%d_%H%M%S).rdb

# AOF 사용 시 AOF 파일도 복사
cp /var/lib/redis/appendonly.aof /backup/redis/
```

#### 복구

```bash
# 1. Redis 중지
redis-cli SHUTDOWN NOSAVE

# 2. 백업 파일을 Redis 데이터 디렉토리에 복사
cp /backup/redis/dump_20260314_120000.rdb /var/lib/redis/dump.rdb

# 3. Redis 시작 (자동으로 dump.rdb 로딩)
redis-server /etc/redis/redis.conf

# 4. 데이터 확인
redis-cli DBSIZE
redis-cli INFO keyspace
```

---

## 39. 모니터링 기초: INFO, MONITOR, SLOWLOG로 진단하기

### INFO 명령어: Redis 상태 종합 리포트

`INFO` 명령어는 Redis 서버의 전체 상태를 섹션별로 보여준다.

```redis
INFO              # 모든 섹션
INFO server       # 서버 정보 (버전, OS, 업타임 등)
INFO clients      # 연결된 클라이언트 정보
INFO memory       # 메모리 사용량 (앞서 다룸)
INFO stats        # 통계 (명령 처리량, 캐시 히트율 등)
INFO replication  # 복제 상태
INFO keyspace     # DB별 키 수
```

### INFO memory: 메모리 진단

```redis
127.0.0.1:6379> INFO memory
# Memory
used_memory:1048576
used_memory_human:1.00M
used_memory_peak:2097152
used_memory_peak_human:2.00M
used_memory_rss:1572864
mem_fragmentation_ratio:1.50
```

| 지표 | 정상 범위 | 경고 |
|------|----------|------|
| `mem_fragmentation_ratio` | 1.0 ~ 1.5 | >2.0: 심각한 메모리 단편화 |
| `used_memory` vs `maxmemory` | 80% 미만 | >90%: Eviction 임박 |
| `used_memory_peak` | — | 평소 대비 급등 시 메모리 릭 의심 |

### INFO stats: 처리량과 캐시 히트율

```redis
127.0.0.1:6379> INFO stats
# Stats
total_connections_received:1000
total_commands_processed:5000000
instantaneous_ops_per_sec:12500
keyspace_hits:4500000
keyspace_misses:500000
```

**캐시 히트율 계산**:

```
히트율 = keyspace_hits / (keyspace_hits + keyspace_misses) × 100

예시: 4,500,000 / (4,500,000 + 500,000) × 100 = 90%

┌────────────────────────────────────────────┐
│           캐시 히트율 기준                   │
│                                            │
│   95% 이상    : 우수 ✅                     │
│   90% ~ 95%  : 양호                        │
│   80% ~ 90%  : 개선 필요 (TTL 조정 검토)    │
│   80% 미만    : 심각 ❌ (캐시 전략 재검토)   │
└────────────────────────────────────────────┘
```

### MONITOR: 실시간 명령어 스트림

`MONITOR`는 Redis에 들어오는 **모든 명령어를 실시간으로 출력**한다.

```redis
127.0.0.1:6379> MONITOR
OK
1710412800.123456 [0 127.0.0.1:54321] "GET" "user:1234"
1710412800.123789 [0 127.0.0.1:54322] "SET" "cache:api:profile:5678" "{...}"
1710412800.124012 [0 127.0.0.1:54321] "INCR" "counter:page:home"
1710412800.124234 [0 127.0.0.1:54323] "EXPIRE" "session:abc" "1800"
```

> **주의**: `MONITOR`는 모든 명령어를 캡처하므로 **프로덕션에서는 부하가 크다**. 트래픽이 높은 환경에서는 Redis 자체 성능이 50% 이상 저하될 수 있다. 디버깅 목적으로 짧은 시간만 사용하고, 확인이 끝나면 즉시 종료한다.

### SLOWLOG: 느린 명령어 추적

설정한 시간보다 오래 걸린 명령어를 기록한다. 성능 병목을 찾는 가장 중요한 도구 중 하나다.

```redis
# 10ms(10,000마이크로초) 이상 걸린 명령어 기록
CONFIG SET slowlog-log-slower-than 10000

# 최대 128개까지 보관
CONFIG SET slowlog-max-len 128

# 느린 명령어 조회
SLOWLOG GET 10
```

```redis
# SLOWLOG 출력 예시
127.0.0.1:6379> SLOWLOG GET 3
1) 1) (integer) 14           # 로그 ID
   2) (integer) 1710412800   # Unix 타임스탬프
   3) (integer) 45230        # 실행 시간 (마이크로초) = 45.23ms
   4) 1) "SORT"              # 실행한 명령어
      2) "mylist"
      3) "BY"
      4) "weight_*"
   5) "127.0.0.1:54321"      # 클라이언트 주소
   6) ""                     # 클라이언트 이름

2) 1) (integer) 13
   2) (integer) 1710412795
   3) (integer) 23100        # 23.1ms
   4) 1) "SMEMBERS"
      2) "large_set"         # ← 큰 Set에 SMEMBERS = O(N)
   5) "127.0.0.1:54322"
   6) ""
```

**SLOWLOG에서 자주 발견되는 문제 명령어**:

| 명령어 | 시간 복잡도 | 대안 |
|--------|-----------|------|
| `KEYS *` | O(N) | `SCAN` |
| `SMEMBERS` (대규모 Set) | O(N) | `SSCAN` |
| `HGETALL` (대규모 Hash) | O(N) | `HSCAN` 또는 필요한 필드만 `HGET`/`HMGET` |
| `SORT` | O(N+M*log(M)) | 애플리케이션 레벨에서 정렬 |
| `LRANGE 0 -1` (대규모 List) | O(N) | 범위를 제한하여 조회 |

### 외부 모니터링 도구

프로덕션 환경에서는 Redis 내장 명령어만으로는 충분하지 않다. 시각화와 알림이 가능한 외부 도구를 함께 사용한다.

| 도구 | 특징 | 용도 |
|------|------|------|
| **Redis Insight** | Redis Labs 공식 GUI | 키 탐색, 메모리 분석, 실시간 모니터링 |
| **Grafana + Prometheus** | `redis_exporter` 연동 | 시계열 지표 시각화, 알림 설정 |
| **Datadog / New Relic** | SaaS 모니터링 | 인프라 통합 모니터링 |

---

## 40. 강좌 마무리: 실무자의 마음가짐

### Redis는 도구다 — 모든 문제에 Redis를 쓰지 마라

Redis를 배우면 모든 것을 Redis로 해결하고 싶어진다. 하지만 Redis는 **특정 문제를 잘 해결하는 도구**일 뿐, 만능 해결책이 아니다.

```
Redis가 적합한 경우:
  ✅ 읽기가 쓰기보다 훨씬 많은 데이터 (캐싱)
  ✅ 짧은 생명주기의 데이터 (세션, OTP, Rate Limit)
  ✅ 실시간 카운터, 랭킹, 큐
  ✅ 분산 환경에서 공유 상태 관리

Redis가 부적합한 경우:
  ❌ 복잡한 관계가 있는 데이터 (→ RDB)
  ❌ 대용량 파일/BLOB 저장 (→ Object Storage)
  ❌ 트랜잭션 무결성이 절대적으로 중요한 경우 (→ RDB)
  ❌ 전문 검색 (→ Elasticsearch)
  ❌ 메시지 보장이 필수인 큐 (→ RabbitMQ, Kafka)
```

### 데이터 유실 가능성을 항상 고려하라

Redis는 아무리 RDB + AOF를 설정해도, **메모리 기반의 한계**를 완전히 벗어날 수 없다.

```
원칙: 원본 데이터는 반드시 RDB(PostgreSQL, MySQL 등)에 보관한다.

Redis에 있는 데이터가 날아가도
→ RDB에서 다시 로딩할 수 있어야 한다.

Redis를 "유일한 저장소"로 사용하는 것은
→ 시한폭탄을 안고 운영하는 것과 같다.
```

### 모니터링 없는 Redis는 시한폭탄

```
운영 체크리스트:

□ maxmemory 설정했는가?
□ Eviction 정책을 용도에 맞게 선택했는가?
□ 메모리 사용률 알림을 설정했는가? (80%, 90% 임계치)
□ SLOWLOG를 주기적으로 확인하고 있는가?
□ 캐시 히트율을 추적하고 있는가?
□ 백업(RDB/AOF)이 정상 동작하는지 확인했는가?
□ KEYS * 명령어를 비활성화했는가?
□ 키 네이밍 컨벤션이 팀에 공유되어 있는가?
```

### 지속적인 학습

Redis는 빠르게 발전하고 있다. 기본기를 단단히 다진 후, 다음 영역으로 확장한다.

```
학습 경로:

기본 (이 강좌)
  │
  ├─ Redis 공식 문서: https://redis.io/docs/
  ├─ Redis University: https://university.redis.com/
  │
  ├─ Sentinel (고가용성)
  ├─ Cluster (수평 확장)
  ├─ Redis Streams (이벤트 스트리밍)
  └─ Redis Stack (검색, JSON, 시계열)
```

---

## 핵심 요약

1. **Key 네이밍**: `{서비스}:{도메인}:{식별자}` 형식으로 통일하고, 콜론(:)을 구분자로 사용한다. 가독성과 디버깅 편의성을 우선시한다.
2. **KEYS * 금지**: 싱글 스레드에서 O(N) 전체 스캔은 서버를 블로킹한다. 반드시 `SCAN` 커서 기반 점진적 스캔을 사용한다.
3. **메모리 관리**: `maxmemory`를 물리 메모리의 60~70%로 설정하고, 용도에 맞는 Eviction 정책을 선택한다 (캐시: `allkeys-lru`, 세션: `volatile-ttl`).
4. **영속성 전략**: RDB(빠른 복구) + AOF(최소 유실)를 혼합하여 사용한다. `appendfsync everysec`이 대부분의 경우 최적 균형점이다.
5. **모니터링 필수**: `INFO memory`로 메모리 단편화, `INFO stats`로 캐시 히트율, `SLOWLOG`로 느린 명령어를 주기적으로 점검한다.
6. **실무 원칙**: Redis는 보조 저장소다. 원본 데이터는 반드시 RDB에 보관하고, 모니터링 없이 운영하지 않는다.

---

**다음**: [[Section 7 - 대용량 서비스 설계 보너스 트랙]]
