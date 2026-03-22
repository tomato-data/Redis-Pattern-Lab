
# Section 2: Redis 기본 개념 및 환경 설정

> Redis의 정체성, 내부 동작 원리, 핵심 특징을 이해하고 로컬 환경에서 Redis를 설치하여 직접 명령어를 실행해본다.

---

## 6. Redis란? 단순 Key-Value를 넘어선 데이터 구조 서버

### Redis의 정의

Redis = **Re**mote **Di**ctionary **S**erver

이름 그대로 "원격 딕셔너리 서버"다. 네트워크를 통해 접근 가능한 인메모리 Key-Value 저장소로 시작했지만, 현재는 **데이터 구조 서버(Data Structure Server)** 로 불리는 것이 더 정확하다.

```
┌────────────────────────────────────────────────────────┐
│                     Redis의 정체성                       │
│                                                        │
│   2009년 출발                    현재                    │
│   ┌────────────┐              ┌────────────────────┐   │
│   │ Key-Value  │    진화 →    │ Data Structure     │   │
│   │ Store      │              │ Server             │   │
│   └────────────┘              └────────────────────┘   │
│                                                        │
│   단순 문자열 저장/조회          List, Set, Hash,        │
│                                Sorted Set, Stream,     │
│                                Bitmap, HyperLogLog...  │
└────────────────────────────────────────────────────────┘
```

### Key-Value 스토어를 넘어서

Redis를 단순 Key-Value 저장소로 이해하면 활용 범위를 크게 제한하게 된다. Redis는 **서버 측에서 자료구조를 직접 조작**할 수 있다는 점이 핵심이다.

```
일반 Key-Value 스토어:
  SET user:1 '{"name":"Alice","scores":[90,85,92]}'
  GET user:1  →  전체 JSON을 가져와서 클라이언트에서 파싱

Redis (데이터 구조 서버):
  HSET user:1 name "Alice"          ← Hash 필드 단위 접근
  LPUSH user:1:scores 92 85 90      ← List 자료구조 직접 사용
  HGET user:1 name                  → "Alice" (필요한 필드만)
  LRANGE user:1:scores 0 0          → "92" (최신 점수만)
```

### Redis가 지원하는 주요 자료구조

| 자료구조 | 설명 | 대표 용도 |
|----------|------|----------|
| **String** | 가장 기본. 문자열, 숫자, 바이너리 모두 저장 | 캐시, 카운터, 세션 토큰 |
| **List** | 삽입 순서 유지 양방향 연결 리스트 | 메시지 큐, 최근 활동 로그 |
| **Set** | 중복 없는 비정렬 집합 | 태그, 고유 방문자, 집합 연산 |
| **Hash** | 필드-값 쌍의 맵 (객체와 유사) | 사용자 프로필, 설정값 |
| **Sorted Set** | 점수 기반 정렬 집합 | 랭킹, 리더보드, 타임라인 |
| **Stream** | 로그형 append-only 데이터 구조 | 이벤트 소싱, 메시지 브로커 |
| **Bitmap** | 비트 단위 연산 | 출석 체크, 플래그 관리 |
| **HyperLogLog** | 확률적 카디널리티 추정 | 고유 방문자 수 근사 집계 |
| **Geospatial** | 위경도 좌표 저장 및 거리 계산 | 주변 매장 검색, 위치 추적 |

### In-Memory 데이터베이스란?

**In-Memory 데이터베이스**란 데이터를 디스크가 아닌 **메인 메모리(RAM)에 저장하고 처리**하는 데이터베이스다.

```
전통적 DB (PostgreSQL, MySQL):
  ┌──────────┐     ┌──────────┐
  │ 클라이언트 │ ──→ │  DB 엔진  │ ──→ 디스크에서 읽기/쓰기
  └──────────┘     └──────────┘     (느리지만 영구 보존)

In-Memory DB (Redis):
  ┌──────────┐     ┌──────────┐
  │ 클라이언트 │ ──→ │  Redis   │ ──→ 메모리에서 읽기/쓰기
  └──────────┘     └──────────┘     (빠르지만 휘발 가능)
```

In-Memory의 장점:
- **읽기/쓰기 속도**: 디스크 대비 수백~수만 배 빠름
- **예측 가능한 지연 시간**: 디스크 I/O의 불확실성 제거

In-Memory의 단점:
- **용량 제한**: RAM은 디스크보다 비싸고 용량이 작음
- **휘발성**: 전원이 꺼지면 데이터 소멸 (영속성 옵션으로 보완)

### Redis vs Memcached

둘 다 인메모리 Key-Value 스토어지만, 근본적인 차이가 있다.

