import hashlib
import json
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Iterable

import redis
from config import REDIS_HOST, REDIS_PORT, LISTENER_WORKERS

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True, socket_connect_timeout=5, socket_keepalive=True, retry_on_timeout=True, health_check_interval=30)
_TIMEZONE_CACHE = {"ts": None, "value": "Asia/Shanghai"}
_TIMEZONE_CACHE_TTL = 60.0

LEGACY_PURE_CODE_TRIGGER_RULE = r"^(?!.*码使用)[^-]+-\d+-(?:Register|Renew)_.+$"
LEGACY_SAFE_PURE_CODE_TRIGGER_RULE = (
    r"^(?!.*码使用)(?:[^\s-]+-)+\d+(?:-[^\s-]+)*-"
    r"(?:Register|Renew)_[A-Za-z0-9_-]+$"
)
SAFE_PURE_CODE_TRIGGER_RULE = (
    r"^(?!.*码使用)(?:[^\s-]+-)+\d+(?:-[^\s-]+)*-"
    r"(?:Register|Renew)_(?:[A-Za-z0-9_-]|数字|字母)+$"
)
KNOWN_REGEX_RULE_MIGRATIONS = {
    LEGACY_PURE_CODE_TRIGGER_RULE: SAFE_PURE_CODE_TRIGGER_RULE,
    LEGACY_SAFE_PURE_CODE_TRIGGER_RULE: SAFE_PURE_CODE_TRIGGER_RULE,
}


def log_line(level: str, message: str, extra: dict | None = None) -> None:
    """Write important runtime diagnostics to Docker stdout.

    The WebUI keeps records in Redis, but docker logs must also show what the
    listener is doing, otherwise delayed Telegram updates cannot be diagnosed.
    This helper is intentionally best-effort and never raises.
    """
    try:
        suffix = ""
        if extra:
            suffix = " " + json.dumps(extra, ensure_ascii=False, default=str)
        print(f"[{format_time()}] [{str(level).upper()}] {message}{suffix}", flush=True)
    except Exception:
        try:
            print(f"[SlowLink] {level}: {message}", flush=True)
        except Exception:
            pass


def now_ts() -> int:
    return int(time.time())


def format_time(ts: int | float | None = None) -> str:
    """Format UI/log time using configured display timezone.

    Default is Beijing time so VPS local timezone will not affect the page.
    """
    now = time.monotonic()
    tz_name = str(_TIMEZONE_CACHE.get("value") or "Asia/Shanghai")
    cached_ts = _TIMEZONE_CACHE.get("ts")
    if cached_ts is None or now - float(cached_ts) > _TIMEZONE_CACHE_TTL:
        try:
            tz_name = r.get("display_timezone") or "Asia/Shanghai"
        except Exception:
            pass
        _TIMEZONE_CACHE.update({"ts": now, "value": str(tz_name)})
    try:
        tz = ZoneInfo(str(tz_name))
    except Exception:
        tz = ZoneInfo("Asia/Shanghai")
    dt = datetime.fromtimestamp(float(ts if ts is not None else time.time()), tz)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def clear_timezone_cache() -> None:
    _TIMEZONE_CACHE.update({"ts": None, "value": "Asia/Shanghai"})


def get(key: str, default: str | None = None) -> str | None:
    value = r.get(key)
    return default if value is None else value


def set_value(key: str, value: Any) -> None:
    r.set(key, str(value))


def delete(*keys: str) -> None:
    if keys:
        r.delete(*keys)


def sadd(key: str, value: str) -> None:
    value = (value or "").strip()
    if value:
        r.sadd(key, value)


def srem(key: str, value: str) -> None:
    r.srem(key, value)


def smembers(key: str) -> set[str]:
    return set(r.smembers(key))


def get_json(key: str, default: Any = None) -> Any:
    raw = r.get(key)
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def set_json(key: str, value: Any) -> None:
    r.set(key, json.dumps(value, ensure_ascii=False))


