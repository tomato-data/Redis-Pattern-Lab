#Projects/Redis-Study #Stack/Redis

# Redis QnA 모음

학습 중 발생한 질문과 답변을 기록한다. 로직/아키텍처 질문과 문법/명령어 질문을 구분한다.

---

## 로직 / 아키텍처

### Q1. Redis도 네트워크 I/O는 존재하는 거 아닌가?

FastAPI 서버와 Redis 서버가 별도이니 네트워크 I/O는 존재하는 것 아닌가?

**답변**: 맞다. 둘 다 네트워크 I/O는 동일하게 존재한다. 차이는 요청이 도착한 다음이다.

```
FastAPI ──네트워크 I/O──→ Redis      ──메모리 I/O──→ RAM
FastAPI ──네트워크 I/O──→ PostgreSQL ──디스크 I/O──→ SSD/HDD
```

- PostgreSQL: 네트워크 + 디스크 읽기 (~100us)
- Redis: 네트워크 + 메모리 읽기 (~100ns)

같은 VPC/도커 네트워크 안에서 네트워크 I/O 자체는 ~0.1ms 수준이라 병목이 되지 않는다. 진짜 병목은 항상 디스크 쪽이다.

---

### Q2. Docker 소켓 에러가 "daemon이 안 켜져 있다"가 아니라 "no such file or directory"로 뜨는 이유?

**답변**: 에러 메시지의 차이는 소켓 파일(`.sock`) 존재 여부에 따른 것이다.

- **데몬이 켜져 있는데 연결 실패** → `connection refused` (소켓 파일은 있지만 응답 안 함)
- **데몬이 꺼져 있음** → `no such file or directory` (소켓 파일 자체가 없음)

"daemon이 안 켜져 있다"는 친절한 메시지는 Docker CLI가 해석해서 보여주는 것인데, `docker compose`는 Docker API에 직접 연결을 시도하다 보니 소켓 레벨의 raw 에러가 그대로 노출된 것이다.

---

### Q3. AOF 파일이 계속 쌓이면 엄청 커지지 않나?

**답변**: Redis는 **AOF Rewrite**라는 압축 과정을 자동으로 수행한다. 중간 과정을 다 버리고 최종 상태만 남긴다.

```
# 원본 AOF (6줄)
SET counter 1
INCR counter
INCR counter
INCR counter
INCR counter
INCR counter

# Rewrite 후 (1줄)
SET counter 6
```

`redis.conf` 설정에 따라 자동 트리거된다 (예: 파일 크기가 이전 대비 100% 이상 커지면 실행). 수동으로는 `BGREWRITEAOF` 명령으로 실행 가능하다. BG는 Background — 메인 스레드를 블로킹하지 않고 백그라운드에서 처리한다는 뜻이다.

---

### Q4. Redis에서 "키가 있는데 값이 없는 상태"가 가능한가?

**답변**: Redis에서는 "키가 있는데 값이 없는 상태"가 존재하지 않는다.

- 키가 있다 = 값도 있다
- 키가 없다 = 아예 존재하지 않는다 (`DEL` 하면 키 자체가 사라짐)

Python의 `cache["name"] = None` 같은 개념이 없다. 따라서 XX는 "빈 변수에 넣기"가 아니라 **이미 존재하는 키-값 쌍을 다른 값으로 교체**하는 것이다.

---

### Q5. XX도 NX처럼 동시성 제어 목적으로 사용되는가?

**답변**: 아니다. NX와 XX는 용도가 다르다.

- **NX**: 여러 요청 중 **딱 하나만 성공** → 동시성 제어에 사용 (분산 락)
- **XX**: 여러 요청이 오면 **전부 성공** → 동시성 제어 목적이 아님

```
# NX: 선착순 1명만 성공
서버 A: SET lock "A" NX  → OK     (승자)
서버 B: SET lock "B" NX  → (nil)  (패자)

# XX: 키가 있으면 전부 성공
서버 A: SET config "v1" XX  → OK
서버 B: SET config "v2" XX  → OK  (둘 다 성공)
```

XX는 단순히 "없는 키를 실수로 만들지 않겠다"는 안전장치다.

---

### Q6. SET을 다시 하면 TTL이 왜 -1로 초기화되는가?

**답변**: `SET`은 키를 **완전히 새로 쓰는** 명령이다. 값뿐 아니라 TTL 포함 전부 초기화된다.

```redis
SET temp "value" EX 30     # 키 생성 + TTL 30초
SET temp "new_value"        # 키를 새로 덮어씀 → EX 옵션 없으므로 영구(-1)
```

TTL을 유지하면서 값만 바꾸려면 `KEEPTTL` 옵션을 사용한다:

```redis
SET temp "value" EX 30
SET temp "new_value" KEEPTTL
TTL temp                        # 기존 TTL 유지됨
```

실무에서 세션 값을 갱신할 때 이걸 빠뜨리면 세션이 영원히 안 지워지는 버그가 생긴다.

---

### Q7. Redis Hash와 비밀번호 해시(Hash)는 어떻게 다른가?

**답변**: 이름만 같고 완전히 다른 개념이다.

