"""Penthos agent execution loop."""

from agent.core import PenthosAgent
from agent.protocol import tool_prompt, parse_tool_call, tool_result


class AgentLoop:
    def __init__(self, project_root="."):
        self.agent = PenthosAgent(project_root)

    def available_tools(self):
        return self.agent.tool_descriptions()

    def call_tool(self, name, **kwargs):
        return self.agent.execute_tool(name, **kwargs)

    def build_tool_context(self):
        return tool_prompt(self.available_tools())

    def process_model_output(self, text):
        """Return a parsed tool call or None."""

        return parse_tool_call(text)

    def execute_model_tool_call(self, text):
        call = self.process_model_output(text)

        if call is None:
            return None

        try:
            result = self.call_tool(
                call["name"],
                **call["arguments"],
            )

            return {
                "name": call["name"],
                "success": True,
                "result": result,
                "message": tool_result(
                    call["name"],
                    result,
                ),
            }

        except Exception as exc:
            return {
                "name": call["name"],
                "success": False,
                "result": str(exc),
                "message": tool_result(
                    call["name"],
                    f"Tool execution failed: {exc}",
                ),
            }
