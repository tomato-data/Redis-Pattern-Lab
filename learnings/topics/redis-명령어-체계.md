# Redis 명령어 체계

Redis 명령어의 네이밍 규칙과 구조를 정리한다.

---

## 자료구조별 접두사

Redis 명령어는 앞에 자��구조 ��두사가 붙는 패턴이다. 이 패턴만 알면 처음 ��는 명령어도 ���떤 자료���조용인지 바로 알 수 ��다.

| ���두사 | 자료구���   | 예시                        |
| ------- | ----------- | --------------------------- |
| (없음)  | String      | `SET`, `GET`, `INCR`        |
| **L**   | List        | `LPUSH`, `LPOP`, `LRANGE`   |
| **S**   | Set         | `SADD`, `SMEMBERS`, `SCARD` |
| **H**   | Hash        | `HSET`, `HGET`, `HLEN`      |
| **Z**   | Sorted Set  | `ZADD`, `ZRANGE`, `ZCARD`   |
| **X**   | Stream      | `XADD`, `XREAD`, `XACK`     |
| **PF**  | HyperLogLog | `PFADD`, `PFCOUNT`          |

---

## 개수 확인 명령어: LEN vs CARD

자료구조에 따라 "개수 확인" 명령어의 이름이 다르다.

| 자료구조   | 명령어  | 의미                       |
| ---------- | ------- | -------------------------- |
| List       | `LLEN`  | List **Length**            |
| Hash       | `HLEN`  | Hash **Length**            |
| Set        | `SCARD` | Set **Cardinality**        |
| Sorted Set | `ZCARD` | Sorted Set **Cardinality** |

Cardinality는 수학 용어로 **집합의 원소 개수**를 뜻한다. Set과 Sorted Set은 집합 계열이라 CARD를, List와 Hash는 LEN을 사용한다.

---

## 동작 수식어

접두사(자료구조) 외에, 명령어 중간에 붙는 **동작 수식어**가 있다.

| 수식어 | 의미                               | 예시                     |
| ------ | ---------------------------------- | ------------------------ |
| **M**  | Multi — 여러 개를 한번에           | `MGET`, `MSET`, `HMGET`  |
| **B**  | Blocking — 데이터가 올 때까지 대기 | `BLPOP`, `BRPOP`         |
| **BG** | Background — 백그라운드 실행       | `BGSAVE`, `BGREWRITEAOF` |

M 명령어는 네트워크 요청 1번으로 여러 값을 처리하므로, 하나씩 여러 번 호출하는 것보다 효율적이다.
