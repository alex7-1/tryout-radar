"""Build the static site: index.html (latest digest), <date>.html per day, trials/<tid>.html per trial report.

Pages work as plain static files. When served by `tryout_radar serve`, buttons on each item let the owner
mark it (want / using / not relevant) and send it to a project for a trial; without the server the
buttons hide themselves. All text from reports is HTML-escaped; only http(s) links are rendered."""
import html
import json
import os
import re
from datetime import date
from pathlib import Path

from . import mdlite
from .config import project_names, topic_names

STRINGS = {
    "en": {
        "weekday": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "generated": "Generated", "github": "GitHub scanned", "x": "X scanned", "x_browser": " (browser)",
        "x_search": " (web search)", "items": "items", "picks": "Look at these first", "tips": "Tips for your coding agents",
        "followups": "Updates on things you marked", "effort": "Effort", "caution": "Caution", "unverified": "link not verified",
        "verdict": {"try": "Try now", "save": "Save", "watch": "Watch"},
        "fit": "fit", "try_btn": "Try it in a project", "send": "Send", "cancel": "Cancel",
        "note_ph": "What should it help with? (optional)", "sending": "Sending…", "send_fail": "Not sent. Try again later.",
        "again": "Try in another project", "queued_msg": "Queued. Trials run at {when}.",
        "fb": {"want": "Want to try", "done": "Using it", "skip": "Not relevant"},
        "status": {"queued": "queued", "running": "running", "done": "report ready", "blocked": "needs your decision",
                   "failed": "failed", "closed": "closed", "adopt-requested": "to be adopted", "adopting": "being merged",
                   "adopted": "adopted"},
        "good": "What is useful", "bad": "What does not fit", "cost": "Cost", "ask": "Your call",
        "tech": "Technical details (for whoever adopts it)", "chose": "You chose “{label}” ({at}).",
        "follow": {"continue": "The trial runner continues as you chose at its next run.",
                   "retarget": "Moved to another project; it is tried at the next run.", "close": "This trial ends here.",
                   "adopt": "The trial runner merges it locally at its next run and reports back."},
        "decided": {"continue": "Got it: continues at the next trial run.", "retarget": "Got it: moved to {project}.",
                    "close": "Got it: this trial ends here.", "adopt": "Got it: it is merged at the next trial run."},
        "tverdict": {"adopt": "adopt", "reject": "don't use", "decide": "your call"},
        "footer": "Press “Try it in a project” on anything that looks useful. At {when} the trial runner installs it in a "
                  "sandbox branch of that project, runs it with the project's tests and sends you a report.",
        "empty": "No digest yet. The first one appears after the scout's first run.",
        "back": "Back to {date}", "report": "Trial report", "requested": "Requested", "finished": "Finished",
        "branch": "Branch", "wanted_for": "Wanted for", "source": "Source",
        "adopt_hint": "To adopt it, ask your agent to “adopt trial {tid}”. It merges using the project's own process. "
                      "The sandbox and branch stay on the trial machine until then.",
        "trial_mode_assess": "read-only assessment",
        "new_projects": "New directions spotted",
        "new_projects_sub": "You have been working on these lately in your coding agents. The scout has started looking for "
                            "tools for them, and you can send items to them. Not needed? Stop following.",
        "part_of": "part of", "ignore": "Stop following", "ignored": "Not following any more",
        "ignored_msg": "**Stopped following “{name}”**\nThe scout will no longer look for tools for it.",
    },
    "zh-CN": {
        "weekday": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"],
        "generated": "生成于", "github": "GitHub 扫描", "x": "X 扫描", "x_browser": "（浏览器）", "x_search": "（网页搜索）",
        "items": "条入选", "picks": "今天先看这几个", "tips": "Claude Code / Codex 用法", "followups": "你标记过的，有新动静",
        "effort": "上手", "caution": "注意", "unverified": "链接未核实",
        "verdict": {"try": "马上试", "save": "收藏", "watch": "观察"},
        "fit": "契合度", "try_btn": "交给项目试", "send": "发送", "cancel": "取消", "note_ph": "想用在哪个功能（可不写）",
        "sending": "发送中…", "send_fail": "没发出去，等会儿再点", "again": "再交给别的项目", "queued_msg": "已排队，{when} 开始试",
        "fb": {"want": "想试", "done": "用上了", "skip": "不相关"},
        "status": {"queued": "排队中", "running": "试用中", "done": "已出报告", "blocked": "要你决定", "failed": "没试成",
                   "closed": "已结束", "adopt-requested": "要采纳，下次合并", "adopting": "正在合并", "adopted": "已采纳"},
        "good": "对你有用的", "bad": "不合适的地方", "cost": "花费", "ask": "要你决定",
        "tech": "技术细节（给技术人员看，采纳时用）", "chose": "你选了「{label}」（{at}）。",
        "follow": {"continue": "试用员下次运行时按你的选择接着做。", "retarget": "已转给另一个项目，下次运行时试。",
                   "close": "这条试用到此为止。", "adopt": "试用员下次运行时在本机按项目原来的流程合并，做完告诉你。"},
        "decided": {"continue": "收到，下次试用时接着做", "retarget": "收到，已转给「{project}」", "close": "收到，这条到此为止",
                    "adopt": "收到，下次试用时合并"},
        "tverdict": {"adopt": "建议采纳", "reject": "不建议用", "decide": "要你决定"},
        "footer": "觉得哪条好用，点「交给项目试」：{when} 试用员在那个项目的单独分支里装上试跑、跑项目测试，然后把报告发给你。",
        "empty": "还没有日报。侦察员第一次运行后会出现在这里。",
        "back": "回到 {date} 的日报", "report": "试用报告", "requested": "请求", "finished": "完成", "branch": "分支",
        "wanted_for": "想用在", "source": "原始链接",
        "adopt_hint": "要采纳：跟你的 agent 说「采纳试用 {tid}」，它会按这个项目原来的流程合并。在那之前沙盒和分支都留在试用的电脑上。",
        "trial_mode_assess": "只读评估",
        "new_projects": "新发现的方向",
        "new_projects_sub": "最近你在编程 agent 里一直在做这些，侦察员已经开始为它们找工具，也可以把条目交给它们试。不需要就点「不用关注」。",
        "part_of": "属于", "ignore": "不用关注", "ignored": "已不再关注",
        "ignored_msg": "**已记下：不再关注「{name}」**\n侦察员不再为它找工具。",
    },
}

