from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ci.pytest_partitions import (  # noqa: E402
    CONTRACT_PATHS,
    UNIT_PATHS,
    compare_node_id_sets,
)


def test_python_partitions_are_path_disjoint() -> None:
    partitions = [set(UNIT_PATHS), set(CONTRACT_PATHS)]

    assert not partitions[0] & partitions[1]


def test_old_and_partitioned_node_id_sets_must_have_equal_union_and_no_overlap() -> None:
    compare_node_id_sets(
        old={"api::one", "contract::one"},
        partitions={
            "unit": {"api::one"},
            "contract": {"contract::one"},
        },
    )


@pytest.mark.parametrize(
    "partitions",
    [
        {
            "unit": {"api::one"},
            "contract": {"api::one"},
        },
        {
            "unit": {"api::one"},
            "contract": set(),
        },
    ],
)
def test_partition_verifier_rejects_overlap_or_missing_node_ids(
    partitions: dict[str, set[str]],
) -> None:
    with pytest.raises(ValueError):
        compare_node_id_sets(
            old={"api::one", "contract::one"},
            partitions=partitions,
        )
