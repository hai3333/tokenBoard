#!/usr/bin/env python3
"""把免安装单文件 exe 复制到 D:\\software\\TokenBoard\\（和用户其它软件放一起）。"""
import os
import shutil
from pathlib import Path

SRC = Path(r"D:\个人资料\项目\token看板\dist\portable\TokenBoard.exe")
DEST_DIR = Path(r"D:\software\TokenBoard")

DEST_DIR.mkdir(parents=True, exist_ok=True)
dst = DEST_DIR / "TokenBoard.exe"
shutil.copy2(SRC, dst)
print(f"已复制 -> {dst}  ({dst.stat().st_size / 1048576:.2f} MB)")
