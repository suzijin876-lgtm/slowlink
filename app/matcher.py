import re
import time
import unicodedata
from redis_store import smembers
from code_rules import extract_code_detail, extract_trigger_code_detail

_RULE_CACHE = {"ts": 0.0, "raw": None, "keywords": [], "regexes": []}
_ANALYZE_CACHE = {"ts": 0.0, "text": None, "result": None}

# ---- pre-compiled guards (unchanged) ----

USAGE_HARD_WORDS = [
    "码使用", "注册码使用", "邀请码使用", "注册代码使用",
    "被使用", "已被使用", "已经使用", "使用成功",
    "使用了", "兑换成功", "已兑换", "被兑换", "激活成功",
    "领取成功", "已领取", "被领取", "使用者", "使用用户",
]

CODE_LINE_RE = re.compile(r"^.+-\d+-(?:Register|Renew)_(?:[A-Za-z0-9_-]|数字|字母)+$", re.I)
INV_CODE_RE = re.compile(r"\bINV-[A-Z0-9]+(?:-[A-Z0-9]+)+\b", re.I)
USAGE_STATUS_RE = re.compile(r"已使用\s*[:：]\s*\d+\s*次?", re.I)

CLOSED_REGISTER_RE = re.compile(
    r"(?:"
    r"(?:已关闭|关闭|暂停|停止|结束|已结束|暂不开放|不开放|未开放)\s*(?:自由注册|开放注册|注册开放|开注|注册)"
    r"|(?:自由注册|开放注册|注册开放|开注)\s*(?:已关闭|关闭|暂停|停止|结束|已结束)"
    r"|注册\s*(?:已关闭|关闭|暂停|停止|结束|已结束|暂不开放|不开放|未开放)"
    r"|(?:满员|已满|满额)"
    r")",
    re.I,
)
REGISTRATION_SUCCESS_RE = re.compile(
    r"(?:自由|定时|开放)?注册成功(?=$|\s|[-—:：|，。!！])",
    re.I,
)
REGISTRATION_ACCOUNT_MARKERS = ["创建了", "账号有效期", "到期时间"]

REGEX_META_RE = re.compile(r"[\^\$\[\]\(\)\{\}\?\+\*\\\|]")


def get_text(message) -> str:
    return (getattr(message, "message", None) or "").strip()


def normalize_text(text: str) -> str:
    text = text or ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff\u2060]", "", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def compact_text(text: str) -> str:
    text = normalize_text(text)
    return re.sub(r"\s+", "", text)


def _split_rule_blob(blob: str) -> list[str]:
    out: list[str] = []
    for part in str(blob or "").split(";;"):
        part = part.strip()
        if not part:
            continue
        if REGEX_META_RE.search(part):
            out.append(part)
        else:
            for line in part.splitlines():
                line = line.strip()
                if line:
                    out.append(line)
    return out


def invalidate_rule_cache():
    _RULE_CACHE.clear()
    _RULE_CACHE.update({"ts": 0.0, "raw": None, "keywords": [], "regexes": []})
    _ANALYZE_CACHE.update({"ts": 0.0, "text": None, "result": None})


def _rule_blob_snapshot() -> tuple[str, ...]:
    rules = smembers("regex_rules")
    return tuple(sorted(rules))


