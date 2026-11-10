"""
Minimal MCP (Model Context Protocol) server for FreshCheck.

It speaks the "Streamable HTTP" transport in its simplest form: the client POSTs JSON-RPC
messages to /mcp and we answer with plain JSON. This lets the Bifrost MCP Gateway
register FreshCheck as an MCP server, so any model behind Bifrost can call the
`check_freshness` tool to review candidate time-sensitive claims using search-result snippets and LLM suggestions.

No extra libraries needed. `handle_rpc` is a pure function so it is easy to test.
"""

SUPPORTED_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

TOOL = {
    "name": "check_freshness",
    "description": (
        "Extracts candidate time-sensitive claims, searches Tavily, and asks an LLM for experimental review suggestions. "
        "Returns model labels (fresh / stale / unclear), a fixed heuristic score (not a probability), possible replacement wording, "
        "and source links. A quote is matched against returned search-result text only; the original page is not opened or authenticated. "
        "Claims may be missed and results can be wrong. Treat all output as a prompt to inspect the original sources, not as verification."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The answer or statement to review for candidate time-sensitive claims (a few sentences).",
            }
        },
        "required": ["text"],
    },
}

SERVER_INFO = {"name": "freshcheck", "version": "1.0.0"}
INSTRUCTIONS = (
    "FreshCheck returns experimental LLM review suggestions based on search-result snippets; it does not verify facts or open original pages. "
    "Use check_freshness as a prompt to inspect sources, not as proof of truth or currentness."
)


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def format_result(fc):
    """Turn FreshCheck's payload into a short text the model can read."""
    claims = fc.get("claims", [])
    if not claims:
        return "No candidate claims were returned. The extractor may have missed time-sensitive claims; this is not evidence that the text is current."
    lines = [
        "Experimental heuristic score (not confidence): %s/100 (model labels: %s suggests fresh, %s possibly stale, %s unclear)"
        % (fc.get("score"), fc.get("fresh"), fc.get("stale"), fc.get("unclear"))
    ]
    for c in claims:
        verdict = str(c.get("verdict", "")).upper()
        line = "- LLM label %s (suggestion only): %s" % (verdict, c.get("claim", ""))
        if verdict != "FRESH" and c.get("correct_value"):
            line += " -> Model-suggested value (check source): %s" % c["correct_value"]
        if c.get("source_url"):
            line += " (source: %s)" % c["source_url"]
        lines.append(line)
    if fc.get("stale"):
        lines.append("Some snippets may contradict claims. Inspect the linked original pages before deciding whether to revise the answer.")
    return "\n".join(lines)


def handle_rpc(msg, check_fn):
    """
    Handle ONE JSON-RPC message.
    check_fn(text) -> FreshCheck payload dict (score, fresh, stale, unclear, claims).
    Returns a response dict, or None when no response is needed (notifications/client responses).
    """
    if not isinstance(msg, dict):
        return _err(None, -32600, "Invalid Request")

    # A JSON-RPC response from the client has no method and is ignored.
    if "method" not in msg:
        if "result" in msg or "error" in msg:
            return None
        return _err(msg.get("id"), -32600, "Invalid Request")

    method = msg.get("method")
    if not isinstance(method, str) or msg.get("jsonrpc") != "2.0":
        return _err(msg.get("id"), -32600, "Invalid Request")

    # JSON-RPC notifications have no id and must not receive a response.
    if "id" not in msg:
        return None

    mid = msg["id"]
    if isinstance(mid, (dict, list, bool)):
        return _err(None, -32600, "Invalid Request")

    params = msg.get("params", {})
    if not isinstance(params, dict):
        return _err(mid, -32602, "Invalid params")

    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if isinstance(asked, str) and asked in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return _ok(mid, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        })

    if method == "ping":
        return _ok(mid, {})

    if method == "tools/list":
        return _ok(mid, {"tools": [TOOL]})

    if method == "tools/call":
        name = params.get("name")
        if name != TOOL["name"]:
            return _err(mid, -32602, "Unknown tool: %s" % name)
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _err(mid, -32602, "Invalid params: arguments must be an object")
        text = arguments.get("text")
        if not isinstance(text, str) or not text.strip():
            return _ok(mid, {
                "content": [{"type": "text", "text": "Error: 'text' must be a non-empty string."}],
                "isError": True,
            })
        try:
            out = format_result(check_fn(text.strip()))
            return _ok(mid, {"content": [{"type": "text", "text": out}], "isError": False})
        except Exception:  # keep provider/library diagnostics out of remote MCP output
            return _ok(mid, {
                "content": [{"type": "text", "text": "FreshCheck could not return review suggestions. Check the server diagnostics."}],
                "isError": True,
            })

    return _err(mid, -32601, "Method not found: %s" % method)


def handle_batch(messages, check_fn):
    """Handle a JSON-RPC batch; an empty batch is itself an invalid request."""
    if not isinstance(messages, list):
        return [_err(None, -32600, "Invalid Request")]
    if not messages:
        return [_err(None, -32600, "Invalid Request")]
    return [response for response in (handle_rpc(message, check_fn) for message in messages)
            if response is not None]
