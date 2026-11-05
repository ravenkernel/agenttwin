"""The two runnable proofs in the README have to stay runnable.

examples/quickstart.py is the ten-minute loop and tools/break_it.py is the
three-ways-a-run-can-break demo.  Both README editions quote their stdout, so
this module runs them and compares, the same way tests/test_hero.py guards the
hero transcript.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READMES = (ROOT / "README.md", ROOT / "README.zh-CN.md")
FENCE = chr(96) * 3

CASES = (
    ("PYTHONPATH=src python examples/quickstart.py", "step 1  record one run"),
    ("PYTHONPATH=src python tools/break_it.py", "tape build/break-it/deploy.jsonl"),
)


def transcript_after(text: str, command: str) -> str:
    """The text block that follows the bash block holding command."""
    pattern = (
        FENCE + "bash\n" + re.escape(command) + "\n" + FENCE
        + "(.*?)" + FENCE + "text\n(.*?)\n" + FENCE
    )
    match = re.search(pattern, text, re.S)
    assert match, "no transcript found after %r" % command
    return match.group(2)


def run(command: str) -> str:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    words = command.split()
    script = words[words.index("python") + 1:]
    done = subprocess.run(
        [sys.executable, *script],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout.strip()


@pytest.mark.parametrize("command,marker", CASES, ids=["quickstart", "break_it"])
def test_the_readme_quotes_a_run_that_still_happens(command: str, marker: str) -> None:
    output = run(command)
    assert output.startswith(marker), "%s no longer starts with %r" % (command, marker)
    for readme in READMES:
        assert output == transcript_after(readme.read_text(encoding="utf-8"), command), (
            "%s shows a transcript that is not what %s prints today" % (readme.name, command)
        )