CSS = """
:root{--bg:#EEF1F4;--surface:#FFFFFF;--ink:#15202C;--muted:#5A6573;--line:#D6DCE3;--accent:#1F4FD1;--accent-soft:#E3EAFB;
--pick:#B76E00;--pick-soft:#FBEFD9;--warn:#A8461B;--ok:#1D7A4E;
--f-display:"Songti SC","Noto Serif SC","Georgia",serif;--f-body:system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
--f-mono:ui-monospace,"SF Mono","Cascadia Mono",Consolas,monospace}
@media (prefers-color-scheme: dark){:root{--bg:#0F151C;--surface:#17202A;--ink:#E6ECF2;--muted:#98A4B2;--line:#2A3542;
--accent:#7FA2FF;--accent-soft:#1D2A47;--pick:#F0B44C;--pick-soft:#34280F;--warn:#F08A5D;--ok:#5FD39A;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--f-body);font-size:15px;line-height:1.65;-webkit-text-size-adjust:100%}
a{color:var(--accent);text-decoration:none}
.wrap{max-width:820px;margin:0 auto;padding:20px 16px 56px;display:flex;flex-direction:column;gap:30px}
.brand{font-family:var(--f-display);font-weight:900;font-size:17px;letter-spacing:.02em}
.days{display:flex;gap:6px;overflow-x:auto;padding-bottom:4px;font-family:var(--f-mono);font-size:12.5px}
.days a{flex:0 0 auto;padding:4px 10px;border-radius:6px;color:var(--muted);background:var(--surface);border:1px solid var(--line)}
.days a.on{color:var(--bg);background:var(--ink);border-color:var(--ink)}
.mast{display:flex;flex-direction:column;gap:8px;padding-bottom:20px;border-bottom:1px solid var(--line)}
.mast .date{font-family:var(--f-display);font-weight:900;font-size:54px;line-height:1;letter-spacing:-.02em}
.mast .meta,.meta{font-family:var(--f-mono);font-size:12px;color:var(--muted);display:flex;flex-wrap:wrap;gap:4px 14px}
.mast .headline{font-size:17px;margin:6px 0 0}
h2{font-family:var(--f-display);font-weight:700;font-size:19px;margin:0}
.sec{display:flex;flex-direction:column;gap:12px}
.picks{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.pick{background:var(--pick-soft);border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:6px;min-width:0}
.pick .rank{font-family:var(--f-mono);font-size:11px;letter-spacing:.12em;color:var(--pick);font-weight:600}
.pick a{font-weight:700;color:var(--ink);overflow-wrap:anywhere}
.pick p{margin:0;font-size:13.5px;color:var(--muted)}
.toc{display:flex;flex-wrap:wrap;gap:6px}
.toc a{border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:2px 11px;font-size:13px;color:var(--ink)}
.group{display:flex;flex-direction:column;gap:10px}
.group h3{font-family:var(--f-mono);font-size:12px;font-weight:600;letter-spacing:.12em;color:var(--muted);margin:6px 0 0;text-transform:uppercase}
.item{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:8px;min-width:0}
.item.is-pick{border-color:var(--pick)}
.top{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;font-family:var(--f-mono);font-size:12px;color:var(--muted)}
.src{font-weight:600;padding:1px 7px;border-radius:4px;background:var(--accent-soft);color:var(--accent)}
.src.x{background:var(--ink);color:var(--bg)}
.verdict{margin-left:auto;font-family:var(--f-body);font-size:12px;font-weight:600;padding:0 9px;border-radius:999px;border:1px solid currentColor}
.verdict.try{color:var(--pick)}.verdict.save{color:var(--accent)}.verdict.watch{color:var(--muted)}
.item h4{margin:0;font-size:16.5px;line-height:1.45;overflow-wrap:anywhere}
.item h4 a{color:var(--ink)}
.item p{margin:0}
.fits{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px;font-size:14px}
.fits li{display:flex;flex-wrap:wrap;gap:2px 8px;align-items:baseline}
.ptag{font-size:12px;font-weight:600;padding:0 8px;border-radius:4px;background:var(--ink);color:var(--bg);white-space:nowrap}
.dots{font-family:var(--f-mono);font-size:11px;color:var(--muted)}
.how{flex-basis:100%}
.foot{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;color:var(--muted);padding-top:4px;border-top:1px dashed var(--line)}
.caution,.unv{color:var(--warn)}
.tips{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.tip{border-left:3px solid var(--accent);padding:2px 0 2px 12px;min-width:0}
.tip .label{font-family:var(--f-mono);font-size:11px;letter-spacing:.08em;color:var(--accent)}
.tip b{display:block}
.tip p{margin:0;font-size:14px;color:var(--muted);overflow-wrap:anywhere}
.note{font-size:13px;color:var(--muted);border-top:1px solid var(--line);padding-top:14px}
.act{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center}
.act[hidden]{display:none}
.act button,.act select,.act input{font:inherit;font-size:13.5px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:7px;padding:5px 10px}
.act .try-btn{border-color:var(--accent);color:var(--accent);font-weight:600}
.act .fb button[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.act .fb{display:inline-flex;gap:4px}
.act form{display:flex;flex-wrap:wrap;gap:6px;width:100%}
.act input{flex:1 1 180px;min-width:0}
.act .send{background:var(--accent);border-color:var(--accent);color:var(--surface);font-weight:600}
.tstat{display:flex;flex-wrap:wrap;gap:6px;font-size:12.5px}
.tstat span,.tstat a{padding:1px 9px;border-radius:999px;background:var(--accent-soft);color:var(--accent)}
.tmsg{font-size:12.5px;color:var(--muted);width:100%}
.sub{margin:0;font-size:13.5px;color:var(--muted)}
.nps{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px}
.np{background:var(--surface);border:1px dashed var(--accent);border-radius:10px;padding:12px 14px;display:flex;flex-direction:column;gap:6px;min-width:0}
.np p{margin:0;font-size:13.5px;color:var(--muted);overflow-wrap:anywhere}
.np button{align-self:flex-start;font:inherit;font-size:13px;color:var(--muted);background:var(--surface);border:1px solid var(--line);border-radius:7px;padding:3px 10px}
.np button[hidden]{display:none}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;display:flex;flex-direction:column;gap:10px}
.card .rv{align-self:flex-start}.headline{font-size:18px;font-weight:700;margin:0;line-height:1.55}
.card h4{font-size:14px;color:var(--muted);margin:6px 0 0;font-weight:600}.card ul{margin:0;padding-left:20px}
.cost{margin:0;color:var(--muted);font-size:14px}.ask{margin:0;background:var(--pick-soft);border-radius:8px;padding:10px 12px;font-weight:600}
.opts{display:flex;flex-direction:column;gap:8px}
.opt{display:flex;flex-direction:column;align-items:flex-start;gap:2px;text-align:left;font:inherit;color:var(--ink);background:var(--surface);border:1.5px solid var(--accent);border-radius:10px;padding:10px 14px;cursor:pointer}
.opt b{color:var(--accent)}.opt span{font-size:13.5px;color:var(--muted)}.opt[disabled]{opacity:.5;cursor:default}
.decided{margin:0;border-left:4px solid var(--ok);padding:8px 12px;font-weight:600}
details{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:10px 16px}summary{cursor:pointer;color:var(--muted);font-size:14px}
.rv{display:inline-block;font-weight:700;padding:2px 12px;border-radius:999px;border:1.5px solid currentColor}
.rv.adopt{color:var(--ok)}.rv.reject{color:var(--warn)}.rv.decide{color:var(--pick)}
.box{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.box h2,.box h3,.box h4{font-family:var(--f-body);font-size:16px;margin:16px 0 4px}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;overflow-x:auto;font-size:13px}
code{font-family:var(--f-mono);font-size:13px;overflow-wrap:anywhere}
"""

