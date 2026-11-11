"""读写 OpenCode 的配置文件，并提供「拉模型目录 / 连通性测试」两个联网能力。

配置文件位置（按顺序找，找到就停）：
    1. 环境变量 OPENCODE_CONFIG 指定的文件
    2. ~/.config/opencode/opencode.jsonc
    3. ~/.config/opencode/opencode.json
    4. %APPDATA%/opencode/opencode.json（Windows 兜底）

配置长这样：
    {
      "model": "hs/doubao-seed-evolving",          # 默认模型 = providerId/modelId
      "$schema": "https://opencode.ai/config.json",
      "provider": {
        "hs": {
          "npm": "@ai-sdk/openai-compatible",
          "name": "火山 Coding Plan",
          "options": { "baseURL": "...", "apiKey": "...", "setCacheKey": true },
          "models": { "doubao-seed-evolving": { "name": "..." } }
        }
      }
    }

注意：文件虽然叫 .jsonc（允许注释），但 OpenCode 读的时候用的是严格 JSON。
所以这里写入时统一输出**严格 JSON**——宁可丢掉注释，也不能写成 OpenCode 读不了的。
读的时候则容忍注释，万一用户手写了几行注释也不会读崩。
"""
from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_NPM = "@ai-sdk/openai-compatible"
MAX_BACKUPS = 10


# ------------------------------------------------------------------ 路径
def config_path() -> Path:
    """返回实际使用的 OpenCode 配置文件路径（不存在时返回首选路径）。"""
    env = os.environ.get("OPENCODE_CONFIG")
    if env:
        return Path(env).expanduser()
    home = Path(os.path.expanduser("~"))
    cands = [
        home / ".config" / "opencode" / "opencode.jsonc",
        home / ".config" / "opencode" / "opencode.json",
    ]
    for c in cands:
        if c.exists():
            return c
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            c = Path(appdata) / "opencode" / "opencode.json"
            if c.exists():
                return c
    return cands[0]


