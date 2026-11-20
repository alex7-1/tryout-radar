"""Run with:  python -m unittest discover -s tests"""
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from tryout_radar import config, mdlite, notify, render, server
from tryout_radar.store import Store

ROOT = Path(__file__).resolve().parents[1]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        cfg_text = (ROOT / "config.example.toml").read_text(encoding="utf-8")
        (self.tmp / "config.toml").write_text(cfg_text, encoding="utf-8")
        self.cfg = config.load(self.tmp / "config.toml")
        self.cfg["notify"] = []
        self.store = Store(self.cfg)
        self.report = json.loads((ROOT / "examples" / "report.example.json").read_text(encoding="utf-8"))
        self.store.save_report(self.report)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class ConfigTest(Base):
    def test_paths_and_defaults(self):
        self.assertEqual(self.cfg["_data"], (self.tmp / "data").resolve())
        self.assertEqual(self.cfg["trial"]["max_per_run"], 3)
        self.assertEqual(config.project(self.cfg, "game")["trial_mode"], "assess")


class SiteTest(Base):
    def test_build_and_escape(self):
        rep = dict(self.report)
        rep["date"] = "2026-10-24"
        rep["items"] = [dict(rep["items"][0], id="evil", title="<script>alert(1)</script>", url="javascript:alert(1)")]
        self.store.save_report(rep)
        dates = render.build_site(self.cfg, self.store)
        self.assertEqual(dates, ["2026-10-24", "2026-10-23"])
        site = Path(self.cfg["_site"])
        page = (site / "2026-10-24.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", page)
        self.assertNotIn('href="javascript', page)
        self.assertEqual(page, (site / "index.html").read_text(encoding="utf-8"))

    def test_chinese_ui(self):
        self.cfg["language"] = "zh-CN"
        render.build_site(self.cfg, self.store)
        self.assertIn("交给项目试", (Path(self.cfg["_site"]) / "index.html").read_text(encoding="utf-8"))
        ok, res, _ = self.store.enqueue({"date": "2026-10-23", "id": "gh-anthropics-skills", "project": "shop"})
        self.store.finish(res["tid"], {"status": "done", "verdict": "adopt", "plain": {"headline": "能用"}})
        self.assertEqual([o["label"] for o in self.store.trial(res["tid"])["options"]], ["采纳", "先不用"])   # added choices in the UI language

    def test_markdown_is_escaped(self):
        h = mdlite.to_html("## T\n- **a** `b`\n[ok](https://x.y) [bad](javascript:alert(1))\n<img src=x onerror=1>")
        self.assertIn('<a href="https://x.y"', h)
        self.assertNotIn('href="javascript', h)
        self.assertNotIn("<img", h)


class TrialTest(Base):
    def test_queue_lifecycle(self):
        ok, res, _ = self.store.enqueue({"date": "2026-10-23", "id": "nope", "project": "shop"})
        self.assertFalse(ok)
        ok, res, _ = self.store.enqueue({"date": "2026-10-23", "id": "gh-anthropics-skills", "project": "nope"})
        self.assertFalse(ok)
        ok, res, t = self.store.enqueue({"date": "2026-10-23", "id": "gh-anthropics-skills", "project": "shop",
                                         "note": "landing <b>pages</b>"})
        self.assertTrue(ok)
        self.assertEqual(t["note"], "landing bpages/b")
        ok, dup, _ = self.store.enqueue({"date": "2026-10-23", "id": "gh-anthropics-skills", "project": "shop"})
        self.assertTrue(dup["duplicate"])
        tid = res["tid"]
        self.store.set_trial_status(tid, "running")
        self.store.finish(tid, {"status": "done", "verdict": "adopt", "summary": "works", "report_md": "## Verdict\nadopt"})
        render.build_site(self.cfg, self.store)
        self.assertTrue((Path(self.cfg["_site"]) / "trials" / f"{tid}.html").exists())
        st = self.store.public_status()["gh-anthropics-skills"][0]
        self.assertEqual((st["status"], st["verdict"]), ("done", "adopt"))

    def test_plain_report_and_decisions(self):
        ok, res, _ = self.store.enqueue({"date": "2026-10-23", "id": "gh-anthropics-skills", "project": "shop"})
        tid = res["tid"]
        self.store.finish(tid, {
            "status": "blocked", "verdict": "decide", "summary": "s", "report_md": "## Tech\n- `npm ci`",
            "plain": {"headline": "Stuck: it wants to install a plugin into your image tool", "good": ["Makes small animations"],
                      "bad": ["Untested on round characters"], "cost": "Nothing spent yet", "ask": "Install it?"},
            "options": [{"id": "game", "label": "Try it in the game instead", "action": "retarget", "project": "game"},
                        {"id": "go", "label": "Yes, install a separate copy", "action": "continue", "approval": "Owner allows a separate copy"},
                        {"id": "bad", "label": "x", "action": "rm"}]})
        t = self.store.trial(tid)
        self.assertEqual([o["id"] for o in t["options"]], ["game", "go", "close"])     # bad one dropped, a way out added
        render.build_site(self.cfg, self.store)
        page = (Path(self.cfg["_site"]) / "trials" / f"{tid}.html").read_text(encoding="utf-8")
        self.assertIn("Stuck: it wants to install", page)
        self.assertEqual(page.count('class="opt"'), 3)
        self.assertIn("<details>", page)                                                # technical layer folded
        ok, res, t, new = self.store.decide({"tid": tid, "option": "go"})
        self.assertEqual((ok, t["status"], t["approvals"][0]["text"]), (True, "queued", "Owner allows a separate copy"))
        self.assertFalse(self.store.decide({"tid": tid, "option": "go"})[0])            # one choice per report
        self.store.finish(tid, {"status": "done", "verdict": "adopt", "plain": {"headline": "Works"}})
        t = self.store.trial(tid)
        self.assertEqual([o["id"] for o in t["options"]], ["adopt", "close"])
        self.store.decide({"tid": tid, "option": "adopt"})
        self.assertEqual(self.store.set_trial_status(tid, "running")["status"], "adopting")
        ok2, r2, _ = self.store.enqueue({"date": "2026-10-23", "id": "gh-openai-codex", "project": "shop"})
        self.store.finish(r2["tid"], {"status": "blocked", "options": [
            {"id": "g", "label": "To the game", "action": "retarget", "project": "game"}]})
        ok, res, t, new = self.store.decide({"tid": r2["tid"], "option": "g"})
        self.assertEqual((t["status"], new["project"], new["status"]), ("closed", "game", "queued"))

    def test_daily_limit(self):
        self.cfg["trial"]["daily_request_limit"] = 1
        self.assertTrue(self.store.enqueue({"date": "2026-10-23", "id": "gh-anthropics-skills", "project": "shop"})[0])
        self.assertFalse(self.store.enqueue({"date": "2026-10-23", "id": "gh-openai-codex", "project": "shop"})[0])


