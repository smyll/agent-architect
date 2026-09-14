import ast
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from architecture_tools import TEMPLATES
from blueprint import Blueprint, DesignRun, fingerprint, render_skeleton
from discovery import Interview
from test_discovery import respond, result


def blueprint_data(with_tool=False):
    return dict(name="课程助手", purpose="整理学习安排", target_user="大学生", pattern="rag" if with_tool else "assistant",
                pattern_reason="需要查询文档" if with_tool else "少量文字直接提供即可",
                capabilities=["整理安排"],
                tools=[dict(name="retrieve_courses", purpose="检索课程片段", access="read", approval="只读用户授权资料")] if with_tool else [],
                memory_strategy="仅当前会话", workflow=["接收输入", "整理建议"], risks=["日期可能不准确"],
                limitations=["业务工具尚未实现"], template="tools" if with_tool else "basic")


def confirmed():
    state = Interview()
    state.advance("测试需求", respond(result()))
    state.confirm()
    return state


class FakeRuntime:
    def __init__(self, with_tool=False, use_evidence=True):
        self.with_tool, self.use_evidence = with_tool, use_evidence

    def invoke(self, prompt, context, *, tools, **kwargs):
        data = blueprint_data(self.with_tool)
        if self.use_evidence:
            tools[0](topic="quickstart")
            tools[1](name=data["pattern"])
            tools[2](name=data["template"])
        return Blueprint(**data).model_dump_json()


DOC = {"topic": "quickstart", "source": "https://strandsagents.com/docs/user-guide/quickstart/python/",
       "retrieved_at": "2026-09-11T00:00:00Z", "excerpt": "Test documentation", "truncated": False}


class BlueprintTests(unittest.TestCase):
    def test_cannot_generate_unconfirmed_requirements(self):
        with self.assertRaises(ValueError):
            DesignRun().generate(Interview(), FakeRuntime())

    def test_no_tool_evidence_means_no_artifact(self):
        with self.assertRaises(ValueError):
            DesignRun().generate(confirmed(), FakeRuntime(use_evidence=False))

    @patch("architecture_tools.fetch_document", return_value=DOC)
    def test_three_real_tool_functions_and_template_render(self, fetch):
        state = confirmed()
        artifact = DesignRun().generate(state, FakeRuntime())
        self.assertEqual(len(artifact.trace), 3)
        self.assertTrue(all(c["status"] == "success" for c in artifact.trace))
        self.assertEqual(artifact.requirements_fingerprint, fingerprint(state.requirements))
        self.assertEqual(artifact.sources[0]["source"], DOC["source"])
        self.assertIn("tools=[]", artifact.code)
        ast.parse(artifact.code)

    @patch("architecture_tools.fetch_document", side_effect=RuntimeError())
    def test_failed_document_lookup_not_claimed_as_grounded(self, fetch):
        run = DesignRun()
        with self.assertRaises(ValueError):
            run.generate(confirmed(), FakeRuntime())
        self.assertEqual(run.trace[0]["status"], "failed")

    @patch("architecture_tools.fetch_document", return_value=DOC)
    def test_tool_skeleton_contains_fail_closed_placeholder(self, fetch):
        artifact = DesignRun().generate(confirmed(), FakeRuntime(with_tool=True))
        self.assertIn("raise NotImplementedError", artifact.code)
        self.assertIn("tools=[retrieve_courses]", artifact.code)
        self.assertIn("MODEL_API_KEY", artifact.code)

    def test_user_text_is_literal_not_executable_code(self):
        state = confirmed()
        state.requirements.goal = "\"\"\"\n__import__('os').system('echo injected')\n$tool_names"
        bp = Blueprint(**blueprint_data())
        code = render_skeleton(bp, state.requirements, TEMPLATES["basic"].read_text(encoding="utf-8"))
        tree = ast.parse(code)
        self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "__import__"
                             for n in ast.walk(tree)))

    def test_reserved_function_names_rejected(self):
        data = blueprint_data(True)
        data["tools"][0]["name"] = "create_agent"
        with self.assertRaises(ValueError):
            Blueprint(**data)

    @patch("architecture_tools.fetch_document", return_value=DOC)
    def test_modified_requirements_invalidate_fingerprint(self, fetch):
        state = confirmed()
        artifact = DesignRun().generate(state, FakeRuntime())
        state.advance("修改", respond(result(tasks="安排三天学习计划")))
        state.confirm()
        self.assertNotEqual(artifact.requirements_fingerprint, fingerprint(state.requirements))

    @patch("architecture_tools.fetch_document", return_value=DOC)
    def test_page_generation_and_stale_design_after_edit(self, fetch):
        with patch("discovery.StrandsDiscovery.__call__", return_value=result()):
            page = AppTest.from_file("app.py", default_timeout=15).run()
            self.assertTrue(page.button(key="generate").disabled)
            page.chat_input[0].set_value("课程助手").run()
            self.assertTrue(page.button(key="generate").disabled)
            page.button(key="confirm").click().run()
            with patch("discovery.StrandsDiscovery.invoke", side_effect=FakeRuntime().invoke):
                page.button(key="generate").click().run()
            self.assertIsNotNone(page.session_state.design)
            self.assertEqual(len(page.code), 1)
            page.chat_input[0].set_value("修改内容").run()
            self.assertTrue(page.button(key="generate").disabled)
            self.assertEqual(len(page.code), 0)
            self.assertFalse(page.exception)


if __name__ == "__main__":
    unittest.main()