def push_event(kind: str, message: str, extra: dict | None = None, limit: int = 300) -> None:
    item = {
        "time": format_time(),
        "kind": kind,
        "message": message,
        "extra": extra or {},
    }
    log_line(kind, message, extra or None)
    try:
        pipe = r.pipeline()
        pipe.lpush("events", json.dumps(item, ensure_ascii=False))
        pipe.ltrim("events", 0, limit - 1)
        pipe.execute()
    except Exception:
        pass


def list_events(limit: int = 50) -> list[dict]:
    items = []
    for raw in r.lrange("events", 0, limit - 1):
        try:
            items.append(json.loads(raw))
        except Exception:
            pass
    return items


def add_perf_event(item: dict, limit: int = 120) -> None:
    try:
        item = dict(item)
        item.setdefault("time", format_time())
        pipe = r.pipeline()
        pipe.lpush("perf_events", json.dumps(item, ensure_ascii=False, default=str))
        pipe.ltrim("perf_events", 0, limit - 1)
        pipe.execute()
    except Exception:
        pass


def list_perf_events(limit: int = 30) -> list[dict]:
    out = []
    for raw in r.lrange("perf_events", 0, limit - 1):
        try:
            out.append(json.loads(raw))
        except Exception:
            pass
    return out


def add_hit(item: dict, limit: int = 300) -> None:
    item = dict(item)
    item.setdefault("time", format_time())
    try:
        pipe = r.pipeline()
        pipe.lpush("hits", json.dumps(item, ensure_ascii=False))
        pipe.ltrim("hits", 0, limit - 1)
        pipe.execute()
    except Exception:
        pass


def list_hits(limit: int = 50) -> list[dict]:
    out = []
    for raw in r.lrange("hits", 0, limit - 1):
        try:
            out.append(json.loads(raw))
        except Exception:
            pass
    return out


def add_fail(item: dict, limit: int = 200) -> None:
    item = dict(item)
    item.setdefault("time", format_time())
    try:
        log_line("error", f"{item.get('stage', 'fail')}：{item.get('error', item)}", {k: v for k, v in item.items() if k not in {'error'}})
    except Exception:
        pass
    try:
        pipe = r.pipeline()
        pipe.lpush("fails", json.dumps(item, ensure_ascii=False))
        pipe.ltrim("fails", 0, limit - 1)
        pipe.execute()
    except Exception:
        pass


def list_fails(limit: int = 50) -> list[dict]:
    out = []
    for raw in r.lrange("fails", 0, limit - 1):
        try:
            out.append(json.loads(raw))
        except Exception:
            pass
    return out


def sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def ensure_defaults() -> None:
    defaults = {
        "dedup_enabled": "1",
        "dedup_minutes": "20",
        "dedup_invite_minutes": "0",
        "dedup_code_minutes": "20",
        "dedup_mode": "strict",
        "display_timezone": "Asia/Shanghai",
        "bot_status": "stopped",
        "listener_desired_state": "stopped",
        "dedup_similarity_enabled": "0",
        "worker_count": str(LISTENER_WORKERS),
    }
    for k, v in defaults.items():
        r.setnx(k, v)
    migrate_known_regex_rules()


def migrate_known_regex_rules() -> int:
    replacements = []
    try:
        for old, new in KNOWN_REGEX_RULE_MIGRATIONS.items():
            if r.sismember("regex_rules", old):
                replacements.append((old, new))
        if not replacements:
            return 0
        pipe = r.pipeline()
        for old, new in replacements:
            pipe.srem("regex_rules", old)
            pipe.sadd("regex_rules", new)
        pipe.execute()
        return len(replacements)
    except Exception:
        return 0


# ---- V1.25 cache / record management ----

def scan_keys(pattern: str, count: int = 500) -> list[str]:
    """Return Redis keys matching a pattern without blocking Redis like KEYS."""
    try:
        return [str(k) for k in r.scan_iter(match=pattern, count=count)]
    except Exception:
        return []


