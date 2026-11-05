"""Console entry for the Windows MCP twin (RepoBrainMCP.exe); Claude Desktop starts it."""
import sys

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        from app.selftest import run as selftest
        sys.exit(selftest())
    from app.mcp_server import run
    run()
