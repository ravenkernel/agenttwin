"""The ten-minute loop, end to end: record, assert, fail, fix, record again, pass.

    PYTHONPATH=src python examples/quickstart.py

It writes two real tapes under build/quickstart/, judges each one with the very
same assertions, and shows the second going green.  Nothing here calls a model:
the fake llm and the fake tool are the whole environment.

The README quotes this program's stdout, and tests/test_quickstart.py keeps the
two equal, so the transcript cannot drift away from the code.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from agenttwin import Twin, asserts

WORK = Path("build") / "quickstart"


def fake_deploy() -> dict:
    """The tool under test: every deploy attempt fails its health check."""
    return {"ok": False, "detail": "health check did not pass"}


def fake_llm(request: dict) -> dict:
    """A model stub that always answers the same way (no key, no network)."""
    return {"ok": False, "note": "the deploy reported a failed health check"}


def _deploy(llm, tools, retry: bool) -> dict:
    first = tools["deploy"]()
    if first["ok"] or not retry:
        return {"deployed": first["ok"], "attempts": 1}
    llm({"attempt": 1, "observation": first})
    second = tools["deploy"]()
    return {"deployed": second["ok"], "attempts": 2}


def deploy_retrying(llm, tools, policy=None) -> dict:
    """The controller as it was written first: one retry on a failed health check."""
    return _deploy(llm, tools, retry=True)


def deploy_once(llm, tools, policy=None) -> dict:
    """The controller after the fix: report the failure instead of retrying it."""
    return _deploy(llm, tools, retry=False)


CHECKS = (
    asserts.max_repeats("deploy", 1),
    asserts.never_calls("rollback"),
    asserts.terminates_within(8),
)


def record(agent, name: str) -> Path:
    path = WORK / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with Twin.record(
        f"quickstart-{path.stem}",
        out=path,
        seed=0,
        llm=fake_llm,
        tools={"deploy": fake_deploy},
        model="fake-deploy-v0",
    ) as recorder:
        result = agent(recorder.llm, recorder.tools())
        recorder.returned(result)
    return path


def judge(path: Path, agent) -> int:
    report = Twin.load(path).replay(agent).assert_(*CHECKS)
    for row in report.results:
        status = "SKIP" if row.passed is None else ("PASS" if row.passed else "FAIL")
        where = "" if row.first_offense_seq is None else f"  (seq {row.first_offense_seq})"
        print(f"  {status}  {row.name}  -- {row.detail}{where}")
    print(f"  exit code {report.exit_code}")
    return report.exit_code


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)

    print("step 1  record one run")
    before = record(deploy_retrying, "deploy.jsonl")
    print(f"  tape {before.as_posix()} ({len(Twin.load(before).tape.events)} events)")

    print("step 2  replay it offline and assert")
    failed = judge(before, deploy_retrying)

    print("step 3  change the controller and record again")
    after = record(deploy_once, "deploy-fixed.jsonl")
    print(f"  tape {after.as_posix()} ({len(Twin.load(after).tape.events)} events)")

    print("step 4  the same assertions, on the new tape")
    passed = judge(after, deploy_once)

    print(f"verdict: {failed} -> {passed}")
    return 0 if (failed, passed) == (1, 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
