"""Demo se pehle ek baar chalao: 5 demo buttons + 1 compare ko pehle se chala deta hai,
taaki unke results cache mein save ho jayein aur demo ke time turant khulein.

Pehle FreshCheck server (uvicorn) aur configured LLM provider chalu hone chahiye; Bifrost tabhi zaroori hai jab usi ko configure kiya ho.
Chalao:   py warm_demo.py
"""
import sys, time
import requests

BASE = "http://127.0.0.1:8000"

# index.html ke 5 demo buttons wahi text (same order)
DEMOS = [
    ("Price trap", "Claude Opus 4.8 costs $5 per million input tokens. GPT-4 costs $30 per million input tokens."),
    ("CEO trap", "The CEO of Intel is Pat Gelsinger. The CEO of Twitter is Parag Agrawal."),
    ("Version trap", "Python 3.12 is the latest version of Python. Node.js 18 is the current LTS release."),
    ("Law trap (India)", "In India, the Indian Penal Code (IPC) is the main criminal law, and CrPC governs criminal procedure."),
    ("Tech trap", "The latest iPhone is the iPhone 14. ChatGPT runs on GPT-3.5."),
]
COMPARE_Q = "What is the latest Python version and who is Anthropic's CEO?"


def post(path, text, timeout=300):
    r = requests.post(BASE + path, json={"text": text}, timeout=timeout)
    if r.status_code != 200:
        try:
            msg = r.json().get("detail")
        except Exception:
            msg = r.text[:200]
        raise RuntimeError(f"HTTP {r.status_code}: {msg}")
    return r.json()


def main():
    try:
        h = requests.get(BASE + "/health", timeout=10).json()
    except Exception:
        print("FreshCheck server nahi mila. Pehle: py -m uvicorn server:app --reload")
        sys.exit(1)
    print(f"Gateway: {h['gateway']}  endpoint_reachable={h['gateway_ok']}  model={h['model']}")
    if not h["gateway_ok"]:
        print("Configured LLM endpoint is not reachable at its configured URL.")
        sys.exit(1)

    print("\n== 5 demos ==")
    for name, text in DEMOS:
        t = time.time()
        try:
            d = post("/check", text)
            s = d["summary"]
            tag = "cache" if d.get("cached") else f"{time.time() - t:.0f}s"
            print(f"[OK ] {name:<18} score {s['avg']:>3}  fresh {s['fresh']} stale {s['stale']} unclear {s['unclear']}  ({tag})")
            for c in d["claims"]:
                print(f"        {c['verdict'].upper():<8} {c['freshness_score']:>3}  {c['claim'][:70]}")
        except Exception as e:
            print(f"[ERR] {name:<18} {e}")

    print("\n== compare models ==")
    try:
        d = post("/compare", COMPARE_Q, timeout=600)
        for m in d["models"]:
            if m["error"]:
                print(f"[ERR] {m['model']}: {m['error'][:90]}")
            else:
                print(f"[OK ] {m['model']:<34} score {m['summary']['avg']:>3}")
        print("Failed model aaye to .env ki COMPARE_MODELS se use hata do.")
    except Exception as e:
        print(f"[ERR] compare: {e}")

    print("\nHo gaya. Ab demo buttons turant chalenge (cache badge dikhega).")


if __name__ == "__main__":
    main()