def _compiled_rules(ttl: float = 60.0):
    """Split rules into fast keywords and compiled regexes.

    Returns dict with:
      keywords: list[str] — plain text for 'in' operator (no regex overhead)
      regexes: list[(str, re.Pattern)] — compiled with re.I|re.M only, no DOTALL
    """
    now = time.monotonic()
    cached_raw = _RULE_CACHE.get("raw")
    cached_ts = float(_RULE_CACHE.get("ts") or 0)
    if cached_raw is not None and now - cached_ts <= ttl:
        return _RULE_CACHE
    raw = tuple(sorted(smembers("regex_rules")))

    keywords: list[tuple[str, str]] = []  # (lowered, original)
    regexes: list[tuple[str, re.Pattern]] = []
    seen = set()

    for blob in raw:
        for rule in _split_rule_blob(blob):
            if rule in seen:
                continue
            seen.add(rule)

            # Plain keyword: no regex metacharacters, fast 'in' check
            if not REGEX_META_RE.search(rule):
                keywords.append((rule.lower(), rule))
                continue

            try:
                # re.I | re.M only — no DOTALL. Rules that need cross-line
                # matching should use (?s) prefix explicitly.
                cre = re.compile(rule, re.I | re.M)
                regexes.append((rule, cre))
            except re.error:
                try:
                    escaped = re.escape(rule)
                    keywords.append((escaped.lower(), escaped))
                except Exception:
                    continue

    _RULE_CACHE.update({"ts": now, "raw": raw, "keywords": keywords, "regexes": regexes})
    return _RULE_CACHE


# ---- usage / closed-register guards (unchanged logic) ----

def is_usage_notice(text: str) -> bool:
    return _is_usage_notice(normalize_text(text), compact_text(text))


def _is_usage_notice(normalized: str, compact: str) -> bool:
    low = normalized.lower()
    compact_low = compact.lower()

    has_status_field = bool(USAGE_STATUS_RE.search(normalized) or USAGE_STATUS_RE.search(compact))
    has_invite_info = (
        "可使用次数" in normalized
        or "邀请有效期" in normalized
        or "注册链接" in normalized
        or "注册权益" in normalized
        or "register?code=" in low
        or "register_" in compact_low
        or "renew_" in compact_low
        or bool(CODE_LINE_RE.search(compact))
        or bool(INV_CODE_RE.search(compact))
    )
    if has_status_field and has_invite_info:
        return False

    has_hard_usage = any(w.lower() in low or w.lower() in compact_low for w in USAGE_HARD_WORDS)
    if not has_hard_usage:
        return False

    code_detail = extract_code_detail(normalized) or extract_code_detail(compact)
    if code_detail or CODE_LINE_RE.search(compact) or "register_" in compact_low or "renew_" in compact_low:
        return True

    if any(k in normalized for k in ["邀请码", "注册码", "注册代码", "兑换码", "激活码"]):
        return True

    return False


def is_closed_register_notice(text: str) -> bool:
    return _is_closed_register_notice(normalize_text(text), compact_text(text))


def _is_closed_register_notice(normalized: str, compact: str) -> bool:
    has_register_marker = any(k in normalized or k in compact for k in [
        "自由注册", "开放注册", "注册开放", "开注", "注册"
    ])
    if not has_register_marker:
        return False

    return bool(CLOSED_REGISTER_RE.search(normalized) or CLOSED_REGISTER_RE.search(compact))


def is_registration_success_notice(text: str) -> bool:
    return _is_registration_success_notice(normalize_text(text), compact_text(text))


def _is_registration_success_notice(normalized: str, compact: str) -> bool:
    has_success = bool(
        REGISTRATION_SUCCESS_RE.search(normalized)
        or REGISTRATION_SUCCESS_RE.search(compact)
    )
    if not has_success:
        return False
    return any(marker in normalized or marker in compact for marker in REGISTRATION_ACCOUNT_MARKERS)


# ---- main matching (optimized) ----

