#Projects/Redis-Study #Stack/Redis

# SET 명령어 NX / XX 옵션

## 개념

`SET key value` 에 조건을 붙이는 옵션이다.

| 옵션 | 의미 | 동작 | 용도 |
|------|------|------|------|
| **NX** | Not eXists | 키가 **없을 때만** 저장 | 분산 락, 중복 방지 |
| **XX** | eXists eXists | 키가 **있을 때만** 저장 | 안전한 업데이트 |

NX와 XX는 정반대 개념이다.

## 키 네이밍 참고

`lock:order`는 **하나의 키 이름**이다. 콜론(`:`)은 Redis의 네이밍 컨벤션으로, 폴더 구분처럼 가독성을 위해 사용한다. `lock`과 `order`가 별도의 개념이 아니라 `lock:order` 전체가 하나의 키다.

## 예시: NX (없을 때만)

```redis
SET lock:order "server-1" NX   → OK     (키가 없었으니 성공)
SET lock:order "server-2" NX   → (nil)  (이미 있으니 실패)
```

## 예시: XX (있을 때만)

```redis
SET lock:order "server-1" XX   → OK     (키가 이미 있으니 성공)
SET nonexistent "value" XX     → (nil)  (키가 없으니 실패)
```

## Python으로 비유하면

```python
# NX: 없을 때만 저장
if "lock:order" not in cache:
    cache["lock:order"] = "server-1"

# XX: 있을 때만 저장
if "lock:order" in cache:
    cache["lock:order"] = "server-2"
```

## 분산 락 원리 (NX의 핵심 활용)

```redis
서버 A: SET lock:coupon "A" NX EX 10  → OK     (락 획득!)
서버 B: SET lock:coupon "B" NX EX 10  → (nil)  (이미 잠김, 대기)
```

"키가 없을 때만 성공"이므로 먼저 도착한 요청 하나만 성공한다. 쿠폰 중복 발급, 재고 차감 같은 동시성 문제를 이 방식으로 해결한다. `EX 10`은 10초 후 자동 만료 — 락이 영원히 잠기는 것을 방지한다.
