"""Talk to any chat model through the OpenAI-compatible Chat Completions API (standard library only).

Nearly every provider and local runner offers this API: OpenAI, DeepSeek, Qwen (DashScope), Kimi, GLM, Doubao,
Gemini, Claude, OpenRouter, Ollama, LM Studio, vLLM. config.toml:

    [model]
    base_url = "https://api.deepseek.com/v1"   # the part before /chat/completions
    model = "deepseek-chat"
    api_key_env = "DEEPSEEK_API_KEY"           # name of the environment variable; empty for local runners

The model only ever receives text and returns text (JSON). It gets no tools and nothing it writes is executed."""
import json
import re
import time
import urllib.error
import urllib.request

from .config import env

USER_AGENT = "tryout-radar"


class ModelError(RuntimeError):
    pass


def settings(cfg):
    m = dict(cfg.get("model") or {})
    if not str(m.get("base_url") or "").startswith(("http://", "https://")) or not m.get("model"):
        raise ModelError("No model set up. Add [model] base_url and model to config.toml "
                         "(see config.example.toml), or run the scout with a coding agent instead.")
    return m


def extract_json(text):
    """The first JSON object in a model reply: tolerates <think> blocks, ```json fences and text around it."""
    s = re.sub(r"<think>.*?</think>", "", str(text or ""), flags=re.S).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    try:
        out = json.loads(s)
        if isinstance(out, dict):
            return out
    except ValueError:
        pass
    start = s.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        out = json.loads(s[start:i + 1])
                        if isinstance(out, dict):
                            return out
                    except ValueError:
                        pass
                    break
        start = s.find("{", start + 1)
    raise ValueError("no JSON object in the reply")


class Client:
    def __init__(self, cfg):
        m = settings(cfg)
        self.url = str(m["base_url"]).rstrip("/") + "/chat/completions"
        self.model = str(m["model"])
        self.key = env(m.get("api_key_env")) or ""
        if m.get("api_key_env") and not self.key:
            raise ModelError(f"environment variable {m['api_key_env']} (model.api_key_env) is empty")
        self.temperature = float(m.get("temperature", 0.2))
        self.timeout = float(m.get("timeout", 180))
        self.json_mode = bool(m.get("json_mode", True))
        self.max_tokens = int(m.get("max_tokens") or 0)
        self.retries = int(m.get("retries", 3))
        self.calls = 0

    def _post(self, body):
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def chat(self, system, user):
        """One reply as text. Retries rate limits and server errors; drops JSON mode once if the provider refuses it."""
        body = {"model": self.model, "temperature": self.temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.max_tokens:
            body["max_tokens"] = self.max_tokens
        attempt = 0
        while True:
            if self.json_mode:
                body["response_format"] = {"type": "json_object"}
            else:
                body.pop("response_format", None)
            wait = 0
            try:
                self.calls += 1
                res = self._post(body)
                choice = (res.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get("content")
                if not text:
                    raise ModelError(f"empty reply ({choice.get('finish_reason') or res.get('error') or 'no choices'})")
                return text
            except urllib.error.HTTPError as ex:
                detail = ex.read().decode("utf-8", "replace")[:300]
                last = ModelError(f"HTTP {ex.code} from {self.url}: {detail}")
                if ex.code == 400 and self.json_mode:
                    self.json_mode = False          # some providers or models don't support response_format
                    continue
                if ex.code in (400, 401, 403, 404):
                    raise last from None
                wait = float(ex.headers.get("Retry-After") or 0) if ex.headers else 0
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as ex:
                last = ModelError(f"cannot reach {self.url}: {ex}")
            attempt += 1
            if attempt > self.retries:
                raise last
            time.sleep(min(60, wait or 2 ** attempt * 3))

    def ask_json(self, system, user, check=None):
        """A JSON object from the model. `check(obj)` may raise ValueError; then the model gets one chance to fix it."""
        text = self.chat(system, user)
        try:
            obj = extract_json(text)
            if check:
                check(obj)
            return obj
        except ValueError as ex:
            fix = (f"{user}\n\nYour previous reply could not be used ({ex}). Reply again with only the JSON object "
                   f"described above, nothing before or after it.")
            obj = extract_json(self.chat(system, fix))
            if check:
                check(obj)
            return obj
