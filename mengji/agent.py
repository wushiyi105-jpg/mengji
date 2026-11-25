"""模型主路径:单日分析、趋势综述、梦境联想。"""

from __future__ import annotations

import json

from . import llm, mock, tools

MAX_STEPS = 12

ANALYZE_SYSTEM = """你在帮人复盘一天的睡眠,只依据记录说话。

规则:
1. 只输出 JSON。
2. summary 不超过 100 字,说明今天这觉的关键点,不许下医学结论。
3. factors 最多 3 条,每条不超过 50 字,写可能影响这觉的因素,用"可能"。
4. advice 最多 4 条,每条不超过 50 字,是今晚或本周能做的动作。
5. 数字只能取记录或本地统计里已有的,不许自己算新数字。
6. 不诊断失眠、睡眠呼吸暂停等疾病,需要时建议就医。

JSON 模板:
{"summary": "...", "factors": ["..."], "advice": ["..."]}"""

TREND_SYSTEM = """你在帮人看一段时间的睡眠趋势。

可用工具:
- recent_sleep: 读取最近记录
- trend_stats: 读取本地算好的统计

每一步只输出一个 JSON 对象,二选一:
{"tool": "trend_stats", "args": {}}
{"final": {"summary": "..."}}

final 规则:
- summary 不超过 90 字,只能引用统计里已有的数字。
- 不诊断疾病,不给药物建议。

【区间】__RANGE__"""

DREAM_SYSTEM = """你在帮人读一个梦,只做文化联想。

规则:
1. 只输出 JSON。
2. motifs 列出梦里确实出现的母题词,没出现的不许编;最多 3 个。
3. reading 不超过 120 字,用"可能""常和……有关"这样的说法。
4. 明确说明这不是解梦也不是心理诊断。
5. 不预言吉凶,不给医疗建议。

JSON 模板:
{"motifs": ["水"], "reading": "...", "disclaimer": "..."}"""


def _use_model(cfg) -> bool:
    return bool((cfg or {}).get("api_key"))


def _allowed(entry: dict, recent: list[dict]) -> str:
    parts = [str(entry.get(k, "")) for k in ("hours", "quality", "note", "dream", "day")]
    for e in recent[:14]:
        parts.extend(str(e.get(k, "")) for k in ("hours", "quality", "note", "dream", "day"))
    if recent:
        t = tools.trend(recent)
        parts.extend(str(t.get(k, "")) for k in
                     ("count", "avg_hours", "min_hours", "max_hours", "stdev", "avg_quality", "low_runs"))
    return " ".join(parts)


