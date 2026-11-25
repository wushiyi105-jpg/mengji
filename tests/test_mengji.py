"""梦记离线单测:不联网、不花 token。"""

from __future__ import annotations

import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mengji import agent, cli, mock, tools, web
from mengji.db import Database

ROOT = os.path.dirname(os.path.dirname(__file__))
SAMPLE = json.load(open(os.path.join(ROOT, "data", "sleep-sample.json"), encoding="utf-8"))


def day(offset: int = 0) -> str:
    return (date.today() - timedelta(days=offset)).isoformat()


class TestTools(unittest.TestCase):
    def test_quality_label(self):
        self.assertEqual(tools.quality_label(1), "很差")
        self.assertEqual(tools.quality_label(9), "一般")

    def test_hours_flag(self):
        self.assertEqual(tools.hours_flag(5.5), "偏少")
        self.assertEqual(tools.hours_flag(10), "偏多")
        self.assertEqual(tools.hours_flag(7.5), "在常见区间")

    def test_analyze_one_flags(self):
        r = tools.analyze_one({"hours": 5, "quality": 2, "note": "翻来覆去"})
        self.assertEqual(r["label"], "偏差")
        self.assertTrue(any("偏少" in f for f in r["flags"]))

    def test_motifs(self):
        self.assertIn("水", tools.motif_list("梦见在水里游"))
        self.assertIn("考试", tools.motif_list("梦到在考试"))

    def test_dream_read_notes(self):
        reads = tools.dream_read("被人追着跑")
        self.assertEqual(reads[0]["motif"], "被追")
        self.assertIn("白天", reads[0]["note"])

    def test_trend_stats(self):
        entries = [{"day": day(2), "hours": 5, "quality": 2, "dream": ""},
                   {"day": day(1), "hours": 7, "quality": 3, "dream": "水"},
                   {"day": day(0), "hours": 8, "quality": 4, "dream": ""}]
        t = tools.trend(entries)
        self.assertEqual(t["count"], 3)
        self.assertEqual(t["avg_hours"], 6.67)
        self.assertEqual(t["low_runs"], 1)
        self.assertEqual(t["dream_count"], 1)

    def test_trend_text_short(self):
        t = tools.trend([{"day": day(), "hours": 6, "quality": 2}])
        self.assertIn("样本不到三天", tools.trend_text(t))

    def test_new_numbers(self):
        self.assertEqual(tools.new_numbers("7 小时", "7 小时,平均 5.2"), ["5.2"])


class BaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Database(os.path.join(self.tmp.name, "t.db"))
        self.db.log(6, 2, "梦到在考试", "一点才睡", day(1))
        self.db.log(8, 4, "梦见在水里游", "", day(0))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()


class TestDb(BaseCase):
    def test_upsert_same_day(self):
        self.db.log(7, 3, "", "", day(0))
        self.assertEqual(self.db.get(day(0))["hours"], 7.0)
        self.assertEqual(self.db.stats()["entries"], 2)

    def test_between(self):
        rows = self.db.between(day(3), day(0))
        self.assertEqual(len(rows), 2)

    def test_delete(self):
        self.assertTrue(self.db.delete(day(1)))
        self.assertFalse(self.db.delete(day(1)))

    def test_seed(self):
        self.assertEqual(self.db.seed(SAMPLE), 10)
        self.assertEqual(self.db.stats()["dreams"], 4)


class TestOffline(BaseCase):
    def test_mock_analyze(self):
        r = mock.analyze(self.db.get(day(1)), [])
        self.assertTrue(r["offline"])
        self.assertTrue(r["advice"])

    def test_mock_dream(self):
        r = mock.dream(self.db.get(day(1)))
        self.assertIn("考试", r["motifs"])

    def test_mock_dream_empty(self):
        self.db.log(7, 3, "", "", day(2))
        r = mock.dream(self.db.get(day(2)))
        self.assertIn("没记梦", r["reading"])

    def test_agent_trend_offline(self):
        r = agent.trend(self.db.list(), {"api_key": ""}, True)
        self.assertTrue(r["offline"])
        self.assertIn("平均睡", r["text"])


class TestVerify(unittest.TestCase):
    def test_analyze_drops_invented_number(self):
        entry = {"day": day(), "hours": 7, "quality": 3, "note": "十一点睡", "dream": ""}
        body, problems = agent.verify_analyze(entry, [], {
            "summary": "睡了 7 小时,深睡只有 40 分钟", "factors": ["下午喝了咖啡"],
            "advice": ["提前 80 分钟上床", "固定起床时间"],
        })
        self.assertEqual(body["summary"], "")
        self.assertEqual(body["advice"], ["固定起床时间"])
        self.assertTrue(problems)

    def test_dream_drops_fake_motif(self):
        body, problems = agent.verify_dream("梦见在水里游", {
            "motifs": ["水", "亲人"], "reading": "可能和情绪有关",
        })
        self.assertEqual(body["motifs"], ["水"])
        self.assertTrue(problems)


    def test_dream_maps_alias_to_motif(self):
        body, _ = agent.verify_dream("梦见在考试,试卷上一个字都看不懂",
                                     {"motifs": ["试卷", "考试"], "reading": "可能和压力有关"})
        self.assertEqual(body["motifs"], ["考试"])


class TestCli(BaseCase):
    def _run(self, argv, db_path):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--db", db_path] + argv)
        return buf.getvalue()

    def test_seed_list_analyze_dream_trend(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        db_path = os.path.join(tmp.name, "c.db")
        self.assertIn("已导入 10 天", self._run(["seed"], db_path))
        self.assertIn("7.5h", self._run(["list"], db_path))
        out = self._run(["analyze", day(1), "--mock"], db_path)
        self.assertIn("离线模式", out)
        self.assertIn("可能的影响", out)
        dream = self._run(["dream", day(2), "--mock"], db_path)
        self.assertIn("母题", dream)
        self.assertIn("不是解梦", dream)
        trend = self._run(["trend", "--days", "14", "--mock"], db_path)
        self.assertIn("平均睡", trend)
        self.assertIn("已删", self._run(["rm", day(1)], db_path))
        tmp.cleanup()


class TestWeb(BaseCase):
    def test_log_analyze_dream(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), web._make_handler(self.db, {"api_key": ""}, True))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        try:
            bad = Request(base + "/api/analyze", data=json.dumps({"day": day(5)}).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
            with self.assertRaises(HTTPError) as ctx:
                urlopen(bad, timeout=15)
            self.assertEqual(ctx.exception.code, 400)
            logreq = Request(base + "/api/log",
                             data=json.dumps({"day": day(3), "hours": 5.5, "quality": 2,
                                              "note": "四点才睡", "dream": "梦到在水里" }).encode("utf-8"),
                             headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(logreq, timeout=20) as resp:
                r = json.loads(resp.read().decode("utf-8"))
            self.assertIn("值得注意", r["text"])
            areq = Request(base + "/api/analyze", data=json.dumps({"day": day(3)}).encode("utf-8"),
                           headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(areq, timeout=20) as resp:
                self.assertIn("advice", json.loads(resp.read().decode("utf-8")))
            dreq = Request(base + "/api/dream", data=json.dumps({"day": day(3)}).encode("utf-8"),
                           headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(dreq, timeout=20) as resp:
                self.assertIn("母题", json.loads(resp.read().decode("utf-8"))["text"])
        finally:
            httpd.shutdown()
            httpd.server_close()


if __name__ == "__main__":
    unittest.main()
