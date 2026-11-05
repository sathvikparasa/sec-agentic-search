"""Run the EDGAR MCP server.

  python -m edgar_mcp          # stdio (for `docker compose exec -T mcp python -m edgar_mcp`)
  python -m edgar_mcp --http   # streamable HTTP on 0.0.0.0:8000/mcp (the `mcp` service)
"""

import argparse

from mcp.server.transport_security import TransportSecuritySettings

from edgar_mcp.server import mcp


def main() -> None:
    ap = argparse.ArgumentParser(prog="edgar_mcp")
    ap.add_argument("--http", action="store_true", help="serve streamable HTTP instead of stdio")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if not args.http:
        mcp.run("stdio")
        return
    # Bound to 0.0.0.0 inside the container; compose publishes it on 127.0.0.1 only.
    # Keep DNS-rebinding protection on, allowing the names clients actually use.
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost:*", "127.0.0.1:*", "[::1]:*", "mcp:*", "localhost", "127.0.0.1"],
        allowed_origins=["http://localhost:*", "http://127.0.0.1:*", "http://[::1]:*"],
    )
    mcp.run(
        "streamable-http",
        host="0.0.0.0",
        port=args.port,
        streamable_http_path="/mcp",
        # Stateless + JSON: no server-side sessions, so the auto-reloader restarting the
        # process after you edit a tool doesn't break your agent's connection.
        stateless_http=True,
        json_response=True,
        transport_security=security,
    )


if __name__ == "__main__":
    main()