| | Redis Hash | 비밀번호 Hash |
|---|---|---|
| **정체** | 자료구조 (필드-값 쌍 저장) | 암호학 알고리즘 (단방향 변환) |
| **목적** | 데이터를 구조화해서 저장 | 원본을 복원 불가능하게 변환 |
| **예시** | `{name: "Alice", role: "admin"}` | `password123` → `$2b$12$x8k...` |
| **유래** | Hash Table (딕셔너리) | Hash Function (SHA-256, bcrypt) |

공통 조상은 **Hash Table**이다. Redis Hash는 Python의 `dict`처럼 데이터를 저장하는 용도이고, 비밀번호 해시는 원본을 숨기기 위한 암호학적 변환이다.

---

### Q8. 분산 락 해제를 Lua Script로 하는 이유 — 실행 주체는 누구인가?

**답변**: Python이 아니라 **Redis 서버가 직접** Lua Script를 실행한다.

```
Python (FastAPI)                    Redis 서버
     │                                  │
     ├── eval(스크립트, 키, 인자) ──────→ │
     │                                  ├── GET lock:coupon:1  (내부)
     │                                  ├── owner 비교          (내부)
     │                                  ├── DEL lock:coupon:1  (내부)
     │   ←── 결과 반환 ────────────────── │
```

Python은 스크립트 텍스트를 보내기만 하고, GET → 비교 → DEL 전체가 Redis 내부에서 실행된다. 싱글 스레드로 돌아가니 이 사이에 다른 명령이 끼어들 수 없다.

만약 Python에서 직접 하면:

```
Python                              Redis 서버
     ├── GET lock:coupon:1 ────────→ │  응답
     ←── "owner-A" ──────────────── │
     │   (이 사이에 다른 요청이 DEL 하고 새 락을 잡을 수 있음!)
     ├── DEL lock:coupon:1 ────────→ │  ← 남의 락을 삭제해버림
```

네트워크를 두 번 왕복하는 사이에 빈틈이 생긴다. Lua Script는 이 빈틈을 없앤다.

---

### Q9. SCAN 커서 번호가 왜 28 같은 불규칙한 숫자인가?

**답변**: Redis 내부적으로 키들을 해시 테이블에 저장하는데, 커서 번호는 이 해시 테이블의 **슬롯 위치**다. 순차적인 인덱스가 아니다.

- 커서 값은 예측 불가 (0, 28, 22, 13... 등 불규칙)
- 결과 순서도 삽입 순서와 무관 (해시 테이블 배치 순)
- **0이 돌아오면 전체 순회 완료**라는 것만 보장

커서는 "여기까지 봤으니 다음엔 여기서부터 이어서 봐라"라는 북마크 역할이다.

---

### Q10. String(JSON) vs Hash — Hash가 만능 아닌가? JSON이 유리한 경우는?

비교표만 보면 Hash가 압도적으로 보이지만, JSON이 유리한 케이스가 3가지 있다.

**1. 중첩 구조는 Hash로 표현이 안 됨**

```json
{
  "name": "Kim",
  "address": { "city": "Seoul", "coords": { "lat": 37.5 } },
  "tags": ["vip", "active"]
}
```

Hash는 1단계 flat만 가능. 억지로 넣으면 `address:coords:lat`처럼 키를 늘려야 하고, 배열은 결국 JSON 직렬화를 하게 된다.

**2. 필드가 많아지면 Hash가 메모리를 더 먹음**

Hash 내부 인코딩:
- 필드 ≤ 128개, 값 ≤ 64바이트 → **ziplist** (압축, 효율적)
- 그 이상 → **hashtable** (필드마다 per-field 오버헤드 발생)

필드 30개짜리 객체에서 hashtable 인코딩이 되면, key 1개 + 필드 30개의 메타데이터가 각각 붙는다. JSON은 key 1개 + value 1개(문자열 하나)라서 오히려 메모리가 적을 수 있다.

**3. 항상 통째로 읽는 경우 — JSON이 더 단순**

```bash
GET user:1          → JSON.parse() 끝
HGETALL user:1      → 필드-값 배열을 객체로 재조립 필요
```

둘 다 1 RTT지만, 클라이언트 측에서 `HGETALL` 결과를 객체로 매핑하는 것보다 `JSON.parse`가 대부분 언어에서 더 간단하고 빠르다.

**판단 기준**:

| 상황 | 유리한 쪽 |
|------|----------|
| 필드 개별 읽기/수정 잦음 | **Hash** |
| 특정 필드 원자적 증감 (HINCRBY) | **Hash** |
| 중첩/배열 구조 | **String(JSON)** |
| 필드 수 많음 (100+) | **String(JSON)** — 메모리 |
| 항상 통째로 읽기/쓰기 | **String(JSON)** — 더 단순 |

---

### Q11. Redis Stack은 언제 쓰는 건가? 기본 Redis와 Trade-off는?

Redis Stack = 기본 Redis + RedisJSON + RediSearch + RedisTimeSeries + RedisBloom 등 모듈 번들. 필요한 기능에 따라 선택이 갈린다.

