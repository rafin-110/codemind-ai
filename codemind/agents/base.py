"""Common agent wrapper: every run is timed and logged on the shared context."""

from __future__ import annotations

from dataclasses import dataclass, field

from codemind.models import AgentLogEntry, WorkflowContext, utc_now


@dataclass
class AgentOutput:
    summary: str
    outputs: list[str] = field(default_factory=list)


class Agent:
    name = "Agent"
    role = ""

    def run(self, ctx: WorkflowContext, **kwargs) -> AgentOutput:  # pragma: no cover - interface
        raise NotImplementedError

    def execute(self, ctx: WorkflowContext, **kwargs) -> AgentOutput:
        started = utc_now()
        before = ctx.state.value
        try:
            result = self.run(ctx, **kwargs)
        except Exception as exc:
            ctx.log.append(AgentLogEntry(self.name, started, utc_now(), before, ctx.state.value,
                                         "failed", (), f"{type(exc).__name__}: {exc}"))
            raise
        ctx.log.append(AgentLogEntry(self.name, started, utc_now(), before, ctx.state.value,
                                     result.summary, tuple(result.outputs)))
        return result
