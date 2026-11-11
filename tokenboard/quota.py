"""订阅额度查询。

两家订阅的额度接口完全不同：

* **MiniMax M Plan** —— 走 MiniMax Code 自己的开放平台接口，
  凭据就是本机登录态（~/.minimax/auth/.../auth.json 里的 accessToken），
  不需要额外配置。返回 5 小时窗口 + 周限额的剩余百分比与重置时间。

* **火山方舟编程包** —— 走 Volcengine OpenAPI（Action=GetCodingPlanUsage），
  必须用**账号的 AccessKey ID / Secret Access Key** 签名（不是推理用的 ark- key），
  AK/SK 放在 ~/.tokenboard/volcengine.json 或环境变量里。
  没配就显示「未配置 AK/SK」，不影响其它功能。

* **Codex（ChatGPT 订阅）** —— 走 ChatGPT 后端
  `GET https://chatgpt.com/backend-api/codex/usage`，
  凭据是本机 Codex 登录态（~/.codex/auth.json 里的 access_token +
  ChatGPT-Account-Id），不需要额外配置。
  返回 primary_window（5 小时窗口）与 secondary_window（周窗口）的
  已用百分比与重置时间。

额度字段统一折算成：
    limit_kind : "5h" | "weekly"
    remaining  : 剩余百分比 (0-100)
    used       : 已用百分比
    reset_at   : 重置时间戳(ms)
    unlimited  : 是否不限量
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path(os.path.expanduser("~"))
VOLC_CONFIG = HOME / ".tokenboard" / "volcengine.json"
CODEX_AUTH = HOME / ".codex" / "auth.json"
CODEX_USAGE_URL = "https://chatgpt.com/backend-api/codex/usage"

# ChatGPT 套餐名 -> 展示名
PLAN_NAMES = {
    "free": "Free", "plus": "Plus", "pro": "Pro", "team": "Team",
    "business": "Business", "enterprise": "Enterprise", "edu": "Edu",
}

MINIMAX_ORIGINS = {
    ("cn", "prod"): "https://www.minimaxi.com",
    ("en", "prod"): "https://platform.minimax.io",
    ("cn", "staging"): "https://open-platform-for-online-test.xaminim.com",
    ("en", "staging"): "https://mmx-pre.xaminim.com",
    ("cn", "test"): "https://openplatform-test.xaminim.com",
    ("en", "test"): "https://mmx-test.xaminim.com",
}

VOLC_HOST = "open.volcengineapi.com"
VOLC_SERVICE = "ark"
VOLC_VERSION = "2024-01-01"


def _http_json(url: str, headers: dict, timeout: int = 12,
               attempts: int = 3) -> tuple[int, dict | str]:
    """GET 一个 JSON 接口。

    ChatGPT 后端偶发 SSL EOF（实测约 12% 概率），重试即可恢复；
    4xx/5xx 是明确错误，不重试直接返回。
    """
    last: tuple[int, dict | str] = (-1, "unknown error")
    for i in range(max(1, attempts)):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read().decode("utf-8", "replace")
                try:
                    return r.status, json.loads(raw)
                except Exception:  # noqa: BLE001
                    return r.status, raw
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            # 403 在 ChatGPT 后端是 Cloudflare 的临时拦截（请求打太急就会触发），
            # 重试能恢复；401 之类的才是真的凭据问题，不重试。
            if e.code == 403 and i < attempts - 1:
                last = (e.code, raw)
                time.sleep(0.8 * (i + 1))
                continue
            try:
                return e.code, json.loads(raw)
            except Exception:  # noqa: BLE001
                return e.code, raw
        except Exception as e:  # noqa: BLE001
            last = (-1, f"{type(e).__name__}: {e}")
            if i < attempts - 1:
                time.sleep(0.8 * (i + 1))
    return last


# ---------------------------------------------------------------- MiniMax
def _minimax_token() -> tuple[str, str, str] | None:
    """返回 (accessToken, region, buildEnv)，取未过期且最新的一条。"""
    base = HOME / ".minimax" / "auth"
    if not base.is_dir():
        return None
    now = time.time() * 1000
    best: tuple[str, int, Path] | None = None
    for p in base.rglob("auth.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for rec in (data.get("records") or {}).values():
            tok = rec.get("accessToken")
            exp = rec.get("expiresAtMs") or 0
            if tok and exp > now and (best is None or exp > best[1]):
                best = (tok, exp, p)
    if not best:
        return None
    tok, _exp, p = best
    state_path = p.parent / "auth-state.json"
    region, env = "cn", "prod"
    if state_path.exists():
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
            region = st.get("region") or region
            env = st.get("buildEnv") or env
        except Exception:  # noqa: BLE001
            pass
    return tok, region, env


def fetch_minimax() -> dict:
    """MiniMax M Plan 的 5 小时 / 周限额。"""
    res = {"provider": "minimax", "name": "MiniMax M Plan", "ok": False,
           "error": "", "windows": []}
    tk = _minimax_token()
    if not tk:
        res["error"] = "未找到 MiniMax 登录凭据"
        return res
    token, region, env = tk
    origin = MINIMAX_ORIGINS.get((region, env), MINIMAX_ORIGINS[("cn", "prod")])
    url = f"{origin}/v1/api/openplatform/coding_plan/remains"
    status, body = _http_json(url, {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    })
    if status != 200 or not isinstance(body, dict):
        res["error"] = f"HTTP {status}"
        return res
    if body.get("base_resp", {}).get("status_code") not in (0, None):
        res["error"] = str(body.get("base_resp"))
        return res

    remains = body.get("model_remains") or []
    if not remains:
        res["error"] = "未订阅 Token Plan"
        return res
    m = remains[0]

    def win(kind, rem_pct, status_v, reset_ms, unlimited_key):
        return {
            "kind": kind,
            "remaining": max(0.0, min(100.0, float(rem_pct or 0))),
            "used": max(0.0, min(100.0, 100.0 - float(rem_pct or 0))),
            "reset_at": int(reset_ms or 0),
            "unlimited": status_v == 3,
        }

    res["windows"] = [
        win("5h", m.get("current_interval_remaining_percent"),
            m.get("current_interval_status"), m.get("end_time"), "current_interval_status"),
        win("weekly", m.get("current_weekly_remaining_percent"),
            m.get("current_weekly_status"), m.get("weekly_end_time"), "current_weekly_status"),
    ]
    res["ok"] = True
    return res


# ---------------------------------------------------------------- 火山方舟
def _volc_creds() -> tuple[str, str] | None:
    ak = os.environ.get("VOLCENGINE_ACCESS_KEY_ID") or os.environ.get("VOLC_ACCESS_KEY_ID")
    sk = os.environ.get("VOLCENGINE_SECRET_ACCESS_KEY") or os.environ.get("VOLC_SECRET_ACCESS_KEY")
    if ak and sk:
        return ak, sk
    if VOLC_CONFIG.exists():
        try:
            d = json.loads(VOLC_CONFIG.read_text(encoding="utf-8"))
            ak = d.get("accessKeyId")
            sk = d.get("secretAccessKey")
            if ak and sk:
                return ak, sk
        except Exception:  # noqa: BLE001
            pass
    return None


def _volc_sign(method: str, path: str, query: dict, body: str,
               ak: str, sk: str, region: str = "cn") -> dict:
    """Volcengine OpenAPI V4 签名。"""
    now = time.time()
    xdate = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
    datestamp = xdate[:8]
    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    qs = "&".join(f"{k}={v}" for k, v in sorted(query.items()))
    signed_headers = "content-type;host;x-content-sha256;x-date"
    canonical_headers = (f"content-type:application/json\n"
                         f"host:{VOLC_HOST}\n"
                         f"x-content-sha256:{payload_hash}\n"
                         f"x-date:{xdate}\n")
    canonical_request = (f"{method}\n{path}\n{qs}\n{canonical_headers}\n"
                         f"{signed_headers}\n{payload_hash}")
    credential_scope = f"{datestamp}/{region}/{VOLC_SERVICE}/request"
    string_to_sign = ("HMAC-SHA256\n"
                      f"{xdate}\n"
                      f"{credential_scope}\n"
                      f"{hashlib.sha256(canonical_request.encode()).hexdigest()}")

    def h(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    k = h(h(h(h(sk.encode("utf-8"), datestamp), region), VOLC_SERVICE), "request")
    signature = hmac.new(k, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    authorization = (f"HMAC-SHA256 Credential={ak}/{credential_scope}, "
                    f"SignedHeaders={signed_headers}, Signature={signature}")
    return {
        "Content-Type": "application/json; charset=utf-8",
        "Host": VOLC_HOST,
        "X-Date": xdate,
        "X-Content-Sha256": payload_hash,
        "Authorization": authorization,
    }


def fetch_volcengine() -> dict:
    """火山方舟编程包的 5 小时 / 周限额。"""
    res = {"provider": "volcengine", "name": "火山方舟编程包", "ok": False,
           "error": "", "windows": []}
    creds = _volc_creds()
    if not creds:
        res["error"] = "未配置 AK/SK"
        res["hint"] = (f"把 AccessKey ID / Secret 写到 {VOLC_CONFIG}"
                       f"（或设 VOLCENGINE_ACCESS_KEY_ID / VOLCENGINE_SECRET_ACCESS_KEY）")
        return res
    ak, sk = creds
    query = {"Action": "GetCodingPlanUsage", "Version": VOLC_VERSION}
    url = f"https://{VOLC_HOST}/?{query['Action']}={query['Action']}&Version={query['Version']}"
    headers = _volc_sign("GET", "/", query, "", ak, sk)
    status, body = _http_json(url, headers)
    if status != 200 or not isinstance(body, dict):
        res["error"] = f"HTTP {status} {str(body)[:120]}"
        return res
    err = (body.get("ResponseMetadata") or {}).get("Error")
    if err:
        res["error"] = str(err.get("Message") or err)[:150]
        return res

    # 字段名在不同版本里可能是 AFPFiveHour / five_hour
    data = body.get("Result") or body.get("data") or body
    five = _pick(data, "AFPFiveHour", "five_hour", "FiveHour")
    weekly = _pick(data, "AFPWeekly", "weekly_limit", "Weekly")
    monthly = _pick(data, "AFPMonthly", "monthly", "Monthly")

    for kind, src, pct_keys in (
        ("5h", five, ("remaining", "Remaining", "remain")),
        ("weekly", weekly, ("remaining", "Remaining", "remain")),
    ):
        if not isinstance(src, dict):
            continue
        pct = _first_num(src, pct_keys)
        used = _first_num(src, ("used", "Used", "QuotaUsed", "usage"))
        if used is not None and pct is None:
            pct = 100.0 - float(used)
        if pct is None:
            continue
        reset = _first_num(src, ("resetTime", "ResetTime", "ResetTimestamp",
                                "reset_at", "resetAt"))
        res["windows"].append({
            "kind": kind,
            "remaining": max(0.0, min(100.0, float(pct))),
            "used": max(0.0, min(100.0, 100.0 - float(pct))),
            "reset_at": int(reset or 0),
            "unlimited": False,
        })
    if monthly:
        res["has_monthly"] = True
    res["ok"] = bool(res["windows"])
    if not res["ok"]:
        res["error"] = "返回里没找到额度字段"
    return res


def _pick(d: dict, *names):
    for n in names:
        if isinstance(d, dict) and n in d and d[n] is not None:
            return d[n]
    return None


def _first_num(d: dict, names):
    for n in names:
        v = d.get(n) if isinstance(d, dict) else None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v)
            except ValueError:
                pass
    return None


# ---------------------------------------------------------------- Codex
def _codex_creds() -> tuple[str, str] | None:
    """返回 (access_token, account_id)；不是 ChatGPT 登录态就返回 None。"""
    if not CODEX_AUTH.exists():
        return None
    try:
        d = json.loads(CODEX_AUTH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    if (d.get("auth_mode") or "") != "chatgpt":
        return None
    tok = d.get("tokens") or {}
    access = tok.get("access_token")
    if not access:
        return None
    return access, tok.get("account_id") or ""


def fetch_codex() -> dict:
    """Codex（ChatGPT 订阅）的 5 小时 / 周限额。"""
    res = {"provider": "codex", "name": "Codex", "ok": False,
           "error": "", "windows": []}
    creds = _codex_creds()
    if not creds:
        res["error"] = "未找到 Codex 登录凭据"
        res["hint"] = "在 Codex 里登录 ChatGPT 账号后重试"
        return res
    access, account = creds
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access}",
        "User-Agent": "codex_cli_rs/0.0.0",
    }
    if account:
        headers["ChatGPT-Account-Id"] = account
    status, body = _http_json(CODEX_USAGE_URL, headers)
    if status != 200 or not isinstance(body, dict):
        if status == 401:
            res["error"] = "登录凭据已过期，请在 Codex 里重新登录"
        else:
            res["error"] = f"HTTP {status}"
        return res

    plan = (body.get("plan_type") or "").strip()
    res["name"] = f"Codex · {PLAN_NAMES.get(plan, plan or 'ChatGPT')}"
    res["plan"] = plan

    rl = body.get("rate_limit") or {}
    now = time.time()
    for key in ("primary_window", "secondary_window"):
        w = rl.get(key)
        if not isinstance(w, dict):
            continue
        secs = int(w.get("limit_window_seconds") or 0)
        # 5 小时窗口(18000s) 归 5h，7 天窗口(604800s) 归 weekly
        kind = "5h" if 0 < secs <= 86400 else "weekly"
        used = max(0.0, min(100.0, float(w.get("used_percent") or 0)))
        # reset_at 是**秒级**时间戳；缺失时用 reset_after_seconds 推算
        reset = w.get("reset_at")
        if reset:
            reset_ms = int(float(reset)) * 1000
        else:
            after = w.get("reset_after_seconds")
            reset_ms = int((now + float(after)) * 1000) if after else 0
        res["windows"].append({
            "kind": kind,
            "remaining": 100.0 - used,
            "used": used,
            "reset_at": reset_ms,
            "unlimited": False,
        })

    # 额度过期后可以用「重置券」手动恢复，额外给个提示
    rc = body.get("rate_limit_reset_credits") or {}
    n = rc.get("applicable_available_count") or rc.get("available_count") or 0
    if n:
        res["note"] = f"剩余重置券 {n} 张"

    res["ok"] = bool(res["windows"])
    if not res["ok"]:
        res["error"] = "返回里没找到额度字段"
    return res


# ---------------------------------------------------------------- 汇总
def fetch_all() -> list[dict]:
    """取所有订阅的额度（单个失败不影响其它）。"""
    out = []
    for fn in (fetch_minimax, fetch_codex, fetch_volcengine):
        try:
            out.append(fn())
        except Exception as e:  # noqa: BLE001
            out.append({"provider": fn.__name__, "name": fn.__name__,
                        "ok": False, "error": f"{type(e).__name__}: {e}",
                        "windows": []})
    return out
