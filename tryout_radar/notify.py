"""Send a short Markdown message to every channel in config.toml [[notify]].

Supported types: wecom_webhook, wecom_app, feishu_webhook, telegram, slack_webhook, discord_webhook.
Secrets come from environment variables named in the config (e.g. key_env = "WECOM_WEBHOOK_KEY")."""
import json
import re
import time
import urllib.parse
import urllib.request

from .config import env
from .mdlite import LINK_RE, to_plain


def _post(url, body, timeout=20):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {"raw": raw[:200]}


def _get(url, timeout=20):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def chunks(text, limit, measure=lambda s: len(s.encode("utf-8"))):
    out, buf = [], ""
    for line in text.split("\n"):
        while measure(line) > limit:
            cut = max(1, limit // 4)
            out.append(line[:cut])
            line = line[cut:]
        if measure(buf + line + "\n") > limit:
            out.append(buf.rstrip())
            buf = ""
        buf += line + "\n"
    if buf.strip():
        out.append(buf.rstrip())
    return [c for c in out if c.strip()]


def _need(ch, *names):
    vals = []
    for n in names:
        v = env(ch.get(n))
        if not v:
            raise RuntimeError(f"environment variable {ch.get(n) or '(' + n + ' not set in config)'} is empty")
        vals.append(v)
    return vals


def _wecom_check(r):
    if r.get("errcode", 0):
        raise RuntimeError(f"WeCom error {r.get('errcode')}: {r.get('errmsg')}")


def send_wecom_webhook(ch, md):
    (key,) = _need(ch, "key_env")
    url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=" + urllib.parse.quote(key)
    for part in chunks(md, 4000):
        _wecom_check(_post(url, {"msgtype": "markdown", "markdown": {"content": part}}))
        time.sleep(0.4)


def send_wecom_app(ch, md):
    corp, secret, to_user = _need(ch, "corp_id_env", "secret_env", "to_user_env")
    r = _get("https://qyapi.weixin.qq.com/cgi-bin/gettoken?" + urllib.parse.urlencode({"corpid": corp, "corpsecret": secret}))
    _wecom_check(r)
    url = "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=" + r["access_token"]
    for part in chunks(md, 2000):
        _wecom_check(_post(url, {"touser": to_user, "msgtype": "markdown", "agentid": int(ch["agent_id"]),
                                 "markdown": {"content": part}}))
        time.sleep(0.4)


def send_feishu_webhook(ch, md):
    (url,) = _need(ch, "url_env")
    for part in chunks(to_plain(md), 4000):
        r = _post(url, {"msg_type": "text", "content": {"text": part}})
        if r.get("code", 0):
            raise RuntimeError(f"Feishu error {r.get('code')}: {r.get('msg')}")


def send_telegram(ch, md):
    token, chat = _need(ch, "token_env", "chat_id_env")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for part in chunks(to_plain(md), 4000, measure=len):
        r = _post(url, {"chat_id": chat, "text": part, "disable_web_page_preview": True})
        if not r.get("ok", False):
            raise RuntimeError(f"Telegram error: {r.get('description')}")


def send_slack_webhook(ch, md):
    (url,) = _need(ch, "url_env")
    text = LINK_RE.sub(r"<\2|\1>", re.sub(r"</?font[^>]*>", "", md)).replace("**", "*")
    for part in chunks(text, 3500, measure=len):
        _post(url, {"text": part})


def send_discord_webhook(ch, md):
    (url,) = _need(ch, "url_env")
    for part in chunks(re.sub(r"</?font[^>]*>", "", md), 1900, measure=len):
        _post(url, {"content": part, "allowed_mentions": {"parse": []}})
        time.sleep(0.4)


SENDERS = {"wecom_webhook": send_wecom_webhook, "wecom_app": send_wecom_app, "feishu_webhook": send_feishu_webhook,
           "telegram": send_telegram, "slack_webhook": send_slack_webhook, "discord_webhook": send_discord_webhook}


def send_all(cfg, md):
    """Returns [(channel_type, ok, message)]. Never raises."""
    results = []
    for ch in cfg.get("notify", []):
        typ = ch.get("type")
        fn = SENDERS.get(typ)
        if not fn:
            results.append((typ, False, "unknown channel type"))
            continue
        try:
            fn(ch, md)
            results.append((typ, True, "sent"))
        except Exception as e:  # noqa: BLE001 - report every failure, keep going
            results.append((typ, False, f"{type(e).__name__}: {e}"))
    return results
