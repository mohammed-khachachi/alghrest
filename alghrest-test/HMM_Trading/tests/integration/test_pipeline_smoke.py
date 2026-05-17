from src.pipeline.runner import run


def test_pipeline_smoke(default_config):
    config = dict(default_config)
    config.update(
        {
            "start": "2020-01-01",
            "end": "2020-06-30",
            "n_iter": 20,
        }
    )

    result = run(config)

    assert isinstance(result, dict)
    assert result.get("status") == "success"
    assert "metrics" in result
    assert "labels" in result
