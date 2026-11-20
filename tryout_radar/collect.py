"""Collect today's candidates for the scout from fixed sources: plain code, no model.

  GitHub    search API per topic query (new repos, and active older ones), trending pages, release lists
  watch     each topic's `watch` URLs: GitHub releases, a changelog file (its newest section), an RSS/Atom feed,
            or any page (the lines that changed since the last run)
  HN        Hacker News stories via the public Algolia API (optional)
  search    a web search service you configure: SearXNG, Brave or Tavily (optional; also how X is read in API mode)

Facts in the digest (titles, links, stars, dates) come from here, never from the model. Everything fetched is
treated as data: it is shown to the model as text and nothing in it is run."""
import concurrent.futures
import hashlib
import html
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .config import env

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"
HN_API = "https://hn.algolia.com/api/v1"
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
TAVILY_API = "https://api.tavily.com/search"
USER_AGENT = "tryout-radar (+https://github.com/alex7-1/tryout-radar)"
PACE = {"anon": 6.5, "token": 2.1}     # seconds between GitHub search calls (limits: 10 / 30 per minute)
MAX_BODY = 3_000_000
GH_REPO_RE = re.compile(r"^https?://(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:[/?#](.*))?$")
GH_NOT_OWNERS = {"topics", "trending", "orgs", "features", "marketplace", "sponsors", "settings", "login", "about",
                 "collections", "search", "explore", "apps", "enterprise", "pricing", "readme", "events"}
X_STATUS_RE = re.compile(r"^https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/(\d+)")


# ---------- small helpers ----------

def clip(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def make_id(prefix, *parts):
    body = "-".join(re.sub(r"[^A-Za-z0-9_.-]+", "-", str(p)).strip("-.") for p in parts if p)
    return (prefix + "-" + body)[:160].rstrip("-.")


def slug(s, n=40):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")[:n].strip("-") or hashlib.sha1(str(s).encode()).hexdigest()[:8]


def norm_url(u):
    u = re.sub(r"^https?://(www\.)?", "", str(u or "").strip().lower())
    return re.sub(r"(\.git)?/*$", "", u.split("#")[0])


def domain(u):
    return re.sub(r"^www\.", "", urllib.parse.urlsplit(str(u)).netloc.lower())


def html_to_text(s):
    s = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|section|article)>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return "\n".join(re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in s.splitlines() if line.strip())


def clean_markdown(s):
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)                  # images and badges
    s = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)", "", s)     # linked badges
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def top_section(md):
    """The newest entry of a changelog: from its first version heading to the next heading of the same level."""
    lines = md.splitlines()
    heads = [(i, len(m.group(1)), m.group(2).strip()) for i, line in enumerate(lines)
             for m in [re.match(r"^(#{1,4})\s+(.+)$", line)] if m]
    if not heads:
        return "", "\n".join(lines[:40])
    if len(heads) > 1 and heads[0][1] < heads[1][1]:            # skip a title such as "# Changelog"
        heads = heads[1:]
    i, level, title = heads[0]
    end = next((j for j, lv, _ in heads[1:] if lv <= level), len(lines))
    return title, "\n".join(lines[i + 1:end]).strip()