| 비교 항목 | Redis | Memcached |
|----------|-------|-----------|
| **자료구조** | String, List, Set, Hash, Sorted Set, Stream 등 | String만 |
| **영속성** | RDB 스냅샷, AOF 로그 지원 | 없음 (순수 캐시) |
| **클러스터링** | Redis Cluster 네이티브 지원 | 클라이언트 측 샤딩만 |
| **Pub/Sub** | 지원 | 미지원 |
| **Lua 스크립팅** | 지원 (서버 측 로직) | 미지원 |
| **메모리 효율** | 자료구조에 따라 다름 | 단순 slab 할당으로 효율적 |
| **멀티스레드** | 기본 싱글 스레드 (I/O는 6.0+에서 멀티) | 멀티스레드 |

**선택 기준**: 단순 문자열 캐싱만 필요하면 Memcached도 충분하지만, 자료구조 활용, 영속성, Pub/Sub 등 하나라도 필요하면 Redis가 유일한 선택이다.

---

## 7. Redis의 특징: 싱글 스레드의 반전 매력과 영속성

### 싱글 스레드 모델

Redis의 명령어 처리는 **단일 스레드**로 동작한다. 모든 클라이언트의 명령어가 하나의 Event Loop에서 순차적으로 처리된다.

```
┌──────────────────────────────────────────────────────┐
│                Redis Event Loop                      │
│                                                      │
│   Client A ──┐                                       │
│   Client B ──┼──→ Event Queue ──→ [ 단일 스레드 ] ──→ 응답  │
│   Client C ──┘    ┌────────┐     ┌──────────────┐   │
│                   │ CMD 1  │ ──→ │              │   │
│                   │ CMD 2  │     │  순차 실행     │   │
│                   │ CMD 3  │ ──→ │              │   │
│                   │ CMD 4  │     │  하나씩 처리   │   │
│                   └────────┘     └──────────────┘   │
│                                                      │
│   I/O Multiplexing (epoll/kqueue)으로                │
│   여러 클라이언트 연결을 단일 스레드가 관리               │
└──────────────────────────────────────────────────────┘
```

### 왜 싱글 스레드인데 빠른가?

직관적으로 "스레드가 하나면 느리지 않나?"라고 생각할 수 있다. 하지만 Redis가 빠른 이유는 스레드 수가 아니라 **무엇을 하느냐**에 있다.

**1) 컨텍스트 스위칭 비용 제거**

```
멀티스레드 DB:
  Thread A 실행 → 스위칭(수 μs) → Thread B 실행 → 스위칭 → Thread C
  매 스위칭마다 CPU 캐시 무효화, 레지스터 저장/복원 발생

Redis (싱글 스레드):
  CMD 1 → CMD 2 → CMD 3 → CMD 4 → ...
  스위칭 없이 연속 실행. CPU 캐시 히트율 극대화.
```

**2) I/O 멀티플렉싱 (epoll / kqueue)**

싱글 스레드라고 해서 한 번에 하나의 클라이언트만 상대하는 것이 아니다. `epoll`(Linux) 또는 `kqueue`(macOS)를 사용하여 **수만 개의 커넥션을 단일 스레드로 동시에 감시**한다.

```
I/O Multiplexing 동작 원리:

  epoll_wait()로 준비된 소켓 확인
       │
       ▼
  ┌─ Socket A: 데이터 있음 → 명령 읽기 → 실행 → 응답
  ├─ Socket B: 대기 중     → 건너뜀
  ├─ Socket C: 데이터 있음 → 명령 읽기 → 실행 → 응답
  └─ Socket D: 대기 중     → 건너뜀
       │
       ▼
  다시 epoll_wait()  (논블로킹 루프)
```

**3) 순수 메모리 연산**

Redis의 각 명령어는 메모리에서 수행되므로 실행 자체가 **마이크로초 단위**로 끝난다. 디스크 I/O 대기가 없으므로 스레드를 여러 개 만들어 대기시킬 필요가 없다.

```
명령어 실행 시간 비교:

  Redis GET  : ~1μs (메모리 접근)
  MySQL SELECT: ~1ms+ (디스크 I/O 포함)

  1μs 짜리 작업을 싱글 스레드로 돌려도
  초당 100만 건 이상 처리 가능
```

**4) 락(Lock) 오버헤드 제거**

멀티스레드 환경에서는 공유 데이터 접근 시 뮤텍스/락이 필수다. 싱글 스레드는 이 자체가 불필요하므로 **락 경합, 데드락 위험이 원천 차단**된다.

### 싱글 스레드의 주의점: O(N) 명령어 블로킹