def analyze_message(text: str) -> dict:
    original = (text or "").strip()
    if not original:
        return {
            "matched": False,
            "rule": "",
            "code_detail": {},
            "normalized": "",
            "compact": "",
            "usage_notice": False,
            "closed_register_notice": False,
            "registration_success_notice": False,
        }
    if len(original) > 8192:
        original = original[:8192]

    normalized = normalize_text(original)
    compact = re.sub(r"\s+", "", normalized)
    usage_notice = _is_usage_notice(normalized, compact)
    closed_register_notice = _is_closed_register_notice(normalized, compact)
    registration_success_notice = _is_registration_success_notice(normalized, compact)
    if usage_notice or closed_register_notice or registration_success_notice:
        return {
            "matched": False,
            "rule": "",
            "code_detail": {},
            "normalized": normalized,
            "compact": compact,
            "usage_notice": usage_notice,
            "closed_register_notice": closed_register_notice,
            "registration_success_notice": registration_success_notice,
        }

    rules = _compiled_rules()

    keywords = rules.get("keywords") or []
    if keywords:
        low_norm = normalized.lower()
        for kw_lower, kw_orig in keywords:
            if kw_lower in low_norm:
                code_detail = extract_code_detail(normalized) or extract_code_detail(compact)
                return {
                    "matched": True,
                    "rule": kw_orig,
                    "code_detail": code_detail or {},
                    "normalized": normalized,
                    "compact": compact,
                    "usage_notice": False,
                    "closed_register_notice": False,
                }

    regexes = rules.get("regexes") or []
    for raw, cre in regexes:
        try:
            if cre.search(normalized):
                code_detail = extract_code_detail(normalized) or extract_code_detail(compact)
                return {
                    "matched": True,
                    "rule": raw,
                    "code_detail": code_detail or {},
                    "normalized": normalized,
                    "compact": compact,
                    "usage_notice": False,
                    "closed_register_notice": False,
                }
        except Exception:
            continue

    trigger_detail = extract_trigger_code_detail(normalized) or extract_trigger_code_detail(compact)
    if trigger_detail and trigger_detail.get("can_trigger"):
        return {
            "matched": True,
            "rule": "code_trigger:" + str(trigger_detail.get("name") or "full_code"),
            "code_detail": trigger_detail,
            "normalized": normalized,
            "compact": compact,
            "usage_notice": False,
            "closed_register_notice": False,
        }

    return {
        "matched": False,
        "rule": "",
        "code_detail": {},
        "normalized": normalized,
        "compact": compact,
        "usage_notice": False,
        "closed_register_notice": False,
    }


def match_rules(text: str) -> tuple[bool, str]:
    """Fast two-tier matching: keywords first, then compiled regexes.

    Text prep done once; guards receive pre-computed values.
    Text capped at 8KB to prevent regex backtrack on huge messages.
    """
    text = (text or "").strip()
    if not text:
        return False, ""
    if len(text) > 8192:
        text = text[:8192]

    normalized = normalize_text(text)
    compact = re.sub(r"\s+", "", normalized)

    # Guards -- pass pre-computed to avoid re-normalization
    if _is_usage_notice(normalized, compact):
        return False, ""
    if _is_closed_register_notice(normalized, compact):
        return False, ""
    if _is_registration_success_notice(normalized, compact):
        return False, ""

    rules = _compiled_rules()

    # Tier 1: fast keyword check
    keywords = rules.get("keywords") or []
    if keywords:
        low_norm = normalized.lower()
        for kw_lower, kw_orig in keywords:
            if kw_lower in low_norm:
                return True, kw_orig

    # Tier 2: compiled regexes
    regexes = rules.get("regexes") or []
    for raw, cre in regexes:
        try:
            if cre.search(normalized):
                return True, raw
        except Exception:
            continue

    # Code-trigger fallback
    code_detail = extract_trigger_code_detail(normalized) or extract_trigger_code_detail(compact)
    if code_detail and code_detail.get("can_trigger"):
        return True, "码识别触发：" + str(code_detail.get("name") or "完整码")

    return False, ""

def expanded_rules() -> list[str]:
    out: list[str] = []
    seen = set()
    for blob in tuple(sorted(smembers("regex_rules"))):
        for rule in _split_rule_blob(blob):
            if rule and rule not in seen:
                seen.add(rule)
                out.append(rule)
    return out


def rule_diagnostics() -> list[dict]:
    items = []
    for rule in expanded_rules():
        is_regex = bool(REGEX_META_RE.search(rule))
        try:
            re.compile(rule, re.I | re.M)
            items.append({"rule": rule, "type": "regex" if is_regex else "keyword", "ok": True, "error": ""})
        except re.error as e:
            items.append({"rule": rule, "type": "regex", "ok": False, "error": str(e)})
    return items