JS = """
(function(){
  var C = __CONFIG__;
  var S = C.s;
  function api(path, body){
    var o = body ? {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)} : {cache: 'no-store'};
    return fetch(C.api + path, o).then(function(r){ return r.json().then(function(j){ return {ok: r.ok, j: j}; }); });
  }
  var boxes = Array.prototype.slice.call(document.querySelectorAll('.act'));
  function chip(t){
    var label = t.projectName + ' · ' + ((t.verdict && S.tverdict[t.verdict]) || S.status[t.status] || t.status);
    var n = document.createElement(t.report ? 'a' : 'span');
    if (t.report) { n.href = t.report; label += ' →'; }
    n.textContent = label; return n;
  }
  function paint(trials, fb){
    boxes.forEach(function(box){
      var id = box.getAttribute('data-id');
      var st = box.querySelector('.tstat'); st.textContent = '';
      (trials[id] || []).forEach(function(t){ st.appendChild(chip(t)); });
      box.querySelectorAll('.fb button').forEach(function(b){
        b.setAttribute('aria-pressed', String(!!fb[id] && fb[id].status === b.getAttribute('data-s')));
      });
    });
  }
  function load(){
    Promise.all([api('trials'), api('feedback')]).then(function(r){
      if (!r[0].ok) return;
      boxes.forEach(function(b){ b.hidden = false; });
      paint(r[0].j, r[1].ok ? r[1].j : {});
    }).catch(function(){});
  }
  function openForm(box, btn){
    var f = document.createElement('form');
    var sel = document.createElement('select'); sel.setAttribute('aria-label', S.try_btn);
    Object.keys(C.projects).forEach(function(k){ var o = document.createElement('option'); o.value = k; o.textContent = C.projects[k]; sel.appendChild(o); });
    if (C.projects[box.getAttribute('data-best')]) sel.value = box.getAttribute('data-best');
    var inp = document.createElement('input'); inp.type = 'text'; inp.maxLength = 300; inp.placeholder = S.note_ph; inp.setAttribute('aria-label', S.note_ph);
    var send = document.createElement('button'); send.type = 'submit'; send.className = 'send'; send.textContent = S.send;
    var cancel = document.createElement('button'); cancel.type = 'button'; cancel.textContent = S.cancel;
    var msg = document.createElement('div'); msg.className = 'tmsg';
    [sel, inp, send, cancel, msg].forEach(function(n){ f.appendChild(n); });
    cancel.onclick = function(){ f.remove(); btn.hidden = false; };
    f.onsubmit = function(ev){
      ev.preventDefault(); send.disabled = true; msg.textContent = S.sending;
      api('trial', {date: C.date, id: box.getAttribute('data-id'), project: sel.value, note: inp.value}).then(function(x){
        if (x.ok) { f.remove(); btn.hidden = false; btn.textContent = S.again; load(); }
        else { send.disabled = false; msg.textContent = (x.j && x.j.error) || S.send_fail; }
      }).catch(function(){ send.disabled = false; msg.textContent = S.send_fail; });
    };
    box.appendChild(f); btn.hidden = true; inp.focus();
  }
  var cards = Array.prototype.slice.call(document.querySelectorAll('.np'));
  function markIgnored(card){ var b = card.querySelector('button'); b.disabled = true; b.textContent = S.ignored; }
  cards.forEach(function(card){
    var b = card.querySelector('button');
    b.addEventListener('click', function(){
      b.disabled = true;
      api('project', {date: C.date, key: card.getAttribute('data-key')}).then(function(x){
        if (x.ok) markIgnored(card); else { b.disabled = false; card.querySelector('.tmsg').textContent = (x.j && x.j.error) || S.send_fail; }
      }).catch(function(){ b.disabled = false; card.querySelector('.tmsg').textContent = S.send_fail; });
    });
  });
  if (cards.length) api('ignored').then(function(x){
    if (!x.ok) return;
    cards.forEach(function(card){ card.querySelector('button').hidden = false; if (x.j[card.getAttribute('data-key')]) markIgnored(card); });
  }).catch(function(){});
  boxes.forEach(function(box){
    var btn = box.querySelector('.try-btn');
    if (btn) btn.addEventListener('click', function(){ if (!box.querySelector('form')) openForm(box, btn); });
    box.querySelectorAll('.fb button').forEach(function(b){
      b.addEventListener('click', function(){
        var on = b.getAttribute('aria-pressed') === 'true';
        api('feedback', {date: C.date, id: box.getAttribute('data-id'), status: on ? null : b.getAttribute('data-s')}).then(load).catch(function(){});
      });
    });
  });
  load();
})();
"""


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def safe_url(u):
    u = str(u or "").strip()
    return u if re.match(r"^https?://", u, re.I) and not re.search(r"[\s<>\"']", u) else ""


