#Projects/Redis-Study #Stack/Redis

# Redis 운영 핵심 가이드

프로덕션 환경에서 Redis를 안정적으로 운영하기 위한 핵심 지식을 정리한다.

---

## 1. Key 네이밍 전략

Redis에는 테이블이나 스키마가 없다. Key 이름이 곧 데이터 구조다.

### 컨벤션: 콜론(:) 구분자

```
{서비스}:{도메인}:{식별자}
```

### 네임스페이스 설계 예시

| 도메인 | Key 패턴 | 자료형 | TTL |
|--------|---------|--------|-----|
| 캐시 | `cache:user:{user_id}` | String (JSON) | 5분 |
| 세션 | `session:{session_id}` | Hash | 30분 |
| 장바구니 | `cart:{user_id}` | Hash | 24시간 |
| 실시간 랭킹 | `rank:daily:{date}` | Sorted Set | 48시간 |
| 최근 본 상품 | `recent:{user_id}` | List | 7일 |
| Rate Limit | `ratelimit:{user_id}:{endpoint}` | String (INCR) | 1분 |
| 분산 락 | `lock:{resource}` | String (NX) | 10초 |
| 인증번호 | `otp:{phone}` | String | 3분 |

### 안티패턴

```redis
# ❌ 너무 긴 키
SET my-awesome-application:user-management-service:user-profile-data:1234 '...'

# ❌ 공백 포함
SET "user profile 1234" '...'

# ❌ 특수문자 (Cluster에서 {}는 해시 슬롯 지정에 사용됨)
SET user{1234} '...'
```

---

## 2. KEYS * 금지 — SCAN으로 대체

### 왜 위험한가

`KEYS *`는 모든 키를 한번에 순회한다. 키가 500만 개면 3~5초 동안 Redis가 **완전히 멈춘다**. 싱글 스레드라서 그 동안 다른 요청 전부 대기.

### SCAN: 안전한 대안

커서 기반으로 조금씩 나눠서 조회한다.

```redis
SCAN 0 MATCH user:* COUNT 5
# 1) "28"              ← 다음 커서 (해시 테이블 슬롯 위치, 불규칙)
# 2) 1) "user:4"
#    2) "user:5"
#    3) "user:1"
#    4) "user:7"

SCAN 28 MATCH user:* COUNT 5
# 1) "22"              ← 다음 커서
# 2) 1) "user:9"
#    ...

SCAN 22 MATCH user:* COUNT 55
# 1) "0"               ← 커서 0 = 순회 완료
# 2) 나머지 전부
```

### 커서 번호가 불규칙한 이유

커서는 Redis 내부 해시 테이블의 슬롯 위치이다. 순차 인덱스가 아니라 북마크 역할. **0이 돌아오면 전체 순회 완료**라는 것만 보장된다.

### 자료구조별 SCAN 변형

| 명령어 | 대상 |
|--------|------|
| `SCAN` | 전체 키 |
| `HSCAN` | Hash 필드 |
| `SSCAN` | Set 멤버 |
| `ZSCAN` | Sorted Set 멤버 |

---

## 3. 메모리 관리: Maxmemory + Eviction 정책

### 현재 설정 (Docker 환경)

```
maxmemory: 256MB
maxmemory-policy: allkeys-lru
```

### Eviction 정책 (실무에서 주로 쓰는 3가지)

| 정책 | 동작 | 사용처 |
|------|------|--------|
| **noeviction** | 메모리 가득 차면 쓰기 거부 (에러) | 데이터 유실 절대 불가 |
| **allkeys-lru** | 모든 키 중 가장 오래 안 쓴 것 삭제 | **캐시 서버 (가장 일반적)** |
| **volatile-lru** | TTL 설정된 키 중에서만 LRU 삭제 | 캐시 + 영구 데이터 혼용 |

LRU = Least Recently Used (가장 오래 사용되지 않은 것)

### 메모리 확인

```bash
redis-cli INFO memory
```

| 항목 | 의미 |
|------|------|
| used_memory | Redis가 실제 사용 중인 메모리 |
| used_memory_rss | OS가 Redis에 할당한 실제 메모리 |
| maxmemory | 한도 |

used_memory_rss가 used_memory보다 큰 이유: OS의 메모리 할당 방식(페이지 단위) + 메모리 단편화.

### 실습 결과

```
used_memory_human: 2.48MB
used_memory_rss_human: 13.29MB
maxmemory: 256MB  → 1%도 안 쓰는 상태
```

---

## 4. 영속성: RDB + AOF

### RDB (스냅샷)

```
save 3600 1 300 100 60 10000

3600초(1시간) 내 1개 이상 변경  → 스냅샷
300초(5분) 내 100개 이상 변경   → 스냅샷
60초(1분) 내 10000개 이상 변경  → 스냅샷
```

변경이 많으면 자주, 적으면 드물게 저장한다.

### AOF (로그)

```
appendonly: yes
appendfsync: everysec
```

| appendfsync 옵션 | 동작 | 데이터 유실 | 성능 |
|-----------------|------|-----------|------|
| **always** | 매 명령마다 디스크 기록 | 거의 0 | 느림 |
| **everysec** | 1초마다 기록 | 최대 1초분 | **균형 (권장)** |
| **no** | OS에 맡김 | 수십 초분 | 빠름 |

현재 `everysec`이므로 서버가 갑자기 죽어도 최대 1초치 데이터만 유실된다.

### AOF Rewrite

AOF 파일이 커지면 Redis가 자동으로 압축한다. 중간 과정을 버리고 최종 상태만 남김.

```
# 수동 실행
BGREWRITEAOF
```

---

## 5. 모니터링

### SLOWLOG — 느린 명령어 추적

```bash
# 설정 확인
CONFIG GET slowlog-log-slower-than
# 10000 (마이크로초) = 10ms 초과 명령어 기록

# 최근 느린 명령어 5개 조회
SLOWLOG GET 5
```

SLOWLOG에 무언가 찍히기 시작하면 위험 신호. 대부분 `KEYS *`, 큰 Set에 `SMEMBERS`, 큰 Hash에 `HGETALL` 같은 O(N) 명령어가 범인이다.

### INFO — 주요 지표

```bash
INFO memory      # 메모리 사용량
INFO stats       # 캐시 히트율 (keyspace_hits / keyspace_misses)
INFO clients     # 연결된 클라이언트 수
INFO replication # 복제 상태
```

캐시 히트율 목표: **95% 이상**. 이하면 TTL 조정이나 캐시 전략 재검토 필요.

### MONITOR — 실시간 명령어 스트림

```bash
redis-cli MONITOR
```

모든 명령어를 실시간으로 출력한다. **디버깅 전용** — 오버헤드가 크므로 프로덕션에서 장시간 사용 금지.

---

## 운영 체크리스트

1. ✅ `maxmemory` 설정 (물리 메모리의 60~70%)
2. ✅ `maxmemory-policy` 설정 (캐시면 `allkeys-lru`)
3. ✅ `KEYS *` 금지 → `SCAN` 사용
4. ✅ AOF `appendfsync everysec` 권장
5. ✅ SLOWLOG 모니터링 (10ms 초과 명령어 추적)
6. ✅ 캐시 히트율 95% 이상 유지
7. ✅ Key 네이밍 컨벤션 통일
8. ✅ 주기적 `INFO memory` 확인
