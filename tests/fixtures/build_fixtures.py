"""Generate the documented local examples into an explicitly chosen empty path.

Run from the repository root:
    python tests/fixtures/build_fixtures.py <new-directory> [correct|problems]

expected.json beside this script is the reviewed static expected-results
manifest. Runtime fixtures must match it; this script does not update it.
"""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pmc.sample import create_sample


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("scenario", choices=["correct", "problems"], nargs="?", default="problems")
    options = parser.parse_args()
    result = create_sample(options.destination, options.scenario)
    reviewed = json.loads(Path(__file__).with_name("expected.json").read_text(encoding="utf-8"))[options.scenario]
    if result["expected"] != reviewed:
        raise SystemExit("Generated example differs from the reviewed expected-results manifest")
    print(f"Created {options.scenario} example: {result['source']}")
