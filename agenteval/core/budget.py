"""Wall-clock and token budget caps, enforced by the broker — not something
an agent can extend or reset from inside a run.
"""

import time


class BudgetExceeded(RuntimeError):
    pass


class RunBudget:
    def __init__(self, wall_clock_seconds: float, token_budgets: dict[str, int]):
        self.wall_clock_seconds = wall_clock_seconds
        self.token_budgets = dict(token_budgets)
        self._spent: dict[str, int] = dict.fromkeys(token_budgets, 0)
        self._start = time.monotonic()

    def check_wall_clock(self) -> None:
        elapsed = time.monotonic() - self._start
        if elapsed > self.wall_clock_seconds:
            raise BudgetExceeded(f"wall-clock budget exceeded: {elapsed:.1f}s > {self.wall_clock_seconds}s")

    def spend_tokens(self, agent_id: str, count: int) -> None:
        cap = self.token_budgets.get(agent_id)
        if cap is None:
            return  # agent has no declared token budget; nothing to enforce
        spent = self._spent.get(agent_id, 0) + count
        self._spent[agent_id] = spent
        if spent > cap:
            raise BudgetExceeded(f"agent {agent_id!r} exceeded token budget: {spent} > {cap}")

    def remaining_tokens(self, agent_id: str) -> int:
        cap = self.token_budgets.get(agent_id)
        if cap is None:
            return -1  # unbounded / not tracked
        return cap - self._spent.get(agent_id, 0)
