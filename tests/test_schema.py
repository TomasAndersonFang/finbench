import pytest

from finbench.diffutils import make_new_file_patch
from finbench.schema import RawTask, Task


def _raw(gold_path: str, test_path: str) -> RawTask:
    return RawTask(
        task_id="t1",
        repo="owner/name",
        base_commit="abc123",
        instruction="do the thing",
        gold_patch=make_new_file_patch(gold_path, "a = 1\n"),
        test_patch=make_new_file_patch(test_path, "def test_a():\n    assert True\n"),
    )


def test_non_overlapping_patches_ok():
    raw = _raw("src/pkg/mod.py", "tests/test_mod.py")
    assert raw.task_id == "t1"


def test_overlapping_patches_rejected():
    # Invariant 3: gold and test patches must not touch the same file.
    with pytest.raises(ValueError):
        _raw("src/pkg/mod.py", "src/pkg/mod.py")


def test_task_from_raw_carries_grading_fields():
    raw = _raw("src/pkg/mod.py", "tests/test_mod.py")
    task = Task.from_raw(
        raw,
        fail_to_pass=["tests/test_mod.py::test_a"],
        pass_to_pass=[],
        image="finbench-name:base",
    )
    d = task.to_dict()
    assert d["fail_to_pass"] == ["tests/test_mod.py::test_a"]
    assert d["image"] == "finbench-name:base"
    assert d["instruction"] == "do the thing"
