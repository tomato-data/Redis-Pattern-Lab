# Redis Pattern Lab

[![Korean](https://img.shields.io/badge/lang-Korean-blue)](README.ko.md)

> **12 production Redis patterns** implemented in FastAPI — from cache-aside to distributed locks, learned by building.

## Highlights

- **12 hands-on patterns** covering caching, sessions, counters, locks, rate limiting, ranking, Pub/Sub, and Streams
- **AI-assisted structured learning** — Claude generated the [phase specs and master roadmap](docs/phases/), scaffolded the project framework, and I documented every [deep-dive topic and Q&A](learnings/) as I built
- **Runnable in one command** — `docker compose up` spins up Redis 7.2, RedisInsight, and the FastAPI app
- **Benchmark-backed insights** — every pattern includes Redis vs SQLite performance comparisons with real numbers

---

## Why I Built This

I introduced Redis at work for caching and session management, but realized my understanding was surface-level — I knew *how* to call `SET` and `GET`, but not *why* Redis uses single-threaded I/O multiplexing, when Sorted Sets beat SQL `ORDER BY`, or how to prevent cache stampedes.

Instead of reading docs passively, I used Claude to design a structured curriculum and build a hands-on lab where I implement each pattern myself, run it, and compare the results against a relational database.

---

## How I Study

```
1. AI generates phase specs + a master roadmap (docs/phases/)
       ↓
2. AI scaffolds the project skeleton + Docker environment
       ↓
3. I implement each pattern, run it, and observe the results
       ↓
4. I document Q&A and deep-dive topics as I go (learnings/)
       ↓
5. I review, question, and refine until the concept sticks
```

> The code is mine; AI is the tutor. See [`docs/phases/`](docs/phases/) for phase specs and [`learnings/`](learnings/) for Q&A and topic deep-dives.

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
├── docs/                       # Claude-authored specs (see docs/README.md)
│   ├── README.md               # Phase index
│   ├── phases/                 # phase01~08 + master roadmap
│   └── plans/                  # /tdd-plan outputs
│
├── learnings/                  # User-authored notes (see learnings/README.md)
│   ├── README.md               # Phase map + topic index
│   ├── qna/                    # Phase Q&A (currently integrated in cross-cutting.md)
│   ├── retrospectives/         # Per-phase retrospectives
│   └── topics/                 # Cross-cutting deep-dives
│       ├── redis-명령어-체계.md
│       ├── redis-운영-핵심-가이드.md
│       ├── redis-stream-로그-처리.md
│       ├── set-nx-xx-옵션.md
│       ├── 캐시-무효화와-stampede-방어.md
│       ├── sorted-set-vs-rdb-랭킹.md
│       ├── redis-라이선스와-오픈소스-선택.md
│       └── 실습-결과.md
│
├── docker-compose.yml          # Redis + RedisInsight + FastAPI
├── Dockerfile
└── requirements.txt
```

---

## Documentation

Study notes are split by authorship. Phase specs live in [`docs/`](docs/README.md) (Claude-written); my own Q&A, retrospectives, and topic deep-dives live in [`learnings/`](learnings/README.md).

| Document | Topic |
|----------|-------|
| [Command Taxonomy](learnings/topics/redis-명령어-체계.md) | Prefix system (L/S/H/Z/X), naming conventions |
| [Operations Guide](learnings/topics/redis-운영-핵심-가이드.md) | Key naming, SCAN vs KEYS, memory policy, monitoring |
| [Cache Invalidation](learnings/topics/캐시-무효화와-stampede-방어.md) | TTL / Write-Through / Write-Behind / Event-based strategies |
| [Q&A Collection](learnings/qna/cross-cutting.md) | Questions answered while studying |
| [Stream Architecture](learnings/topics/redis-stream-로그-처리.md) | Producer → Stream → Consumer Group pipeline |
| [Sorted Set vs RDB](learnings/topics/sorted-set-vs-rdb-랭킹.md) | Skip List O(log N) vs ORDER BY O(N log N) |
| [Lab Results](learnings/topics/실습-결과.md) | Actual output from every pattern |
| [SET NX/XX Options](learnings/topics/set-nx-xx-옵션.md) | Lock primitive semantics |
| [License Analysis](learnings/topics/redis-라이선스와-오픈소스-선택.md) | RSALv2 + SSPL impact assessment |

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