싱글 스레드의 가장 큰 약점은 **하나의 느린 명령어가 전체 서버를 멈추게 한다**는 것이다.

```
위험한 시나리오:

  시간 ──→
  ┌────┬──────────────────────────┬────┬────┐
  │CMD1│   KEYS * (10만 건 스캔)   │CMD3│CMD4│
  │ 1μs│        500ms 소요!        │    │    │
  └────┴──────────────────────────┴────┴────┘
         ↑                         ↑
         이 시간 동안               CMD3, CMD4는
         모든 클라이언트가           500ms 동안
         응답을 못 받음              대기해야 함
```

**피해야 할 O(N) 명령어들**:

| 위험 명령어 | 대안 | 이유 |
|------------|------|------|
| `KEYS *` | `SCAN` | 전체 키 스캔. 프로덕션 절대 금지 |
| `SMEMBERS` (큰 Set) | `SSCAN` | Set 전체 반환 |
| `HGETALL` (큰 Hash) | `HSCAN` | Hash 전체 반환 |
| `LRANGE 0 -1` (큰 List) | 범위 제한 | List 전체 반환 |
| `FLUSHALL` | 비동기 옵션 사용 | 전체 DB 삭제 |

> `KEYS` 명령어는 개발 환경에서만 사용하고, 프로덕션에서는 반드시 `SCAN`으로 대체해야 한다. `SCAN`은 커서 기반으로 소량씩 순회하므로 서버를 블로킹하지 않는다.

### 영속성 옵션 개요: RDB vs AOF

Redis는 인메모리지만 **데이터를 디스크에 기록하는 영속성 메커니즘**을 제공한다.

```
┌───────────────────────────────────────────────────┐
│              Redis 영속성 옵션                      │
│                                                   │
│   RDB (Snapshotting)          AOF (Append-Only)   │
│   ┌─────────────────┐        ┌─────────────────┐  │
│   │ 특정 시점의       │        │ 모든 쓰기 명령을  │  │
│   │ 메모리 전체를     │        │ 로그 파일에       │  │
│   │ 바이너리로 덤프   │        │ 순서대로 기록     │  │
│   └─────────────────┘        └─────────────────┘  │
│                                                   │
│   장점: 복구 빠름              장점: 데이터 손실 최소  │
│   단점: 스냅샷 간 손실          단점: 파일 크기 큼     │
│                                                   │
│   ──────── 또는 함께 사용 가능 ────────             │
└───────────────────────────────────────────────────┘
```

| 항목 | RDB | AOF |
|------|-----|-----|
| **방식** | 주기적 스냅샷 (fork 기반) | 모든 쓰기 명령 로그 기록 |
| **데이터 손실** | 마지막 스냅샷 이후 손실 가능 | 설정에 따라 최대 1초 손실 |
| **복구 속도** | 빠름 (바이너리 로드) | 느림 (명령 재실행) |
| **파일 크기** | 작음 (압축 바이너리) | 큼 (텍스트 로그) |
| **서버 부하** | fork 시 메모리 사용 증가 | fsync 빈도에 따라 다름 |

> 영속성 옵션의 상세 동작 원리와 설정은 Section 6에서 다룬다. 여기서는 "Redis도 데이터를 디스크에 저장할 수 있다"는 사실만 알면 된다.

---

## 8. Redis 특징 총 정리: 9가지 핵심 키워드

Redis를 정의하는 9가지 키워드를 하나의 표로 정리한다.

| 키워드 | 한 줄 설명 |
|--------|----------|
| **In-Memory** | 데이터를 RAM에 저장하여 마이크로초 단위 응답 제공 |
| **Single Thread** | 명령어를 단일 스레드로 순차 처리하여 락 없는 안전성 확보 |
| **Key-Value** | 모든 데이터를 고유 키에 매핑하는 기본 저장 모델 |
| **Data Structures** | String, List, Set, Hash, Sorted Set, Stream 등 서버 측 자료구조 제공 |
| **Persistence** | RDB 스냅샷과 AOF 로그로 디스크 영속성 지원 |
| **Replication** | Master-Replica 구조로 읽기 분산 및 고가용성 확보 |
| **Pub/Sub** | 채널 기반 메시지 발행/구독으로 실시간 통신 지원 |
| **Lua Scripting** | 서버 측에서 Lua 스크립트를 원자적으로 실행하여 복잡한 연산 처리 |
| **Cluster** | 데이터를 여러 노드에 자동 분산(샤딩)하여 수평 확장 가능 |

