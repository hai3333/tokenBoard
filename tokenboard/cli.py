"""命令行入口：扫描 + 报表（用于自检和排查）。"""
from __future__ import annotations

import argparse
import sys
import time

from .config import DB_PATH, ensure_dirs
from .pricing import get_pricing
from .scanner import Scanner
from .store import Store


def _fmt(n: float) -> str:
    """大数字转可读形式。"""
    n = float(n)
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= div:
            return f"{n / div:,.2f}{unit}"
    return f"{n:,.0f}"


def _fmt_ms(ms) -> str:
    ms = float(ms or 0)
    if ms <= 0:
        return "-"
    if ms < 1000:
        return f"{ms:.0f}ms"
    if ms < 60_000:
        return f"{ms / 1000:.1f}s"
    return f"{ms / 60000:.1f}m"


def _fmt_tps(v) -> str:
    v = float(v or 0)
    return f"{v:,.0f} t/s" if v > 0 else "-"


def cmd_reset(args) -> int:
    ensure_dirs()
    store = Store(DB_PATH)
    store.conn.execute("DELETE FROM usage_events")
    store.conn.execute("DELETE FROM sync_state")
    store.conn.commit()
    store.close()
    print("已清空用量库与同步水位，下次扫描将全量重扫。")
    return 0


def cmd_scan(args) -> int:
    ensure_dirs()
    store = Store(DB_PATH)
    scanner = Scanner(store)
    t0 = time.time()
    results = scanner.scan()
    elapsed = time.time() - t0

    print(f"扫描完成，用时 {elapsed:.2f}s\n" + "=" * 72)
    for r in results:
        flag = "OK " if r.ok else "ERR"
        detail = (f"{r.new_records:>6} 条新增 / {r.new_samples:>5} 条速度采样"
                  if r.ok else r.error)
        print(f"  [{flag}] {r.app:<10} {r.duration_ms:>6}ms  {detail}")
        if r.detail:
            for line in r.detail.strip().splitlines()[-2:]:
                print(f"        {line}")
    print("=" * 72)
    total = store.count_usage()
    print(f"库存总量：{total:,} 条请求记录 / {store.count_speed():,} 条速度采样")
    store.close()
    return 0


def cmd_report(args) -> int:
    ensure_dirs()
    store = Store(DB_PATH)
    since = args.days
    since_day = None
    if since and since > 0:
        since_day = time.strftime("%Y-%m-%d", time.localtime(time.time() - since * 86400))

    rows = store.summary(since_day=since_day)
    speed = store.speed_stats(since_day=since_day)
    label = f"最近 {since} 天" if since_day else "全部"

    print(f"\nTokenBoard 报表（{label}）")
    print("=" * 96)
    print(f"{'应用':<18}{'请求数':>9}{'总 tokens':>14}{'缓存读':>12}"
          f"{'费用 USD':>11}{'首字P50':>10}{'速度':>12}")
    print("-" * 96)
    grand = 0
    grand_cost = 0.0
    for r in rows:
        grand += r["total_tokens"] or 0
        grand_cost += r["cost_usd"] or 0
        sp = speed["apps"].get(r["app"]) or {}
        print(f"{r['app']:<18}{r['requests']:>9,}{_fmt(r['total_tokens']):>14}"
              f"{_fmt(r['cache_read_tokens']):>12}{r['cost_usd']:>11.4f}"
              f"{_fmt_ms(sp.get('ttft_p50')):>10}{_fmt_tps(sp.get('tps')):>12}")
    print("-" * 96)
    tot = speed.get("total") or {}
    print(f"{'合计':<18}{'':>9}{_fmt(grand):>14}{'':>12}{grand_cost:>11.4f}"
          f"{_fmt_ms(tot.get('ttft_p50')):>10}{_fmt_tps(tot.get('tps')):>12}")

    models = store.models_aggregated(since_day=since_day, limit=20)
    if models:
        print("\n按模型汇总 Top 20（跨工具合并同名模型）")
        print("-" * 96)
        print(f"  {'模型':<32}{'tokens':>12}{'请求':>7}{'费用':>10}"
              f"{'首字':>9}{'tok/s':>9}{'主要工具':>12}")
        for m in models:
            sp = speed["models"].get(m["key"]) or {}
            print(f"  {m['name'][:31]:<32}{_fmt(m['total_tokens']):>12}"
                  f"{m['requests']:>7}{m['cost_usd']:>10.4f}"
                  f"{_fmt_ms(sp.get('ttft_p50')):>9}{_fmt_tps(sp.get('tps')):>9}"
                  f"{m['app']:>12}")
    store.close()
    return 0


def _fmt_ts(ms) -> str:
    if not ms:
        return "从未"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ms / 1000))


