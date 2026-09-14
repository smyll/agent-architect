"""Three complete synthetic trials; opt-in paid API calls, no hidden retries."""
import argparse
import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from blueprint import DesignRun
from critic import review_design
from discovery import Interview, StrandsDiscovery

ROOT = Path(__file__).parent
IDEA = "我想做一个帮助大学生管理课程作业的助手。"
DETAILS = "第一版只根据我粘贴的少量课程作业文字整理截止日期，并给出三天学习安排。用户是大学生。不连接学校系统或日历，不发送通知，不自动提交作业。只给建议，不执行外部操作；课程资料不长期保存，费用尽量低。输出按天分组的优先级列表，模糊日期请用户确认。"


class RecordedRuntime(StrandsDiscovery):
    def __init__(self):
        super().__init__()
        self.last_text = ""
        self.agent_identity = None

    def invoke(self, *args, **kwargs):
        self.last_text = ""
        text = super().invoke(*args, **kwargs)
        self.last_text = text
        if self.agent_identity is None:
            self.agent_identity = id(self.agent)
        assert id(self.agent) == self.agent_identity, "Agent instance changed between stages"
        return text


def trial(index):
    state, runtime = Interview(), RecordedRuntime()
    result = {"trial": index, "passed": False, "stages": [], "synthetic": True}
    started = time.perf_counter()
    stage = "discovery"
    run = DesignRun()

    def checkpoint(name):
        result["stages"].append({"stage": name, "elapsed_seconds": round(time.perf_counter() - started, 2)})
        print(f"Trial {index}: {name}", flush=True)

    try:
        state.advance(IDEA, runtime)
        checkpoint("idea_processed")
        state.advance(DETAILS, runtime)
        if state.stage == "interview":
            state.advance("请根据已有信息总结，未确定项明确列出。", runtime, force_summary=True)
        assert state.stage == "summary" and len(state.asked) <= 5
        stage = "confirmation"
        try:
            state.confirmed_requirements()
        except ValueError:
            pass
        else:
            raise AssertionError("Unconfirmed requirements were accessible")
        state.confirm()
        checkpoint("confirmed")
        stage = "design"
        design = run.generate(state, runtime)
        assert design.blueprint.pattern == "assistant" and not design.blueprint.tools
        checkpoint("design_generated")
        stage = "critic"
        critic = review_design(state, design, runtime)
        checkpoint("critic_finished")
        result.update(passed=True, requirements=state.requirements.model_dump(),
                      transcript=state.transcript, blueprint=design.blueprint.model_dump(), code=design.code,
                      review=critic.review.model_dump(), tool_calls=design.trace, same_agent=True)
    except Exception as exc:
        result.update(failed_stage=stage, error_type=type(exc).__name__,
                      last_model_output=runtime.last_text, tool_calls=run.trace)
        if isinstance(exc, ValidationError):
            result["validation_errors"] = [{"location": e["loc"], "type": e["type"]} for e in exc.errors()]
        print(f"Trial {index}: FAILED at {stage} ({type(exc).__name__})", flush=True)
    result["duration_seconds"] = round(time.perf_counter() - started, 2)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, choices=range(1, 4), default=3)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    output = ROOT / "outputs"
    output.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = {"started_at": stamp, "no_automatic_retries": True,
              "source_hashes": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in ["discovery.py", "blueprint.py", "critic.py"]}, "trials": []}
    destination = output / f"flow-live-{stamp}.json"
    for index in range(1, args.runs + 1):
        report["trials"].append(trial(index))
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    passed = sum(item["passed"] for item in report["trials"])
    print(f"RESULT: {passed}/{args.runs} passed without retries. Report: {destination.name}")
    return 0 if passed == args.runs else 1


if __name__ == "__main__":
    raise SystemExit(main())
