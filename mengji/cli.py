"""命令行入口:python -m mengji <子命令>。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

from . import __version__, agent, llm, tools
from .db import Database

MOCK_BANNER = "· 离线模式:没配 LLM_API_KEY,或显式 --mock。统计照算,解释只做模板。"

_OPEN: list[Database] = []


def _db(args) -> Database:
    db = Database(args.db)
    _OPEN.append(db)
    return db


def _close_all() -> None:
    for db in _OPEN:
        try:
            db.close()
        except Exception:
            pass
    _OPEN.clear()


def render_analyze(r: dict) -> str:
    lines = [f"{r.get('summary', '')}", ""]
    if r.get("flags"):
        lines.append("值得注意:")
        lines.extend(f"  ! {f}" for f in r["flags"])
    if r.get("factors"):
        lines.append("可能的影响:")
        lines.extend(f"  · {f}" for f in r["factors"])
    if r.get("advice"):
        lines.append("今晚/本周能做:")
        lines.extend(f"  {i}. {a}" for i, a in enumerate(r["advice"], 1))
    if r.get("problems"):
        lines.extend(f"! {p}" for p in r["problems"])
    if r.get("note"):
        lines.append(r["note"])
    return "\n".join(lines)


def render_trend(r: dict) -> str:
    lines = [r.get("text", ""), ""]
    if r.get("summary") and r["summary"] != r.get("text"):
        lines.append(r["summary"])
    if r.get("problems"):
        lines.extend(f"! {p}" for p in r["problems"])
    if r.get("note"):
        lines.append(r["note"])
    return "\n".join(lines)


def render_dream(r: dict) -> str:
    lines = []
    if r.get("motifs"):
        lines.append("母题:" + "、".join(r["motifs"]))
    if r.get("reading"):
        lines.append(r["reading"])
    for n in r.get("notes", []):
        lines.append(f"  · {n}")
    if r.get("problems"):
        lines.extend(f"! {p}" for p in r["problems"])
    lines.append(r.get("disclaimer") or r.get("note") or "文化联想,不是解梦,也不是诊断")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mengji", description="梦记 · 睡眠记录:时长、质量、梦境与趋势。")
    p.add_argument("--version", action="version", version=f"mengji {__version__}")
    p.add_argument("--mock", action="store_true", help="强制离线模式")
    p.add_argument("--json", action="store_true")
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--api-key")
    p.add_argument("--db", default="data/mengji.db")
    sub = p.add_subparsers(dest="cmd", required=True)

    lg = sub.add_parser("log", help="记一天的睡眠")
    lg.add_argument("hours", type=float)
    lg.add_argument("--quality", type=int, default=3, choices=[1, 2, 3, 4, 5])
    lg.add_argument("--dream", default="")
    lg.add_argument("--note", default="")
    lg.add_argument("--date", default="", help="默认今天,格式 YYYY-MM-DD")
    sub.add_parser("seed", help="导入示例记录")
    li = sub.add_parser("list", help="记录列表")
    li.add_argument("--limit", type=int, default=0)
    s = sub.add_parser("show", help="看某一天")
    s.add_argument("day", nargs="?", default="")
    a = sub.add_parser("analyze", help="分析某一天")
    a.add_argument("day", nargs="?", default="")
    d = sub.add_parser("dream", help="读某个梦")
    d.add_argument("day", nargs="?", default="")
    t = sub.add_parser("trend", help="看一段时间趋势")
    t.add_argument("--days", type=int, default=14)
    r = sub.add_parser("rm", help="删某一天")
    r.add_argument("day")
    sub.add_parser("stats", help="统计")
    we = sub.add_parser("web", help="启动 Web 界面")
    we.add_argument("--host", default="127.0.0.1")
    we.add_argument("--port", type=int, default=8774)
    return p


def _entry_or_exit(db: Database, day: str) -> dict:
    e = db.get(day or date.today().isoformat())
    if not e:
        print(f"❌ 没有 {day or date.today().isoformat()} 的记录,先 log", file=sys.stderr)
        raise SystemExit(1)
    return e


def run(args) -> None:
    db = _db(args)
    cfg = llm.config_from_args(args)
    force = args.mock or not cfg.get("api_key")
    cmd = args.cmd

    if cmd == "log":
        if not 0 < args.hours <= 24:
            print("❌ 时长要在 0 到 24 小时之间", file=sys.stderr)
            raise SystemExit(1)
        day = args.date or date.today().isoformat()
        db.log(args.hours, args.quality, args.dream, args.note, day)
        print(f"· 已记 {day}:{args.hours}h 质量 {args.quality}/5({tools.quality_label(args.quality)})")
    elif cmd == "seed":
        import os
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sleep-sample.json")
        with open(path, encoding="utf-8") as f:
            items = json.load(f)
        n = db.seed(items)
        print(f"· 已导入 {n} 天记录")
    elif cmd == "list":
        rows = db.list(args.limit)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        for e in rows:
            dream = f"  {tools.clamp(e['dream'], 18)}" if e["dream"] else ""
            print(f"{e['day']}  {e['hours']}h  {e['quality']}/5  {tools.quality_label(e['quality'])}{dream}")
        if not rows:
            print("还没有记录。python -m mengji log 7.5 --quality 4")
    elif cmd == "show":
        e = _entry_or_exit(db, args.day)
        print(f"{e['day']}  {e['hours']} 小时  质量 {e['quality']}/5({tools.quality_label(e['quality'])})")
        if e["note"]:
            print(f"备注:{e['note']}")
        if e["dream"]:
            print(f"梦:{e['dream']}")
    elif cmd == "analyze":
        e = _entry_or_exit(db, args.day)
        recent = [r for r in db.list(14) if r["day"] != e["day"]]
        result = agent.analyze(e, recent, cfg, force)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if force:
            print(MOCK_BANNER, file=sys.stderr)
        print(render_analyze(result))
    elif cmd == "dream":
        e = _entry_or_exit(db, args.day)
        if not e["dream"]:
            print("这天没记梦。")
            return
        result = agent.dream(e, cfg, force)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if force:
            print(MOCK_BANNER, file=sys.stderr)
        print(render_dream(result))
    elif cmd == "trend":
        days = max(3, min(60, args.days))
        start = (date.today() - timedelta(days=days - 1)).isoformat()
        rows = db.between(start, date.today().isoformat())
        result = agent.trend(rows, cfg, force, label=f"{start} 到 {date.today().isoformat()}")
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return
        if force:
            print(MOCK_BANNER, file=sys.stderr)
        print(render_trend(result))
    elif cmd == "rm":
        print("· 已删" if db.delete(args.day) else "❌ 没有这天的记录")
    elif cmd == "stats":
        print(json.dumps(db.stats(), ensure_ascii=False, indent=2))
    elif cmd == "web":
        from .web import serve
        serve(args.host, args.port, args.db, force, cfg)


def hoist_globals(argv: list[str]) -> list[str]:
    takes_value = {"--model", "--base-url", "--api-key", "--db"}
    flags = {"--mock", "--json"}
    head: list[str] = []
    rest: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in flags:
            head.append(a)
            i += 1
        elif a in takes_value and i + 1 < len(argv):
            head.extend(argv[i:i + 2])
            i += 2
        else:
            rest.append(a)
            i += 1
    return head + rest


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(hoist_globals(argv))
        run(args)
        return 0
    except llm.LLMError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    finally:
        _close_all()


if __name__ == "__main__":
    raise SystemExit(main())