def match_rule_details(text: str) -> dict:
    original = (text or "").strip()
    normalized = normalize_text(original)
    compact = re.sub(r"\s+", "", normalized)
    usage = _is_usage_notice(normalized, compact)
    closed_register = _is_closed_register_notice(normalized, compact)
    registration_success = _is_registration_success_notice(normalized, compact)
    code_detail = extract_code_detail(normalized) or extract_code_detail(compact)

    if usage:
        return {
            "matched": False, "rule": "", "candidate": "",
            "usage_notice": True, "closed_register_notice": False, "registration_success_notice": False,
            "code_detected": bool(code_detail),
            "code_rule": code_detail.get("name", "") if code_detail else "",
            "code_note": code_detail.get("safe_reason", "") if code_detail else "",
            "original": original, "normalized": normalized, "compact": compact,
        }
    if closed_register:
        return {
            "matched": False, "rule": "", "candidate": "",
            "usage_notice": False, "closed_register_notice": True, "registration_success_notice": False,
            "code_detected": bool(code_detail),
            "code_rule": code_detail.get("name", "") if code_detail else "",
            "code_note": "已关闭/暂停注册状态，底层安全过滤，不触发转发",
            "original": original, "normalized": normalized, "compact": compact,
        }
    if registration_success:
        return {
            "matched": False, "rule": "", "candidate": "",
            "usage_notice": False, "closed_register_notice": False, "registration_success_notice": True,
            "code_detected": bool(code_detail),
            "code_rule": code_detail.get("name", "") if code_detail else "",
            "code_note": "个人注册成功通知，底层安全过滤，不触发转发",
            "original": original, "normalized": normalized, "compact": compact,
        }

    rules = _compiled_rules(ttl=0)

    # Tier 1: keywords
    keywords = rules.get("keywords") or []
    if keywords:
        low_norm = normalized.lower()
        for kw_lower, kw_orig in keywords:
            if kw_lower in low_norm:
                return {
                    "matched": True, "rule": kw_orig, "candidate": "清理文本",
                    "usage_notice": False, "closed_register_notice": False,
                    "code_detected": bool(code_detail),
                    "code_rule": code_detail.get("name", "") if code_detail else "",
                    "code_note": code_detail.get("safe_reason", "") if code_detail else "",
                    "original": original, "normalized": normalized, "compact": compact,
                }

    # Tier 2: regexes
    regexes = rules.get("regexes") or []
    for raw, cre in regexes:
        try:
            if cre.search(normalized):
                return {
                    "matched": True, "rule": raw, "candidate": "清理文本",
                    "usage_notice": False, "closed_register_notice": False,
                    "code_detected": bool(code_detail),
                    "code_rule": code_detail.get("name", "") if code_detail else "",
                    "code_note": code_detail.get("safe_reason", "") if code_detail else "",
                    "original": original, "normalized": normalized, "compact": compact,
                }
        except Exception:
            continue

    # Code trigger fallback
    trigger_detail = extract_trigger_code_detail(normalized) or extract_trigger_code_detail(compact)
    if trigger_detail and trigger_detail.get("can_trigger"):
        return {
            "matched": True, "rule": "码识别触发：" + str(trigger_detail.get("name") or "完整码"),
            "candidate": "码识别规则",
            "usage_notice": False, "closed_register_notice": False,
            "code_detected": True,
            "code_rule": trigger_detail.get("name", ""),
            "code_note": trigger_detail.get("safe_reason", ""),
            "original": original, "normalized": normalized, "compact": compact,
        }

    return {
        "matched": False, "rule": "", "candidate": "",
        "usage_notice": False, "closed_register_notice": False,
        "code_detected": bool(code_detail),
        "code_rule": code_detail.get("name", "") if code_detail else "",
        "code_note": ("已识别完整码，但默认仅辅助去重，不触发转发" if code_detail else ""),
        "original": original, "normalized": normalized, "compact": compact,
    }
