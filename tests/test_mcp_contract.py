import os
import unittest
from unittest.mock import patch

os.environ.setdefault("X_AGENT_DEBUG_LOG", "/tmp/x-agent-test.log")

from x_agent import mcp_http, mcp_server


class McpContractTest(unittest.TestCase):
    def test_article_draft_publish_tool_is_exposed(self):
        names = {tool["name"] for tool in mcp_server.TOOLS}
        self.assertIn("create_x_article", names)
        self.assertIn("publish_x_article_draft", names)

    def test_default_http_port_is_loopback_port(self):
        self.assertEqual(mcp_http.HOST, "127.0.0.1")
        self.assertEqual(mcp_http.PORT, 8765)

    def test_invalid_http_port_is_rejected(self):
        with patch.dict(os.environ, {"X_AGENT_MCP_PORT": "not-a-port"}):
            with self.assertRaisesRegex(RuntimeError, "must be an integer"):
                mcp_http._configured_port()

    def test_security_headers_prevent_caching_and_framing(self):
        self.assertEqual(mcp_http.SECURITY_HEADERS["Cache-Control"], "no-store")
        self.assertEqual(mcp_http.SECURITY_HEADERS["X-Frame-Options"], "DENY")
