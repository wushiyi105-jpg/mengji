"""Web 入口:http.server 零依赖,单页两个页签。"""

from __future__ import annotations

import json
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import agent, tools
from .db import Database

PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>梦记 · 睡眠记录</title>
<style>
:root{--bg:#0e0f1a;--card:#181a2b;--line:#2a2d45;--text:#e8e9f5;--dim:#8f93b3;--accent:#8f7cf0;--warn:#e5b45c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.7 "Segoe UI","Microsoft YaHei",sans-serif}
.wrap{max-width:940px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 4px}.sub{color:var(--dim);font-size:13px;margin-bottom:18px}
.tabs{display:flex;gap:8px;margin-bottom:18px}
.tab{padding:7px 14px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--dim);cursor:pointer}
.tab.on{color:#fff;background:var(--accent);border-color:var(--accent)}
.panel{display:none}.panel.on{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}
label{display:block;font-size:13px;color:var(--dim);margin:10px 0 6px}
input,textarea,select{width:100%;background:#0b0d16;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:10px;font:14px/1.6 inherit}
textarea{min-height:90px;resize:vertical}
.row{display:flex;gap:10px}.row>*{flex:1}
button.go{margin-top:12px;background:var(--accent);color:#fff;border:0;border-radius:8px;padding:10px 18px;font-weight:600;cursor:pointer}
button.go:disabled{opacity:.55;cursor:wait}
button.ghost{background:#262a3f;color:var(--text)}
pre{white-space:pre-wrap;word-break:break-word;background:#0b0d16;border:1px solid var(--line);border-radius:8px;padding:14px;min-height:90px;font:13px/1.65 "Cascadia Mono",monospace}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:500}
.badge{display:inline-block;font-size:12px;padding:2px 8px;border-radius:999px;border:1px solid var(--line);color:var(--dim);margin-left:8px}
.badge.off{color:var(--accent);border-color:var(--accent)}
</style></head><body><div class="wrap">
<h1>梦记 · 睡眠记录<span id="status" class="badge">…</span></h1>
<div class="sub">记时长、自评质量、梦。统计本地算,解释交给模型,梦只当联想看。</div>
<div class="tabs">
  <button class="tab on" data-tab="day">记录与单日</button>
  <button class="tab" data-tab="trend">趋势</button>
</div>

<div class="panel on" id="day">
  <div class="card">
    <div class="row">
      <div><label>日期</label><input id="day" type="date"></div>
      <div><label>睡了几个小时</label><input id="hours" type="number" step="0.1" min="0" max="24" value="7.5"></div>
      <div><label>质量 1–5</label><input id="quality" type="number" min="1" max="5" value="3"></div>
    </div>
    <label>备注(醒了几次、睡前做了什么)</label><input id="note" placeholder="两点才睡,中间醒了一次">
    <label>梦</label><textarea id="dream" placeholder="梦到在考试,试卷发下来一个字都看不懂……"></textarea>
    <button class="go" id="btnLog">记下来</button>
    <button class="go ghost" id="btnAnalyze">分析这一天</button>
    <button class="go ghost" id="btnDream">读这个梦</button>
  </div>
  <div class="card"><pre id="outDay">结果会出现在这里。</pre></div>
  <div class="card"><table><thead><tr><th>日期</th><th>时长</th><th>质量</th><th>梦</th></tr></thead>
  <tbody id="listBody"><tr><td colspan="4">读取中…</td></tr></tbody></table></div>
</div>

<div class="panel" id="trend">
  <div class="card">
    <div class="row"><div><label>看最近多少天</label>
    <select id="days"><option value="7">7 天</option><option value="14" selected>14 天</option><option value="30">30 天</option></select></div></div>
    <button class="go" id="btnTrend">看趋势</button>
  </div>
  <div class="card"><pre id="outTrend">还没有算。</pre></div>
</div>
</div>
<script>
const $=s=>document.querySelector(s);
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===t));
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',p.id===t.dataset.tab));
});
function loading(btn,on){
  if(on){btn.dataset.label=btn.dataset.label||btn.textContent;btn.disabled=true;btn.textContent='处理中…';}
  else{btn.disabled=false;btn.textContent=btn.dataset.label||btn.textContent;}
}
async function api(path,opt){
  const r=await fetch(path,opt);const j=await r.json();
  if(!r.ok||j.error)throw new Error(j.error||('HTTP '+r.status));
  return j;
}
function today(){const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
async function loadList(){
  try{
    const rows=await api('/api/entries');
    $('#listBody').innerHTML=rows.map(e=>`<tr><td>${e.day}</td><td>${e.hours}h</td><td>${e.quality}/5</td>
      <td>${e.dream||''}</td></tr>`).join('')||'<tr><td colspan="4">还没有记录</td></tr>';
  }catch(e){$('#listBody').innerHTML='<tr><td colspan="4">读取失败</td></tr>';}
}
$('#btnLog').onclick=async()=>{
  const btn=$('#btnLog');loading(btn,true);
  try{
    const r=await api('/api/log',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({day:$('#day').value,hours:Number($('#hours').value),quality:Number($('#quality').value),
        note:$('#note').value,dream:$('#dream').value})});
    $('#outDay').textContent=r.text;await loadList();
  }catch(e){$('#outDay').textContent='出错:'+e.message;}
  finally{loading(btn,false);}
};
$('#btnAnalyze').onclick=async()=>{
  const btn=$('#btnAnalyze');loading(btn,true);
  try{
    const r=await api('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({day:$('#day').value})});
    $('#outDay').textContent=r.text;
  }catch(e){$('#outDay').textContent='出错:'+e.message;}
  finally{loading(btn,false);}
};
$('#btnDream').onclick=async()=>{
  const btn=$('#btnDream');loading(btn,true);
  try{
    const r=await api('/api/dream',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({day:$('#day').value})});
    $('#outDay').textContent=r.text;
  }catch(e){$('#outDay').textContent='出错:'+e.message;}
  finally{loading(btn,false);}
};
$('#btnTrend').onclick=async()=>{
  const btn=$('#btnTrend');loading(btn,true);
  try{
    const r=await api('/api/trend?days='+$('#days').value);
    $('#outTrend').textContent=r.text;
  }catch(e){$('#outTrend').textContent='出错:'+e.message;}
  finally{loading(btn,false);}
};
(async()=>{
  $('#day').value=today();
  try{
    const s=await api('/api/status');
    const b=$('#status');b.textContent=s.offline?'离线模式':'模型 '+s.model;b.classList.toggle('off',s.offline);
  }catch(e){$('#status').textContent='读取失败';}
  await loadList();
})();
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    db: Database
    cfg: dict
    force_mock: bool

    def log_message(self, *args):
        pass

    def _json(self, data, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk", errors="replace")
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if path == "/":
            self._html(PAGE)
            return
        if path == "/api/status":
            self._json({"mode": "offline" if self.force_mock else "model",
                        "model": self.cfg.get("model", ""), "offline": self.force_mock})
            return
        if path == "/api/entries":
            self._json(self.db.list())
            return
        if path == "/api/entry":
            day = (qs.get("day") or [""])[0]
            e = self.db.get(day)
            if not e:
                self._json({"error": "没有这天的记录"}, 404)
                return
            e["one"] = tools.analyze_one(e)
            self._json(e)
            return
        if path == "/api/trend":
            days = max(3, min(60, int((qs.get("days") or ["14"])[0])))
            start = (date.today() - timedelta(days=days - 1)).isoformat()
            rows = self.db.between(start, date.today().isoformat())
            t = tools.trend(rows)
            self._json({"stats": t, "text": tools.trend_text(t), "days": days})
            return
        self._json({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        data = self._read_json()
        try:
            if path == "/api/log":
                self._log(data)
            elif path == "/api/analyze":
                self._analyze(data)
            elif path == "/api/dream":
                self._dream(data)
            elif path == "/api/delete":
                self._json({"deleted": self.db.delete(str(data.get("day", "")))})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)}, 502)

    def _log(self, data: dict):
        from .cli import render_analyze
        try:
            hours = float(data.get("hours") or 0)
            quality = int(data.get("quality") or 3)
        except (TypeError, ValueError):
            self._json({"error": "时长或质量格式不对"}, 400)
            return
        if not 0 < hours <= 24:
            self._json({"error": "时长要在 0 到 24 小时之间"}, 400)
            return
        quality = max(1, min(5, quality))
        day = str(data.get("day") or date.today().isoformat())
        self.db.log(hours, quality, str(data.get("dream", "")), str(data.get("note", "")), day)
        entry = self.db.get(day)
        recent = [r for r in self.db.list(14) if r["day"] != day]
        insight = agent.analyze(entry, recent, self.cfg, self.force_mock)
        result = {"day": day, "hours": hours, "quality": quality, "label": tools.quality_label(quality),
                  "text": render_analyze(insight), "insight": insight}
        self._json(result)

    def _analyze(self, data: dict):
        from .cli import render_analyze
        day = str(data.get("day") or date.today().isoformat())
        entry = self.db.get(day)
        if not entry:
            self._json({"error": "先记这一天的睡眠"}, 400)
            return
        recent = [r for r in self.db.list(14) if r["day"] != day]
        result = agent.analyze(entry, recent, self.cfg, self.force_mock)
        result["text"] = render_analyze(result)
        self._json(result)

    def _dream(self, data: dict):
        from .cli import render_dream
        day = str(data.get("day") or date.today().isoformat())
        entry = self.db.get(day)
        if not entry:
            self._json({"error": "先记这一天的睡眠"}, 400)
            return
        if not entry.get("dream"):
            self._json({"error": "这天没记梦"}, 400)
            return
        result = agent.dream(entry, self.cfg, self.force_mock)
        result["text"] = render_dream(result)
        self._json(result)


def _make_handler(db: Database, cfg: dict, force_mock: bool):
    return type("Handler", (_Handler,), {"db": db, "cfg": cfg, "force_mock": force_mock})


def serve(host: str = "127.0.0.1", port: int = 8774, db_path: str = "data/mengji.db",
          force_mock: bool = False, cfg: dict | None = None):
    from . import llm
    db = Database(db_path)
    cfg = dict(llm.default_config() if cfg is None else cfg)
    if not cfg.get("api_key"):
        force_mock = True
    httpd = ThreadingHTTPServer((host, port), _make_handler(db, cfg, force_mock))
    print(f"🌙 梦记已启动  http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n· 已停止")
    finally:
        httpd.server_close()
        db.close()
