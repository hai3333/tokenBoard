#!/usr/bin/env python3
"""细粒度内存剖析：逐段叠加 + 扫描前后对比。"""
import os
import subprocess
import sys
import time

import psutil

ROOT = r"D:\个人资料\项目\token看板"
PY = sys.executable


def priv(pr) -> float:
    try:
        return pr.memory_full_info().private / 1048576
    except Exception:  # noqa: BLE001
        return -1.0


def run(label, code, wait=6.0):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.Popen([PY, "-c", code], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
    time.sleep(wait)
    if p.poll() is not None:
        err = p.stderr.read().decode("utf-8", "replace")[-300:] if p.stderr else ""
        print(f"  {label:<44} 退出 {p.returncode} {err[:110]}")
        return
    try:
        pr = psutil.Process(p.pid)
        m = pr.memory_info()
        print(f"  {label:<44} RSS {m.rss / 1048576:6.1f} MB   private {priv(pr):6.1f} MB")
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            p.kill()


print("=" * 80)
print("A. 逐段叠加")
print("=" * 80)
run("空 python", "import time; time.sleep(30)")
run("+ ctypes + user32/gdi32/kernel32",
    "import ctypes; ctypes.WinDLL('user32'); ctypes.WinDLL('gdi32');"
    "ctypes.WinDLL('kernel32'); time.sleep(30)")
run("+ shell32 + shcore",
    "import ctypes; ctypes.WinDLL('shell32'); ctypes.WinDLL('shcore'); time.sleep(30)")
run("+ zstandard", "import zstandard; time.sleep(30)")
run("+ sqlite3 + 本项目 store",
    "import sys; sys.path.insert(0,r'%s'); from tokenboard.store import Store;"
    "from tokenboard.config import DB_PATH; s=Store(DB_PATH); time.sleep(30)" % ROOT)
run("+ 全部 collector 模块",
    "import sys; sys.path.insert(0,r'%s'); from tokenboard.collectors import"
    " build_collectors; time.sleep(30)" % ROOT)
run("+ 全部 UI 模块 (win32)",
    "import sys; sys.path.insert(0,r'%s'); from tokenboard.ui import panel, tray;"
    "time.sleep(30)" % ROOT)

print()
print("=" * 80)
print("B. 完整应用：每秒内存")
print("=" * 80)
p = subprocess.Popen([PY, "-m", "tokenboard.app"], cwd=ROOT,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env={**os.environ, "PYTHONIOENCODING": "utf-8"})
pr = psutil.Process(p.pid)
for i in range(14):
    time.sleep(1)
    if p.poll() is not None:
        break
    m = pr.memory_info()
    print(f"  t+{i + 1:>2}s  RSS {m.rss / 1048576:6.1f} MB   private {priv(pr):6.1f} MB")
p.terminate()
try:
    p.wait(timeout=5)
except Exception:  # noqa: BLE001
    p.kill()
