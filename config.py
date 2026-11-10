"""Shared settings, LLM + Tavily clients, caching and request tracing."""
import os, re, json, time, threading
from dotenv import load_dotenv
from openai import OpenAI
from tavily import TavilyClient

load_dotenv()

# ---- Settings (override any of these in .env) ----
# Direct Groq (default):   nothing to set.
# Through Bifrost (Day 3): put these 4 lines in .env
#     LLM_BASE_URL=http://localhost:8080/v1
#     LLM_API_KEY=bifrost
#     GATEWAY_NAME=Bifrost
#     MODEL=groq/openai/gpt-oss-120b
#     COMPARE_MODELS=groq/openai/gpt-oss-120b,groq/openai/gpt-oss-20b,groq/qwen/qwen3.8-27b
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or "not-needed"
GATEWAY_NAME = os.getenv("GATEWAY_NAME", "Groq (direct)")
MODEL = os.getenv("MODEL", "openai/gpt-oss-120b")
COMPARE_MODELS = [
    m.strip()
    for m in os.getenv(
        "COMPARE_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b"
    ).split(",")
    if m.strip()
]

# Every call FreshCheck makes itself carries this header. The Bifrost FreshCheck
# plugin ignores requests that have it, so the plugin never checks our own
# internal calls (that would loop forever).
BIFROST_VK = os.getenv("BIFROST_VK", "")
_headers = {"X-FreshCheck-Skip": "1"}
if BIFROST_VK:
    _headers["x-bf-vk"] = BIFROST_VK  # Bifrost virtual key

llm = OpenAI(
    api_key=LLM_API_KEY,
    base_url=LLM_BASE_URL,
    default_headers=_headers,
)
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

LOCK = threading.RLock()

# 1 = add a second query aimed at possible updates/replacements; it does not guarantee useful or current results.
RECENCY_PROBE = os.getenv("RECENCY_PROBE", "1") != "0"


def explain_error(e):
    """Turn a scary Python error into one clear sentence (shown on the website)."""
    name = type(e).__name__
    msg = str(e)
    low = msg.lower()
    if name == "APIConnectionError" or "connection error" in low or "connection refused" in low:
        return (f"Could not connect to the configured LLM endpoint ({LLM_BASE_URL}). "
                "Check that the endpoint is reachable and the configured provider is running.")
    if "virtual_key" in low or "virtual key" in low:
        return "The configured gateway requires a virtual key. Check BIFROST_VK in .env and restart the server."
    if name in ("AuthenticationError", "PermissionDeniedError") or "invalid api key" in low:
        return "The configured LLM provider rejected its API key. Check the provider credentials in .env."
    if name == "NotFoundError" or "does not exist" in low:
        return f"The configured endpoint does not provide model {MODEL!r}. Check MODEL and the provider’s model names."
    if name == "RateLimitError" or "rate limit" in low or "429" in low:
        return "The configured LLM provider returned a rate limit. Wait before retrying and check its quota."
    if "usagelimit" in name.lower() or "credit" in low or "plan limit" in low:
        return "Tavily reported a usage or plan limit. Check the account’s available search quota."
    if "invalidapikey" in name.lower() or "missingapikey" in name.lower():
        return "Tavily rejected or could not find its API key. Check TAVILY_API_KEY in .env."
    if "timeout" in name.lower() or "timed out" in low:
        return "The request timed out. Check the configured service and try again when it is available."
    return f"{name}: {msg[:300]}"


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


# ---- Trace: records every step of one request (shown in the Gateway panel) ----
class Trace:
    def __init__(self):
        self.t0 = time.time()
        self.steps = []
        self.tokens = 0
        self.llm_calls = 0
        self.live_searches = 0
        self.cache_hits = 0
        self._lock = threading.Lock()

    def add(self, name, detail="", ms=0):
        with self._lock:
            self.steps.append({"name": name, "detail": detail, "ms": int(ms)})

    def summary(self):
        return {
            "gateway": GATEWAY_NAME,
            "base_url": LLM_BASE_URL,
            "model": MODEL,
            "steps": list(self.steps),
            "llm_calls": self.llm_calls,
            "tokens": self.tokens,
            "live_searches": self.live_searches,
            "cache_hits": self.cache_hits,
            "total_ms": int((time.time() - self.t0) * 1000),
        }


def parse_json(text):
    """Pull the first {...} block out of an LLM reply and parse it."""
    text = text or ""
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < 0:
        return {}
    try:
        parsed = json.loads(text[a : b + 1])
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def chat(messages, model=None, trace=None, label="LLM call", temperature=0, json_mode=False):
    model = model or MODEL
    t = time.time()
    kwargs = dict(model=model, messages=messages, temperature=temperature)
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        r = llm.chat.completions.create(**kwargs)
    except Exception:
        if not json_mode:
            raise
        kwargs.pop("response_format")  # some models/gateways do not support json mode
        r = llm.chat.completions.create(**kwargs)
    text = r.choices[0].message.content or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    usage = getattr(r, "usage", None)
    tokens = (getattr(usage, "total_tokens", 0) or 0) if usage else 0
    if trace is not None:
        trace.llm_calls += 1
        trace.tokens += tokens
        trace.add(label, f"{model} | {tokens} tokens", (time.time() - t) * 1000)
    return text


# ---- Tavily search with a file cache (saves credits) ----
CACHE_FILE = "cache.json"
_cache = load_json(CACHE_FILE, {})


def search(query, trace=None):
    t = time.time()
    if query in _cache:
        if trace is not None:
            trace.cache_hits += 1
            trace.add("Tavily search (cache)", query, (time.time() - t) * 1000)
        return _cache[query]
    res = tavily.search(query=query, max_results=5, search_depth="basic")["results"]
    with LOCK:
        _cache[query] = res
        save_json(CACHE_FILE, _cache)
    if trace is not None:
        trace.live_searches += 1
        trace.add("Tavily search (live)", query, (time.time() - t) * 1000)
    return res
