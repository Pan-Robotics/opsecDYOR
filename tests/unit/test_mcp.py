"""Tests for the DYOR MCP server — tool registration + offline tools.

(analyze_token / resolve_token / narratives / compare_tokens hit the network, so
they're not unit-tested here; the underlying functions are covered elsewhere.)
"""

import asyncio

from dyor import mcp_server


def test_expected_tools_registered():
    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {"analyze_token", "resolve_token", "compare_tokens",
            "narratives", "asset_classes", "methodology"} <= names


def test_tools_have_descriptions():
    # the LLM picks tools by their docstring — every tool must describe itself
    tools = asyncio.run(mcp_server.mcp.list_tools())
    for t in tools:
        assert t.description and len(t.description) > 30, t.name


def test_analyze_token_has_input_schema():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    schema = tools["analyze_token"].inputSchema
    assert "query" in schema["properties"]
    assert "peer_mode" in schema["properties"]


def test_methodology_tool_offline():
    m = mcp_server.methodology()
    assert "weights" in m and "tiers" in m and "gates" in m
    assert m["disclaimer"].lower().startswith("research aid")
    assert any(g["key"] == "price_to_fees" for g in m["glossary"])


def test_asset_classes_tool_offline():
    c = mcp_server.asset_classes()
    names = {x["name"] for x in c["classes"]}
    assert {"defi", "l1", "monetary", "meme", "stablecoin"} <= names
