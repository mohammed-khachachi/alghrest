def test_full_pipeline_runs(default_config, tmp_path):
    """Smoke test: entire pipeline completes without exception."""
    import copy

    config = copy.deepcopy(default_config)
    config["n_iter"] = 10
    config["ticker"] = "SYNTHETIC_TEST"
    from src.pipeline.runner import run

    result = run(config)
    assert result["status"] == "success"
    assert result["n_states"] == config["n_states"]
    assert isinstance(result["regime_labels"], dict)
    assert len(result["regime_labels"]) == config["n_states"]


def test_pipeline_is_deterministic(default_config):
    """Same config -> same regime labels."""
    import copy

    config = copy.deepcopy(default_config)
    config["n_iter"] = 10
    config["ticker"] = "SYNTHETIC_TEST"
    from src.pipeline.runner import run

    result1 = run(config)
    result2 = run(config)
    assert result1["regime_labels"] == result2["regime_labels"]
