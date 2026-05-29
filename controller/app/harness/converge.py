from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .verifier.base import VerificationResult


class ConvergenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    converged: bool = False
    should_continue: bool = False
    reason: str
    successful_attempts: int = 0
    total_attempts: int = 0


class ConvergenceDetector:
    def __init__(self, *, required_successes: int = 3, max_attempts: int = 3):
        self.required_successes = max(1, required_successes)
        self.max_attempts = max(1, max_attempts)

    def decide(self, results: list[VerificationResult]) -> ConvergenceDecision:
        total = len(results)
        consecutive = 0
        for result in reversed(results):
            if result.passed is True:
                consecutive += 1
            else:
                break
        if consecutive >= self.required_successes:
            return ConvergenceDecision(
                status="converged",
                converged=True,
                should_continue=False,
                reason=f"{consecutive} consecutive verified runs",
                successful_attempts=consecutive,
                total_attempts=total,
            )
        if total >= self.max_attempts:
            return ConvergenceDecision(
                status="unconverged",
                converged=False,
                should_continue=False,
                reason="attempt budget exhausted",
                successful_attempts=consecutive,
                total_attempts=total,
            )
        return ConvergenceDecision(
            status="running",
            converged=False,
            should_continue=True,
            reason="convergence threshold not reached",
            successful_attempts=consecutive,
            total_attempts=total,
        )
