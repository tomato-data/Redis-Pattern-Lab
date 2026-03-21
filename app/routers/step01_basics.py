"""
Step 01: Redis 기본 자료형 체험 (Section 3)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
String, List, Set, Hash, Sorted Set 5가지 자료형을
직접 조작하고 결과를 확인하는 엔드포인트.
"""

import json
import time

from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.dependencies import get_redis

router = APIRouter(prefix="/step01", tags=["Step 01: 기본 자료형"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STRING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/string/set")
async def string_set(key: str, value: str, ex: int | None = None, redis: Redis = Depends(get_redis)):
    """SET key value [EX seconds] — 값 저장"""
    await redis.set(key, value, ex=ex)
    ttl = await redis.ttl(key)
    return {"command": f"SET {key} {value}" + (f" EX {ex}" if ex else ""), "ttl": ttl}


@router.get("/string/get/{key}")
async def string_get(key: str, redis: Redis = Depends(get_redis)):
    """GET key — 값 조회"""
    value = await redis.get(key)
    ttl = await redis.ttl(key)
    return {"command": f"GET {key}", "value": value, "ttl": ttl}


@router.post("/string/incr/{key}")
async def string_incr(key: str, amount: int = 1, redis: Redis = Depends(get_redis)):
    """INCR / INCRBY — 원자적 증가"""
    if amount == 1:
        result = await redis.incr(key)
        cmd = f"INCR {key}"
    else:
        result = await redis.incrby(key, amount)
        cmd = f"INCRBY {key} {amount}"
    return {"command": cmd, "result": result}


@router.post("/string/mset")
async def string_mset(data: dict, redis: Redis = Depends(get_redis)):
    """MSET — 여러 키-값을 한 번에 저장 (네트워크 왕복 1회)"""
    await redis.mset(data)
    values = await redis.mget(*data.keys())
    return {"command": f"MSET {data}", "values": dict(zip(data.keys(), values))}


@router.post("/string/setnx")
async def string_setnx(key: str, value: str, ex: int = 60, redis: Redis = Depends(get_redis)):
    """SET key value NX EX — 분산 락의 기초 (키가 없을 때만 설정)"""
    result = await redis.set(key, value, nx=True, ex=ex)
    return {
        "command": f"SET {key} {value} NX EX {ex}",
        "acquired": result is not None,
        "설명": "NX: 키가 없을 때만 설정됨" if result else "키가 이미 존재하여 설정 실패",
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LIST
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/list/push")
async def list_push(key: str, values: list[str], side: str = "left", redis: Redis = Depends(get_redis)):
    """LPUSH / RPUSH — 리스트에 값 추가"""
    if side == "left":
        await redis.lpush(key, *values)
        cmd = f"LPUSH {key} {' '.join(values)}"
    else:
        await redis.rpush(key, *values)
        cmd = f"RPUSH {key} {' '.join(values)}"
    items = await redis.lrange(key, 0, -1)
    return {"command": cmd, "list": items, "length": len(items)}


@router.post("/list/pop/{key}")
async def list_pop(key: str, side: str = "left", redis: Redis = Depends(get_redis)):
    """LPOP / RPOP — 리스트에서 값 꺼내기"""
    if side == "left":
        value = await redis.lpop(key)
        cmd = f"LPOP {key}"
    else:
        value = await redis.rpop(key)
        cmd = f"RPOP {key}"
    items = await redis.lrange(key, 0, -1)
    return {"command": cmd, "popped": value, "remaining": items}


@router.get("/list/range/{key}")
async def list_range(key: str, start: int = 0, stop: int = -1, redis: Redis = Depends(get_redis)):
    """LRANGE — 리스트 범위 조회"""
    items = await redis.lrange(key, start, stop)
    length = await redis.llen(key)
    return {"command": f"LRANGE {key} {start} {stop}", "items": items, "total_length": length}


@router.post("/list/trim/{key}")
async def list_trim(key: str, start: int = 0, stop: int = 4, redis: Redis = Depends(get_redis)):
    """LTRIM — 리스트를 지정 범위로 자르기 (최근 N개 유지)"""
    before = await redis.lrange(key, 0, -1)
    await redis.ltrim(key, start, stop)
    after = await redis.lrange(key, 0, -1)
    return {"command": f"LTRIM {key} {start} {stop}", "before": before, "after": after}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/set/add")
async def set_add(key: str, members: list[str], redis: Redis = Depends(get_redis)):
    """SADD — Set에 원소 추가 (중복 자동 무시)"""
    added = await redis.sadd(key, *members)
    all_members = await redis.smembers(key)
    return {"command": f"SADD {key} {' '.join(members)}", "added_count": added, "all_members": list(all_members)}


@router.get("/set/members/{key}")
async def set_members(key: str, redis: Redis = Depends(get_redis)):
    """SMEMBERS — Set 전체 조회"""
    members = await redis.smembers(key)
    return {"command": f"SMEMBERS {key}", "members": list(members), "count": len(members)}


@router.get("/set/ismember/{key}/{member}")
async def set_ismember(key: str, member: str, redis: Redis = Depends(get_redis)):
    """SISMEMBER — 멤버 존재 여부 O(1) 확인"""
    exists = await redis.sismember(key, member)
    return {"command": f"SISMEMBER {key} {member}", "exists": bool(exists)}


@router.get("/set/operations")
async def set_operations(key1: str, key2: str, redis: Redis = Depends(get_redis)):
    """SINTER / SUNION / SDIFF — 집합 연산"""
    inter = await redis.sinter(key1, key2)
    union = await redis.sunion(key1, key2)
    diff = await redis.sdiff(key1, key2)
    set1 = await redis.smembers(key1)
    set2 = await redis.smembers(key2)
    return {
        f"{key1}": list(set1),
        f"{key2}": list(set2),
        "교집합 (SINTER)": list(inter),
        "합집합 (SUNION)": list(union),
        f"차집합 (SDIFF {key1}-{key2})": list(diff),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HASH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/hash/set")
async def hash_set(key: str, fields: dict, redis: Redis = Depends(get_redis)):
    """HSET — Hash에 필드-값 저장"""
    await redis.hset(key, mapping=fields)
    all_data = await redis.hgetall(key)
    return {"command": f"HSET {key} {fields}", "all_fields": all_data}


@router.get("/hash/get/{key}/{field}")
async def hash_get(key: str, field: str, redis: Redis = Depends(get_redis)):
    """HGET — Hash의 특정 필드만 조회"""
    value = await redis.hget(key, field)
    return {"command": f"HGET {key} {field}", "value": value}


@router.get("/hash/getall/{key}")
async def hash_getall(key: str, redis: Redis = Depends(get_redis)):
    """HGETALL — Hash 전체 조회"""
    data = await redis.hgetall(key)
    return {"command": f"HGETALL {key}", "data": data, "field_count": len(data)}


@router.post("/hash/incrby/{key}/{field}")
async def hash_incrby(key: str, field: str, amount: int = 1, redis: Redis = Depends(get_redis)):
    """HINCRBY — Hash 특정 필드만 원자적 증감"""
    result = await redis.hincrby(key, field, amount)
    return {"command": f"HINCRBY {key} {field} {amount}", "new_value": result}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SORTED SET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.post("/zset/add")
async def zset_add(key: str, members: dict[str, float], redis: Redis = Depends(get_redis)):
    """ZADD — Sorted Set에 score와 함께 추가"""
    # members: {"alice": 2500, "bob": 3200}
    added = await redis.zadd(key, members)
    ranking = await redis.zrange(key, 0, -1, withscores=True)
    return {"command": f"ZADD {key} {members}", "added": added, "ranking_asc": ranking}


@router.get("/zset/range/{key}")
async def zset_range(key: str, start: int = 0, stop: int = -1, rev: bool = False, redis: Redis = Depends(get_redis)):
    """ZRANGE / ZREVRANGE — 순위별 조회"""
    if rev:
        result = await redis.zrevrange(key, start, stop, withscores=True)
        cmd = f"ZREVRANGE {key} {start} {stop} WITHSCORES"
    else:
        result = await redis.zrange(key, start, stop, withscores=True)
        cmd = f"ZRANGE {key} {start} {stop} WITHSCORES"
    return {"command": cmd, "result": result}


@router.post("/zset/incrby/{key}/{member}")
async def zset_incrby(key: str, member: str, amount: float = 1, redis: Redis = Depends(get_redis)):
    """ZINCRBY — 점수 원자적 증가 (실시간 랭킹 갱신)"""
    new_score = await redis.zincrby(key, amount, member)
    rank = await redis.zrevrank(key, member)
    return {
        "command": f"ZINCRBY {key} {amount} {member}",
        "new_score": new_score,
        "rank": rank,
    }


@router.get("/zset/rank/{key}/{member}")
async def zset_rank(key: str, member: str, redis: Redis = Depends(get_redis)):
    """ZREVRANK / ZSCORE — 특정 멤버의 순위와 점수"""
    score = await redis.zscore(key, member)
    rank = await redis.zrevrank(key, member)
    total = await redis.zcard(key)
    return {
        "member": member,
        "score": score,
        "rank": rank,
        "total_members": total,
        "설명": f"{total}명 중 {rank + 1}등" if rank is not None else "멤버 없음",
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공통 유틸
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@router.get("/key/type/{key}")
async def key_type(key: str, redis: Redis = Depends(get_redis)):
    """TYPE — 키의 자료형 확인"""
    key_type = await redis.type(key)
    ttl = await redis.ttl(key)
    return {"key": key, "type": key_type, "ttl": ttl}


@router.delete("/key/{key}")
async def key_delete(key: str, redis: Redis = Depends(get_redis)):
    """DEL — 키 삭제"""
    deleted = await redis.delete(key)
    return {"command": f"DEL {key}", "deleted": bool(deleted)}


@router.post("/key/expire/{key}")
async def key_expire(key: str, seconds: int, redis: Redis = Depends(get_redis)):
    """EXPIRE — 키에 만료 시간 설정"""
    result = await redis.expire(key, seconds)
    ttl = await redis.ttl(key)
    return {"command": f"EXPIRE {key} {seconds}", "success": bool(result), "ttl": ttl}


@router.get("/info")
async def redis_info(redis: Redis = Depends(get_redis)):
    """INFO — Redis 서버 주요 정보"""
    info = await redis.info()
    return {
        "redis_version": info.get("redis_version"),
        "used_memory_human": info.get("used_memory_human"),
        "connected_clients": info.get("connected_clients"),
        "total_commands_processed": info.get("total_commands_processed"),
        "keyspace_hits": info.get("keyspace_hits"),
        "keyspace_misses": info.get("keyspace_misses"),
        "maxmemory_policy": info.get("maxmemory_policy"),
        "db0": info.get("db0"),
    }
