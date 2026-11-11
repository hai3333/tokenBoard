#!/usr/bin/env python3
"""内存随时间变化：全量扫描峰值 -> 稳定态 -> 增量扫描后。"""
import os
import subprocess
import sys
import time

import psutil

ROOT = r"D:\个人资料\项目\token看板"


def priv(pr) -> float:
    try:
        return pr.memory_full_info().private / 1048576
    except Exception:  # noqa: BLE001
        return -1.0


def run(label: str, seconds: int = 150):
    print(f"\n--- {label} ---")
    p = subprocess.Popen([sys.executable, "-m", "tokenboard.app"], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    pr = psutil.Process(p.pid)
    prev = None
    for i in range(seconds):
        time.sleep(1)
        if p.poll() is not None:
            break
        m = pr.memory_info()
        rss = m.rss / 1048576
        if prev is None or abs(rss - prev) > 0.4:
            print(f"  t+{i + 1:>3}s  RSS {rss:6.1f} MB   private {priv(pr):6.1f} MB")
            prev = rss
    print(f"  末态: RSS {rss:6.1f} MB   private {priv(pr):6.1f} MB")
    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:  # noqa: BLE001
        p.kill()


if __name__ == "__main__":
    run("库里有数据（增量扫描为主）", 150)
    # 清库后再测全量
    subprocess.run([sys.executable, "-m", "tokenboard.reset"], cwd=ROOT,
                   stdout=subprocess.DEVNULL, env={**os.environ})
    run("空库首次启动（全量扫描）", 150)
