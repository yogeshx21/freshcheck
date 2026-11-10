"""Offline tests for malformed JSON-RPC input handling."""
import unittest
from mcp_server import handle_batch, handle_rpc


def rpc(method, params=None, request_id=1, **extra):
    msg = {"jsonrpc": "2.0", "method": method, "id": request_id}
    if params is not None:
        msg["params"] = params
    msg.update(extra)
    return msg


class McpProtocolTests(unittest.TestCase):
    def test_initialize_with_non_object_params_is_invalid_params(self):
        response = handle_rpc(rpc("initialize", []), lambda _: {})
        self.assertEqual(response["error"]["code"], -32602)

    def test_initialize_with_unexpected_protocol_version_type_falls_back(self):
        response = handle_rpc(rpc("initialize", {"protocolVersion": []}), lambda _: {})
        self.assertEqual(response["result"]["protocolVersion"], "2025-06-18")

    def test_tools_call_with_non_object_params_is_invalid_params(self):
        response = handle_rpc(rpc("tools/call", ["bad"]), lambda _: {})
        self.assertEqual(response["error"]["code"], -32602)

    def test_tools_call_with_non_object_arguments_is_invalid_params(self):
        response = handle_rpc(rpc("tools/call", {"name": "check_freshness", "arguments": "bad"}), lambda _: {})
        self.assertEqual(response["error"]["code"], -32602)

    def test_tools_call_with_non_text_argument_returns_tool_error_not_500(self):
        response = handle_rpc(rpc("tools/call", {"name": "check_freshness", "arguments": {"text": ["bad"]}}), lambda _: {})
        self.assertTrue(response["result"]["isError"])
        self.assertIn("non-empty string", response["result"]["content"][0]["text"])

    def test_tool_failure_does_not_echo_exception_details(self):
        def fail(_):
            raise RuntimeError("provider secret=do-not-disclose")
        response = handle_rpc(rpc("tools/call", {"name": "check_freshness", "arguments": {"text": "hello"}}), fail)
        text = response["result"]["content"][0]["text"]
        self.assertTrue(response["result"]["isError"])
        self.assertNotIn("do-not-disclose", text)
        self.assertIn("server diagnostics", text)

    def test_valid_text_is_trimmed_before_tool_call(self):
        seen = []
        response = handle_rpc(rpc("tools/call", {"name": "check_freshness", "arguments": {"text": "  hello  "}}),
                              lambda text: seen.append(text) or {"claims": []})
        self.assertEqual(seen, ["hello"])
        self.assertFalse(response["result"]["isError"])

    def test_client_response_is_ignored(self):
        self.assertIsNone(handle_rpc({"jsonrpc": "2.0", "id": 1, "result": {}}, lambda _: {}))

    def test_object_without_method_or_response_is_invalid_request(self):
        response = handle_rpc({"jsonrpc": "2.0", "id": 1}, lambda _: {})
        self.assertEqual(response["error"]["code"], -32600)

    def test_notification_has_no_response(self):
        self.assertIsNone(handle_rpc({"jsonrpc": "2.0", "method": "ping"}, lambda _: {}))

    def test_wrong_jsonrpc_version_is_invalid_request(self):
        response = handle_rpc({"jsonrpc": "1.0", "method": "ping", "id": 1}, lambda _: {})
        self.assertEqual(response["error"]["code"], -32600)

    def test_empty_batch_is_invalid_request(self):
        responses = handle_batch([], lambda _: {})
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["error"]["code"], -32600)

    def test_batch_of_notifications_has_no_responses(self):
        self.assertEqual(handle_batch([{"jsonrpc": "2.0", "method": "ping"}], lambda _: {}), [])


if __name__ == "__main__":
    unittest.main()
