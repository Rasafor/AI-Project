from mcp.server.mcpserver import MCPServer

# This name is what any connecting client (like the MCP Inspector) will show
# for this server. No tools, resources, or prompts are defined yet.
mcp = MCPServer("ai-project-mcp-server")

if __name__ == "__main__":
    mcp.run()
