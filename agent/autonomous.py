"""Bounded autonomous coding loop for Penthos."""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class AgentStep:
    action: str
    result: str
    success: bool = True


@dataclass
class AgentRun:
    request: str
    steps: list[AgentStep] = field(default_factory=list)
    completed: bool = False
    iterations: int = 0

    def add(self, action, result, success=True):
        self.steps.append(
            AgentStep(
                action=action,
                result=result,
                success=success,
            )
        )


class AutonomousCodingEngine:
    """Execution coordinator.

    The model remains responsible for deciding what to do.
    This engine provides bounded execution and verification.
    """

    def __init__(
        self,
        agent,
        max_iterations=6,
    ):
        self.agent = agent
        self.max_iterations = max_iterations

    def inspect(self, request):
        """Collect compact repository information."""

        context = self.agent.execute_tool(
            "project_context"
        )

        return context

    def run_command(self, command):
        """Execute a verification command."""

        return self.agent.execute_tool(
            "shell_exec",
            command=command,
        )

    def execute(
        self,
        request: str,
        verify_command: str | None = None,
        on_iteration: Callable | None = None,
    ):
        run = AgentRun(request=request)

        context = self.inspect(request)

        run.add(
            "inspect_repository",
            str(context),
        )

        if on_iteration:
            on_iteration(run)

        if not verify_command:
            run.completed = True
            return run

        for iteration in range(
            1,
            self.max_iterations + 1,
        ):
            run.iterations = iteration

            result = self.run_command(
                verify_command
            )

            success = bool(
                isinstance(result, dict)
                and result.get("success")
            )

            output = str(result)

            run.add(
                f"verify_{iteration}",
                output,
                success,
            )

            if on_iteration:
                on_iteration(run)

            if success:
                run.completed = True
                break

        return run
