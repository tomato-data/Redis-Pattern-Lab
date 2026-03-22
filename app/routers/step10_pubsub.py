"""
Step 10: Pub/Sub 실시간 알림 (Section 4, 5 - 패턴 09)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Redis Pub/Sub로 실시간 메시지 브로커를 체험.
SSE(Server-Sent Events)로 브라우저에서 실시간 수신.
"""

import asyncio
import json
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.dependencies import get_redis

router = APIRouter(prefix="/step10", tags=["Step 10: Pub/Sub"])


@router.post("/publish")
async def publish_message(channel: str, message: str, redis: Redis = Depends(get_redis)):
    """PUBLISH — 채널에 메시지 발행"""
    data = json.dumps({"message": message, "timestamp": time.time()})
    receivers = await redis.publish(channel, data)
    return {
        "command": f'PUBLISH {channel} "{message}"',
        "receivers": receivers,
        "설명": f"현재 {receivers}명이 '{channel}' 채널을 구독 중"
            + (" — 구독자가 없어 메시지가 소멸됨 (Fire-and-Forget)" if receivers == 0 else ""),
    }


@router.get("/subscribe/{channel}")
async def subscribe_sse(channel: str, request: Request):
    """SSE로 Pub/Sub 메시지 실시간 수신 (브라우저에서 테스트)"""

    async def event_generator():
        redis: Redis = request.app.state.redis
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)

        try:
            yield f"data: {{\"status\": \"subscribed\", \"channel\": \"{channel}\"}}\n\n"

            async for message in pubsub.listen():
                if await request.is_disconnected():
                    break
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/subscribe-page/{channel}")
async def subscribe_page(channel: str):
    """Pub/Sub 테스트 HTML 페이지"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>Redis Pub/Sub - {channel}</title></head>
    <body>
        <h2>Redis Pub/Sub 실시간 수신 [{channel}]</h2>
        <p style="color:gray">구독 중... 다른 탭에서 POST /step10/publish 로 메시지를 보내세요.</p>
        <div id="messages" style="font-family:monospace; background:#f0f0f0; padding:10px;"></div>
        <script>
            const evtSource = new EventSource("/step10/subscribe/{channel}");
            const div = document.getElementById("messages");
            evtSource.onmessage = function(event) {{
                const p = document.createElement("p");
                p.textContent = new Date().toLocaleTimeString() + " → " + event.data;
                div.prepend(p);
            }};
            evtSource.onerror = function() {{
                const p = document.createElement("p");
                p.style.color = "red";
                p.textContent = "연결 끊김. 재연결 시도 중...";
                div.prepend(p);
            }};
        </script>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)


@router.post("/notification/{user_id}")
async def send_notification(user_id: int, message: str, redis: Redis = Depends(get_redis)):
    """사용자별 알림 발행"""
    channel = f"user:{user_id}:notifications"
    data = json.dumps({
        "type": "notification",
        "user_id": user_id,
        "message": message,
        "timestamp": time.time(),
    })
    receivers = await redis.publish(channel, data)
    return {
        "channel": channel,
        "receivers": receivers,
        "로그": "Fire-and-Forget: 구독자가 없으면 메시지는 영구 소멸. 메시지 보존이 필요하면 Stream을 사용.",
    }
