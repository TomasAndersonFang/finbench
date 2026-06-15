from pathlib import Path

from finbench.pipeline import load_registry, write_task
from finbench.schema import RawTask, Task
from finbench.diffutils import make_new_file_patch

REGISTRY = Path(__file__).resolve().parents[1] / "finbench" / "repos.yaml"


def test_load_registry_keyed_by_full_repo():
    reg = load_registry(REGISTRY)
    assert "stefan-jansen/empyrical-reloaded" in reg
    assert reg["stefan-jansen/empyrical-reloaded"]["numpy"] == "1.26.4"


def test_write_task_emits_task_json(tmp_path):
    raw = RawTask(
        task_id="demo",
        repo="owner/name",
        base_commit="abc",
        instruction="do it",
        gold_patch=make_new_file_patch("src/m.py", "a=1\n"),
        test_patch=make_new_file_patch("tests/test_m.py", "def test_a():\n    assert True\n"),
    )
    task = Task.from_raw(raw, ["tests/test_m.py::test_a"], [], "img:base")
    path = write_task(tmp_path, task)
    assert path == tmp_path / "demo" / "task.json"
    assert path.exists()
    assert '"fail_to_pass"' in path.read_text()
