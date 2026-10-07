from claimlab.statistics import StatisticalEngine


def test_null_centered_bootstrap_is_two_sided_for_negative_effect():
    values = [-0.02] * 40
    result = StatisticalEngine.block_bootstrap_ci(
        values, block_size=5, resamples=1000, seed=7
    )
    assert result["mean"] == -0.02
    assert result["p_value"] < 0.01


def test_null_centered_bootstrap_does_not_call_zero_effect_significant():
    values = [(-1.0) ** i * 0.001 for i in range(100)]
    result = StatisticalEngine.block_bootstrap_ci(
        values, block_size=5, resamples=1000, seed=11
    )
    assert result["p_value"] > 0.01
