#Projects/Redis-Study #Stack/Redis

# Sorted Set vs RDB 랭킹: 왜 Redis가 압도적인가

## 문제 상황

게임 리더보드에서 "상위 10명"을 조회한다고 가정하자. 유저가 100만 명이다.

---

## RDB (PostgreSQL) 방식

매 요청마다 이런 쿼리를 실행해야 한다:

```sql
SELECT username, score
FROM rankings
ORDER BY score DESC
LIMIT 10;
```

### 내부 동작

1. `score` 컬럼에 인덱스가 없으면 → **100만 행 전체를 스캔**한 뒤 정렬 (O(N log N))
2. 인덱스가 있어도 → 점수가 **변경될 때마다 인덱스를 재구성**해야 한다
3. 동시에 수천 명이 점수를 갱신하면 → 행 잠금(row lock)으로 인한 **대기 발생**
4. "나는 몇 등이지?" 를 구하려면 → `SELECT COUNT(*) FROM rankings WHERE score > my_score` → **매번 집계 쿼리**

### 병목 요약

| 작업 | 비용 |
|------|------|
| 상위 N명 조회 | 인덱스 있어도 디스크 I/O 발생 |
| 점수 갱신 | UPDATE + 인덱스 재구성 + 행 잠금 |
| 내 등수 조회 | COUNT 집계 쿼리 (O(N)) |
| 동시 갱신 | 락 경합으로 처리량 저하 |

---

## Redis Sorted Set 방식

```redis
ZADD ranking 100 "Alice"
ZINCRBY ranking 50 "Alice"
ZREVRANGE ranking 0 9 WITHSCORES    -- 상위 10명
ZREVRANK ranking "Alice"             -- Alice의 등수
```

### 내부 동작

Sorted Set은 내부적으로 **Skip List**라는 자료구조를 사용한다.

```
Level 4:  HEAD ──────────────────────────────→ Bob(250)
Level 3:  HEAD ──────────────→ Charlie(180) → Bob(250)
Level 2:  HEAD → Alice(100) → Charlie(180) → Bob(250)
Level 1:  HEAD → Alice(100) → Charlie(180) → Bob(250)
```

Skip List는 정렬된 연결 리스트에 여러 단계의 "고속도로"를 깔아놓은 구조다. 어떤 작업이든 **위층에서 아래층으로 내려가며 빠르게 탐색**한다.

| 작업 | Skip List 시간복잡도 | 설명 |
|------|---------------------|------|
| 삽입/변경 (`ZADD`, `ZINCRBY`) | **O(log N)** | 위치를 찾아 끼워넣기 |
| 삭제 (`ZREM`) | **O(log N)** | 위치를 찾아 제거 |
| 등수 조회 (`ZREVRANK`) | **O(log N)** | 탐색하며 건너뛴 노드 수를 카운트 |
| 상위 N명 (`ZREVRANGE`) | **O(log N + M)** | 시작점 탐색 + M개 순회 |

핵심: **데이터를 넣는 순간 정렬이 완료**된다. 조회 시점에 정렬하는 게 아니다.

---

## 직접 비교

유저 100만 명 기준:

| 작업 | PostgreSQL | Redis Sorted Set |
|------|-----------|-----------------|
| **상위 10명 조회** | 인덱스 스캔 + 디스크 I/O (~수 ms) | 메모리에서 바로 반환 (~0.1ms) |
| **점수 갱신** | UPDATE + 인덱스 재구성 + 락 | ZINCRBY 한 줄, 락 없음 (~0.01ms) |
| **내 등수 조회** | COUNT 집계 쿼리 (O(N)) | ZREVRANK (O(log N), ~0.01ms) |
| **초당 처리량** | 수천 건 (디스크 + 락 병목) | 수십만 건 (메모리 + 싱글스레드) |
| **동시 갱신** | 행 잠금 경합 | 싱글 스레드라 경합 자체가 없음 |

---

## 왜 이런 차이가 나는가

1. **저장소**: RDB는 디스크, Redis는 메모리 — 접근 속도가 1,000배 차이
2. **정렬 시점**: RDB는 조회할 때 정렬, Redis는 삽입할 때 정렬 — 읽기가 압도적으로 빠름
3. **락**: RDB는 동시 쓰기 시 행 잠금 필요, Redis는 싱글 스레드라 락이 필요 없음
4. **등수 계산**: RDB는 매번 집계 쿼리, Redis는 Skip List 구조상 탐색 경로에서 자동 계산

---

## 그렇다고 RDB가 필요 없는 건 아니다

Redis Sorted Set은 랭킹의 **실시간 조회/갱신**에 최적이지만:

- 서버가 죽으면 메모리 데이터가 유실될 수 있다 (AOF/RDB 백업으로 완화)
- 복잡한 조건 검색 (예: "서울 거주 유저 중 상위 10명")은 불가능하다

따라서 실무에서는 **Redis로 실시간 랭킹을 서빙**하고, **RDB에 원본 데이터를 보관**하는 하이브리드 구조를 사용한다.

```
유저 점수 획득 → Redis ZINCRBY (실시간 반영)
                  ↓ (주기적 동기화)
               PostgreSQL UPDATE (영구 보관)
```
