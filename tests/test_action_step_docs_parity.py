"""Keep the action-step reference table aligned with the executor registry."""

import re
from pathlib import Path

from src.action.executor import ActionExecutor

DOCS_PATH = Path(__file__).resolve().parents[1] / "docs" / "action-step-types-reference.md"
STEP_ROW = re.compile(r"^\|\s*`(?P<name>[a-z0-9_]+)`\s*\|")


def documented_step_types() -> set[str]:
    """Return the step names from the reference document's Step table."""
    in_step_table = False
    documented: list[str] = []

    for line in DOCS_PATH.read_text().splitlines():
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if cells and cells[0] == "Step":
            in_step_table = True
            continue
        if not in_step_table:
            continue
        if not line.lstrip().startswith("|"):
            break
        match = STEP_ROW.match(line)
        if match:
            documented.append(match.group("name"))

    assert documented, f"No step rows found in {DOCS_PATH}"
    assert len(documented) == len(set(documented)), "Duplicate step in reference table"
    return set(documented)


def test_every_documented_step_type_is_registered():
    documented = documented_step_types()
    registered = set(ActionExecutor()._step_executors)

    assert documented <= registered, (
        "Documented action steps missing from ActionExecutor._step_executors: "
        f"{sorted(documented - registered)}"
    )


def test_every_registered_step_type_is_documented():
    documented = documented_step_types()
    registered = set(ActionExecutor()._step_executors)

    assert registered <= documented, (
        "ActionExecutor._step_executors keys missing from the reference table: "
        f"{sorted(registered - documented)}"
    )
