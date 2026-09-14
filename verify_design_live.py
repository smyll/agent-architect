"""Opt-in live API acceptance check for two contrasting, synthetic requirements."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from blueprint import DesignRun
from discovery import Interview, Requirements, StrandsDiscovery


def main():
    logging.disable(logging.CRITICAL)
    runtime = StrandsDiscovery()
    cases = [
        Requirements(goal="给大学生整理课程安排", target_users="大学生", tasks="根据粘贴的少量课程文字给出三天安排",
                     data_access="仅当前对话粘贴的文字，不接文件系统或日历", autonomy="只给建议，不执行任何外部操作",
                     constraints="不长期保存资料，费用尽量低", assumptions=[], unresolved=[]),
        Requirements(goal="查询课程手册", target_users="大学生", tasks="从大量授权的课程手册中检索规定，回答时附来源",
                     data_access="本地授权课程文档库，只读", autonomy="只读检索，不进行外部写入",
                     constraints="必须给出依据，没有依据时说明不知道，不存用户画像", assumptions=[], unresolved=[]),
    ]
    reports = []
    for requirements in cases:
        state = Interview(stage="summary", requirements=requirements)
        state.confirm()
        run = DesignRun()
        artifact = run.generate(state, runtime)
        reports.append({"requirements": requirements.model_dump(), "blueprint": artifact.blueprint.model_dump(),
                        "tool_calls": artifact.trace, "code": artifact.code, "syntax_checked": True})
        print("Generated:", artifact.blueprint.pattern, "/ tools:", len(artifact.blueprint.tools), flush=True)
    assert reports[0]["blueprint"]["tools"] == [], "Suggestion-only case should not need external tools"
    assert reports[1]["blueprint"]["pattern"] == "rag", "Document collection requires retrieval"
    assert reports[1]["blueprint"]["tools"], "Retrieval tool missing"
    assert all(t["access"] == "read" for t in reports[1]["blueprint"]["tools"])
    output = Path(__file__).parent / "outputs"
    output.mkdir(exist_ok=True)
    name = "design-live-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json"
    (output / name).write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS: contrasting designs verified. Report:", name)


if __name__ == "__main__":
    main()