class ServerTest(Base):
    def test_http(self):
        render.build_site(self.cfg, self.store)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(self.cfg))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{httpd.server_address[1]}/{self.cfg['server']['secret_path']}/"
        try:
            with urllib.request.urlopen(base) as r:
                self.assertIn("anthropics/skills", r.read().decode("utf-8"))
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/wrong/")
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(base + "..%2Fconfig.toml")

            def post(path, body):
                req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req) as r:
                    return json.loads(r.read())

            self.assertEqual(post("api/trial", {"date": "2026-10-23", "id": "gh-openai-codex", "project": "game"})["status"], "queued")
            self.assertEqual(post("api/feedback", {"date": "2026-10-23", "id": "gh-openai-codex", "status": "want"})["status"], "want")
            with urllib.request.urlopen(base + "api/feedback") as r:
                self.assertEqual(json.loads(r.read())["gh-openai-codex"]["status"], "want")
        finally:
            httpd.shutdown()
            httpd.server_close()


class DiscoveryTest(Base):
    def test_discover_reads_titles_and_folders_only(self):
        from tryout_radar import discover
        home = self.tmp / "home"
        proj = home / ".claude" / "projects" / "C--code-shop"
        proj.mkdir(parents=True)
        lines = [{"type": "user", "cwd": str(self.tmp / "code" / "shop"), "message": {"content": "SECRET CUSTOMER TEXT"}},
                 {"type": "custom-title", "customTitle": "Sticker pack design"}]
        (proj / "a.jsonl").write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")
        wt = home / ".claude" / "projects" / "C--code-shop-wt"
        wt.mkdir(parents=True)
        wt_cwd = json.dumps({"cwd": str(self.tmp / "code" / "shop" / ".claude" / "worktrees" / "x")})
        (wt / "b.jsonl").write_text(wt_cwd + "\n" + json.dumps({"type": "custom-title", "customTitle": "Sticker batch 2"}),
                                    encoding="utf-8")
        (wt / "c.jsonl").write_text(wt_cwd + "\n" + json.dumps({"type": "custom-title", "customTitle": "[cron] nightly"}),
                                    encoding="utf-8")
        (self.tmp / "code" / "newthing").mkdir(parents=True)
        out = discover.discover(7, [str(self.tmp / "code")], [r"^\[cron\]"], [], [], home=home)
        text = json.dumps(out)
        self.assertNotIn("SECRET CUSTOMER TEXT", text)
        ws = out["workspaces"]
        self.assertEqual(len(ws), 1)                                   # worktree folded into the project
        self.assertEqual(sorted(ws[0]["titles"]), ["Sticker batch 2", "Sticker pack design"])   # [cron] session skipped
        self.assertEqual(ws[0]["claude_sessions"], 2)
        self.assertIn(str(self.tmp / "code" / "newthing"), [f["path"] for f in out["new_folders"]])

    def test_add_ignore_and_reload(self):
        p = self.store.add_project({"key": "shop-stickers", "name": "Shop stickers", "parent": "shop",
                                    "why": "5 sessions", "trial_mode": "assess"})
        self.assertEqual(p["status"], "active")
        with self.assertRaises(ValueError):
            self.store.add_project({"key": "shop-stickers", "name": "again"})
        with self.assertRaises(ValueError):
            self.store.add_project({"key": "Bad Key", "name": "x"})
        cfg2 = config.load(self.tmp / "config.toml")
        self.assertIn("shop-stickers", config.project_names(cfg2))
        rep = dict(self.report, newProjects=[{"key": "shop-stickers", "parent": "shop", "why": "5 sessions"}])
        Store(cfg2).save_report(rep)
        render.build_site(cfg2, Store(cfg2))
        page = (Path(cfg2["_site"]) / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-key="shop-stickers"', page)
        ok, res, _ = Store(cfg2).web_ignore_project({"date": "2026-10-23", "key": "shop"})
        self.assertFalse(ok)                                           # config projects can't be ignored from the web
        ok, res, _ = Store(cfg2).web_ignore_project({"date": "2026-10-23", "key": "shop-stickers"})
        self.assertTrue(ok)
        self.assertNotIn("shop-stickers", config.project_names(config.load(self.tmp / "config.toml")))


class ManualControlTest(Base):
    def reload(self):
        self.cfg = config.load(self.tmp / "config.toml")
        self.store = Store(self.cfg)

    def test_projects_by_hand_and_switches(self):
        p = self.store.add_project({"name": "网店表情包", "path": "~/code/stickers", "interests": ["sticker generation"]},
                                   source="manual")
        self.assertRegex(p["key"], r"^p-[0-9a-f]+$")          # a Chinese name gets a generated key
        self.reload()
        self.assertEqual(config.project(self.cfg, p["key"])["source"], "manual")
        self.store.set_project_status("game", "ignored")       # a project written in config.toml
        self.reload()
        self.assertIsNone(config.project(self.cfg, "game"))
        self.assertEqual([q["key"] for q in self.cfg["_ignored_projects"]], ["game"])
        with self.assertRaises(ValueError):                    # the scout cannot bring it back
            self.store.add_project({"key": "game", "name": "Game again"})
        self.store.set_project_status("game", "active")
        self.reload()
        self.assertIsNotNone(config.project(self.cfg, "game"))

    def test_topics_by_hand(self):
        t = self.store.add_topic({"name": "Sticker packs", "keywords": "sticker generator, 表情包", "projects": ["shop"]})
        self.assertEqual((t["key"], t["github_queries"], t["projects"]), ("sticker-packs", ["sticker generator", "表情包"], ["shop"]))
        with self.assertRaises(ValueError):
            self.store.add_topic({"name": "Bad", "projects": ["nope"]})
        self.reload()
        self.assertIn("sticker-packs", config.topic_names(self.cfg))
        self.store.set_topic("sticker-packs", projects=["shop", "game"])
        self.store.set_topic("sticker-packs", status="paused")
        self.reload()
        self.assertNotIn("sticker-packs", config.topic_names(self.cfg))
        self.assertEqual(self.cfg["_paused_topics"][0]["projects"], ["shop", "game"])

    def test_publish_records_projects_and_topics(self):
        from tryout_radar import cli
        self.store.set_project_status("game", "ignored")
        self.store.add_topic({"name": "Sticker packs", "projects": ["shop"]})
        path = self.tmp / "r.json"
        path.write_text(json.dumps(dict(self.report, date="2026-10-25")), encoding="utf-8")
        cli.main(["--config", str(self.tmp / "config.toml"), "publish", str(path)])
        saved = Store(config.load(self.tmp / "config.toml")).load_report("2026-10-25")
        self.assertEqual(saved["_projects"]["game"]["status"], "ignored")
        self.assertIn({"key": "sticker-packs", "name": "Sticker packs", "focus": "", "projects": ["shop"],
                       "source": "custom", "status": "active"}, saved["_topics"])


class NotifyTest(unittest.TestCase):
    def test_chunks_and_missing_env(self):
        parts = notify.chunks("\n".join("行" * 300 for _ in range(10)), 2000)
        self.assertTrue(all(len(p.encode()) <= 2000 for p in parts))
        res = notify.send_all({"notify": [{"type": "telegram", "token_env": "NO_SUCH_VAR_X", "chat_id_env": "NO_SUCH_VAR_Y"},
                                          {"type": "nope"}]}, "hi")
        self.assertEqual([r[1] for r in res], [False, False])


if __name__ == "__main__":
    unittest.main()
