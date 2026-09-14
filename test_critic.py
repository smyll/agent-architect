import copy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from blueprint import Blueprint, DesignArtifact, fingerprint
from critic import Review, design_fingerprint, review_design
from test_blueprint import blueprint_data, confirmed
from test_discovery import result


def artifact_for(state):
    return DesignArtifact(fingerprint(state.requirements), Blueprint(**blueprint_data()),
                          "print('starter')\n", [], [])


class Runtime:
    def __init__(self, value):
        self.value = value

    def invoke(self, prompt, context, **kwargs):
        assert kwargs["tools"] == ()
        return self.value.model_dump_json()


def finding(quote="仅当前会话", path="memory_strategy"):
    return Review.model_validate({"strengths": [], "issues": [{"severity": "low", "category": "assumptions",
        "title": "说明保留范围", "explanation": "需要区分应用状态和提供商保留政策。",
        "evidence": [{"source": "blueprint", "path": path, "quote": quote}],
        "suggestion": "把范围限定为本地应用状态。"}]})


class CriticTests(unittest.TestCase):
    def test_review_preserves_original_and_accepts_real_evidence(self):
        state = confirmed()
        artifact = artifact_for(state)
        before = copy.deepcopy(artifact)
        reviewed = review_design(state, artifact, Runtime(finding()))
        self.assertEqual(artifact, before)
        self.assertEqual(reviewed.design_fingerprint, design_fingerprint(artifact))

    def test_zero_findings_is_valid(self):
        state = confirmed()
        reviewed = review_design(state, artifact_for(state), Runtime(Review(strengths=[], issues=[])))
        self.assertEqual(reviewed.review.issues, [])

    def test_fabricated_quote_rejected(self):
        state = confirmed()
        with self.assertRaises(ValueError):
            review_design(state, artifact_for(state), Runtime(finding("不存在的原文")))

    def test_missing_field_rejected(self):
        state = confirmed()
        with self.assertRaises(KeyError):
            review_design(state, artifact_for(state), Runtime(finding(path="invented")))

    def test_unconfirmed_and_stale_requirements_rejected(self):
        state = confirmed()
        artifact = artifact_for(state)
        state.stage = "summary"
        with self.assertRaises(ValueError):
            review_design(state, artifact, Runtime(finding()))
        state.confirm()
        state.requirements.tasks = "新的任务"
        with self.assertRaises(ValueError):
            review_design(state, artifact, Runtime(finding()))

    def test_blueprint_or_code_changes_change_review_identity(self):
        artifact = artifact_for(confirmed())
        original = design_fingerprint(artifact)
        artifact.code += "# changed\n"
        self.assertNotEqual(original, design_fingerprint(artifact))
        original = design_fingerprint(artifact)
        artifact.blueprint.memory_strategy = "修改策略"
        self.assertNotEqual(original, design_fingerprint(artifact))

    def test_page_failure_retry_and_old_review_hidden_after_edit(self):
        state = confirmed()
        artifact = artifact_for(state)
        page = AppTest.from_file("app.py", default_timeout=15).run()
        self.assertTrue(page.button(key="run_critic").disabled)
        page.session_state.interview = state
        page.session_state.design = artifact
        page.run()
        with patch("discovery.StrandsDiscovery.invoke", side_effect=[RuntimeError(), finding().model_dump_json()]):
            page.button(key="run_critic").click().run()
            self.assertTrue(page.session_state.critic_failed)
            self.assertEqual(page.session_state.design, artifact)
            page.button(key="run_critic").click().run()
            self.assertFalse(page.session_state.critic_failed)
            self.assertIsNotNone(page.session_state.critic)
        with patch("discovery.StrandsDiscovery.__call__", return_value=result(tasks="新任务")):
            page.chat_input[0].set_value("修改任务").run()
        self.assertTrue(page.button(key="run_critic").disabled)
        self.assertFalse(any("说明保留范围" in m.value for m in page.markdown))
        self.assertFalse(page.exception)


if __name__ == "__main__":
    unittest.main()
