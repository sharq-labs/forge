from __future__ import annotations

import json

from engcore.systems.aerospace.multirotor import run_reference_study


def main() -> None:
    run = run_reference_study(count=1000, attempt_budget=3000)
    print(json.dumps(run.summary(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
