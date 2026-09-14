import copy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from discovery import DiscoveryResult, Interview, Requirements


def result(next_field=None, **changes):
    values = dict(goal="整理课程作业", target_users="大学生", tasks="给出学习安排建议",
                  data_access="用户上传的课程文件", autonomy="仅建议，不操作日历",
                  constraints="不长期存储课程资料", assumptions=[], unresolved=[])
    values.update(changes)
    return DiscoveryResult(requirements=Requirements(**values), next_field=next_field)


def respond(value):
    return lambda context, **kwargs: value


class InterviewTests(unittest.TestCase):
    def test_five_questions_is_hard_cap_even_if_model_requests_sixth(self):
        state = Interview()
        for name in ["goal", "target_users", "tasks", "data_access", "autonomy"]:
            state.advance("回答", respond(result(name)))
        self.assertEqual(len(state.asked), 5)
        state.advance("回答第五问", respond(result("constraints", unresolved=["预算尚未确定"])))
        self.assertEqual(state.stage, "summary")
        self.assertEqual(len(state.asked), 5)
        self.assertEqual(state.requirements.unresolved, ["预算尚未确定"])

    def test_enough_information_can_finish_without_questions(self):
        state = Interview()
        state.advance("完整想法", respond(result()))
        self.assertEqual(state.stage, "summary")
        self.assertEqual(state.asked, [])

    def test_confirmation_gate_and_copy(self):
        state = Interview()
        with self.assertRaises(ValueError):
            state.confirm()
        state.advance("想法", respond(result()))
        with self.assertRaises(ValueError):
            state.confirmed_requirements()
        state.confirm()
        exported = state.confirmed_requirements()
        exported.goal = "外部修改"
        self.assertNotEqual(state.requirements.goal, exported.goal)

    def test_correction_keeps_question_count_and_requires_confirmation(self):
        state = Interview()
        state.advance("想法", respond(result("data_access")))
        state.advance("仅文件", respond(result()))
        state.confirm()
        state.advance("改成老师使用", respond(result("tasks", target_users="老师")))
        self.assertEqual(state.stage, "summary")
        self.assertEqual(state.asked, ["data_access"])
        self.assertEqual(state.requirements.target_users, "老师")
        with self.assertRaises(ValueError):
            state.confirmed_requirements()

    def test_failed_request_does_not_change_state_and_retry_adds_input_once(self):
        state = Interview()
        state.advance("想法", respond(result("goal")))
        before = copy.deepcopy(state)
        def fail(*args, **kwargs):
            raise RuntimeError("Synthetic failure")
        with self.assertRaises(RuntimeError):
            state.advance("回答", fail)
        self.assertEqual(state, before)
        state.advance("回答", respond(result()))
        self.assertEqual(sum(m["text"] == "回答" for m in state.transcript), 1)

    def test_invalid_model_output_does_not_overwrite_summary(self):
        state = Interview()
        state.advance("想法", respond(result()))
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            state.advance("修改", respond({"confirmed": True}))
        self.assertEqual(state, before)

    def test_repeated_question_rejected_without_consuming_budget(self):
        state = Interview()
        state.advance("想法", respond(result("goal")))
        before = copy.deepcopy(state)
        with self.assertRaises(ValueError):
            state.advance("回答", respond(result("goal")))
        self.assertEqual(state, before)

    def test_early_summary_ignores_extra_question(self):
        state = Interview()
        state.advance("想法", respond(result("goal")))
        state.advance("先总结", respond(result("tasks")), force_summary=True)
        self.assertEqual(state.stage, "summary")
        self.assertEqual(len(state.asked), 1)


class PageTests(unittest.TestCase):
    def test_page_answer_confirm_modify_reconfirm(self):
        with patch("discovery.StrandsDiscovery.__call__", side_effect=[
            result("autonomy"), result(), result(target_users="老师")
        ]):
            page = AppTest.from_file("app.py", default_timeout=15).run()
            self.assertFalse(page.exception)
            self.assertNotIn("confirm", [b.key for b in page.button])
            page.chat_input[0].set_value("我想做课程助手").run()
            self.assertEqual(page.session_state.interview.stage, "interview")
            page.chat_input[0].set_value("只给建议").run()
            self.assertEqual(page.session_state.interview.stage, "summary")
            page.button(key="confirm").click().run()
            self.assertEqual(page.session_state.interview.stage, "confirmed")
            page.chat_input[0].set_value("改成老师使用").run()
            self.assertEqual(page.session_state.interview.stage, "summary")
            page.button(key="confirm").click().run()
            self.assertEqual(page.session_state.interview.requirements.target_users, "老师")
            self.assertEqual(len(page.session_state.interview.asked), 1)
            self.assertFalse(page.exception)

    def test_failed_page_input_can_retry_without_losing_answer(self):
        with patch("discovery.StrandsDiscovery.__call__", side_effect=[RuntimeError(), result()]):
            page = AppTest.from_file("app.py", default_timeout=15).run()
            page.chat_input[0].set_value("课程助手").run()
            self.assertTrue(page.session_state.failed)
            self.assertEqual(page.session_state.pending[0], "课程助手")
            self.assertEqual(page.session_state.interview.asked, [])
            page.button(key="retry").click().run()
            self.assertFalse(page.session_state.failed)
            self.assertIsNone(page.session_state.pending)
            self.assertEqual(page.session_state.interview.stage, "summary")
            self.assertEqual(len(page.session_state.interview.transcript), 2)
            self.assertFalse(page.exception)


if __name__ == "__main__":
    unittest.main()
