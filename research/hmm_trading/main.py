from src.core.config import load_config
from src.pipeline.runner import run


def main() -> None:
    config = load_config("configs/default.json")
    run(config)


if __name__ == "__main__":
    main()
