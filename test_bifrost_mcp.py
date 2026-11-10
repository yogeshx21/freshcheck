# Live integration smoke test: Bifrost -> model -> FreshCheck MCP; Tavily may return cached search snippets.
# Run:  py test_bifrost_mcp.py
# Needs: Bifrost (port 8080) and FreshCheck (port 8000) running, and BIFROST_VK in .env
import json
import os

import requests
from dotenv import load_dotenv

load_dotenv()
VK = os.getenv("BIFROST_VK", "")
MODEL = os.getenv("MODEL", "groq/openai/gpt-oss-120b")

headers = {
    "Content-Type": "application/json",
    # opt in to the FreshCheck tool for THIS request only (format: clientName-toolName)
    "x-bf-mcp-include-tools": "freshcheck-check_freshness",
}
if VK:
    headers["x-bf-vk"] = VK

body = {
    "model": MODEL,
    "messages": [{
        "role": "user",
        "content": ("Is Python 3.12 the latest Python version? "
                    "Use FreshCheck's review suggestions, and inspect their limits before answering."),
    }],
}

print("Bifrost ko request bhej raha hoon (1-2 minute lag sakte hain)...")
r = requests.post("http://localhost:8080/v1/chat/completions", headers=headers,
                  data=json.dumps(body), timeout=300)
print("HTTP status:", r.status_code)
try:
    data = r.json()
except Exception:
    print(r.text[:800])
    raise SystemExit(1)

if "choices" not in data:
    print(json.dumps(data, indent=2)[:1500])
    raise SystemExit(1)

choice = data["choices"][0]
msg = choice["message"]
print("finish_reason:", choice.get("finish_reason"))
calls = msg.get("tool_calls") or []
if calls:
    print("Model ne tool bulaya (auto-execute abhi OFF hai):")
    for c in calls:
        print("  -", c["function"]["name"], c["function"]["arguments"][:200])
print("--- jawab ---")
print((msg.get("content") or "")[:1500])