def delete_pattern(pattern: str) -> int:
    """Delete keys by pattern using SCAN. Returns deleted count."""
    keys = scan_keys(pattern)
    deleted = 0
    if not keys:
        return 0
    pipe = r.pipeline()
    for k in keys:
        pipe.delete(k)
    results = pipe.execute()
    for item in results:
        try:
            deleted += int(item or 0)
        except Exception:
            pass
    return deleted


def list_len(key: str) -> int:
    try:
        return int(r.llen(key) or 0)
    except Exception:
        return 0


def safe_dbsize() -> int:
    try:
        return int(r.dbsize() or 0)
    except Exception:
        return 0


def count_patterns(patterns: list[str]) -> int:
    if not patterns:
        return 0
    seen = set()
    try:
        for pattern in patterns:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor=cursor, match=pattern, count=500)
                for k in keys:
                    seen.add(str(k))
                if cursor == 0:
                    break
    except Exception:
        return 0
    return len(seen)


ACTIVE_DEDUP_PATTERNS = [
    "dedup:main:*",
    "dedup:core:*",
    "dedup:link:*",
    "dedup:code:*",
    "dedup:lottery:*",
    "dedup:register_snapshot:*",
    "dedup:content_url:*",
    "dedup:text:*",
]

DEDUP_META_PATTERNS = ["dedup:meta:*"]


_CACHED_STATS = {"ts":0.0,"data":{}}

def clear_stats_cache():
    _CACHED_STATS["ts"] = 0.0


def cache_stats() -> dict:
    """Small, safe stats for the WebUI cache management panel.

    Important wording:
    - dedup_cache means active anti-duplicate TTL keys, not page records.
    - dedup_recent / dedup_records are display/history lists.
    """
    nt = time.time()
    if nt - _CACHED_STATS["ts"] < 120:
        return _CACHED_STATS["data"]
    active_dedup = count_patterns(ACTIVE_DEDUP_PATTERNS)
    dedup_meta = count_patterns(DEDUP_META_PATTERNS)
    result = {
        "redis_keys": safe_dbsize(),
        "record_logs": list_len("events") + list_len("hits") + list_len("fails") + list_len("dedup:recent") + list_len("perf_events"),
        "events": list_len("events"),
        "hits": list_len("hits"),
        "fails": list_len("fails"),
        "perf_events": list_len("perf_events"),
        "dedup_recent": list_len("dedup:recent"),
        "dedup_cache": active_dedup,
        "dedup_meta": dedup_meta,
        "dedup_records": list_len("dedup:records"),
        "dialog_cache": len(get_json("dialog_cache", []) or []),
        "temp_cache": count_patterns(["tmp:*", "temp:*", "test:*", "runtime:*"]),
    }
    _CACHED_STATS["ts"] = nt
    _CACHED_STATS["data"] = result
    return result


def trim_runtime_lists() -> None:
    """Keep Redis lists bounded after upgrade, without touching config/login/session."""
    try:
        r.ltrim("events", 0, 299)
        r.ltrim("hits", 0, 299)
        r.ltrim("fails", 0, 199)
        r.ltrim("perf_events", 0, 119)
        r.ltrim("dedup:recent", 0, 299)
        r.ltrim("dedup:records", 0, 499)
    except Exception:
        pass


def cleanup_expired_dedup_keys() -> int:
    deleted = 0
    try:
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor=cursor, match="dedup:*", count=200)
            if not keys:
                if cursor == 0:
                    break
                continue
            pipe = r.pipeline()
            for k in keys:
                pipe.ttl(k)
            ttls = pipe.execute()
            for k, ttl_val in zip(keys, ttls):
                if int(ttl_val or -1) < -1:
                    r.delete(k)
                    deleted += 1
            if cursor == 0:
                break
    except Exception:
        pass
    return deleted
