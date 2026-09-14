"""Live Strands -> model -> Python tool -> model check. Uses a small paid API call."""
import json
import logging
import secrets
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from strands import Agent, tool

from model_config import create_model

ROOT = Path(__file__).parent


def main():
    # Do not expose provider exceptions, headers or credentials in console logs.
    logging.disable(logging.CRITICAL)
    nonce = secrets.token_hex(12)
    calls = []

    @tool
    def lookup_pattern(name: str) -> dict:
        """Read an architecture pattern and its verification receipt.

        Args:
            name: Pattern identifier: assistant, rag or automation.
        """
        patterns = json.loads((ROOT / "patterns.json").read_text(encoding="utf-8"))
        result = {"name": name, "pattern": patterns[name], "receipt": nonce}
        calls.append({"tool": "lookup_pattern", "input": {"name": name}, "result": result})
        return result

    report = {"checked_at": datetime.now(timezone.utc).isoformat(),
              "strands_version": version("strands-agents"), "passed": False}
    try:
        agent = Agent(model=create_model(), tools=[lookup_pattern], callback_handler=None,
                      system_prompt="Use lookup_pattern once when asked about a pattern. Return its receipt verbatim.")
        response = str(agent("Look up the rag pattern. Reply with its receipt and one short sentence about its purpose."))
        report.update(tool_calls=calls, response=response,
                      passed=bool(calls) and nonce in response and calls[0]["input"]["name"] == "rag")
    except Exception as exc:
        # An exception class is enough for local diagnostics; never persist raw API errors.
        report.update(error_type=type(exc).__name__, tool_calls=calls)
    output = ROOT / "outputs"
    output.mkdir(exist_ok=True)
    filename = datetime.now(timezone.utc).strftime("smoke-%Y%m%dT%H%M%S%fZ.json")
    (output / filename).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS: real tool call and returned receipt verified." if report["passed"] else
          "FAILED: check model configuration and retry.")
    print(f"Report: outputs/{filename}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
