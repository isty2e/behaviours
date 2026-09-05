"""Execute the project's type checker; missing tools are failures, not skips."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_pyrefly(*paths: str) -> tuple[int, list[dict[str, object]]]:
    venv_pyrefly = Path(sys.executable).with_name("pyrefly")
    executable = (
        os.environ.get("PYREFLY")
        or (str(venv_pyrefly) if venv_pyrefly.exists() else None)
        or shutil.which("pyrefly")
    )
    assert executable is not None, "Install the dev dependencies or set PYREFLY"
    result = subprocess.run(
        [
            executable,
            "check",
            "--config",
            str(ROOT / "pyrefly.toml"),
            "--output-format",
            "json",
            *paths,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode in (0, 1), (
        result.returncode,
        result.stdout,
        result.stderr,
    )
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict) and isinstance(payload.get("errors"), list)
    errors = payload["errors"]
    assert all(isinstance(error, dict) for error in errors)
    return result.returncode, errors


def test_source_and_positive_consumer() -> None:
    code, errors = run_pyrefly("src", "tests/typing/valid.py")
    assert (code, errors) == (0, [])


def test_negative_consumer_is_rejected_for_each_expected_contract() -> None:
    code, errors = run_pyrefly("tests/typing/invalid.py")
    assert code == 1 and errors
    kinds = {error["name"] for error in errors}
    assert {"bad-override", "bad-instantiation", "bad-argument-type"} <= kinds
    messages = "\n".join(str(error["description"]) for error in errors)
    for expected in ("Wrong.energy", "Missing", "reference", "self"):
        assert expected in messages


def test_decorated_cross_module_consumer() -> None:
    code, errors = run_pyrefly(
        "tests/typing/decorated_api.py", "tests/typing/decorated_consumer.py"
    )
    assert (code, errors) == (0, [])


def test_decorated_invalid_consumer_keeps_each_static_contract() -> None:
    code, errors = run_pyrefly("tests/typing/decorated_invalid.py")
    assert code == 1
    assert all(
        error["name"] not in {"parse-error", "missing-import"} for error in errors
    )
    descriptions = "\n".join(str(error["description"]) for error in errors)
    for text in (
        "Missing",
        "AbstractSubtrait",
        "BadReturn.value",
        "BadGeneric.item",
        "WrongProperty.label",
        "reference",
        "self",
        "list[int]",
    ):
        assert text in descriptions, (text, errors)
    assert {
        "bad-override",
        "bad-instantiation",
        "bad-argument-type",
        "bad-assignment",
    } <= {error["name"] for error in errors}


def test_decorated_consumer_runs_with_native_dispatch() -> None:
    result = subprocess.run(
        [sys.executable, "tests/typing/decorated_consumer.py"],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_data_model_static_contracts() -> None:
    import pytest

    pytest.importorskip("attrs")
    code, errors = run_pyrefly(
        "tests/typing/data_models.py", "tests/typing/data_models_consumer.py"
    )
    assert (code, errors) == (0, [])


def test_data_model_negative_consumer() -> None:
    import pytest

    pytest.importorskip("attrs")
    code, errors = run_pyrefly("tests/typing/data_models_invalid.py")
    assert code == 1
    assert all(
        error["name"] not in {"parse-error", "missing-import"} for error in errors
    )
    assert {error["line"] for error in errors} == {3, 4, 5, 6, 7, 8}


def test_framework_data_model_static_contracts() -> None:
    import pytest

    pytest.importorskip("pydantic")
    pytest.importorskip("sqlalchemy")
    code, errors = run_pyrefly("tests/typing/framework_models.py")
    assert (code, errors) == (0, [])
    code, errors = run_pyrefly("tests/typing/framework_models_invalid.py")
    assert code == 1
    assert all(
        error["name"] not in {"parse-error", "missing-import"} for error in errors
    )
    assert {error["line"] for error in errors} == {3, 4, 5, 6}


def test_extended_methods_and_mixin_decorator_consumers() -> None:
    code, errors = run_pyrefly(
        "tests/typing/extended_api.py", "tests/typing/extended_consumer.py"
    )
    assert (code, errors) == (0, [])
    result = subprocess.run(
        [sys.executable, "tests/typing/extended_consumer.py"],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)


def test_extended_negative_consumer_exact_contracts() -> None:
    path = ROOT / "tests/typing/extended_invalid.py"
    expected = {
        (i, line.split("# expected: ", 1)[1].strip())
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if "# expected: " in line
    }
    code, errors = run_pyrefly("tests/typing/extended_invalid.py")
    actual = {(error["line"], error["name"]) for error in errors}
    assert code == 1 and actual == expected
    assert len(errors) == len(expected)