def verify_analyze(entry: dict, recent: list[dict], data: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    src = _allowed(entry, recent)
    summary = tools.clamp(str(data.get("summary", "")), 100)
    if summary and tools.new_numbers(src, summary):
        problems.append("摘要里出现记录外的数字,已清空")
        summary = ""
    factors = []
    for f in data.get("factors") or []:
        f = tools.clamp(str(f), 50)
        if tools.new_numbers(src, f):
            problems.append(f"「{f}」用了记录外的数字,已丢弃")
            continue
        factors.append(f)
    advice = []
    for a in data.get("advice") or []:
        a = tools.clamp(str(a), 50)
        if tools.new_numbers(src, a):
            problems.append(f"「{a}」用了记录外的数字,已丢弃")
            continue
        advice.append(a)
    return {"summary": summary, "factors": factors[:3], "advice": advice[:4]}, problems


def verify_dream(dream: str, data: dict) -> tuple[dict, list[str]]:
    problems: list[str] = []
    motifs = []
    for m in data.get("motifs") or []:
        m = tools.clamp(str(m), 8)
        key = m
        if m not in tools.MOTIFS:
            key = next((k for k, words in tools.MOTIFS.items() if m in words), "")
        words = tools.MOTIFS.get(key, ())
        if key and any(w in dream for w in words) and key not in motifs:
            motifs.append(key)
        else:
            problems.append(f"母题「{m}」在梦里找不到,已丢弃")
    reading = tools.clamp(str(data.get("reading", "")), 120)
    disclaimer = tools.clamp(str(data.get("disclaimer", "")), 40) or "文化联想,不是解梦,也不是诊断"
    return {"motifs": motifs[:3], "reading": reading, "disclaimer": disclaimer}, problems


def analyze(entry: dict, recent: list[dict], cfg: dict | None = None,
            force_mock: bool = False) -> dict:
    if force_mock or not _use_model(cfg):
        return mock.analyze(entry, recent)
    one = tools.analyze_one(entry)
    user = (f"【今天】{entry.get('day', '')} 睡了 {entry.get('hours')} 小时,"
            f"自评 {entry.get('quality')}/5({one['label']})\n"
            f"【备注】{entry.get('note', '') or '(无)'}\n"
            f"【梦】{entry.get('dream', '') or '(无)'}\n"
            f"【最近】" + ";".join(f"{e['day']} {e['hours']}h q{e['quality']}" for e in recent[:7]))
    text = llm.chat(
        [{"role": "system", "content": ANALYZE_SYSTEM}, {"role": "user", "content": user}],
        cfg, temperature=0.3, max_tokens=1000,
    )
    data = llm.extract_json(text)
    body, problems = verify_analyze(entry, recent, data if isinstance(data, dict) else {})
    if not body["summary"]:
        body["summary"] = f"睡了 {entry.get('hours')} 小时,自评{one['label']}。"
    body.update({"label": one["label"], "hours_flag": one["hours_flag"], "flags": one["flags"],
                 "problems": problems, "offline": False})
    return body


def trend(entries: list[dict], cfg: dict | None = None, force_mock: bool = False,
          label: str = "") -> dict:
    t = tools.trend(entries)
    if force_mock or not _use_model(cfg) or not entries:
        return mock.trend(entries)
    ctx = {"entries": entries, "recent": entries}
    system = TREND_SYSTEM.replace("__RANGE__", label or "最近记录")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": f"共 {len(entries)} 条记录,请先取统计再写综述。"}]
    final: dict | None = None
    for _ in range(MAX_STEPS):
        text = llm.chat(messages, cfg, temperature=0.3, max_tokens=900)
        try:
            obj = llm.extract_json(text)
        except llm.LLMError:
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "只输出一个 JSON 对象。"})
            continue
        if isinstance(obj, dict) and obj.get("tool"):
            result = tools.execute(str(obj["tool"]), ctx)
            messages.append({"role": "assistant", "content": text})
            messages.append({"role": "user", "content": "工具返回:" + json.dumps(result, ensure_ascii=False)})
            continue
        if isinstance(obj, dict) and isinstance(obj.get("final"), dict):
            final = obj["final"]
            break
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": '要么 {"tool": ...},要么 {"final": {"summary": ...}}。'})
    summary = tools.clamp(str((final or {}).get("summary", "")), 90)
    problems = []
    src = " ".join(str(v) for e in entries for v in e.values()) + " " + \
        " ".join(str(t.get(k, "")) for k in ("count", "avg_hours", "min_hours", "max_hours", "stdev", "avg_quality"))
    if summary and tools.new_numbers(src, summary):
        problems.append("综述里出现统计外的数字,改用本地结论")
        summary = ""
    if not summary:
        summary = tools.trend_text(t)
    return {"stats": t, "text": tools.trend_text(t), "summary": summary,
            "problems": problems, "offline": False}


def dream(entry: dict, cfg: dict | None = None, force_mock: bool = False) -> dict:
    if force_mock or not _use_model(cfg):
        return mock.dream(entry)
    text = llm.chat(
        [{"role": "system", "content": DREAM_SYSTEM},
         {"role": "user", "content": f"【梦】{entry.get('dream', '')}"}],
        cfg, temperature=0.4, max_tokens=800,
    )
    data = llm.extract_json(text)
    body, problems = verify_dream(entry.get("dream", ""), data if isinstance(data, dict) else {})
    body.update({"problems": problems, "offline": False})
    return body
