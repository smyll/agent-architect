"""Opt-in paid model check with explicitly synthetic, intentionally conflicting design."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from architecture_tools import TEMPLATES
from blueprint import Blueprint, DesignArtifact, fingerprint, render_skeleton
from critic import review_design
from discovery import Interview, Requirements, StrandsDiscovery


def main():
    logging.disable(logging.CRITICAL)
    requirements = Requirements(goal="帮助大学生整理学习安排", target_users="大学生", tasks="根据粘贴文字给出三天计划",
        data_access="仅使用当前对话提供的文字，不连接日历", autonomy="只给建议，禁止写入日历",
        constraints="不长期保存用户课程资料", assumptions=[], unresolved=[])
    state = Interview(stage="summary", requirements=requirements)
    state.confirm()
    bp = Blueprint(name="故意带缺陷的测试样例", purpose="给出三天计划", target_user="大学生", pattern="automation",
        pattern_reason="测试样例，安排后自动执行", capabilities=["生成学习计划", "写入日历"],
        tools=[{"name":"write_calendar","purpose":"将计划写入日历","access":"write","approval":"无需用户确认"}],
        memory_strategy="永久保存所有课程资料", workflow=["接收输入", "自动写入日历"],
        risks=["时间可能不准确"], limitations=["日历工具是未实现占位"], template="tools")
    code = render_skeleton(bp, requirements, TEMPLATES["tools"].read_text(encoding="utf-8"))
    artifact = DesignArtifact(fingerprint(requirements), bp, code, [], [])
    reviewed = review_design(state, artifact, StrandsDiscovery())
    issues = reviewed.review.issues
    quotes = " ".join(e.quote for issue in issues for e in issue.evidence)
    assert any(i.category in {"autonomy", "requirements", "tools"} for i in issues), "Missed authority conflict"
    assert "日历" in quotes, "Missing calendar evidence"
    assert any(i.category in {"security", "requirements"} for i in issues), "Missed retention conflict"
    assert "永久" in quotes or "不长期" in quotes, "Missing retention evidence"
    output = Path(__file__).parent / "outputs"
    output.mkdir(exist_ok=True)
    name = "critic-live-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    report = {"test_case": "Synthetic intentionally conflicting blueprint; not normal product output",
              "requirements": requirements.model_dump(), "blueprint": bp.model_dump(), "review": reviewed.review.model_dump()}
    (output / name).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS: authority and retention conflicts detected with matching source quotes.")
    print("Report:", name)


if __name__ == "__main__":
    main()
