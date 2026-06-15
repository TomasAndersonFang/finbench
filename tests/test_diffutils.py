from finbench.diffutils import (
    is_test_path,
    make_new_file_patch,
    patch_paths,
    split_patch,
)


def test_make_new_file_patch_roundtrips_paths():
    diff = make_new_file_patch("src/pkg/mod.py", "a = 1\nb = 2\n")
    assert "diff --git a/src/pkg/mod.py b/src/pkg/mod.py" in diff
    assert "--- /dev/null" in diff
    assert "+++ b/src/pkg/mod.py" in diff
    assert "@@ -0,0 +1,2 @@" in diff
    assert patch_paths(diff) == ["src/pkg/mod.py"]


def test_make_new_file_patch_handles_missing_trailing_newline():
    diff = make_new_file_patch("a.py", "x = 1")
    assert "\\ No newline at end of file" in diff


def test_is_test_path():
    assert is_test_path("tests/test_x.py")
    assert is_test_path("pkg/test_y.py")
    assert is_test_path("pkg/y_test.py")
    assert is_test_path("conftest.py")
    assert not is_test_path("src/pkg/mod.py")


def test_split_patch_by_path():
    diff = make_new_file_patch("src/pkg/mod.py", "a = 1\n") + make_new_file_patch(
        "tests/test_mod.py", "def test_a():\n    assert True\n"
    )
    test_patch, source_patch = split_patch(diff)
    assert patch_paths(test_patch) == ["tests/test_mod.py"]
    assert patch_paths(source_patch) == ["src/pkg/mod.py"]
