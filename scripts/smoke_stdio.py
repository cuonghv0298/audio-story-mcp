"""Khởi động server qua stdio như Claude Code và gọi vài tool (cần VieNeu đang chạy cho list_voices)."""
import asyncio
import os
import sys

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main() -> None:
    params = StdioServerParameters(command="uv", args=["run", "--quiet", "audio-story-mcp"], env=dict(os.environ))
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        tools = await s.list_tools()
        print("tools:", [t.name for t in tools.tools])
        for name, args in [("doctor", {}), ("list_voices", {}), ("run_status", {"run": "khong-co"})]:
            res = await s.call_tool(name, args)
            text = res.content[0].text if res.content else ""
            print(f"{name}: isError={res.is_error if hasattr(res, 'is_error') else res.isError} {text[:160]!r}")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
