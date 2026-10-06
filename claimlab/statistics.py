"""Statistical inference for ClaimLab, including overlap-aware effective-N.

Pure Python implementation is intentional: the CI runner must not silently depend
on a scientific Python stack merely to validate a research contract.
"""
from __future__ import annotations

import math
import random
from typing import Dict, Iterable, List, Sequence


class StatisticalEngine:
    @staticmethod
    def calculate_effective_n(returns: Sequence[float], horizon: int) -> int:
        """Estimate effective N using Bartlett-weighted autocorrelation.

        The result is conservative: it is clipped to [1, N]. For overlapping
        h-period observations, autocorrelation through h is material to inference.
        """
        values = [float(x) for x in returns]
        n = len(values)
        h = max(1, int(horizon))
        if n <= 1:
            return max(1, n)
        if n <= h:
            return n

        mean = sum(values) / n
        var = sum((x - mean) ** 2 for x in values) / n
        if var <= 0:
            return n

        rho_sum = 0.0
        for lag in range(1, min(h, n - 1) + 1):
            cov = sum(
                (values[i] - mean) * (values[i + lag] - mean)
                for i in range(n - lag)
            ) / (n * var)
            weight = 1.0 - lag / float(h)
            rho_sum += weight * cov

        denominator = 1.0 + 2.0 * rho_sum
        if denominator <= 0:
            return n
        return max(1, min(n, int(math.floor(n / denominator))))

    @staticmethod
    def benjamini_hochberg_correction(
        p_values: Sequence[float], alpha: float = 0.05
    ) -> List[bool]:
        """Return BH/FDR rejection decisions in original input order."""
        p = [min(1.0, max(0.0, float(x))) for x in p_values]
        m = len(p)
        if m == 0:
            return []
        ranked = sorted(enumerate(p), key=lambda x: x[1])
        cutoff = -1
        for rank, (_, value) in enumerate(ranked, start=1):
            if value <= (rank / m) * alpha:
                cutoff = rank
        reject = [False] * m
        if cutoff >= 0:
            for rank, (idx, _) in enumerate(ranked, start=1):
                if rank <= cutoff:
                    reject[idx] = True
        return reject

    @staticmethod
    def block_bootstrap_ci(
        values: Sequence[float],
        block_size: int,
        resamples: int = 2000,
        alpha: float = 0.05,
        seed: int = 20261006,
    ) -> Dict[str, float]:
        """Percentile CI for a mean using contiguous, circular blocks."""
        x = [float(v) for v in values]
        n = len(x)
        if not x:
            return {"mean": float("nan"), "ci_lower": float("nan"),
                    "ci_upper": float("nan"), "p_value": float("nan")}
        b = max(1, min(int(block_size), n))
        rng = random.Random(seed)
        means = []
        blocks = max(1, math.ceil(n / b))
        for _ in range(max(100, int(resamples))):
            sample = []
            for _ in range(blocks):
                start = rng.randrange(n)
                for j in range(b):
                    sample.append(x[(start + j) % n])
                    if len(sample) >= n:
                        break
                if len(sample) >= n:
                    break
            means.append(sum(sample) / n)
        means.sort()
        lower_i = max(0, min(len(means) - 1, int((alpha / 2) * len(means))))
        upper_i = max(0, min(len(means) - 1, int((1 - alpha / 2) * len(means)) - 1))
        mean = sum(x) / n
        # One-sided null p-value for H1: mean > 0.
        nonpositive = sum(v <= 0 for v in means)
        p_value = (nonpositive + 1) / (len(means) + 1)
        return {
            "mean": mean,
            "ci_lower": means[lower_i],
            "ci_upper": means[upper_i],
            "p_value": p_value,
        }

    @staticmethod
    def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> Dict[str, float]:
        """Wilson score interval for a binomial proportion."""
        if n <= 0:
            return {"value": float("nan"), "ci_lower": float("nan"),
                    "ci_upper": float("nan"), "p_value": float("nan")}
        z = 1.959963984540054
        phat = max(0.0, min(1.0, successes / n))
        denom = 1 + z * z / n
        center = (phat + z * z / (2 * n)) / denom
        radius = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
        lower, upper = max(0.0, center - radius), min(1.0, center + radius)
        # Normal approximation to the one-sided null p-value against 0.5.
        se = math.sqrt(max(1e-18, 0.25 / n))
        zstat = (phat - 0.5) / se
        p_value = 0.5 * math.erfc(zstat / math.sqrt(2))
        return {"value": phat, "ci_lower": lower, "ci_upper": upper, "p_value": p_value}

    @staticmethod
    def summarize(
        rows: Iterable[dict],
        horizon: int = 5,
        resamples: int = 2000,
        alpha: float = 0.05,
        seed: int = 20261006,
    ) -> Dict[str, object]:
        """Build overlap-aware performance statistics from valid observations."""
        valid = [r for r in rows if r.get("status") == "VALID"]
        n = len(valid)
        if not n:
            return {"n": 0, "effective_n": 0, "status": "INSUFFICIENT_DATA"}

        mae_delta = [
            (
                float(r["baseline_error_absolute"]) - float(r["error_absolute"])
                if "baseline_error_absolute" in r and "error_absolute" in r
                else abs(float(r["actual"]) - float(r["baseline_prediction"]))
                - abs(float(r["actual"]) - float(r.get("prediction", 0.0)))
            )
            for r in valid
        ]
        net = [float(r["friction_adjusted_return"]) for r in valid]
        hit = sum(bool(r["direction_hit"]) for r in valid)
        neff = StatisticalEngine.calculate_effective_n(net, horizon)
        mae_ci = StatisticalEngine.block_bootstrap_ci(
            mae_delta, horizon, resamples, alpha, seed
        )
        net_ci = StatisticalEngine.block_bootstrap_ci(
            net, horizon, resamples, alpha, seed + 1
        )
        hit_ci = StatisticalEngine.wilson_ci(hit, n, alpha)

        p_values = [mae_ci["p_value"], hit_ci["p_value"], net_ci["p_value"]]
        bh = StatisticalEngine.benjamini_hochberg_correction(p_values, alpha)
        return {
            "n": n,
            "effective_n": neff,
            "mae_delta": mae_ci["mean"],
            "mae_delta_ci_lower": mae_ci["ci_lower"],
            "mae_delta_ci_upper": mae_ci["ci_upper"],
            "mae_delta_p_value": mae_ci["p_value"],
            "hit_rate": hit_ci["value"],
            "hit_rate_ci_lower": hit_ci["ci_lower"],
            "hit_rate_ci_upper": hit_ci["ci_upper"],
            "hit_rate_p_value": hit_ci["p_value"],
            "friction_adjusted_return": net_ci["mean"],
            "friction_adjusted_return_ci_lower": net_ci["ci_lower"],
            "friction_adjusted_return_ci_upper": net_ci["ci_upper"],
            "friction_adjusted_return_p_value": net_ci["p_value"],
            "bh_reject": {
                "C001": bh[0], "C002": bh[1], "C003": bh[2]
            },
            "status": "OK",
        }
