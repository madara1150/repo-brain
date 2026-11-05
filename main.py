"""Repo Brain: run the desktop app, or the MCP server with --mcp (started by Claude Desktop)."""
import sys


def main():
    args = sys.argv[1:]
    if "--mcp" in args:
        from app.mcp_server import run
        run()
        return 0
    if "--selftest" in args:
        from app.selftest import run as selftest
        return selftest()
    if "--sync" in args:  # headless update, handy for scripts and CI
        from app.cli import sync_cli
        return sync_cli()
    from app.ui.main_window import run_app
    return run_app()


if __name__ == "__main__":
    sys.exit(main())
