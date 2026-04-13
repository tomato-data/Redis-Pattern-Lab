# learnings — Redis Pattern Lab

> 사용자(토마토)가 직접 쓴 산출물. Claude가 만든 Phase 스펙은 `../docs/`에 있다.

## 구조

- `qna/` — Phase 진행 중 Q&A
- `retrospectives/` — Phase 완료 회고
- `topics/` — Phase에 귀속되지 않는 크로스커팅 심화

---

## Phase 맵

| Phase | 배운 것 (2줄) | Q&A | 회고 |
|---|---|---|---|
| 01 | _(회고 백필 예정)_ | — | — |
| 02 | _(회고 백필 예정)_ | — | — |
| 03 | _(회고 백필 예정)_ | — | — |
| 04 | _(회고 백필 예정)_ | — | — |
| 05 | _(회고 백필 예정)_ | — | — |
| 06 | _(회고 백필 예정)_ | — | — |
| 07 | _(회고 백필 예정)_ | — | — |
| 08 | _(회고 백필 예정)_ | — | — |

초기 학습 기록은 Phase 단위로 분리되지 않은 채 누적되었기 때문에 Q&A는 [qna/cross-cutting.md](qna/cross-cutting.md)에 통합되어 있다. 이후 Phase 단위 분할이 필요하면 `qna/phaseNN.md`로 분리한다.

---

## Cross-cutting Topics

| 파일 | 설명 |
|---|---|
| [redis-guide-outline](topics/redis-guide-outline.md) | 전체 Redis 학습 범위 개요 (초기 마스터 아웃라인) |
| [redis-운영-핵심-가이드](topics/redis-운영-핵심-가이드.md) | 운영 관점 핵심 정리 |
| [redis-명령어-체계](topics/redis-명령어-체계.md) | 명령어 구조 체계화 |
| [redis-stream-로그-처리](topics/redis-stream-로그-처리.md) | Stream 기반 로그 처리 |
| [set-nx-xx-옵션](topics/set-nx-xx-옵션.md) | SET NX/XX 옵션 의미와 활용 |
| [캐시-무효화와-stampede-방어](topics/캐시-무효화와-stampede-방어.md) | 캐시 무효화·Stampede 방어 전략 |
| [sorted-set-vs-rdb-랭킹](topics/sorted-set-vs-rdb-랭킹.md) | 랭킹 구현에서 Sorted Set vs RDB 비교 |
| [redis-라이선스와-오픈소스-선택](topics/redis-라이선스와-오픈소스-선택.md) | 2024년 라이선스 이슈와 대안 선택 기준 |
| [실습-결과](topics/실습-결과.md) | 패턴별 실습에서 측정한 실제 결과 로그 |
