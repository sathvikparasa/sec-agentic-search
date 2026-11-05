-- Read-only role used by the MCP server, baseline and evals.
-- Local-only credentials: the database is not published outside the compose network.
CREATE ROLE mcp_reader LOGIN PASSWORD 'mcp_reader';
ALTER ROLE mcp_reader SET statement_timeout = '5s';
ALTER ROLE mcp_reader SET default_transaction_read_only = on;
ALTER ROLE mcp_reader SET idle_in_transaction_session_timeout = '30s';
