"""Pure budget arithmetic shared by API, workers, and database tests."""

from dataclasses import dataclass


class BudgetDisabled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    version: str
    monthly_points: int
    document_points: int
    alert_points: int
    points_per_usd: int
    cache_hit_microusd_per_million: int
    cache_miss_microusd_per_million: int
    output_microusd_per_million: int

    @classmethod
    def deepseek_v4_flash(cls) -> "BudgetPolicy":
        return cls(
            version="deepseek-v4-flash-2026-07-17",
            monthly_points=20_000,
            document_points=100,
            alert_points=16_000,
            points_per_usd=800,
            cache_hit_microusd_per_million=2_800,
            cache_miss_microusd_per_million=140_000,
            output_microusd_per_million=280_000,
        )

    @staticmethod
    def require(policy: "BudgetPolicy | None") -> "BudgetPolicy":
        if policy is None:
            raise BudgetDisabled("MODEL_DISABLED: no active budget policy")
        return policy

    def points_for_microusd(self, microusd: int) -> int:
        if microusd < 0:
            raise ValueError("cost cannot be negative")
        return (microusd * self.points_per_usd + 999_999) // 1_000_000


def compute_cost_microusd(
    *,
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    output_tokens: int,
    policy: BudgetPolicy,
) -> int:
    if min(cache_hit_tokens, cache_miss_tokens, output_tokens) < 0:
        raise ValueError("token usage cannot be negative")
    numerator = (
        cache_hit_tokens * policy.cache_hit_microusd_per_million
        + cache_miss_tokens * policy.cache_miss_microusd_per_million
        + output_tokens * policy.output_microusd_per_million
    )
    return (numerator + 999_999) // 1_000_000 if numerator else 0
