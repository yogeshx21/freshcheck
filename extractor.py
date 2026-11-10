from config import chat, parse_json

TYPES = {"pricing", "version", "leadership", "law", "stat", "other"}
MAX_CLAIM_CHARS = 500
MAX_QUERY_CHARS = 300
MAX_EXACT_TEXT_CHARS = 1000

PROMPT = """You are a fact-extraction engine. Below is an AI's answer.
Extract ONLY facts that can change with time: prices, version numbers, "latest/current" claims,
who holds a role (CEO, minister, etc.), laws and rules, release dates, statistics, rankings.

For every such fact return:
- "claim": the fact in one short line, in the same language as the answer
- "exact_text": the shortest EXACT substring copied character-for-character from the answer that states this fact
- "type": one of pricing | version | leadership | law | stat | other
- "search_query": a short English web-search query (3-8 words) that may find current source material to review. The result is not guaranteed to establish the truth.
  Do NOT put the claimed value in the query.
  For laws, rules, "main", "latest" or "currently" claims, end the query with: current status replaced 2026
Return ONLY JSON: {"claims":[{"claim":"","exact_text":"","type":"","search_query":""}]}
Maximum 8 claims. If there are none, return {"claims":[]}.

ANSWER:
"""


def extract_claims(answer, trace=None):
    raw = chat(
        [{"role": "user", "content": PROMPT + answer}],
        trace=trace,
        label="Extract claims",
        json_mode=True,
    )
    data = parse_json(raw)
    claims = data.get("claims", []) if isinstance(data, dict) else []
    clean = []
    for c in claims if isinstance(claims, list) else []:
        if not isinstance(c, dict):
            continue
        claim = c.get("claim")
        query = c.get("search_query")
        if not isinstance(claim, str) or not claim.strip() or len(claim) > MAX_CLAIM_CHARS:
            continue
        if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
            continue
        kind = c.get("type")
        exact = c.get("exact_text")
        clean.append({
            "claim": claim.strip(),
            "search_query": query.strip(),
            "type": kind if isinstance(kind, str) and kind in TYPES else "other",
            "exact_text": exact if isinstance(exact, str) and len(exact) <= MAX_EXACT_TEXT_CHARS else "",
        })
    return clean[:8]


if __name__ == "__main__":
    sample = (
        "Claude Opus 4.8 costs $5 per million input tokens. "
        "Anthropic ka CEO Dario Amodei hai. Python 3.12 latest version hai."
    )
    for c in extract_claims(sample):
        print(c)
