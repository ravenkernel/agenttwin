"""Three deliberate breakages, three different outcomes -- the whole point of the tool.

    PYTHONPATH=src python tools/break_it.py

It records one small tape, then attacks it three ways:

1. the controller sends a different prompt        -> PromptDrift, exit code 2
2. the controller calls the same tool with other  -> ArgsDrift,   exit code 2
   arguments
3. the recorded run itself misbehaves             -> the assertion fails, exit code 1

The distinction is the product: a changed request is not a failed assertion, and
a failed assertion is not a damaged tape.  The script exits 0 only when all three
come out as documented, so it can run in CI as living evidence.

Nothing here is mocked at the model boundary beyond a stub that returns a fixed
dict: no API key, no network, no real tool.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from agenttwin import DriftError, Twin, asserts

WORK = Path("build") / "break-it"
TAPE = WORK / "deploy.jsonl"


def fake_status() -> dict:
    return {"ready": True}


def fake_deploy(name: str) -> dict:
    return {"ok": True, "name": name}


def fake_llm(request: dict) -> dict:
    return {"plan": "deploy", "goal": request["goal"]}


def agent(llm, tools, policy=None):
    """The controller every case starts from: status, plan, deploy."""
    tools["status"]()
    plan = llm({"goal": "green"})
    result = tools["deploy"](plan["plan"])
    return {"ok": result["ok"]}


def record() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    with Twin.record(
        "break-it",
        out=TAPE,
        seed=0,
        llm=fake_llm,
        tools={"status": fake_status, "deploy": fake_deploy},
        model="fake-break-v0",
    ) as recorder:
        result = agent(recorder.llm, recorder.tools())
        recorder.returned(result)


def changed_prompt(llm, tools):
    """Same shape, same positions -- one value in the request is different."""
    tools["status"]()
    llm({"goal": "ship it"})


def changed_args(llm, tools):
    """Same request, same tool -- different arguments."""
    tools["status"]()
    llm({"goal": "green"})
    tools["deploy"]("other-app")


def drift_of(controller) -> str:
    try:
        Twin.load(TAPE).replay(controller)
    except DriftError as exc:
        return type(exc).__name__
    return "no drift"


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    record()
    events = len(Twin.load(TAPE).tape.events)
    print(f"tape {TAPE.as_posix()} ({events} events)")

    first = drift_of(changed_prompt)
    second = drift_of(changed_args)

    report = Twin.load(TAPE).replay(agent).assert_(asserts.never_calls("deploy"))
    row = report.results[0]
    third = f"{'PASS' if row.passed else 'FAIL'} {row.name}"

    print(f"case 1  changed prompt     -> {first:<14} exit code 2")
    print(f"case 2  changed tool args  -> {second:<14} exit code 2")
    print(f"case 3  bad behaviour      -> {third}  exit code {report.exit_code}")

    expected = (first == "PromptDrift", second == "ArgsDrift", report.exit_code == 1)
    print("verdict:", "all three as documented" if all(expected) else f"unexpected {expected}")
    return 0 if all(expected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
