from finbench.diffutils import make_new_file_patch
from finbench.mutation import (
    TaskMutationReport,
    generate_mutants,
    _is_code_line,
    _mutate_line,
)


def test_mutate_line_numeric_and_operator():
    kinds = dict(_mutate_line("factor = 252 * 4"))
    # numeric literal bumped
    assert any("253" in v for v in kinds.values())
    # one operator swapped (here * -> /)
    assert "op*" in kinds


def test_is_code_line_skips_prose():
    assert _is_code_line("    return x + 1")
    assert not _is_code_line("    # a comment with 252")
    assert not _is_code_line('    """docstring 252"""')
    assert not _is_code_line("    :param x: the 252 factor")
    assert not _is_code_line("")


def test_generate_mutants_only_touches_added_code_lines():
    src = (
        "ANNUAL = 252\n"
        '"""factor of 252 days"""\n'
        "def f(x):\n"
        "    return x * 2\n"
    )
    patch = make_new_file_patch("src/pkg/mod.py", src)
    mutants = generate_mutants(patch, cap=16)
    assert mutants, "should produce at least one mutant"
    # every mutant must still be a valid-looking new-file diff for the same path
    for mut in mutants:
        assert "+++ b/src/pkg/mod.py" in mut.patch
        # exactly one added line differs from the original gold patch
        gold_added = [l for l in patch.splitlines() if l.startswith("+")]
        mut_added = [l for l in mut.patch.splitlines() if l.startswith("+")]
        assert len(gold_added) == len(mut_added)
        assert sum(a != b for a, b in zip(gold_added, mut_added)) == 1
    # the docstring numeric (252 in prose) must NOT be a mutation target
    labels = {m.label for m in mutants}
    # line indices: header(5 lines) then +ANNUAL(idx5), +docstring(idx6), ...
    # the docstring line should not appear as a code mutant
    docstring_idx = None
    for i, line in enumerate(patch.splitlines(keepends=True)):
        if line.startswith("+") and "factor of 252 days" in line:
            docstring_idx = i
    assert docstring_idx is not None
    assert f"L{docstring_idx}:num" not in labels


def test_report_flagged_logic():
    r = TaskMutationReport(task_id="t", mutants_total=5, mutants_killed=3)
    assert not r.flagged
    r2 = TaskMutationReport(task_id="t", mutants_total=5, mutants_killed=0)
    assert r2.flagged
    r3 = TaskMutationReport(task_id="t", error="boom")
    assert r3.flagged
