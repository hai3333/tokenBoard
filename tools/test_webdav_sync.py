#!/usr/bin/env python3
"""WebDAV 同步的端到端验收。

两个「设备」= 两个临时 TOKENBOARD_HOME，各写一批不同的用量，通过一个
本地假 WebDAV 服务器互相同步，最后校验两边的数据完全一致、没有重复。

全程只碰临时目录，不会动 %LOCALAPPDATA%\\TokenBoard 里的真实数据。

    python tools/test_webdav_sync.py
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 18923
BASE = f"http://127.0.0.1:{PORT}"
PY = sys.executable
OK = "[ OK ]"
FAIL = "[FAIL]"

failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"{OK} {name}")
    else:
        print(f"{FAIL} {name}  {detail}")
        failures.append(name)


def run(args: list[str], home: Path, timeout: int = 90) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["TOKENBOARD_HOME"] = str(home)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(args, cwd=str(ROOT), env=env,
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def py(code: str, home: Path) -> subprocess.CompletedProcess:
    return run([PY, "-c", code], home)


def seed(home: Path, prefix: str, n_usage: int, n_speed: int) -> None:
    code = f"""
import time
from tokenboard.config import DB_PATH, ensure_dirs
from tokenboard.store import Store
from tokenboard.models import UsageRecord, SpeedSample
ensure_dirs()
st = Store(DB_PATH)
base = int(time.time()*1000) - 86_400_000
recs = [UsageRecord(app="claude", source="test", request_id="{prefix}-u%d" % i,
                    ts_ms=base + i*1000, model="claude-test",
                    input_tokens=100, output_tokens=50, cost_usd=0.001)
        for i in range({n_usage})]
st.upsert_usage(recs)
samps = [SpeedSample(app="claude", source="test", sample_id="{prefix}-s%d" % i,
                     ts_ms=base + i*1000, model="claude-test", kind="call",
                     ttft_ms=500 + i, duration_ms=2000 + i, output_tokens=50)
         for i in range({n_speed})]
st.upsert_speed(samps)
print(st.counts())
st.close()
"""
    r = py(code, home)
    if r.returncode != 0:
        raise RuntimeError(f"seed 失败:\n{r.stdout}\n{r.stderr}")


def counts(home: Path) -> tuple[int, int]:
    code = """
