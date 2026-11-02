"""Gọi tool qua lớp MCP (không qua stdio) — kiểm đăng ký tool và đổi lỗi thành ToolError."""

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from audio_story import server

EXPECTED = {"fetch_source", "transcribe", "run_status", "list_runs", "check_script", "list_voices", "tts_preview",
            "tts_render", "qa_audio", "assemble_audio", "doctor"}


def test_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED
    assert all(t.description for t in tools)


def test_tool_flow_and_errors(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("Ngày xưa có một cô bé.\n\nCô bé đi vào rừng.", encoding="utf-8")
    out = server.fetch_source(str(f))
    run = out["run_dir"]
    assert server.transcribe(run)["segments"] == 2
    st = server.run_status(run)
    assert st["next"].startswith("write_story")
    assert server.list_runs()[0]["run_dir"] == run
    res = server.check_script(run)  # chưa có cast/script → lỗi schema, không ném
    assert not res["ok"] and res["voices_checked"] is False
    with pytest.raises(ToolError, match="check_script còn lỗi"):
        server.tts_render(run)
    with pytest.raises(ToolError, match="không thấy thư mục run"):
        server.run_status("khong-ton-tai")
    with pytest.raises(ToolError, match="VieNeu chưa chạy"):
        server.list_voices()
