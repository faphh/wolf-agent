"""MCP Client — Connect to MCP servers and register their tools."""

import json
import subprocess
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPServerConnection:
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.transport = config.get("transport", "stdio")
        self.command = config.get("command", "")
        self.args = config.get("args", [])
        self.tools: List[Dict[str, Any]] = []
        self._process: Optional[subprocess.Popen] = None
        self._connected = False

    def connect(self) -> bool:
        if self.transport != "stdio" or not self.command:
            return False
        try:
            cmd = [self.command] + self.args
            self._process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )
            init_msg = json.dumps({
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "wolf", "version": "1.0.0"}},
            })
            self._process.stdin.write(init_msg + "\n")
            self._process.stdin.flush()
            response = self._process.stdout.readline()
            if response:
                self._connected = True
                self._discover_tools()
                return True
        except Exception as e:
            logger.error(f"MCP connect failed: {e}")
        return False

    def _discover_tools(self):
        if not self._connected or not self._process:
            return
        try:
            msg = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            self._process.stdin.write(msg + "\n")
            self._process.stdin.flush()
            response = self._process.stdout.readline()
            if response:
                data = json.loads(response)
                if "result" in data and "tools" in data["result"]:
                    self.tools = data["result"]["tools"]
                    logger.info(f"MCP {self.name}: {len(self.tools)} tools")
        except Exception as e:
            logger.error(f"MCP discovery failed: {e}")

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        if not self._connected or not self._process:
            return {"error": f"MCP {self.name} not connected"}
        try:
            msg = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                              "params": {"name": tool_name, "arguments": arguments}})
            self._process.stdin.write(msg + "\n")
            self._process.stdin.flush()
            response = self._process.stdout.readline()
            if response:
                data = json.loads(response)
                return data.get("result", {"error": data.get("error", "Unknown")})
        except Exception as e:
            return {"error": str(e)}

    def disconnect(self):
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
            self._connected = False


class MCPManager:
    def __init__(self):
        self.connections: Dict[str, MCPServerConnection] = {}

    def add_server(self, name: str, config: Dict[str, Any]) -> bool:
        conn = MCPServerConnection(name, config)
        if conn.connect():
            self.connections[name] = conn
            self._register_tools(conn)
            return True
        return False

    def _register_tools(self, conn: MCPServerConnection):
        from wolf.tools.registry import registry
        for tool in conn.tools:
            tool_name = f"mcp_{conn.name}_{tool['name']}"
            schema = {
                "description": tool.get("description", f"MCP tool from {conn.name}"),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            }
            def make_handler(c, tn):
                def handler(args, context=None):
                    original = tn.replace(f"mcp_{c.name}_", "")
                    return c.call_tool(original, args)
                return handler
            registry.register(name=tool_name, toolset=f"mcp-{conn.name}",
                              schema=schema, handler=make_handler(conn, tool_name), emoji="\U0001f50c")

    def list_servers(self):
        return [{"name": n, "tools": len(c.tools), "connected": c._connected}
                for n, c in self.connections.items()]

    def disconnect_all(self):
        for c in self.connections.values():
            c.disconnect()


mcp_manager = MCPManager()