# ------------------------------------------------------------------ JSONC
def strip_jsonc(text: str) -> str:
    """去掉 JSONC 注释（只动字符串外的 // 和 /* */），尾逗号一并清掉。

    字符串里的 "//"（比如 URL）不能当注释，所以要逐字符扫。
    """
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    cleaned = "".join(out)
    # 尾逗号：, 后面紧跟 } 或 ]
    res = []
    i = 0
    n = len(cleaned)
    in_str = False
    while i < n:
        ch = cleaned[i]
        if in_str:
            res.append(ch)
            if ch == "\\" and i + 1 < n:
                res.append(cleaned[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            res.append(ch)
            i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < n and cleaned[j] in " \t\r\n":
                j += 1
            if j < n and cleaned[j] in "}]":
                i += 1          # 丢掉这个尾逗号
                continue
        res.append(ch)
        i += 1
    return "".join(res)


def read(path: Path | None = None) -> dict:
    """读配置；文件不存在/坏了都返回空字典（不抛异常，界面要能继续用）。"""
    p = Path(path) if path else config_path()
    if not p.exists():
        return {}
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(strip_jsonc(raw))
    except json.JSONDecodeError:
        return {}


def backup(path: Path) -> Path | None:
    """写之前先备份，返回备份文件路径。"""
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = path.with_name(f"{path.name}.bak-{stamp}")
    try:
        shutil.copy2(path, dst)
    except OSError:
        return None
    # 只留最近 MAX_BACKUPS 份，旧的清掉
    try:
        olds = sorted(path.parent.glob(f"{path.name}.bak-*"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        for old in olds[MAX_BACKUPS:]:
            try:
                old.unlink()
            except OSError:
                pass
    except OSError:
        pass
    return dst


def write(cfg: dict, path: Path | None = None, backup_first: bool = True) -> Path:
    """写配置（严格 JSON，2 空格缩进，保留原有 UTF-8 中文）。"""
    p = Path(path) if path else config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    if backup_first:
        backup(p)
    text = json.dumps(cfg, ensure_ascii=False, indent=2) + "\n"
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)
    return p


# ------------------------------------------------------------------ provider
def providers_from(cfg: dict) -> list[dict]:
    """把配置里的 provider 段整理成统一结构。"""
    out = []
    for pid, p in (cfg.get("provider") or {}).items():
        if not isinstance(p, dict):
            continue
        opts = p.get("options") or {}
        models = p.get("models") or {}
        out.append({
            "id": pid,
            "name": p.get("name") or pid,
            "npm": p.get("npm") or DEFAULT_NPM,
            "base_url": opts.get("baseURL") or "",
            "api_key": opts.get("apiKey") or "",
            "models": models if isinstance(models, dict) else {},
        })
    return out


def provider_to_json(p: dict) -> dict:
    """统一结构 -> OpenCode 的 provider JSON。"""
    models = p.get("models") or {}
    if not isinstance(models, dict):
        models = {}
    node = {
        "npm": p.get("npm") or DEFAULT_NPM,
        "name": p.get("name") or p.get("id") or "",
        "options": {
            "baseURL": p.get("base_url") or "",
            "apiKey": p.get("api_key") or "",
            "setCacheKey": True,
        },
        "models": models,
    }
    return node


def apply_providers(cfg: dict, providers: list[dict],
                    default_model: str = "") -> dict:
    """把 provider 列表写回配置结构（保留其它顶层字段，比如 $schema）。"""
    new = dict(cfg or {})
    new["provider"] = {p["id"]: provider_to_json(p) for p in providers}
    if default_model:
        new["model"] = default_model
    return new


def model_ids(p: dict) -> list[str]:
    """provider 里的模型 id 列表。"""
    models = p.get("models") or {}
    if isinstance(models, dict):
        return list(models.keys())
    return []


def model_label(p: dict, mid: str) -> str:
    """模型显示名：优先取 name 字段，其次用 id。"""
    models = p.get("models") or {}
    if isinstance(models, dict) and isinstance(models.get(mid), dict):
        return models[mid].get("name") or mid
    return mid


# ------------------------------------------------------------------ 联网
def _request(url: str, headers: dict, method: str = "GET",
             body: bytes | None = None, timeout: int = 12):
    req = urllib.request.Request(url, headers=headers, method=method,
                                 data=body)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def _join(base: str, path: str) -> str:
    return base.rstrip("/") + "/" + path.lstrip("/")


def fetch_models(base_url: str, api_key: str, timeout: int = 12
                 ) -> tuple[list[str], str]:
    """拉取 baseURL 上可用的模型列表。

    返回 (模型 id 列表, 错误信息)。空列表 + 空错误串 = 成功但没有模型。
    """
    if not base_url:
        return [], "baseURL 为空"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    status, text = _request(_join(base_url, "models"), headers, timeout=timeout)
    if status != 200:
        return [], f"HTTP {status}: {text[:180]}"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return [], "返回的不是 JSON"
    ids: list[str] = []
    if isinstance(data, dict):
        items = data.get("data") or data.get("models") or []
        for it in items:
            if isinstance(it, str):
                ids.append(it)
            elif isinstance(it, dict):
                mid = it.get("id") or it.get("name") or it.get("model")
                if mid:
                    ids.append(str(mid))
    elif isinstance(data, list):
        for it in data:
            if isinstance(it, str):
                ids.append(it)
            elif isinstance(it, dict):
                mid = it.get("id") or it.get("name")
                if mid:
                    ids.append(str(mid))
    # 去重保序
    seen, uniq = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    return uniq, ""


def test_connection(base_url: str, api_key: str, model: str,
                    timeout: int = 20) -> tuple[bool, str]:
    """发一个最小的对话请求，验证 baseURL / key / 模型能不能用。"""
    if not base_url:
        return False, "baseURL 为空"
    if not model:
        return False, "没有选模型"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,
        "stream": False,
    }
    body = json.dumps(payload).encode("utf-8")
    status, text = _request(_join(base_url, "chat/completions"), headers,
                             method="POST", body=body, timeout=timeout)
    if status == 200:
        try:
            obj = json.loads(text)
            usage = obj.get("usage") or {}
            detail = ""
            if usage:
                detail = (f"tokens in/out "
                          f"{usage.get('prompt_tokens', '-')}/"
                          f"{usage.get('completion_tokens', '-')}")
            return True, f"连接正常 {detail}".strip()
        except json.JSONDecodeError:
            return True, "连接正常（返回非 JSON）"
    if status == 400:
        # 有些服务端只认 max_completion_tokens（OpenAI 新参数名）
        payload["max_completion_tokens"] = 1
        payload.pop("max_tokens", None)
        body = json.dumps(payload).encode("utf-8")
        status, text = _request(_join(base_url, "chat/completions"), headers,
                                 method="POST", body=body, timeout=timeout)
        if status == 200:
            return True, "连接正常"
    if status == 0:
        return False, f"请求失败：{text[:180]}"
    if status in (401, 403):
        return False, f"鉴权失败（HTTP {status}）：APIKey 不对或没权限"
    if status == 404:
        return False, "HTTP 404：baseURL 或模型名不对"
    return False, f"HTTP {status}: {text[:180]}"
