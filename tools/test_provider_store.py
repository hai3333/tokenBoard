#!/usr/bin/env python3
"""provider 存储层自测：导入 / 加密 / 投影 / 备份。

全部在临时目录里跑，不碰用户真实的 opencode.jsonc 和 tokenboard.db。
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, r"D:\个人资料\项目\token看板")

from tokenboard import opencode_config as oc
from tokenboard.providers import ProviderStore, parse_models_text

FAIL = []


def check(name: str, cond: bool, extra: str = ""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}" + (f"  {extra}" if extra else ""))
    if not cond:
        FAIL.append(name)


class FakeStore:
    """只提供 ProviderStore 需要的 conn / _lock。"""

    def __init__(self, path):
        self.conn = sqlite3.connect(path, timeout=15, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()


SAMPLE = {
    "model": "hs/doubao-seed-evolving",
    "$schema": "https://opencode.ai/config.json",
    "provider": {
        "hs": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "火山 Coding Plan",
            "options": {
                "baseURL": "https://ark.cn-beijing.volces.com/api/coding/v3",
                "apiKey": "sk-volc-abcdef123456",
                "setCacheKey": True,
            },
            "models": {
                "doubao-seed-evolving": {"name": "doubao-seed-evolving",
                                         "reasoning": True},
                "glm-5.3": {"name": "glm-5.3"},
            },
        },
        "bailian": {
            "npm": "@ai-sdk/openai-compatible",
            "options": {
                "baseURL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "apiKey": "sk-ali-9876543210",
                "setCacheKey": True,
            },
            "models": {"glm-5.3": {"name": "alliglm-5.3"}},
        },
    },
}


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="tb_oc_"))
    # 护栏：记录用户真实配置的指纹，跑完必须一模一样
    real_cfg = oc.config_path()
    real_before = (real_cfg.read_bytes() if real_cfg.exists() else None)
    try:
        cfg_path = tmp / "opencode.jsonc"
        cfg_path.write_text(json.dumps(SAMPLE, ensure_ascii=False, indent=2),
                            encoding="utf-8")

        print("[1] JSONC 读取（容忍注释/尾逗号）")
        raw = ('{\n  // 这是注释\n  "a": 1,   // 行尾注释\n  "b": [1,2,],\n}\n')
        p2 = tmp / "c.jsonc"
        p2.write_text(raw, encoding="utf-8")
        obj = oc.read(p2)
        check("注释被忽略且解析成功", obj.get("a") == 1 and obj.get("b") == [1, 2],
              json.dumps(obj, ensure_ascii=False))

        print("\n[2] 从 opencode.jsonc 导入")
        # 关键：store 显式指向临时文件，绝不能写到用户真实配置上
        store = ProviderStore(FakeStore(tmp / "tb.db"), config_path=cfg_path)
        n = store.import_from_opencode_config(cfg_path)
        providers = store.list()
        check("导入 2 个 provider", n == 2 and len(providers) == 2, f"n={n}")
        hs = store.get("hs")
        check("名称/baseURL 正确",
              hs is not None and hs.name == "火山 Coding Plan"
              and hs.base_url.endswith("/api/coding/v3"))
        check("密钥解密还原正确", hs is not None and hs.api_key == "sk-volc-abcdef123456",
              hs.api_key if hs else "")
        check("模型保留附加字段",
              hs is not None and hs.models["doubao-seed-evolving"].get("reasoning") is True)

        print("\n[3] 数据库里存的是密文")
        row = store.conn.execute(
            "SELECT api_key_enc FROM oc_providers WHERE id='hs'").fetchone()
        enc = row["api_key_enc"]
        check("明文不在库里", "sk-volc-abcdef123456" not in enc, enc[:36] + "...")
        check("密文非空且能 base64 解码",
              bool(enc) and len(base64.b64decode(enc + "=" * (-len(enc) % 4))) > 16)

        print("\n[4] 投影写回 opencode.jsonc")
        store.set_default_model("bailian/glm-5.3")
        out = store.export_to_opencode_config(cfg_path)
        back = json.loads(out.read_text(encoding="utf-8"))
        check("provider 数量一致", len(back.get("provider", {})) == 2,
              str(list(back.get("provider", {}))))
        check("默认模型写入正确", back.get("model") == "bailian/glm-5.3", back.get("model"))
        check("其它顶层字段保留（$schema）", back.get("$schema") == SAMPLE["$schema"])
        check("写回后密钥完整",
              back["provider"]["hs"]["options"]["apiKey"] == "sk-volc-abcdef123456")
        backups = list(tmp.glob("opencode.jsonc.bak-*"))
        check("写前自动备份", len(backups) >= 1, f"{len(backups)} 份")

        print("\n[5] 切 provider / 切模型")
        val = store.switch_to("hs", "glm-5.3")
        back2 = json.loads(cfg_path.read_text(encoding="utf-8"))
        check("切换后默认模型 = hs/glm-5.3", val == "hs/glm-5.3" and
              back2.get("model") == "hs/glm-5.3", back2.get("model"))
        check("当前 provider 标记正确", store.current() is not None
              and store.current().id == "hs")

        print("\n[6] 模型文本双向转换")
        text = "doubao-seed-evolving doubao-seed-evolving\nglm-5.3 GLM5.3"
        models = parse_models_text(text)
        check("解析成 models 结构",
              models["glm-5.3"]["name"] == "GLM5.3"
              and models["doubao-seed-evolving"]["name"] == "doubao-seed-evolving")
        check("空行/注释行忽略",
              len(parse_models_text("# 注释\n\n  \n")) == 0)

        print("\n[7] 从 cc-switch.db 导入（只读，不改它）")
        ccdb = Path.home() / ".cc-switch" / "cc-switch.db"
        if ccdb.exists():
            before = ccdb.stat().st_mtime
            n2 = store.import_from_ccswitch(ccdb)
            check("导入到 opencode provider", n2 > 0, f"n={n2}")
            check("cc-switch.db 未被修改", ccdb.stat().st_mtime == before)
            sample = store.get("hs")
            check("ccswitch 的 key 也能解密", sample is not None
                  and len(sample.api_key) > 10,
                  (sample.api_key[:8] + "...") if sample else "")
        else:
            print("  -- 没装 ccswitch，跳过")

        print("\n[8] 空/坏文件不炸")
        bad = tmp / "bad.jsonc"
        bad.write_text("{ 这不是 json", encoding="utf-8")
        check("坏文件返回空字典", oc.read(bad) == {})
        missing = tmp / "nope.jsonc"
        check("文件不存在返回空字典", oc.read(missing) == {})

        print("\n[9] 护栏：用户真实配置没被动过")
        real_after = (real_cfg.read_bytes() if real_cfg.exists() else None)
        check("真实 opencode.jsonc 字节完全一致", real_before == real_after,
              str(real_cfg))

        print()
        if FAIL:
            print(f"!!! {len(FAIL)} 项失败: {FAIL}")
            return 1
        print("全部通过")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