def cmd_webdav(args) -> int:
    """WebDAV 云同步：status / test / set / enable / disable / sync。"""
    from . import sync as syncmod

    cfg = syncmod.load_config()
    action = args.action

    if action == "set":
        changed = False
        for attr, val in (("url", args.url), ("username", args.user),
                          ("remote_dir", args.remote_dir),
                          ("interval_min", args.interval),
                          ("timeout_sec", args.timeout)):
            if val not in (None, ""):
                if attr in ("interval_min", "timeout_sec"):
                    val = max(1, int(val))
                setattr(cfg, attr, val)
                changed = True
        if args.insecure:
            cfg.insecure = True
            changed = True
        if args.password is not None:
            cfg.set_password(args.password)
            changed = True
        elif args.ask_pass:
            import getpass
            cfg.set_password(getpass.getpass("WebDAV 密码（不回显）: "))
            changed = True
        if args.enable:
            cfg.enabled = True
            changed = True
        if not changed:
            print("没有要改的内容。用 --url/--user/--pass/--dir/--interval/--enable")
            return 1
        syncmod.save_config(cfg)
        print(f"已保存到 {syncmod.SYNC_CONFIG_PATH}")
        if not cfg.enabled:
            print("提示：还没启用，跑 `tokenboard webdav enable` 或加 --enable")
        return 0

    if action in ("enable", "disable"):
        cfg.enabled = action == "enable"
        syncmod.save_config(cfg)
        print("已" + ("启用" if cfg.enabled else "停用") + "云同步")
        return 0

    if action == "test":
        r = syncmod.probe(cfg)
        print(("✓ " if r["ok"] else "✗ ") + r["message"])
        return 0 if r["ok"] else 1

    if action == "sync":
        ensure_dirs()
        store = Store(DB_PATH)
        try:
            res = syncmod.sync_once(store, cfg, force=True)
            u, s = store.counts()
            print(f"结果：{res.summary()}")
            print(f"本地：{u:,} 条用量 / {s:,} 条速度采样")
            print(f"远端：{res.remote_count:,} 条 / {res.remote_bytes / 1024:.1f} KB"
                  f"{'（已存在）' if res.remote_exists else '（本次新建）'}")
            print(f"耗时：{res.duration_ms} ms")
            return 0 if res.ok else 1
        finally:
            store.close()

    # status
    print("WebDAV 云同步")
    print("=" * 56)
    print(f"  状态      : {'已启用' if cfg.enabled else '未启用'}")
    print(f"  服务器    : {cfg.url or '（未配置）'}")
    print(f"  用户名    : {cfg.username or '（空）'}   密码：{cfg.masked_password() or '（空）'}")
    print(f"  远程目录  : {cfg.remote_dir}")
    print(f"  同步间隔  : 每 {cfg.interval_min} 分钟")
    print(f"  上次成功  : {_fmt_ts(cfg.last_sync_at)}  ({cfg.last_status})")
    if cfg.last_error:
        print(f"  上次错误  : {cfg.last_error}（{_fmt_ts(cfg.last_error_at)}）")
    print(f"  远端快照  : {cfg.last_remote_count:,} 条 / {cfg.last_remote_bytes / 1024:.1f} KB")
    try:
        ensure_dirs()
        store = Store(DB_PATH)
        u, s = store.counts()
        store.close()
        print(f"  本地数据  : {u:,} 条用量 / {s:,} 条速度采样")
    except Exception as e:  # noqa: BLE001
        print(f"  本地数据  : 读库失败 {e}")
    print(f"  配置文件  : {syncmod.SYNC_CONFIG_PATH}")
    return 0


def cmd_startup(args) -> int:
    from . import startup
    if args.action == "install":
        path = startup.install()
        print(f"已添加开机自启：{path}")
    elif args.action == "uninstall":
        if startup.uninstall():
            print("已移除开机自启。")
        else:
            print("未找到开机自启项。")
    else:
        state = "已启用" if startup.is_installed() else "未启用"
        print(f"开机自启：{state}")
    return 0


def cmd_pricing(args) -> int:
    p = get_pricing()
    for mid in (args.models or []):
        print(f"{mid:<40} -> {p.resolve(mid)}")
    print(f"\n价格表共 {len(p.pricing_map())} 条")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tokenboard", description="本机 AI IDE Token 消耗看板")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="扫描各 IDE 的本地会话日志")
    p_scan.set_defaults(func=cmd_scan)

    p_reset = sub.add_parser("reset", help="清空用量库，下次全量重扫")
    p_reset.set_defaults(func=cmd_reset)

    p_rep = sub.add_parser("report", help="输出用量报表")
    p_rep.add_argument("--days", type=int, default=0, help="只看最近 N 天")
    p_rep.set_defaults(func=cmd_report)

    p_pr = sub.add_parser("pricing", help="查询模型价格")
    p_pr.add_argument("models", nargs="*", help="模型名")
    p_pr.set_defaults(func=cmd_pricing)

    p_su = sub.add_parser("startup", help="开机自启管理")
    p_su.add_argument("action", nargs="?", default="status",
                       choices=["install", "uninstall", "status"])
    p_su.set_defaults(func=cmd_startup)

    p_wd = sub.add_parser("webdav", help="WebDAV 云同步（多机合并）")
    p_wd.add_argument("action", nargs="?", default="status",
                      choices=["status", "test", "set", "sync",
                               "enable", "disable"])
    p_wd.add_argument("--url", help="WebDAV 根地址，如 https://dav.jianguoyun.com/dav")
    p_wd.add_argument("--user", help="用户名")
    p_wd.add_argument("--pass", dest="password", help="密码（会经 DPAPI 加密后落盘）")
    p_wd.add_argument("--ask-pass", action="store_true", help="交互式输入密码，避免留在命令历史里")
    p_wd.add_argument("--dir", dest="remote_dir", help="远端目录，默认 TokenBoard")
    p_wd.add_argument("--interval", type=int, help="自动同步间隔（分钟）")
    p_wd.add_argument("--timeout", type=int, help="单次请求超时（秒）")
    p_wd.add_argument("--insecure", action="store_true", help="跳过 HTTPS 证书校验（自签证书 NAS）")
    p_wd.add_argument("--enable", action="store_true", help="保存后立即启用")
    p_wd.set_defaults(func=cmd_webdav)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