### 9가지 키워드 간의 관계

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│   ┌────────────┐   ┌───────────────┐                │
│   │ In-Memory  │   │ Single Thread │                │
│   │ (속도 기반) │   │ (단순성 기반)  │                │
│   └─────┬──────┘   └───────┬───────┘                │
│         │                  │                         │
│         ▼                  ▼                         │
│   ┌────────────────────────────────┐                │
│   │     Key-Value + Data Structures │  ← 핵심 모델   │
│   └──────────────┬─────────────────┘                │
│                  │                                   │
│         ┌────────┼────────┐                          │
│         ▼        ▼        ▼                          │
│   ┌──────┐ ┌────────┐ ┌────────┐                    │
│   │Persis│ │Replica │ │Cluster │  ← 운영 안정성      │
│   │tence │ │tion    │ │        │                     │
│   └──────┘ └────────┘ └────────┘                    │
│                  │                                   │
│         ┌────────┴────────┐                          │
│         ▼                 ▼                          │
│   ┌──────────┐    ┌────────────┐                    │
│   │ Pub/Sub  │    │Lua Script  │  ← 확장 기능        │
│   └──────────┘    └────────────┘                    │
│                                                      │
└──────────────────────────────────────────────────────┘
```

- **In-Memory + Single Thread**: Redis의 성능 기반. 메모리 연산이라 싱글 스레드로도 충분히 빠르다.
- **Key-Value + Data Structures**: Redis의 핵심 데이터 모델. 단순 키-값을 넘어 다양한 구조 제공.
- **Persistence + Replication + Cluster**: 운영 안정성. 데이터 보존, 복제, 수평 확장.
- **Pub/Sub + Lua Scripting**: 확장 기능. 실시간 메시징과 서버 측 로직 실행.

---

## 9. Redis 설치 및 CLI 시작하기

### Mac에서 설치 (Homebrew)

```bash
# Redis 설치
brew install redis

# Redis 서버 시작 (포그라운드)
redis-server

# Redis 서버를 백그라운드 서비스로 시작
brew services start redis

# 서비스 상태 확인
brew services info redis

# 서비스 중지
brew services stop redis
```

### Windows에서 설치

Redis는 공식적으로 Linux/macOS만 지원한다. Windows에서는 두 가지 방법을 권장한다.

**방법 1: WSL2 (Windows Subsystem for Linux)**

```bash
# WSL2 설치 후 Ubuntu 터미널에서
sudo apt update
sudo apt install redis-server

# Redis 서버 시작
sudo service redis-server start
```

**방법 2: Docker (권장)**

```bash
# Docker Desktop 설치 후
docker run -d --name redis -p 6379:6379 redis:latest
```

### redis-cli 기본 사용법

Redis 서버에 접속하여 명령어를 실행하는 클라이언트 도구다.

```bash
# Redis CLI 접속 (기본: localhost:6379)
redis-cli

# 특정 호스트/포트로 접속
redis-cli -h 127.0.0.1 -p 6379
```

### 필수 기본 명령어

```bash
# 연결 확인
127.0.0.1:6379> PING
PONG

# 값 저장
127.0.0.1:6379> SET greeting "Hello Redis"
OK

# 값 조회
127.0.0.1:6379> GET greeting
"Hello Redis"

# 키 존재 여부 확인 (1: 존재, 0: 없음)
127.0.0.1:6379> EXISTS greeting
(integer) 1

# 키 삭제
127.0.0.1:6379> DEL greeting
(integer) 1

# 삭제 확인
127.0.0.1:6379> GET greeting
(nil)

# 만료 시간이 있는 키 설정 (10초 후 자동 삭제)
127.0.0.1:6379> SET session:abc123 "user:1" EX 10
OK

# 남은 만료 시간 확인
127.0.0.1:6379> TTL session:abc123
(integer) 7
```

### 연결 확인 및 기본 정보

```bash
# 서버 정보 요약
127.0.0.1:6379> INFO server
# Server
redis_version:7.2.4
...

# 현재 DB의 키 수 확인
127.0.0.1:6379> DBSIZE
(integer) 0

# 모든 설정 확인
127.0.0.1:6379> CONFIG GET *

# CLI 종료
127.0.0.1:6379> QUIT
```

### 명령어 요약

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `PING` | 연결 확인 | `PING` → `PONG` |
| `SET` | 값 저장 | `SET key value` |
| `GET` | 값 조회 | `GET key` → `"value"` |
| `DEL` | 키 삭제 | `DEL key` → `(integer) 1` |
| `EXISTS` | 존재 여부 | `EXISTS key` → `1` or `0` |
| `TTL` | 남은 만료 시간 | `TTL key` → 초 단위 |
| `DBSIZE` | 키 수 확인 | `DBSIZE` → `(integer) N` |

---

## 10. Docker로 Redis 실행하기

### Docker로 Redis 컨테이너 실행

```bash
# Redis 컨테이너를 백그라운드로 실행
docker run -d \
  --name redis \
  -p 6379:6379 \
  redis:latest
