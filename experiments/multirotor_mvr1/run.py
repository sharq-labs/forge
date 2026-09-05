from __future__ import annotations

import argparse
import json

from engcore.scientific.units.quantity import Quantity
from engcore.systems.aerospace.multirotor.study import (
    MultirotorStudySpecification,
    run_multirotor_study,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the MVR1 typed multirotor reference-model study."
    )
    parser.add_argument("--payload-kg", type=float, required=True)
    parser.add_argument("--min-endurance-min", type=float, required=True)
    parser.add_argument("--max-mass-kg", type=float, required=True)
    parser.add_argument("--max-disk-loading", type=float, required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    specification = MultirotorStudySpecification(
        payload_mass=Quantity(args.payload_kg, "kg"),
        minimum_hover_endurance=Quantity(args.min_endurance_min, "min"),
        maximum_takeoff_mass=Quantity(args.max_mass_kg, "kg"),
        maximum_disk_loading=Quantity(args.max_disk_loading, "N/m^2"),
    )
    run = run_multirotor_study(specification)
    print(json.dumps(run.summary(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
