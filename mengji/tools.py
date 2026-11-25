"""本地规则:睡眠统计、质量判定、梦境母题、数字校验。"""

from __future__ import annotations

import re
import statistics

_NUM = re.compile(r"\d+(?:\.\d+)?")
_CJK = re.compile(r"[\u4e00-\u9fff]+")

MOTIFS = {
    "水": ("水", "河", "海", "雨", "游泳", "淹"),
    "飞": ("飞", "飘", "腾空"),
    "坠落": ("掉下", "坠落", "摔", "悬崖"),
    "被追": ("追", "逃", "跑不"),
    "考试": ("考试", "考场", "试卷", "迟到"),
    "亲人": ("妈妈", "爸爸", "奶奶", "爷爷", "家人", "外婆"),
    "牙齿": ("牙", "掉牙"),
    "迷路": ("迷路", "找不到", "走不出去"),
}

MOTIF_NOTE = {
    "水": "梦里常和情绪起伏联系在一起,不必当成预兆",
    "飞": "多出现在压力释放或想脱身的阶段",
    "坠落": "常见于身体突然放松或白天有过失重感",
    "被追": "多和白天没处理完的事有关",
    "考试": "典型的表现焦虑母题,和真实考试未必相关",
    "亲人": "常出现在想念或需要支撑的时候",
    "牙齿": "常见于咬牙、磨牙或口腔不适之后",
    "迷路": "多和方向感、选择焦虑有关",
}

QUALITY_WORDS = ("很沉", "一夜没醒", "醒了几次", "翻来覆去", "睡得浅", "多梦", "早醒", "起不来")


def numbers(text: str) -> list[str]:
    return _NUM.findall(text or "")


def new_numbers(before: str, after: str) -> list[str]:
    old = set(numbers(before))
    return [n for n in numbers(after) if n not in old]


def contains_quote(quote: str, text: str, min_len: int = 6) -> bool:
    return len(quote or "") >= min_len and quote in (text or "")


def clamp(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def quality_label(q: int) -> str:
    return {1: "很差", 2: "偏差", 3: "一般", 4: "不错", 5: "很好"}.get(int(q), "一般")


def hours_flag(hours: float) -> str:
    if hours < 6:
        return "偏少"
    if hours > 9.5:
        return "偏多"
    return "在常见区间"


def analyze_one(entry: dict) -> dict:
    hours = float(entry.get("hours") or 0)
    q = int(entry.get("quality") or 3)
    notes = [w for w in QUALITY_WORDS if w in (entry.get("note") or "")]
    flags = []
    if hours < 6:
        flags.append("时长偏少,先看是不是睡得太晚")
    elif hours > 9.5:
        flags.append("时长偏多,留意白天是否仍然犯困")
    if q <= 2:
        flags.append("自评质量偏低,记录里写清楚醒了几次")
    if notes:
        flags.append("记录里提到:" + "、".join(notes))
    return {"hours": hours, "quality": q, "label": quality_label(q),
            "hours_flag": hours_flag(hours), "flags": flags, "note_words": notes}


def motif_list(dream: str) -> list[str]:
    hits = []
    for name, keys in MOTIFS.items():
        if any(k in (dream or "") for k in keys):
            hits.append(name)
    return hits


def dream_read(dream: str) -> list[dict]:
    return [{"motif": m, "note": MOTIF_NOTE[m]} for m in motif_list(dream)]


def trend(entries: list[dict]) -> dict:
    if not entries:
        return {"count": 0}
    hours = [float(e["hours"]) for e in entries]
    qual = [int(e["quality"]) for e in entries]
    best = max(entries, key=lambda e: (int(e["quality"]), float(e["hours"])))
    worst = min(entries, key=lambda e: (int(e["quality"]), float(e["hours"])))
    low_runs = 0
    cur = 0
    for e in entries:
        if float(e["hours"]) < 6 or int(e["quality"]) <= 2:
            cur += 1
            low_runs = max(low_runs, cur)
        else:
            cur = 0
    return {
        "count": len(entries),
        "avg_hours": round(statistics.fmean(hours), 2),
        "min_hours": min(hours), "max_hours": max(hours),
        "stdev": round(statistics.pstdev(hours), 2) if len(hours) > 1 else 0.0,
        "avg_quality": round(statistics.fmean(qual), 2),
        "best": best["day"], "worst": worst["day"],
        "low_runs": low_runs,
        "dream_count": sum(1 for e in entries if e.get("dream")),
    }


def trend_text(t: dict) -> str:
    if not t.get("count"):
        return "还没有记录,先连续记三天再看趋势。"
    lines = [f"{t['count']} 天平均睡 {t['avg_hours']} 小时,质量均分 {t['avg_quality']}/5",
             f"最短 {t['min_hours']}({t['worst']}),最长 {t['max_hours']}({t['best']})"]
    if t["count"] < 3:
        lines.append("样本不到三天,还看不出连续段")
    elif t["low_runs"] >= 3:
        lines.append(f"有连续 {t['low_runs']} 天偏少或质量偏低,值得当成一件事来看")
    else:
        lines.append("没有连续三天以上的低谷")
    return "\n".join(lines)


TOOLS = [
    {"name": "recent_sleep", "desc": "读取最近若干天的睡眠记录"},
    {"name": "trend_stats", "desc": "读取本地算好的时长与质量统计"},
]


def execute(name: str, ctx: dict) -> dict:
    if name == "recent_sleep":
        return {"entries": ctx.get("recent", [])}
    if name == "trend_stats":
        return trend(ctx.get("entries", []))
    return {"error": f"未知工具:{name}"}