```

| 옵션 | 설명 |
|------|------|
| `-d` | 백그라운드(detached) 모드로 실행 |
| `--name redis` | 컨테이너 이름을 `redis`로 지정 |
| `-p 6379:6379` | 호스트 6379 포트를 컨테이너 6379 포트에 매핑 |
| `redis:latest` | 최신 Redis 이미지 사용 |

### 컨테이너 내부에서 redis-cli 실행

```bash
# 실행 중인 Redis 컨테이너에 접속하여 CLI 실행
docker exec -it redis redis-cli
```

```
127.0.0.1:6379> PING
PONG
```

### INFO server로 버전 및 서버 정보 확인

```bash
127.0.0.1:6379> INFO server
# Server
redis_version:7.2.4
redis_git_sha1:00000000
redis_git_dirty:0
redis_build_id:abc123def456
redis_mode:standalone
os:Linux 5.15.0 x86_64
arch_bits:64
multiplexing_api:epoll
gcc_version:12.2.0
process_id:1
run_id:a1b2c3d4e5f6...
tcp_port:6379
uptime_in_seconds:3600
uptime_in_days:0
hz:10
configured_hz:10
```

주요 확인 항목:

| 필드 | 의미 |
|------|------|
| `redis_version` | Redis 버전 |
| `redis_mode` | 실행 모드 (standalone, sentinel, cluster) |
| `os` | 호스트 OS 정보 |
| `multiplexing_api` | I/O 멀티플렉싱 방식 (epoll, kqueue) |
| `tcp_port` | 수신 대기 포트 |
| `uptime_in_seconds` | 서버 가동 시간 |

### Docker 컨테이너 관리 필수 명령어

```bash
# 실행 중인 컨테이너 목록
docker ps

# 컨테이너 중지
docker stop redis

# 컨테이너 시작
docker start redis

# 컨테이너 로그 확인
docker logs redis

# 컨테이너 삭제 (중지 후)
docker stop redis && docker rm redis
```

### Docker Compose로 Redis 정의

프로젝트에서 Redis를 반복적으로 사용할 때는 `docker-compose.yml`로 정의하면 편리하다.

```yaml
# docker-compose.yml
version: "3.8"

services:
  redis:
    image: redis:7.2-alpine
    container_name: redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes
    restart: unless-stopped

volumes:
  redis-data:
```

| 설정 | 설명 |
|------|------|
| `redis:7.2-alpine` | Alpine 기반 경량 이미지 (약 30MB) |
| `volumes: redis-data:/data` | 데이터를 Docker 볼륨에 저장하여 컨테이너 재시작 시에도 유지 |
| `--appendonly yes` | AOF 영속성 활성화 |
| `restart: unless-stopped` | 수동 중지 전까지 자동 재시작 |

```bash
# Docker Compose로 실행
docker compose up -d

# 상태 확인
docker compose ps

# 중지 및 제거
docker compose down

# 볼륨까지 제거 (데이터 삭제)
docker compose down -v
```

### 데이터 영속성이 필요 없는 개발용 최소 설정

```yaml
# docker-compose.yml (개발용)
version: "3.8"

services:
  redis:
    image: redis:7.2-alpine
    ports:
      - "6379:6379"
```

---

## 핵심 요약

1. **Redis = 데이터 구조 서버**: 단순 Key-Value를 넘어 List, Set, Hash, Sorted Set, Stream 등 서버 측에서 자료구조를 직접 조작 가능
2. **싱글 스레드이지만 빠른 이유**: 메모리 연산 + I/O 멀티플렉싱 + 컨텍스트 스위칭/락 없음으로 초당 수십만 건 처리
3. **싱글 스레드의 약점**: `KEYS *` 같은 O(N) 명령어는 전체 서버를 블로킹하므로 프로덕션에서 `SCAN`으로 대체
4. **영속성**: RDB(스냅샷)와 AOF(로그) 두 가지 방식으로 인메모리의 휘발성 보완
5. **9가지 핵심 키워드**: In-Memory, Single Thread, Key-Value, Data Structures, Persistence, Replication, Pub/Sub, Lua Scripting, Cluster
6. **환경 설정**: Mac은 Homebrew, Windows는 WSL2/Docker, 실무에서는 Docker Compose로 정의하여 관리

---

**다음**: [[Section 3 - Redis 자료형과 필수 명령어]]
