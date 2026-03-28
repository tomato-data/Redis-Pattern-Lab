# Redis Pattern Lab

[![English](https://img.shields.io/badge/lang-English-blue)](README.md)

> **12개 실무 Redis 패턴**을 FastAPI로 직접 구현 — 캐시부터 분산 락까지, 만들면서 배우기.

## Highlights

- **12개 실습 패턴** — 캐싱, 세션, 카운터, 분산 락, Rate Limiting, 랭킹, Pub/Sub, Stream까지
- **AI 활용 구조적 학습** — Claude로 [학습 로드맵](roadmap/) 설계, 프로젝트 프레임워크 구축, [심화 문서](docs/) 작성
- **한 줄로 실행** — `docker compose up`으로 Redis 7.2 + RedisInsight + FastAPI 즉시 구동
- **벤치마크 기반 인사이트** — 모든 패턴에 Redis vs SQLite 성능 비교 데이터 포함

---

## 왜 만들었나

실무에서 Redis를 캐싱과 세션 관리에 도입해서 사용하고 있었지만, 이해가 피상적이라는 걸 깨달았습니다. `SET`과 `GET`을 호출하는 방법은 알지만, Redis가 왜 싱글 스레드 I/O 멀티플렉싱을 쓰는지, Sorted Set이 언제 SQL `ORDER BY`를 이기는지, 캐시 스탬피드를 어떻게 방지하는지는 몰랐습니다.

문서를 수동적으로 읽는 대신, Claude를 활용해 구조적인 커리큘럼을 설계하고, 각 패턴을 직접 구현하고 실행하고 관계형 DB와 비교하는 실습 환경을 구축했습니다.

---

## 학습 방식

```
1. AI가 구조적 학습 로드맵 생성 (roadmap/)
       ↓
2. AI가 프로젝트 골격 + Docker 환경 구축
       ↓
3. 패턴별 직접 구현, 실행, 결과 관찰
       ↓
4. 학습 내용을 AI와 함께 심화 문서로 정리 (docs/)
       ↓
5. 검토하고, 질문하고, 개념이 확실해질 때까지 반복
```

> 코드는 내가 작성하고, AI는 튜터. [학습 로드맵](roadmap/)과 [학습 노트](docs/) 전문 참조.

---

## 12개 패턴

| # | 패턴 | 자료구조 | 실무 사용처 | 핵심 개념 |
|---|------|---------|-----------|----------|
| 01 | [기본 자료형](app/routers/step01_basics.py) | String, List, Set, Hash, Sorted Set | 모든 패턴의 기반 | 5가지 핵심 타입, O(1) 연산 |
| 02 | [Cache-Aside](app/routers/step02_cache.py) | String (JSON) | 상품 페이지 캐싱 | TTL + jitter로 스탬피드 방지 |
| 03 | [최근 본 항목](app/routers/step03_recent.py) | List | 쇼핑몰 "최근 본 상품" | LREM → LPUSH → LTRIM 파이프라인 |
| 04 | [분산 세션](app/routers/step04_session.py) | Hash | 멀티 서버 인증 | 슬라이딩 만료, 필드 단위 접근 |
| 05 | [원자적 카운터](app/routers/step05_counter.py) | String + Set | 조회수, 좋아요 토글 | INCR 원자성, Set으로 중복 방지 |
| 06 | [OTP 인증](app/routers/step06_verification.py) | String + TTL | 휴대폰/이메일 인증 | 자동 만료, 쿨다운, 시도 횟수 제한 |
| 07 | [분산 락](app/routers/step07_lock.py) | String (NX) + Lua | 쿠폰 재고 관리 | SET NX EX + Lua 소유권 확인 |
| 08 | [Rate Limiting](app/routers/step08_ratelimit.py) | String / Sorted Set | API 쿼터 제어 | 고정 vs 슬라이딩 윈도우 비교 |
| 09 | [실시간 랭킹](app/routers/step09_ranking.py) | Sorted Set | 게임 리더보드 | O(log N) vs SQL O(N log N) |
| 10 | [Pub/Sub](app/routers/step10_pubsub.py) | Channel | 실시간 알림 | Fire-and-Forget + SSE 스트리밍 |
| 11 | [Stream](app/routers/step11_stream.py) | Stream | 이벤트 소싱, 작업 큐 | Consumer Group + XACK 확인 응답 |
| 12 | [벤치마크](app/routers/step12_comparison.py) | 전체 | 성능 검증 | Redis vs SQLite 직접 비교 |

---

## 벤치마크 결과

| 테스트 | Redis | SQLite | 차이 |
|--------|-------|--------|------|
| 단일 읽기 | 0.137 ms | 0.843 ms | **6.1배** |
| 100회 반복 읽기 (평균) | 0.088 ms | 0.284 ms | **3.2배** |
| 카운터 100회 증가 | 6.031 ms | 164.063 ms | **27.2배** |
| Pipeline vs 개별 | 0.724 ms | 6.109 ms | **8.4배** |
| Top 10 랭킹 조회 | 0.164 ms | 1.094 ms | **6.7배** |

> 쓰기에서 가장 큰 차이(27배) — SQLite는 UPDATE마다 디스크 커밋, Redis INCR은 메모리에서 완료.
> 네트워크 없는 로컬 SQLite에서도 Redis가 일관되게 3~27배 빠름.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| **앱 프레임워크** | FastAPI 0.115 (async) |
| **Redis 클라이언트** | redis-py 5.2 (async) |
| **비교 DB** | SQLite + SQLAlchemy 2.0 (async) |
| **컨테이너** | Docker Compose (Redis 7.2, RedisInsight, FastAPI) |
| **언어** | Python 3.12 |

---

## 프로젝트 구조

```
Redis-Pattern-Lab/
├── app/
│   ├── main.py                 # FastAPI 앱 + Redis 커넥션 풀
│   ├── database.py             # 비교용 SQLite 모델
│   ├── dependencies.py         # DI (get_redis, get_db)
│   └── routers/
│       ├── step01_basics.py    # 5가지 자료형
│       ├── step02_cache.py     # Cache-Aside + TTL jitter
│       ├── step03_recent.py    # 최근 본 항목 (List 파이프라인)
│       ├── step04_session.py   # 분산 세션 (Hash)
│       ├── step05_counter.py   # 원자적 카운터 (INCR + Set)
│       ├── step06_verification.py  # TTL 기반 OTP
│       ├── step07_lock.py      # 분산 락 (Lua Script)
│       ├── step08_ratelimit.py # 고정 & 슬라이딩 윈도우
│       ├── step09_ranking.py   # Sorted Set 리더보드
│       ├── step10_pubsub.py    # Pub/Sub + SSE
│       ├── step11_stream.py    # Stream + Consumer Group
│       └── step12_comparison.py # Redis vs SQLite 벤치마크
│
├── docs/                       # 심화 학습 노트
│   ├── Redis guide.md
│   ├── Redis 명령어 체계.md      # 명령어 분류 체계
│   ├── Redis 운영 핵심 가이드.md   # 운영 가이드
│   ├── Redis QnA 모음.md        # 학습 중 정리한 Q&A 15선
│   ├── 캐시 무효화와 Stampede 방어.md  # 캐시 무효화 전략
│   ├── SET NX XX 옵션.md        # 락 프리미티브
│   ├── Redis Stream 로그 처리 가이드.md  # Stream 아키텍처
│   ├── Sorted Set vs RDB 랭킹.md  # Skip List vs B-Tree
│   ├── 실습 결과.md              # 전 패턴 실행 결과 기록
│   └── Redis 라이선스와 오픈소스 선택.md  # 라이선스 분석
│
├── roadmap/                    # AI 생성 학습 커리큘럼
│   ├── Redis 마스터 로드맵.md     # 마스터 로드맵 (42개 주제, 약 10시간)
│   └── Section 1-8             # 섹션별 상세 노트
│
├── docker-compose.yml          # Redis + RedisInsight + FastAPI
├── Dockerfile
└── requirements.txt
```

---

## 학습 문서

각 패턴을 구현하며 작성한 심화 학습 노트:

| 문서 | 주제 |
|------|------|
| [명령어 분류 체계](docs/Redis%20명령어%20체계.md) | 접두어 체계 (L/S/H/Z/X), 네이밍 규칙 |
| [운영 핵심 가이드](docs/Redis%20운영%20핵심%20가이드.md) | 키 네이밍, SCAN vs KEYS, 메모리 정책, 모니터링 |
| [캐시 무효화 전략](docs/캐시%20무효화와%20Stampede%20방어.md) | TTL / Write-Through / Write-Behind / 이벤트 기반 |
| [Q&A 모음](docs/Redis%20QnA%20모음.md) | 학습 중 정리한 15개 질문과 답 |
| [Stream 아키텍처](docs/Redis%20Stream%20로그%20처리%20가이드.md) | Producer → Stream → Consumer Group 파이프라인 |
| [Sorted Set vs RDB](docs/Sorted%20Set%20vs%20RDB%20랭킹.md) | Skip List O(log N) vs ORDER BY O(N log N) |
| [실습 결과 기록](docs/실습%20결과.md) | 전 패턴 실제 실행 결과 |
| [라이선스 분석](docs/Redis%20라이선스와%20오픈소스%20선택.md) | RSALv2 + SSPL 영향 분석 |

---

## 시작하기

```bash
docker compose up -d

# Swagger UI: http://localhost:8000/docs
# RedisInsight: http://localhost:5540
```

각 스텝은 별도의 API 그룹 — Swagger UI에서 순서대로 실행 (Step 01 → 12).

---

## License

This project is licensed under the [MIT License](LICENSE).
