"""离线模式:统计照算,解释只做模板;解梦明确标成文化联想。"""

from __future__ import annotations

from . import tools

WINDOWS = (
    ("咖啡", "下午的咖啡因可能把入睡往后推"),
    ("茶", "下午的茶同样可能拖后入睡"),
    ("手机", "睡前看手机可能让脑子停不下来"),
    ("屏幕", "睡前看屏幕可能让脑子停不下来"),
    ("装修", "环境噪音可能把睡眠切碎"),
    ("吵", "环境噪音可能把睡眠切碎"),
    ("醒", "夜里醒过,睡眠被切成几段"),
    ("才睡", "入睡时间偏晚,时长被压短"),
)


def analyze(entry: dict, recent: list[dict] | None = None) -> dict:
    one = tools.analyze_one(entry)
    note = entry.get("note") or ""
    factors = [why for key, why in WINDOWS if key in note][:3]
    if not factors and one["quality"] <= 2:
        factors = ["自评质量偏低,但记录里没写清原因"]
    advice = []
    if one["hours"] < 6:
        advice.append("比平时提前 30 分钟上床,先固定起床时间")
    if one["quality"] <= 2:
        advice.append("睡前两小时不喝咖啡与酒,醒的次数记下来")
    if tools.motif_list(entry.get("dream") or ""):
        advice.append("梦多到影响白天的状态时,把梦境写下来再看它是不是重复")
    advice.append("本周先连续记 3 天,再看趋势,一天说明不了什么")
    return {
        "score": one["quality"], "label": one["label"], "hours_flag": one["hours_flag"],
        "flags": one["flags"], "factors": factors, "advice": advice[:4], "offline": True,
        "note": "离线模式:只按时长与自评质量给规则判断,不解释睡眠障碍",
    }


def trend(entries: list[dict]) -> dict:
    t = tools.trend(entries)
    return {"stats": t, "text": tools.trend_text(t), "offline": True,
            "note": "离线模式:数字全是本地算的,结论按阈值给"}


def dream(entry: dict) -> dict:
    dream = entry.get("dream") or ""
    if not dream:
        return {"motifs": [], "notes": [], "reading": "这天没记梦。", "offline": True,
                "note": "离线模式:没有梦境文本可读"}
    reads = tools.dream_read(dream)
    motifs = [r["motif"] for r in reads]
    return {
        "motifs": motifs,
        "notes": [r["note"] for r in reads],
        "reading": "梦里出现了" + "、".join(motifs) + "这些母题。" if motifs else "没认出常见母题。",
        "offline": True,
        "note": "离线模式:只按母题表给文化联想,不是解梦,更不是诊断",
    }
