from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.pipelines.colmap.pipeline import _classify_failure, _failure_hint


def main() -> int:
    no_initial_pair_log = """
    Finding good initial image pair
    => No good initial image pair found.
    E20260606 sfm.cc:281] Failed to create any sparse model
    """
    bad_initial_pair_log = "Discarding reconstruction due to bad initial pair"

    if _classify_failure(no_initial_pair_log) != "no_initial_pair":
        raise AssertionError("No initial pair should be classified explicitly")
    if _classify_failure(bad_initial_pair_log) != "bad_initial_pair":
        raise AssertionError("Bad initial pair should be classified explicitly")
    if "overlap" not in _failure_hint("no_initial_pair"):
        raise AssertionError("No initial pair hint should explain input image requirements")

    print("colmap failure classification smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
