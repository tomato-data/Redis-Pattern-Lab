"""
Step 11: Redis Stream (Section 4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pub/Sub의 한계(메시지 유실)를 보완하는 로그형 자료구조.
Consumer Group으로 분담 처리 + ACK 메커니즘 체험.
"""

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.dependencies import get_redis

router = APIRouter(prefix="/step11", tags=["Step 11: Stream"])


@router.post("/add")
async def stream_add(
    stream: str = "events",
    data: dict = {"type": "order", "user": "Alice", "item": "keyboard"},
    maxlen: int | None = 1000,
    redis: Redis = Depends(get_redis),
):
    """XADD — Stream에 메시지 추가"""
    kwargs = {}
    if maxlen:
        kwargs["maxlen"] = maxlen
        kwargs["approximate"] = True

    message_id = await redis.xadd(stream, data, **kwargs)
    length = await redis.xlen(stream)

    return {
        "command": f"XADD {stream} * {data}" + (f" MAXLEN ~ {maxlen}" if maxlen else ""),
        "message_id": message_id,
        "stream_length": length,
        "설명": f"메시지 ID {message_id} = Unix타임스탬프(ms)-시퀀스번호. 메시지는 Stream에 영구 저장 (Pub/Sub과 다름).",
    }


@router.get("/range/{stream}")
async def stream_range(
    stream: str,
    start: str = "-",
    end: str = "+",
    count: int = 10,
    redis: Redis = Depends(get_redis),
):
    """XRANGE — 범위로 메시지 조회"""
    messages = await redis.xrange(stream, start, end, count=count)
    return {
        "command": f"XRANGE {stream} {start} {end} COUNT {count}",
        "messages": [{"id": msg_id, "data": data} for msg_id, data in messages],
        "count": len(messages),
        "설명": "- = 최소 ID, + = 최대 ID. 과거 메시지를 언제든 조회 가능 (Pub/Sub에서는 불가).",
    }


@router.get("/length/{stream}")
async def stream_length(stream: str, redis: Redis = Depends(get_redis)):
    """XLEN — Stream 길이"""
    length = await redis.xlen(stream)
    return {"command": f"XLEN {stream}", "length": length}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Consumer Group
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/group/create")
async def create_consumer_group(
    stream: str = "events",
    group: str = "workers",
    start_id: str = "0",
    redis: Redis = Depends(get_redis),
):
    """XGROUP CREATE — Consumer Group 생성"""
    try:
        await redis.xgroup_create(stream, group, id=start_id, mkstream=True)
        return {
            "command": f"XGROUP CREATE {stream} {group} {start_id} MKSTREAM",
            "설명": f"'{group}' 그룹 생성 완료. start_id={start_id} (0=처음부터, $=지금부터)",
        }
    except Exception as e:
        if "BUSYGROUP" in str(e):
            return {"message": f"그룹 '{group}'은 이미 존재합니다"}
        raise


@router.get("/group/read")
async def read_from_group(
    stream: str = "events",
    group: str = "workers",
    consumer: str = "worker-1",
    count: int = 5,
    redis: Redis = Depends(get_redis),
):
    """XREADGROUP — Consumer Group에서 메시지 읽기"""
    messages = await redis.xreadgroup(group, consumer, {stream: ">"}, count=count)

    if not messages:
        return {
            "command": f"XREADGROUP GROUP {group} {consumer} COUNT {count} STREAMS {stream} >",
            "messages": [],
            "설명": "새 메시지 없음. > 는 '아직 이 그룹에 전달되지 않은 메시지'를 의미",
        }

    result = []
    for stream_name, stream_messages in messages:
        for msg_id, data in stream_messages:
            result.append({"id": msg_id, "data": data})

    return {
        "command": f"XREADGROUP GROUP {group} {consumer} COUNT {count} STREAMS {stream} >",
        "consumer": consumer,
        "messages": result,
        "count": len(result),
        "설명": "메시지를 읽으면 Pending 상태. XACK로 처리 완료를 알려야 함.",
    }


@router.post("/group/ack")
async def ack_message(
    stream: str = "events",
    group: str = "workers",
    message_id: str = "",
    redis: Redis = Depends(get_redis),
):
    """XACK — 메시지 처리 완료 확인"""
    if not message_id:
        return {"error": "message_id를 입력하세요"}

    result = await redis.xack(stream, group, message_id)
    return {
        "command": f"XACK {stream} {group} {message_id}",
        "acknowledged": result,
        "설명": "ACK 처리된 메시지는 Pending 목록에서 제거됨. Pub/Sub에는 없는 메커니즘.",
    }


@router.get("/group/pending")
async def pending_messages(
    stream: str = "events",
    group: str = "workers",
    count: int = 10,
    redis: Redis = Depends(get_redis),
):
    """XPENDING — ACK 되지 않은 메시지 조회"""
    try:
        summary = await redis.xpending(stream, group)
        details = await redis.xpending_range(stream, group, "-", "+", count)

        return {
            "command": f"XPENDING {stream} {group}",
            "summary": {
                "pending_count": summary.get("pending", 0),
                "min_id": summary.get("min"),
                "max_id": summary.get("max"),
                "consumers": summary.get("consumers"),
            },
            "pending_messages": [
                {
                    "id": msg.get("message_id"),
                    "consumer": msg.get("consumer"),
                    "idle_time_ms": msg.get("time_since_delivered"),
                    "delivery_count": msg.get("times_delivered"),
                }
                for msg in details
            ],
        }
    except Exception as e:
        return {"error": str(e), "hint": "먼저 /group/create로 그룹을 생성하세요"}


@router.get("/vs-pubsub")
async def stream_vs_pubsub():
    """Stream vs Pub/Sub 비교"""
    return {
        "비교": {
            "메시지 영속성": {"Pub/Sub": "없음 (Fire-and-Forget)", "Stream": "있음 (로그형 저장)"},
            "과거 메시지 조회": {"Pub/Sub": "불가", "Stream": "XRANGE로 가능"},
            "Consumer Group": {"Pub/Sub": "없음", "Stream": "XREADGROUP으로 분담 처리"},
            "ACK 메커니즘": {"Pub/Sub": "없음", "Stream": "XACK로 처리 확인"},
            "적합 시나리오": {
                "Pub/Sub": "실시간 알림, 설정 전파 (유실 허용)",
                "Stream": "이벤트 소싱, 작업 큐 (유실 방지)",
            },
        }
    }
