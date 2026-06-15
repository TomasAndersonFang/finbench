from finbench.builder import image_tag, render_dockerfile


def test_image_tag():
    assert image_tag("stefan-jansen/empyrical-reloaded") == "finbench-empyrical-reloaded:base"


def test_render_dockerfile_pins_and_single_threads():
    spec = {
        "repo": "stefan-jansen/empyrical-reloaded",
        "python": "3.10",
        "numpy": "1.26.4",
        "pandas": "2.1.4",
        "install": ["pip install -e ."],
    }
    df = render_dockerfile(spec)
    assert "FROM python:3.10-slim" in df
    assert "OMP_NUM_THREADS=1" in df
    assert "git clone https://github.com/stefan-jansen/empyrical-reloaded.git repo" in df
    assert "pip install -e ." in df
    # Pins are a global constraint set BEFORE the repo install, so pip resolves
    # once against them (no numpy 2.x install-then-downgrade backtracking).
    assert "numpy==1.26.4" in df
    assert "pandas==2.1.4" in df
    assert "ENV PIP_CONSTRAINT=/constraints.txt" in df
    assert df.index("PIP_CONSTRAINT") < df.index("pip install -e .")
    assert "pytest-json-report" in df
