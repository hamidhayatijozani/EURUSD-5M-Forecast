import random

from claimlab.statistics import StatisticalEngine


def test_effective_n_materially_reduces_for_high_autocorrelation():
    """A strongly persistent series must lose a material amount of effective N."""
    rng = random.Random(42)
    innovations = [rng.gauss(0.0, 1.0) for _ in range(1000)]
    correlated = [0.0] * len(innovations)

    for i in range(1, len(innovations)):
        correlated[i] = 0.8 * correlated[i - 1] + innovations[i]

    n_raw = len(correlated)
    n_eff = StatisticalEngine.calculate_effective_n(correlated, horizon=5)

    assert 1 <= n_eff < n_raw
    assert n_eff <= int(0.5 * n_raw)


def test_block_bootstrap_ci_is_deterministic_and_bounded():
    values = [0.1, 0.2, -0.05, 0.3, 0.15, -0.1] * 20

    first = StatisticalEngine.block_bootstrap_ci(
        values, block_size=5, resamples=500, alpha=0.05, seed=20261006
    )
    second = StatisticalEngine.block_bootstrap_ci(
        values, block_size=5, resamples=500, alpha=0.05, seed=20261006
    )

    assert first == second
    assert first["ci_lower"] <= first["mean"] <= first["ci_upper"]
    assert 0.0 <= first["p_value"] <= 1.0