def parse_time(s):
    s = str(s or "").strip()
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            t = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def parse_feed(body):
    """Entries of an RSS or Atom feed: [{title, url, published (datetime|None), summary}]."""
    root = ET.fromstring(body)
    out = []
    atom = "{http://www.w3.org/2005/Atom}"
    for it in root.iter("item"):
        out.append({"title": (it.findtext("title") or "").strip(), "url": (it.findtext("link") or "").strip(),
                    "published": parse_time(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")),
                    "summary": html_to_text(it.findtext("description") or "")})
    for en in root.iter(atom + "entry"):
        link = next((l.get("href") for l in en.findall(atom + "link") if l.get("rel", "alternate") == "alternate"), "")
        out.append({"title": (en.findtext(atom + "title") or "").strip(), "url": link or "",
                    "published": parse_time(en.findtext(atom + "published") or en.findtext(atom + "updated")),
                    "summary": html_to_text(en.findtext(atom + "summary") or en.findtext(atom + "content") or "")})
    return out


def parse_trending(page):
    """Repositories on a GitHub trending page: owner, name, description, total stars, stars today."""
    out = []
    num = lambda s: int(re.sub(r"[^\d]", "", s) or 0)  # noqa: E731
    for art in re.findall(r'<article[^>]*class="[^"]*Box-row[^"]*"[^>]*>(.*?)</article>', page, re.S):
        m = re.search(r'<h2[^>]*>.*?href="/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)"', art, re.S)
        if not m:
            continue
        owner, name = m.groups()
        desc = re.search(r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>(.*?)</p>', art, re.S)
        stars = re.search(rf'href="/{re.escape(owner)}/{re.escape(name)}/stargazers"[^>]*>(.*?)</a>', art, re.S)
        today = re.search(r"([\d,]+)\s+stars?\s+today", art)
        out.append({"owner": owner, "name": name, "description": html_to_text(desc.group(1)) if desc else "",
                    "stars": num(html_to_text(stars.group(1))) if stars else None, "starsDelta": num(today.group(1)) if today else 0})
    return out


class Http:
    def __init__(self, timeout=25):
        self.timeout = timeout

    def get(self, url, headers=None, data=None):
        """(status, lower-case headers, body bytes); status 0 when the server can't be reached. Never raises."""
        h = {"User-Agent": USER_AGENT, **(headers or {})}
        try:
            req = urllib.request.Request(url, headers=h, data=data)
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(MAX_BODY)
        except urllib.error.HTTPError as ex:
            hd = {k.lower(): v for k, v in (ex.headers or {}).items()}
            try:
                body = ex.read(MAX_BODY)
            except OSError:
                body = b""
            return ex.code, hd, body
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as ex:
            return 0, {}, str(ex).encode()

    def json(self, url, headers=None, data=None):
        st, hd, body = self.get(url, headers, data)
        if st != 200:
            return st, hd, None
        try:
            return st, hd, json.loads(body.decode("utf-8"))
        except ValueError:
            return st, hd, None


# ---------- the collector ----------

class Collector:
    def __init__(self, cfg, history=(), feedback=None, state=None, extra=(), http=None, now=None):
        self.cfg, self.src = cfg, cfg.get("sources") or {}
        self.http = http or Http()
        self.now = now or datetime.now(timezone.utc)
        self.cutoff = self.now - timedelta(hours=int(cfg["digest"].get("lookback_hours", 72)))
        self.excerpt = int(cfg["scout"].get("excerpt_chars", 1000))
        fb = feedback or {}
        self.seen_ids = {str(h.get("id")) for h in history if h.get("id")} | {k for k, v in fb.items() if v.get("status") == "done"}
        self.seen_urls = ({norm_url(h["url"]) for h in history if h.get("url")}
                          | {norm_url(v["url"]) for v in fb.values() if v.get("status") == "done" and v.get("url")})
        self.feedback = fb
        self.state = state if isinstance(state, dict) else {}
        self.state.setdefault("watch", {})
        self.extra = list(extra)                 # [{"queries": [...], "projects": [key]}] for directions found today
        self.cands, self.problems, self.followups = {}, [], []
        self.stats = {"github": 0, "x": 0, "web": 0}
        self.x_mode = "off"
        gh = self.src.get("github") or {}
        token = env(gh.get("token_env"))
        self.gh_headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.gh_headers["Authorization"] = f"Bearer {token}"
        self.pace = PACE["token" if token else "anon"]

    # ----- bookkeeping -----
    def topics(self):
        return [t for t in self.cfg.get("topics", [])]

    def add(self, c):
        c.setdefault("topics", [])
        c.setdefault("for_projects", [])
        if c["id"] in self.seen_ids or norm_url(c["url"]) in self.seen_urls:
            return
        old = self.cands.get(c["id"])
        if old:
            old["topics"] = sorted(set(old["topics"]) | set(c["topics"]))
            old["for_projects"] = sorted(set(old["for_projects"]) | set(c["for_projects"]))
            for k in ("stars", "starsDelta", "hn_points"):
                if c.get(k) and (old.get(k) or 0) < c[k]:
                    old[k] = c[k]
            old["description"] = old.get("description") or c.get("description", "")
            old["verified"] = old.get("verified") or c.get("verified", False)
            return
        same = next((x for x in self.cands.values() if norm_url(x["url"]) == norm_url(c["url"])), None)
        if same:
            same["topics"] = sorted(set(same["topics"]) | set(c["topics"]))
            return
        self.cands[c["id"]] = c

    def problem(self, msg):
        if msg not in self.problems:
            self.problems.append(msg)

    def recent(self, t):
        return t is not None and t >= self.cutoff

    def repo_candidate(self, owner, name, **kw):
        c = {"id": make_id("gh", owner, name), "title": f"{owner}/{name}", "url": f"https://github.com/{owner}/{name}",
             "source": "github", "author": owner, "kind": "repo", "verified": True}
        c.update({k: v for k, v in kw.items() if v is not None})
        return c

    def link_candidate(self, url, title, kind, **kw):
        """A candidate for any link: a GitHub repo, an X post or a web page."""
        m = GH_REPO_RE.match(url)
        if m and m.group(1).lower() not in GH_NOT_OWNERS and not m.group(3):
            self.stats["github"] += 1
            return self.repo_candidate(m.group(1), m.group(2), description=clip(title, 300), verified=False, **kw)
        x = X_STATUS_RE.match(url)
        if x:
            self.stats["x"] += 1
            return dict({"id": make_id("x", x.group(2)), "title": clip(title, 160), "url": url, "source": "x",
                         "author": x.group(1), "kind": kind, "verified": False}, **kw)
        self.stats["web"] += 1
        path = urllib.parse.urlsplit(url).path.strip("/")
        return dict({"id": make_id("web", domain(url), slug(path or title)), "title": clip(title, 160), "url": url,
                     "source": "web", "author": domain(url), "kind": kind, "verified": False}, **kw)

    # ----- GitHub -----
    def github_search(self):
        gh = self.src.get("github") or {}
        if not gh.get("enabled", True):
            return
        days = max(1, int(self.cfg["digest"].get("lookback_hours", 72)) // 24)
        created = (self.now.date() - timedelta(days=7)).isoformat()
        pushed = (self.now.date() - timedelta(days=days)).isoformat()
        rows = [(q, [t["key"]], list(t.get("projects") or [])) for t in self.topics()
                for q in (t.get("github_queries") or [t["name"]])]
        rows += [(q, [], list(e.get("projects") or [])) for e in self.extra for q in e.get("queries") or []]
        # one pass of new repositories for every query, then active older ones while the budget lasts
        order = sorted(range(len(rows)), key=lambda i: (sum(1 for j in range(i) if rows[j][1] == rows[i][1]), i))
        min_stars = int(gh.get("min_stars", 5))
        plan = [(rows[i], f"{rows[i][0]} created:>={created}" + (f" stars:>={min_stars}" if min_stars > 0 else "")) for i in order]
        plan += [(rows[i], f"{rows[i][0]} pushed:>={pushed} stars:>=50") for i in order]
        budget = int(gh.get("max_requests", 24))
        for n, ((q, topics, projects), query) in enumerate(plan[:budget]):
            if n:
                time.sleep(self.pace)
            url = f"{GITHUB_API}/search/repositories?" + urllib.parse.urlencode(
                {"q": query, "sort": "stars", "order": "desc", "per_page": 10})
            st, hd, data = self.http.json(url, self.gh_headers)
            if st in (403, 429):
                wait = float(hd.get("retry-after") or max(0, int(hd.get("x-ratelimit-reset") or 0) - time.time()) or 61)
                if wait > 75:
                    self.problem("GitHub search rate limit reached; stopped early (set GITHUB_TOKEN for a higher limit)")
                    break
                time.sleep(wait + 1)
                st, hd, data = self.http.json(url, self.gh_headers)
            if st != 200 or not isinstance(data, dict):
                self.gh_api_problem("GitHub search", st, hd)
                continue
            for r in data.get("items") or []:
                if r.get("archived") or not r.get("owner"):
                    continue
                self.stats["github"] += 1
                self.add(self.repo_candidate(
                    r["owner"]["login"], r["name"], url=r.get("html_url"), stars=int(r.get("stargazers_count") or 0),
                    published=str(r.get("created_at") or "")[:10], pushed=str(r.get("pushed_at") or "")[:10],
                    description=clip(r.get("description"), 300), license=(r.get("license") or {}).get("spdx_id") or "",
                    topics=topics, for_projects=projects))

    def trending(self):
        gh = self.src.get("github") or {}
        if not gh.get("enabled", True):
            return
        for url in gh.get("trending") or []:
            st, _, body = self.http.get(url)
            if st != 200:
                self.problem(f"trending page failed (HTTP {st}): {url}")
                continue
            for r in parse_trending(body.decode("utf-8", "replace")):
                self.stats["github"] += 1
                self.add(self.repo_candidate(r["owner"], r["name"], description=clip(r["description"], 300),
                                             stars=r["stars"], starsDelta=r["starsDelta"] or None, kind="repo"))

    def gh_api_problem(self, what, st, hd):
        if st in (403, 429) and hd.get("x-ratelimit-remaining") == "0":
            self.problem("GitHub API hourly limit used up (60 requests without a token): set the variable named in "
                         "sources.github.token_env, e.g. GITHUB_TOKEN, for 5000")
        else:
            self.problem(f"{what} failed (HTTP {st})")

    def releases(self, owner, name, topics=(), limit=5):
        st, hd, data = self.http.json(f"{GITHUB_API}/repos/{owner}/{name}/releases?per_page={limit}", self.gh_headers)
        if st != 200 or not isinstance(data, list):
            self.gh_api_problem(f"releases of {owner}/{name}", st, hd)
            return []
        out = []
        for r in data:
            when = parse_time(r.get("published_at"))
            if r.get("draft") or not self.recent(when):
                continue
            tag = str(r.get("tag_name") or "")
            out.append({"id": make_id("gh", owner, name, tag), "title": f"{owner}/{name} {tag}".strip(),
                        "url": r.get("html_url") or f"https://github.com/{owner}/{name}/releases", "source": "github",
                        "author": owner, "kind": "release", "published": when.date().isoformat(), "verified": True,
                        "description": clip(r.get("name"), 200), "excerpt": clip(clean_markdown(r.get("body") or ""), self.excerpt),
                        "topics": list(topics), "tag": tag})
        return out

    # ----- watched URLs -----
    def watch(self):
        for t in self.topics():
            for url in t.get("watch") or []:
                url = str(url)
                m = GH_REPO_RE.match(url)
                rest = (m.group(3) or "") if m else ""
                try:
                    if m and (not rest or rest.startswith(("releases", "tags"))):
                        for c in self.releases(m.group(1), m.group(2), [t["key"]]):
                            self.stats["github"] += 1
                            self.add(c)
                    elif m and rest.startswith("blob/"):
                        self.changelog(f"{GITHUB_RAW}/{m.group(1)}/{m.group(2)}/{rest[5:]}", url, m.group(1), m.group(2), t["key"])
                    else:
                        self.page(url, t["key"])
                except Exception as ex:  # noqa: BLE001 - one broken source never stops the run
                    self.problem(f"watch {url}: {type(ex).__name__}: {ex}")

    def changelog(self, raw, url, owner, name, topic):
        st, _, body = self.http.get(raw)
        if st != 200:
            self.problem(f"changelog failed (HTTP {st}): {url}")
            return
        title, text = top_section(body.decode("utf-8", "replace"))
        h = hashlib.sha1((title + text).encode()).hexdigest()[:10]
        today = self.now.date().isoformat()
        prev = self.state["watch"].get(url) or {}
        first = prev.get("first", today) if prev.get("hash") == h else today
        self.state["watch"][url] = {"hash": h, "first": first}
        if first != today:                           # seen on an earlier day; a second run today still reports it
            return
        self.stats["github"] += 1
        self.add({"id": make_id("gh", owner, name, "changelog", h), "title": clip(f"{owner}/{name} changelog: {title}", 160),
                  "url": url, "source": "github", "author": owner, "kind": "changelog", "verified": True,
                  "published": self.now.date().isoformat(), "excerpt": clip(clean_markdown(text), self.excerpt * 2),
                  "topics": [topic]})

    def page(self, url, topic):
        st, hd, body = self.http.get(url)
        if st != 200:
            self.problem(f"watched page failed (HTTP {st}): {url}")
            return
        head = body[:400].lstrip().lower()
        if "xml" in hd.get("content-type", "") or head.startswith((b"<?xml", b"<rss", b"<feed")):
            for e in parse_feed(body):
                if e["url"] and self.recent(e["published"]):
                    c = self.link_candidate(e["url"], e["title"], "post", topics=[topic],
                                            published=e["published"].date().isoformat(), excerpt=clip(e["summary"], self.excerpt))
                    c["verified"] = True
                    self.add(c)
            return
        text = html_to_text(body.decode("utf-8", "replace"))
        lines = [ln for ln in text.splitlines() if len(ln) >= 30]
        hashes = [hashlib.sha1(ln.encode()).hexdigest()[:12] for ln in lines]
        today = self.now.date().isoformat()
        prev = self.state["watch"].get(url) or {}
        base = prev.get("base") if prev.get("day") == today else prev.get("lines")   # compare with before today
        self.state["watch"][url] = {"lines": hashes[:3000], "base": base, "day": today}
        if base is None:
            return                                   # first visit: remember the page, report changes from next time
        old = set(base)
        new = [ln for ln, h in zip(lines, hashes) if h not in old]
        if not new:
            return
        page_title = re.search(r"(?is)<title[^>]*>(.*?)</title>", body.decode("utf-8", "replace"))
        name = clip(html.unescape(page_title.group(1)) if page_title else domain(url), 100)
        self.stats["web"] += 1
        self.add({"id": make_id("web", domain(url), slug(urllib.parse.urlsplit(url).path or "page"),
                                hashlib.sha1("".join(new).encode()).hexdigest()[:8]),
                  "title": clip(f"{name}: new on this page", 160), "url": url, "source": "web", "author": domain(url),
                  "kind": "page", "verified": True, "published": self.now.date().isoformat(),
                  "excerpt": clip("\n".join(new), self.excerpt * 2), "topics": [topic]})

    # ----- Hacker News -----
    def hn(self):
        hn = self.src.get("hn") or {}
        if not hn.get("enabled", True):
            return
        since = int(self.cutoff.timestamp())
        for t in self.topics():
            for q in (t.get("github_queries") or [t["name"]])[:2]:
                url = f"{HN_API}/search_by_date?" + urllib.parse.urlencode(
                    {"query": q, "tags": "story", "hitsPerPage": 10,
                     "numericFilters": f"created_at_i>{since},points>={int(hn.get('min_points', 30))}"})
                st, _, data = self.http.json(url)
                if st != 200 or not isinstance(data, dict):
                    self.problem(f"Hacker News search failed (HTTP {st})")
                    return
                for h in data.get("hits") or []:
                    link = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
                    if not str(link).startswith("http"):
                        continue
                    self.add(self.link_candidate(link, h.get("title") or link, "story", topics=[t["key"]],
                                                 published=str(h.get("created_at") or "")[:10], hn_points=int(h.get("points") or 0),
                                                 excerpt=clip(html_to_text(h.get("story_text") or ""), self.excerpt)))

    # ----- web search service -----
    def search(self):
        s = self.src.get("search") or {}
        provider = str(s.get("provider") or "none").lower()
        if provider == "none":
            return
        key = env(s.get("key_env"))
        if provider in ("brave", "tavily") and not key:
            self.problem(f"search: environment variable {s.get('key_env') or '(search.key_env)'} is empty")
            return
        queries = []
        if (self.src.get("web") or {}).get("enabled", True):
            queries += [(q, t["key"]) for t in self.topics() for q in (t.get("github_queries") or [t["name"]])[:1]]
        if (self.src.get("x") or {}).get("mode", "search") != "off":
            self.x_mode = "search"
            queries += [(f"site:x.com {q}", t["key"]) for t in self.topics() for q in (t.get("x_queries") or [])[:1]]
        for q, topic in queries[:int(s.get("max_requests", 12))]:
            try:
                results = self._search_one(provider, s, key, q)
            except Exception as ex:  # noqa: BLE001
                self.problem(f"search ({provider}): {type(ex).__name__}: {ex}")
                return
            for r in results:
                if r["url"].startswith("http"):
                    self.add(self.link_candidate(r["url"], r["title"] or r["url"], "search", topics=[topic],
                                                 published=r.get("published") or None, excerpt=clip(r.get("snippet"), self.excerpt)))

    def _search_one(self, provider, s, key, q):
        if provider == "searxng":
            base = str(s.get("url") or "").rstrip("/")
            if not base:
                raise ValueError("sources.search.url is empty")
            st, _, data = self.http.json(f"{base}/search?" + urllib.parse.urlencode({"q": q, "format": "json", "time_range": "week"}))
            rows = (data or {}).get("results") or []
            return [{"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("content", ""),
                     "published": str(r.get("publishedDate") or "")[:10]} for r in rows[:10]]
        if provider == "brave":
            st, _, data = self.http.json(BRAVE_API + "?" + urllib.parse.urlencode({"q": q, "freshness": "pw", "count": 10}),
                                         {"X-Subscription-Token": key, "Accept": "application/json"})
            rows = ((data or {}).get("web") or {}).get("results") or []
            return [{"url": r.get("url", ""), "title": r.get("title", ""), "snippet": html_to_text(r.get("description", "")),
                     "published": ""} for r in rows[:10]]
        if provider == "tavily":
            body = json.dumps({"query": q, "max_results": 10}).encode()
            st, _, data = self.http.json(TAVILY_API, {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, body)
            rows = (data or {}).get("results") or []
            return [{"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("content", ""),
                     "published": str(r.get("published_date") or "")[:10]} for r in rows[:10]]
        raise ValueError(f"unknown search provider {provider!r} (searxng, brave, tavily or none)")

    # ----- follow-ups on items the owner wants -----
    def wanted_news(self, limit=6):
        n = 0
        for iid, v in self.feedback.items():
            m = GH_REPO_RE.match(str(v.get("url") or ""))
            if v.get("status") != "want" or not m or n >= limit:
                continue
            n += 1
            for r in self.releases(m.group(1), m.group(2), limit=3)[:1]:
                self.followups.append({"itemId": iid, "title": v.get("title") or r["title"], "tag": r["tag"],
                                       "name": r["description"], "url": r["url"], "published": r["published"]})

    # ----- shortlist and details -----
    def score(self, c):
        s = 2.0 if c["topics"] or c["for_projects"] else 0.0
        s += math.log10((c.get("stars") or 0) + 1) + math.log10((c.get("hn_points") or 0) + 1)
        s += 1.5 if c.get("starsDelta") else 0
        s += 1.5 if c.get("kind") in ("release", "changelog", "page", "post") else 0
        s += 1.0 if c.get("published") and c["published"] >= self.cutoff.date().isoformat() else 0
        return s

    def shortlist(self, n):
        groups = {}
        for c in sorted(self.cands.values(), key=self.score, reverse=True):
            g = (c["topics"] or c["for_projects"] or ["other"])[0]
            groups.setdefault(g, []).append(c)
        out, lists = [], list(groups.values())
        while len(out) < n and any(lists):
            for lst in lists:
                if lst and len(out) < n:
                    out.append(lst.pop(0))
        return out

    def details(self, cands):
        """README excerpts for repositories, stars where missing, and a check that the other links open."""
        check = bool(self.cfg["scout"].get("check_links", True))

        def one(c):
            m = GH_REPO_RE.match(c["url"])
            if c["source"] == "github" and c.get("kind") == "repo" and m:
                owner, name = m.group(1), m.group(2)
                if c.get("stars") is None or not c.get("verified"):
                    st, hd, data = self.http.json(f"{GITHUB_API}/repos/{owner}/{name}", self.gh_headers)
                    if st != 200:
                        self.gh_api_problem(f"details of {owner}/{name}", st, hd)
                    elif isinstance(data, dict):
                        c.update(stars=int(data.get("stargazers_count") or 0), verified=True,
                                 description=c.get("description") or clip(data.get("description"), 300),
                                 license=(data.get("license") or {}).get("spdx_id") or "")
                if not c.get("excerpt"):
                    for fn in ("README.md", "readme.md", "README.rst", "README"):
                        st, _, body = self.http.get(f"{GITHUB_RAW}/{owner}/{name}/HEAD/{fn}")
                        if st == 200:
                            c["excerpt"] = clip(clean_markdown(body.decode("utf-8", "replace")), self.excerpt)
                            break
            elif check and not c.get("verified") and c["source"] == "web":
                st, hd, body = self.http.get(c["url"])
                c["verified"] = 200 <= st < 400
                if c["verified"] and not c.get("excerpt") and "html" in hd.get("content-type", ""):
                    c["excerpt"] = clip(html_to_text(body.decode("utf-8", "replace")), self.excerpt)
            return c

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            return list(pool.map(one, cands))

    def run(self, max_candidates=40):
        for step in (self.trending, self.github_search, self.watch, self.hn, self.search, self.wanted_news):
            try:
                step()
            except Exception as ex:  # noqa: BLE001 - one broken source never stops the run
                self.problem(f"{step.__name__}: {type(ex).__name__}: {ex}")
        found = len(self.cands)
        short = self.details(self.shortlist(max_candidates))
        return {"candidates": short, "found": found, "stats": self.stats, "xMode": self.x_mode,
                "problems": self.problems, "followups": self.followups, "state": self.state}


def collect(cfg, history, feedback, state=None, extra=(), http=None, now=None):
    c = Collector(cfg, history, feedback, state, extra, http, now)
    return c.run(int(cfg["scout"].get("max_candidates", 40)))
