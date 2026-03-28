# Redis Pattern Lab

[![Korean](https://img.shields.io/badge/lang-Korean-blue)](README.ko.md)

> **12 production Redis patterns** implemented in FastAPI — from cache-aside to distributed locks, learned by building.

## Highlights

- **12 hands-on patterns** covering caching, sessions, counters, locks, rate limiting, ranking, Pub/Sub, and Streams
- **AI-assisted structured learning** — Claude generated the [study roadmap](roadmap/), scaffolded the project framework, and produced [deep-dive documentation](docs/)
- **Runnable in one command** — `docker compose up` spins up Redis 7.2, RedisInsight, and the FastAPI app
- **Benchmark-backed insights** — every pattern includes Redis vs SQLite performance comparisons with real numbers

---

## Why I Built This

I introduced Redis at work for caching and session management, but realized my understanding was surface-level — I knew *how* to call `SET` and `GET`, but not *why* Redis uses single-threaded I/O multiplexing, when Sorted Sets beat SQL `ORDER BY`, or how to prevent cache stampedes.

Instead of reading docs passively, I used Claude to design a structured curriculum and build a hands-on lab where I implement each pattern myself, run it, and compare the results against a relational database.

---

## How I Study

```
1. AI generates a structured roadmap (roadmap/)
       ↓
2. AI scaffolds the project skeleton + Docker environment
       ↓
3. I implement each pattern, run it, and observe the results
       ↓
4. AI helps me write deep-dive docs from what I learned (docs/)
       ↓
5. I review, question, and refine until the concept sticks
```

> The code is mine; AI is the tutor. See the full [Learning Roadmap](roadmap/) and [Study Notes](docs/).

---

## 12 Patterns

| # | Pattern | Data Structure | Real-World Use Case | Key Concept |
|---|---------|---------------|-------------------|-------------|
| 01 | [Basic Types](app/routers/step01_basics.py) | String, List, Set, Hash, Sorted Set | Foundation for all patterns | 5 core types, O(1) operations |
| 02 | [Cache-Aside](app/routers/step02_cache.py) | String (JSON) | Product page caching | TTL + jitter to prevent stampede |
| 03 | [Recent Items](app/routers/step03_recent.py) | List | "Recently viewed" on e-commerce | LREM → LPUSH → LTRIM pipeline |
| 04 | [Distributed Session](app/routers/step04_session.py) | Hash | Multi-server auth | Sliding expiration, field-level access |
| 05 | [Atomic Counter](app/routers/step05_counter.py) | String + Set | View counts, like toggles | INCR atomicity, deduplication via Set |
| 06 | [OTP Verification](app/routers/step06_verification.py) | String with TTL | Phone/email verification | Auto-expiry, cooldown, attempt limiting |
| 07 | [Distributed Lock](app/routers/step07_lock.py) | String (NX) + Lua | Coupon stock management | SET NX EX + Lua ownership check |
| 08 | [Rate Limiting](app/routers/step08_ratelimit.py) | String / Sorted Set | API quota enforcement | Fixed vs sliding window comparison |
| 09 | [Real-time Ranking](app/routers/step09_ranking.py) | Sorted Set | Game leaderboard | O(log N) vs SQL O(N log N) |
| 10 | [Pub/Sub](app/routers/step10_pubsub.py) | Channel | Live notifications | Fire-and-forget + SSE streaming |
| 11 | [Stream](app/routers/step11_stream.py) | Stream | Event sourcing, task queues | Consumer Group + XACK acknowledgment |
| 12 | [Benchmark](app/routers/step12_comparison.py) | All | Performance validation | Redis vs SQLite head-to-head |

---

## Benchmark Results

| Test | Redis | SQLite | Difference |
|------|-------|--------|-----------|
| Single read | 0.137 ms | 0.843 ms | **6.1x** |
| 100 batch reads (avg) | 0.088 ms | 0.284 ms | **3.2x** |
| 100 counter increments | 6.031 ms | 164.063 ms | **27.2x** |
| Pipeline vs individual | 0.724 ms | 6.109 ms | **8.4x** |
| Top 10 ranking | 0.164 ms | 1.094 ms | **6.7x** |

> Writes show the largest gap (27x) — SQLite commits to disk per UPDATE, Redis INCR completes in memory.
> Even with local SQLite (no network), Redis is consistently 3-27x faster.

---

## Tech Stack

| Area | Technology |
|------|-----------|
| **App Framework** | FastAPI 0.115 (async) |
| **Redis Client** | redis-py 5.2 (async) |
| **Comparison DB** | SQLite + SQLAlchemy 2.0 (async) |
| **Container** | Docker Compose (Redis 7.2, RedisInsight, FastAPI) |
| **Language** | Python 3.12 |

---

## Project Structure

```
Redis-Pattern-Lab/
├── app/
│   ├── main.py                 # FastAPI app + Redis connection pool
│   ├── database.py             # SQLite models for comparison
│   ├── dependencies.py         # DI (get_redis, get_db)
│   └── routers/
│       ├── step01_basics.py    # 5 data types
│       ├── step02_cache.py     # Cache-Aside + TTL jitter
│       ├── step03_recent.py    # Recent items (List pipeline)
│       ├── step04_session.py   # Distributed session (Hash)
│       ├── step05_counter.py   # Atomic counter (INCR + Set)
│       ├── step06_verification.py  # OTP with TTL
│       ├── step07_lock.py      # Distributed lock (Lua)
│       ├── step08_ratelimit.py # Fixed & sliding window
│       ├── step09_ranking.py   # Sorted Set leaderboard
│       ├── step10_pubsub.py    # Pub/Sub + SSE
│       ├── step11_stream.py    # Stream + Consumer Group
│       └── step12_comparison.py # Redis vs SQLite benchmark
│
├── docs/                       # Deep-dive study notes
│   ├── Redis guide.md
│   ├── Redis 명령어 체계.md      # Command taxonomy
│   ├── Redis 운영 핵심 가이드.md   # Operations guide
│   ├── Redis QnA 모음.md        # 15 Q&A from studying
│   ├── 캐시 무효화와 Stampede 방어.md  # Cache invalidation strategies
│   ├── SET NX XX 옵션.md        # Lock primitives
│   ├── Redis Stream 로그 처리 가이드.md  # Stream architecture
│   ├── Sorted Set vs RDB 랭킹.md  # Skip List vs B-Tree
│   ├── 실습 결과.md              # Lab results with real data
│   └── Redis 라이선스와 오픈소스 선택.md  # License analysis
│
├── roadmap/                    # AI-generated learning curriculum
│   ├── Redis 마스터 로드맵.md     # Master roadmap (42 topics, ~10h)
│   └── Section 1-8             # Detailed notes per section
│
├── docker-compose.yml          # Redis + RedisInsight + FastAPI
├── Dockerfile
└── requirements.txt
```

---

## Documentation

Study notes produced while implementing each pattern:

| Document | Topic |
|----------|-------|
| [Command Taxonomy](docs/Redis%20명령어%20체계.md) | Prefix system (L/S/H/Z/X), naming conventions |
| [Operations Guide](docs/Redis%20운영%20핵심%20가이드.md) | Key naming, SCAN vs KEYS, memory policy, monitoring |
| [Cache Invalidation](docs/캐시%20무효화와%20Stampede%20방어.md) | TTL / Write-Through / Write-Behind / Event-based strategies |
| [Q&A Collection](docs/Redis%20QnA%20모음.md) | 15 questions answered while studying |
| [Stream Architecture](docs/Redis%20Stream%20로그%20처리%20가이드.md) | Producer → Stream → Consumer Group pipeline |
| [Sorted Set vs RDB](docs/Sorted%20Set%20vs%20RDB%20랭킹.md) | Skip List O(log N) vs ORDER BY O(N log N) |
| [Lab Results](docs/실습%20결과.md) | Actual output from every pattern |
| [License Analysis](docs/Redis%20라이선스와%20오픈소스%20선택.md) | RSALv2 + SSPL impact assessment |

---

## Getting Started

```bash
docker compose up -d

# Swagger UI: http://localhost:8000/docs
# RedisInsight: http://localhost:5540
```

Each step is a separate API group — open Swagger UI and run the endpoints in order (Step 01 → 12).

---

## License

This project is licensed under the [MIT License](LICENSE).