def link(u, text, cls=""):
    u = safe_url(u)
    c = f' class="{cls}"' if cls else ""
    if not u:
        return f"<span{c}>{e(text)}</span>"
    return f'<a{c} href="{e(u)}" target="_blank" rel="noopener noreferrer">{e(text)}</a>'


def kfmt(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return ""
    if n >= 10000:
        return f"{n / 1000:.0f}k"
    return f"{n / 1000:.1f}k" if n >= 1000 else str(int(n))


def safe_anchor(s):
    return re.sub(r"[^A-Za-z0-9_-]", "-", str(s or "x"))[:120] or "x"


def strings(cfg):
    lang = str(cfg.get("language") or "en")
    if lang in STRINGS:
        return STRINGS[lang]
    return STRINGS["zh-CN"] if lang.lower().startswith("zh") else STRINGS["en"]


def day_label(d, S):
    y, m, dd = map(int, d.split("-"))
    return f"{m:02d}.{dd:02d}", S["weekday"][date(y, m, dd).weekday()], str(y)


def head(title, cfg):
    return (f'<!doctype html><html lang="{e(cfg.get("language", "en"))}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<meta name="robots" content="noindex,nofollow"><meta name="referrer" content="no-referrer">'
            f"<title>{e(title)}</title><style>{CSS}</style></head><body><div class=\"wrap\">")


def item_html(it, picks, cfg, S):
    projects, topics = project_names(cfg), topic_names(cfg)
    src = it.get("source")
    top = [f'<span class="src{" x" if src == "x" else ""}">{ {"github": "GitHub", "x": "X"}.get(src, "Web") }</span>']
    if it.get("author"):
        top.append(f"<span>{e(it['author'])}</span>")
    if it.get("stars") is not None:
        delta = f" (+{kfmt(it['starsDelta'])})" if it.get("starsDelta") else ""
        top.append(f"<span>★ {kfmt(it['stars'])}{delta}</span>")
    if it.get("published"):
        top.append(f"<span>{e(it['published'])}</span>")
    if it.get("verdict") in S["verdict"]:
        top.append(f'<span class="verdict {it["verdict"]}">{S["verdict"][it["verdict"]]}</span>')
    fits = []
    ranked = []
    for p in it.get("projects") or []:
        if p.get("key") in projects:
            try:
                n = max(0, min(3, int(p.get("fit") or 0)))
            except (TypeError, ValueError):
                n = 0
            ranked.append((n, p["key"]))
            fits.append(f'<li><span class="ptag">{e(projects[p["key"]])}</span>'
                        f'<span class="dots" title="{S["fit"]} {n}/3">{"●" * n}{"○" * (3 - n)}</span>'
                        f'<span class="how">{e(p.get("how"))}</span></li>')
    foot = []
    if it.get("effort"):
        foot.append(f"<span>{S['effort']}: {e(it['effort'])}</span>")
    if it.get("verified") is False:
        foot.append(f'<span class="unv">{S["unverified"]}</span>')
    if it.get("caution"):
        foot.append(f'<span class="caution">{S["caution"]}: {e(it["caution"])}</span>')
    best = max(ranked)[1] if ranked else ""
    fb = "".join(f'<button type="button" data-s="{k}" aria-pressed="false">{v}</button>' for k, v in S["fb"].items())
    act = (f'<div class="act" hidden data-id="{e(it.get("id"))}" data-best="{e(best)}">'
           f'<span class="fb">{fb}</span><button type="button" class="try-btn">{S["try_btn"]}</button>'
           f'<span class="tstat"></span></div>')
    pick = " is-pick" if it.get("id") in picks else ""
    return (f'<article class="item{pick}" id="i-{safe_anchor(it.get("id"))}"><div class="top">{"".join(top)}</div>'
            f'<h4>{link(it.get("url"), it.get("title"))}</h4>'
            + (f'<p>{e(it.get("summary"))}</p>' if it.get("summary") else "")
            + (f'<ul class="fits">{"".join(fits)}</ul>' if fits else "")
            + (f'<div class="foot">{"".join(foot)}</div>' if foot else "") + act + "</article>")


def cards_html(title, cards, label_key):
    if not cards:
        return ""
    out = []
    for c in cards:
        src = f" {link(c.get('url'), '↗')}" if safe_url(c.get("url")) else ""
        out.append(f'<div class="tip"><span class="label">{e(c.get(label_key) or "")}</span><b>{e(c.get("title"))}</b>'
                   f'<p>{e(c.get("detail"))}{src}</p></div>')
    return f'<section class="sec"><h2>{e(title)}</h2><div class="tips">{"".join(out)}</div></section>'


def day_page(r, dates, cfg):
    S = strings(cfg)
    d = r["date"]
    md, wd, y = day_label(d, S)
    items = r.get("items") or []
    picks = r.get("picks") or []
    topics = topic_names(cfg)
    src = r.get("sources") or {}
    meta = [f"{y} {wd}"]
    if r.get("generatedAt"):
        meta.append(f"{S['generated']} {e(str(r['generatedAt']).replace('T', ' ')[:16])}")
    if src.get("github") is not None:
        meta.append(f"{S['github']} {e(src['github'])}")
    if src.get("x") is not None:
        meta.append(f"{S['x']} {e(src['x'])}" + {"browser": S["x_browser"], "search": S["x_search"]}.get(src.get("xMode"), ""))
    meta.append(f"{len(items)} {S['items']}")
    nav = "".join(f'<a class="{"on" if x == d else ""}" href="{x}.html">{" ".join(day_label(x, S)[:2])}</a>' for x in dates[:30])
    by_id = {i.get("id"): i for i in items}
    pk = []
    for n, pid in enumerate(picks, 1):
        it = by_id.get(pid)
        if not it:
            continue
        how = ((it.get("projects") or [{}])[0] or {}).get("how") or it.get("summary")
        pk.append(f'<div class="pick"><span class="rank">NO.{n} · {e(topics.get(it.get("category"), topics["other"]))}</span>'
                  f'<a href="#i-{safe_anchor(pid)}">{e(it.get("title"))}</a><p>{e(how)}</p></div>')
    groups, toc = [], []
    order = list(topics)
    for key in order:
        g = [i for i in items if (i.get("category") if i.get("category") in topics else "other") == key]
        if g:
            toc.append(f'<a href="#c-{e(key)}">{e(topics[key])} {len(g)}</a>')
            groups.append(f'<section class="group" id="c-{e(key)}"><h3>{e(topics[key])} · {len(g)}</h3>'
                          f'{"".join(item_html(i, picks, cfg, S) for i in g)}</section>')
    extra = "".join(cards_html(s.get("title"), s.get("cards"), "label") for s in r.get("sections") or [])
    fu = r.get("followups") or []
    fu_html = (f'<section class="sec"><h2>{S["followups"]}</h2>'
               + "".join(f"<p><b>{e(f.get('title'))}</b>: {e(f.get('note'))}</p>" for f in fu) + "</section>") if fu else ""
    when = e(cfg["trial"].get("schedule_note") or "")
    conf = {"date": d, "api": "api/", "projects": {p["key"]: p["name"] for p in cfg.get("projects", []) if p["trial_mode"] != "off"},
            "s": {k: S[k] for k in ("try_btn", "send", "cancel", "note_ph", "sending", "send_fail", "again", "status", "tverdict",
                                    "ignored")}}
    script = JS.replace("__CONFIG__", json.dumps(conf, ensure_ascii=False).replace("<", "\\u003c"))
    names = project_names(cfg)
    nps = []
    for p in r.get("newProjects") or []:
        key = str(p.get("key", ""))
        if key in names:
            parent = names.get(str(p.get("parent") or ""))
            nps.append(f'<div class="np" data-key="{e(key)}"><b>{e(names[key])}</b>'
                       + (f'<span class="meta">{S["part_of"]} {e(parent)}</span>' if parent else "")
                       + f'<p>{e(p.get("why"))}</p><button type="button" hidden>{S["ignore"]}</button><div class="tmsg"></div></div>')
    np_html = (f'<section class="sec"><h2>{S["new_projects"]}</h2><p class="sub">{S["new_projects_sub"]}</p>'
               f'<div class="nps">{"".join(nps)}</div></section>') if nps else ""
    return (head(f"{cfg['site']['title']} {md}", cfg)
            + f'<div class="brand">{e(cfg["site"]["title"])}</div><nav class="days">{nav}</nav>'
            + f'<header class="mast"><div class="date">{md}</div><div class="meta">{"".join(f"<span>{x}</span>" for x in meta)}</div>'
            + (f'<p class="headline">{e(r.get("headline"))}</p>' if r.get("headline") else "") + "</header>"
            + (f'<section class="sec"><h2>{S["picks"]}</h2><div class="picks">{"".join(pk)}</div></section>' if pk else "")
            + np_html
            + (f'<nav class="toc">{"".join(toc)}</nav>' if toc else "")
            + "".join(groups)
            + cards_html(S["tips"], r.get("tips"), "tool")
            + extra + fu_html
            + f'<p class="note">{S["footer"].format(when=when)}</p>'
            + f"</div><script>{script}</script></body></html>")


def empty_page(cfg):
    S = strings(cfg)
    return head(cfg["site"]["title"], cfg) + f'<div class="brand">{e(cfg["site"]["title"])}</div><p>{S["empty"]}</p></div></body></html>'


DECIDE_JS = """(function(){var T=__TID__;var bs=document.querySelectorAll('.opt');var m=document.getElementById('tmsg');
bs.forEach(function(b){b.addEventListener('click',function(){bs.forEach(function(x){x.disabled=true});m.textContent=__SENDING__;
fetch('../api/decide',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tid:T,option:b.getAttribute('data-id')})})
.then(function(r){return r.json().then(function(j){return {ok:r.ok,j:j}})}).then(function(x){if(x.ok){m.textContent=x.j.message||'OK'}
else{m.textContent=x.j.error||__FAIL__;bs.forEach(function(y){y.disabled=false})}})
.catch(function(){m.textContent=__FAIL__;bs.forEach(function(y){y.disabled=false})});});});})();"""


def trial_page(t, cfg):
    """Two layers: a plain card for the owner (verdict, headline, good / not so good, cost, the question and the
    choice buttons), then the technical report folded away for whoever adopts it."""
    from .store import DECIDABLE, clean_plain
    S = strings(cfg)
    it = t.get("item") or {}
    names = project_names(cfg)
    pname = names.get(t["project"], t["project"])
    st, v = t["status"], t.get("verdict")
    plain = t.get("plain") or clean_plain({}, t.get("summary", ""))
    chip_cls, chip = (v, S["tverdict"][v]) if st == "done" and v in S["tverdict"] else (
        {"blocked": "decide", "failed": "reject", "adopted": "adopt"}.get(st, "decide"), S["status"].get(st, st))
    meta = [e(pname), f"{S['requested']} {e(str(t.get('createdAt', ''))[:16].replace('T', ' '))}"]
    if t.get("finishedAt"):
        meta.append(f"{S['finished']} {e(str(t['finishedAt'])[:16].replace('T', ' '))}")
    if t.get("mode") == "assess":
        meta.append(S["trial_mode_assess"])
    lists = "".join(f'<h4>{S[k]}</h4><ul>{"".join(f"<li>{e(x)}</li>" for x in plain.get(k) or [])}</ul>'
                    for k in ("good", "bad") if plain.get(k))
    dec = t.get("decision")
    if dec:
        choose = (f'<p class="decided">{e(S["chose"].format(label=dec.get("label"), at=str(dec.get("at", ""))[5:16].replace("T", " ")))} '
                  f'{e(S["follow"].get(dec.get("action"), ""))}</p>')
    elif st in DECIDABLE and t.get("options"):
        choose = ('<div class="opts">' + "".join(
            f'<button type="button" class="opt" data-id="{e(o["id"])}"><b>{e(o["label"])}</b><span>{e(o.get("effect"))}</span></button>'
            for o in t["options"]) + '</div><p class="tmsg" id="tmsg"></p>')
    else:
        choose = ""
    src = safe_url(it.get("url"))
    where = " · ".join(x for x in (f"{S['branch']} {e(t['branch'])}" if t.get("branch") else "",
                                   e(t.get("sandbox") or "")) if x)
    script = ""
    if choose and not dec:
        script = "<script>" + DECIDE_JS.replace("__TID__", json.dumps(t["tid"])).replace(
            "__SENDING__", json.dumps(S["sending"])).replace("__FAIL__", json.dumps(S["send_fail"])) + "</script>"
    return (head(f"{S['report']} · {it.get('title', '')}", cfg)
            + f'<a href="../{e(t["date"])}.html">← {e(S["back"].format(date=t["date"]))}</a>'
            + f'<h1 style="font-size:21px;line-height:1.45;margin:0">{e(it.get("title"))} → {e(pname)}</h1>'
            + f'<div class="meta">{"".join(f"<span>{m}</span>" for m in meta)}</div>'
            + f'<section class="card"><span class="rv {chip_cls}">{e(chip)}</span>'
            + f'<p class="headline">{e(plain.get("headline"))}</p>{lists}'
            + (f'<p class="cost">{S["cost"]}: {e(plain["cost"])}</p>' if plain.get("cost") else "")
            + (f'<p class="ask">{S["ask"]}: {e(plain["ask"])}</p>' if plain.get("ask") and not dec else "")
            + choose
            + (f'<p class="tmsg">{S["wanted_for"]}: {e(t["note"])}</p>' if t.get("note") else "")
            + "</section>"
            + f'<details><summary>{S["tech"]}</summary>'
            + (f'<p>{S["source"]}: {link(src, src)}</p>' if src else "")
            + (f'<p class="meta">{where}</p>' if where else "")
            + f'<div class="box">{mdlite.to_html(t.get("report_md"))}</div></details>'
            + f"</div>{script}</body></html>")


def _write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def build_site(cfg, store, keep_days=60):
    site = Path(cfg["_site"])
    dates = store.report_dates()[:keep_days]
    if not dates:
        _write(site / "index.html", empty_page(cfg))
    for i, d in enumerate(dates):
        page = day_page(store.load_report(d), dates, cfg)
        _write(site / f"{d}.html", page)
        if i == 0:
            _write(site / "index.html", page)
    for old in site.glob("*.html"):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", old.stem) and old.stem not in dates:
            old.unlink()
    for t in store.trials():
        if t["status"] in ("done", "blocked", "failed"):
            _write(site / "trials" / f"{t['tid']}.html", trial_page(t, cfg))
    return dates


def publish(cfg, store, rep):
    """Save a day's report (with the projects and topics as they are now, for the panel), rebuild the site.
    Returns the day page's URL (relative when site.base_url is not set). Raises ValueError for a bad report."""
    rep["_projects"] = {p["key"]: {"name": p["name"], "trial_mode": p["trial_mode"], "source": p.get("source", "config"),
                                   "status": st}
                        for st, ps in (("active", cfg["projects"]), ("ignored", cfg["_ignored_projects"])) for p in ps}
    rep["_topics"] = [{"key": t["key"], "name": t["name"], "focus": t.get("focus", ""), "projects": t.get("projects", []),
                       "source": t.get("source", "config"), "status": st}
                      for st, ts in (("active", cfg["topics"]), ("paused", cfg["_paused_topics"])) for t in ts]
    store.save_report(rep)
    store.prune()
    build_site(cfg, store)
    return f"{cfg['site'].get('base_url') or ''}{rep['date']}.html"