**기본 Redis만 쓸 때**:
- 가볍고 안정적 (20년+ 검증)
- 운영 단순 (모듈 호환성 걱정 없음)
- AWS ElastiCache 등 대부분 매니지드 서비스에서 바로 지원
- 메모리 풋프린트 작음
- 단점: JSON 부분 수정, 전문 검색 등은 애플리케이션에서 직접 구현

**Redis Stack 쓸 때**:
- JSON 부분 수정, 검색, 시계열을 Redis 안에서 해결
- 별도 시스템(Elasticsearch 등) 안 붙여도 됨
- 단점: 매니지드 서비스 지원 제한적 (ElastiCache는 기본 Redis만, Redis Cloud는 Stack 지원), 모듈 버전 관리 필요, 메모리 더 먹음

**실무에서 가장 흔한 패턴**: 기본 Redis + 필요하면 전문 시스템 조합

```
캐시/세션/큐        → Redis (기본)
전문 검색           → Elasticsearch
시계열 데이터        → InfluxDB / Prometheus
복잡한 JSON 조작    → PostgreSQL (jsonb)
```

Redis Stack은 **"시스템 하나 더 붙이기엔 과한데, 기본 Redis로는 부족한" 중간 지점**에서 선택하는 것. 대부분의 프로젝트는 기본 Redis만으로 충분하다.

---

### Q12. BLPOP이 싱글 스레드인데 서버를 30초 블로킹하는 거 아닌가?

`BLPOP queue:jobs 30` — 리스트가 비면 30초 대기. Redis가 싱글 스레드인데 그 동안 다른 요청은?

**답변**: "블로킹"은 **클라이언트 관점**이지, Redis 서버 관점이 아니다. Redis는 이벤트 루프(epoll/kqueue) 기반이라 대기 클라이언트를 등록만 해두고 즉시 다른 요청을 처리한다.

```
Client A: BLPOP queue:jobs 30
  → Redis 내부: "queue:jobs 비어있네 → A를 대기 목록에 등록 → 다음 요청 처리"

Client B: SET foo bar          ← 정상 처리됨
Client C: GET foo              ← 정상 처리됨
Client D: RPUSH queue:jobs "send-email:user-42"
  → Redis 내부: "대기 목록 확인 → A가 기다리고 있네 → 바로 전달"
```

Node.js와 같은 원리:

```
┌─────────────────────────────────────┐
│       Event Loop (epoll/kqueue)     │
│                                     │
│  Client A: BLPOP 대기 → 등록만 해두고 넘어감
│  Client B: SET → 처리 → 응답
│  Client C: GET → 처리 → 응답
│  Client D: RPUSH → 처리 → A에게 알림
│                                     │
│  ※ 어떤 명령도 서버를 "멈추게" 하지 않음
└─────────────────────────────────────┘
```

| 관점 | 블로킹 여부 |
|------|-----------|
| 클라이언트 (BLPOP 호출한 쪽) | **블로킹됨** — 응답 올 때까지 대기 |
| Redis 서버 | **블로킹 아님** — 등록만 하고 다른 요청 계속 처리 |
| 다른 클라이언트들 | **영향 없음** — 평소처럼 명령 실행 |

비유: 식당에 웨이터 1명 — 손님 A가 "디저트 나오면 갖다주세요" → 메모해두고 다른 손님 서빙 → 디저트 나오면 메모 확인 → A에게 전달. 웨이터가 A 앞에서 서서 기다리는 게 아니다.

---

## 문법 / 명령어

### Q13. `recent:user:1`에서 콜론으로 구분된 건 뭔가?

**답변**: `recent:user:1`은 **하나의 키 이름**이다. 콜론(`:`)은 Redis에서 계층 구조를 표현하기 위한 **네이밍 컨벤션**이지, 문법적인 구분자가 아니다.

```
recent:user:1   → "최근 본 상품 / 유저 / 1번" 이라는 의미를 담은 키 이름
lock:order      → "락 / 주문" 이라는 의미를 담은 키 이름
```

이 키에 어떤 자료구조가 담기는지는 사용한 명령어가 결정한다. `LPUSH`를 썼으면 List, `SADD`를 썼으면 Set이 된다.

---

### Q14. `LTRIM`의 인자 `0 1`은 무슨 뜻인가?

**답변**: **0번~1번 인덱스만 남기고 나머지를 삭제**한다.

```
LTRIM 전: [상품C, 상품B, 상품A]   ← 인덱스 0, 1, 2
LTRIM 0 1 후: [상품C, 상품B]       ← 0~1만 남김, 상품A 삭제
```

`LPUSH` + `LTRIM` 조합으로 "최근 N개"를 고정 길이로 유지하는 패턴에 사용된다.

---

### Q15. redis-cli에서 한글이 깨져 보이는 문제

**답변**: redis-cli의 기본 출력 인코딩 문제다. 실제 데이터는 정상이며 Python에서 읽으면 한글로 잘 나온다. CLI에서 한글을 보려면 `--raw` 옵션을 붙인다:

```bash
docker exec -it redis-study redis-cli --raw
```
