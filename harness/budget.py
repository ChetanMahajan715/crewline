# Budgets: limits on steps, seconds, tokens and estimated cost. There is one budget for the
# whole run and one for each agent; every model call charges both. When any limit is used up,
# check() raises BudgetExceeded so the caller can stop cleanly and keep the finished work.
import time

from harness import config


# Raised when a limit is hit. `limit` names it, for example "run tokens".
class BudgetExceeded(Exception):
    def __init__(self, limit: str):
        super().__init__(limit)
        self.limit = limit


class Budget:
    # Remember the limits and start the clock.
    def __init__(self, name: str, max_steps: int, max_seconds: float, max_tokens: int, max_cost_usd: float):
        self.name = name
        self.limits = {"steps": max_steps, "seconds": max_seconds, "tokens": max_tokens, "cost": max_cost_usd}
        self.used = {"steps": 0, "tokens": 0, "cost": 0.0}
        self.start = time.monotonic()

    # Record one model call.
    def charge(self, tokens: int, cost: float) -> None:
        self.used["steps"] += 1
        self.used["tokens"] += tokens
        self.used["cost"] += cost

    # Raise BudgetExceeded if any limit is already used up.
    def check(self) -> None:
        used = {**self.used, "seconds": time.monotonic() - self.start}
        for which, limit in self.limits.items():
            if used[which] >= limit:
                raise BudgetExceeded(f"{self.name} {which}")


# Estimated cost in USD at paid prices (the free tier really costs $0). A model missing from
# the price table counts as $0, so switching provider never breaks a run.
def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = config.PRICES.get("mock" if config.PROVIDER == "mock" else config.MODEL, (0.0, 0.0))
    return round((input_tokens * price_in + output_tokens * price_out) / 1_000_000, 6)
