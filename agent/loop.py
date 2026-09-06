"""Agent loop foundation.

The model-facing tool-calling protocol will be connected here.
"""

from agent.core import PenthosAgent


class AgentLoop:
    def __init__(self, project_root="."):
        self.agent = PenthosAgent(project_root)

    def available_tools(self):
        return self.agent.tool_descriptions()

    def call_tool(self, name, **kwargs):
        return self.agent.execute_tool(name, **kwargs)