from tokenboard.config import DB_PATH
from tokenboard.store import Store
st = Store(DB_PATH)
print(*st.counts())
st.close()
"""
    r = py(code, home)
    if r.returncode != 0:
        raise RuntimeError(f"counts 失败:\n{r.stdout}\n{r.stderr}")
    a, b = (r.stdout.strip().split() + ["0", "0"])[:2]
    return int(a), int(b)


def wait_port(port: int, timeout: float = 10.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.15)
    return False


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tb-sync-test-"))
    home_a = tmp / "home-a"
    home_b = tmp / "home-b"
    dav_root = tmp / "dav"
    for p in (home_a, home_b, dav_root):
        p.mkdir(parents=True, exist_ok=True)

    server = subprocess.Popen(
        [PY, str(ROOT / "tools" / "fake_webdav.py"),
         "--root", str(dav_root), "--port", str(PORT)],
        cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        if not wait_port(PORT):
            print(f"{FAIL} 假 WebDAV 服务器没起来")
            return 1
        print(f"临时目录: {tmp}\n假 WebDAV: {BASE}\n")

        # ---- 初始数据：A 100 条用量 / 10 条采样，B 50 条 / 5 条
        seed(home_a, "a", 100, 10)
        seed(home_b, "b", 50, 5)
        print(f"A: {counts(home_a)}   B: {counts(home_b)}")
        check("初始两边数据独立", counts(home_a) == (100, 10) and counts(home_b) == (50, 5))

        # ---- 配置（密码走 --pass，落盘应加密）
        r = run([PY, "-m", "tokenboard", "webdav", "set",
                 "--url", BASE, "--user", "tester", "--pass", "s3cret",
                 "--dir", "TokenBoard", "--interval", "30", "--enable"], home_a)
        check("webdav set 成功", r.returncode == 0, r.stdout + r.stderr)
        cfg_text = (home_a / "sync.json").read_text(encoding="utf-8")
        check("密码没有明文落盘", "s3cret" not in cfg_text,
              "sync.json 里出现了明文密码")
        check("配置里已启用", '"enabled": true' in cfg_text)

        # ---- A 第一次同步：远端还没文件，应创建
        r = run([PY, "-m", "tokenboard", "webdav", "sync"], home_a)
        print(r.stdout.strip())
        check("A 首次同步成功", r.returncode == 0, r.stdout + r.stderr)
        remote = dav_root / "TokenBoard" / "usage.jsonl.gz"
        check("远端快照已创建", remote.is_file())

        # ---- B 配好并同步：应下载 A 的 100 条，再把自己 50 条传上去
        r = run([PY, "-m", "tokenboard", "webdav", "set",
                 "--url", BASE, "--user", "tester", "--pass", "s3cret", "--enable"], home_b)
        check("B 配置成功", r.returncode == 0, r.stdout + r.stderr)
        r = run([PY, "-m", "tokenboard", "webdav", "sync"], home_b)
        print(r.stdout.strip())
        check("B 同步成功", r.returncode == 0, r.stdout + r.stderr)
        check("B 合并后是 150 条用量", counts(home_b) == (150, 15), str(counts(home_b)))

        # ---- B 再新增 7 条，A 同步后应拿到
        seed(home_b, "b2", 7, 3)
        r = run([PY, "-m", "tokenboard", "webdav", "sync"], home_b)
        check("B 增量同步成功", r.returncode == 0, r.stdout + r.stderr)
        r = run([PY, "-m", "tokenboard", "webdav", "sync"], home_a)
        print(r.stdout.strip())
        check("A 同步后拿到 B 的新数据", counts(home_a) == (157, 18), str(counts(home_a)))
        check("两边最终一致", counts(home_a) == counts(home_b),
              f"{counts(home_a)} vs {counts(home_b)}")

        # ---- 幂等：再同步一次不应产生重复
        run([PY, "-m", "tokenboard", "webdav", "sync"], home_a)
        run([PY, "-m", "tokenboard", "webdav", "sync"], home_b)
        check("重复同步不会重复计数", counts(home_a) == (157, 18) == counts(home_b),
              f"{counts(home_a)} / {counts(home_b)}")

        # ---- 测试连接
        r = run([PY, "-m", "tokenboard", "webdav", "test"], home_a)
        print(r.stdout.strip())
        check("测试连接通过", r.returncode == 0, r.stdout + r.stderr)

        # ---- status 输出
        r = run([PY, "-m", "tokenboard", "webdav", "status"], home_a)
        check("status 正常输出", "已启用" in r.stdout and "157" in r.stdout.replace(",", ""),
              r.stdout)

        # ---- ETag 冲突：故意用过期 ETag 上传，服务器应回 412
        code = f"""
from tokenboard import sync
from tokenboard.webdav import WebDAV, WebDAVError
cfg = sync.load_config()
dav = WebDAV(cfg.url, cfg.username, cfg.password)
try:
    dav.put(cfg.remote_path(), b"x", if_match='"deadbeef"')
    print("NO412")
except WebDAVError as e:
    print("412" if e.status == 412 else f"OTHER{{e.status}}")
"""
        r = py(code, home_a)
        check("过期 ETag 上传被拒（412 冲突保护生效）", "412" in r.stdout, r.stdout + r.stderr)

        # ---- 坏配置不应崩
        (home_b / "sync.json").write_text('{"url": "http://127.0.0.1:9/dav",'
                                         '"enabled": true, "interval_min": 30}',
                                         encoding="utf-8")
        r = run([PY, "-m", "tokenboard", "webdav", "sync"], home_b, timeout=120)
        check("连不上时给出错误而不是崩", r.returncode == 1 and "连不上" in r.stdout,
              r.stdout + r.stderr)
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()

    print()
    if failures:
        print(f"失败 {len(failures)} 项: {failures}")
        print(f"（临时目录保留供排查: {tmp}）")
        return 1
    print("全部通过")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())