"""Local UI for the first reviewable product slice."""
import logging
import os
import json

import streamlit as st

from discovery import Interview, LABELS, StrandsDiscovery
from blueprint import DesignRun, fingerprint
from critic import design_fingerprint, review_design

logging.disable(logging.CRITICAL)
st.set_page_config(page_title="Agent Architect", page_icon="◈", layout="wide")

if "interview" not in st.session_state:
    st.session_state.interview = Interview()
    st.session_state.responder = StrandsDiscovery()
    st.session_state.pending = None
    st.session_state.failed = False
    st.session_state.settings = {}

session = st.session_state.interview
for name, default in {"design": None, "design_pending": False, "design_failed": False,
                      "design_run": None, "critic": None, "critic_failed": False}.items():
    st.session_state.setdefault(name, default)
if not hasattr(st.session_state.responder, "invoke"):
    st.session_state.responder = StrandsDiscovery()


def queue(text, force=False):
    st.session_state.pending = (text, force)
    st.session_state.failed = False
    st.rerun()


with st.sidebar:
    st.title("◈ Agent Architect")
    st.caption("把一个想法，整理成可实施的 Agent 需求。")
    st.divider()
    st.write("**01 · 需求发现**")
    st.write("**02 · 架构与代码**")
    st.write("**03 · 审查与交付**")
    st.divider()
    with st.expander("模型连接"):
        st.caption("默认读取本机环境变量。修改配置后，点击重试可继续当前步骤。")
        with st.form("connection"):
            provider = st.selectbox("提供商", ["deepseek", "openai_compatible"])
            model_id = st.text_input("模型名称", value=os.getenv("MODEL_ID", "deepseek-flash"))
            base_url = st.text_input("API 地址", value=os.getenv("MODEL_BASE_URL", "https://api.deepseek.com"))
            api_key = st.text_input("API Key（留空使用环境变量）", type="password")
            if st.form_submit_button("应用连接配置"):
                st.session_state.settings = {"provider": provider, "model_id": model_id.strip(),
                                             "base_url": base_url.strip(), "api_key": api_key.strip()}
                st.success("已应用；下次调用生效。")
        st.caption("密钥仅保留在当前会话，不写入文件。")
    st.caption("当前版本在本机运行。刷新页面可能重置会话；确认后可下载需求记录。")

st.caption("IDEA → REQUIREMENTS → BLUEPRINT")
st.title("先把问题说清楚。")
st.write("从你的想法出发，最多追问五个关键问题。由你确认最终需求。")
st.progress(len(session.asked) / 5, text=f"已提出 {len(session.asked)} / 5 个问题 · 信息足够时提前结束")

pending = st.session_state.pending
if pending and not st.session_state.failed:
    with st.spinner("正在整理需求…"):
        try:
            session.advance(pending[0], st.session_state.responder,
                            force_summary=pending[1], settings=st.session_state.settings)
        except Exception:
            st.session_state.failed = True
        else:
            st.session_state.pending = None
        st.rerun()

if st.session_state.failed:
    st.error("本次调用未完成。已保留输入和当前进度，可重试或修改左侧模型连接。")
    st.text("待提交内容：" + pending[0])
    if st.button("重试本次输入", key="retry"):
        st.session_state.failed = False
        st.rerun()

if st.session_state.design_pending:
    run = DesignRun()
    st.session_state.design_run = run
    with st.spinner("正在查询设计依据并生成蓝图…"):
        try:
            artifact = run.generate(session, st.session_state.responder, st.session_state.settings)
        except Exception:
            st.session_state.design_failed = True
        else:
            st.session_state.design = artifact
            st.session_state.design_failed = False
        st.session_state.design_pending = False
        st.rerun()

left, right = st.columns([1.05, 1], gap="large")
with left:
    st.subheader("需求对话")
    with st.container(height=430, border=True):
        if not session.transcript:
            st.chat_message("assistant").write("你想做一个什么样的 Agent？可以先用一句话描述。")
            st.caption("例如：帮助大学生管理课程作业的助手。")
        for message in session.transcript:
            st.chat_message(message["role"]).write(message["text"])
    placeholder = "描述你的想法" if session.stage == "idea" else (
        "指出需要修改的内容" if session.stage in {"summary", "confirmed"} else "回答当前问题；不确定也可以说明")
    text = st.chat_input(placeholder, key="message", max_chars=6000,
                         disabled=bool(st.session_state.pending))
    if text and text.strip():
        queue(text)
    if session.stage == "interview" and st.button("先用已有信息生成总结", disabled=bool(pending), key="summarize"):
        queue("请用已有信息生成需求总结，尚不明确的内容标记为待确认。", True)

with right:
    st.subheader("需求总结")
    if session.requirements is None:
        st.info("你的目标、任务、数据来源和权限边界将整理在这里。")
    else:
        if session.stage == "interview":
            st.caption("整理中 · 访谈结束后可确认")
        for name, label in LABELS.items():
            st.markdown(f"**{label}**")
            st.write(getattr(session.requirements, name))
        st.markdown("**假设（不是已知事实）**")
        for item in session.requirements.assumptions:
            st.write("• " + item)
        if not session.requirements.assumptions:
            st.caption("暂无额外假设")
        st.markdown("**待确认项**")
        for item in session.requirements.unresolved:
            st.write("• " + item)
        if not session.requirements.unresolved:
            st.caption("暂无")
        if session.stage == "summary":
            st.caption("确认表示接受上面的需求以及明确列出的假设、待确认项。")
            if st.button("确认这份需求", key="confirm", type="primary", disabled=bool(pending)):
                session.confirm()
                st.rerun()
        elif session.stage == "confirmed":
            st.success("需求已确认。可在下方生成架构与代码骨架。")
            st.caption("继续在左侧提出修改，会生成新版本并要求重新确认。")
            st.download_button("下载已确认需求", session.confirmed_requirements().model_dump_json(indent=2),
                               file_name="requirements.json", mime="application/json")

st.divider()
st.header("架构与起步代码")
can_generate = session.stage == "confirmed" and not st.session_state.pending
if not can_generate:
    st.caption("先确认需求，再生成架构。修改需求后需要重新确认、重新生成。")
if st.button("生成蓝图与代码骨架", key="generate", type="primary", disabled=not can_generate):
    st.session_state.design_pending = True
    st.rerun()
if st.session_state.design_failed:
    st.error("本次生成未完成。需求仍保留，可修改模型连接后再次点击生成。")
    with st.expander("本次工具调用记录"):
        st.json(st.session_state.design_run.trace)

artifact = st.session_state.design
current = (artifact is not None and session.stage == "confirmed" and
           artifact.requirements_fingerprint == fingerprint(session.requirements) and not st.session_state.pending)
if artifact and not current:
    st.warning("之前的蓝图已不适用于当前待确认或已修改的需求。确认后请重新生成。")
if current:
    if st.session_state.design_failed:
        st.caption("下方保留的是上一份成功结果，本次重试没有替换它。")
    blueprint = artifact.blueprint
    architecture_tab, code_tab, evidence_tab = st.tabs(["架构蓝图", "代码骨架", "工具调用与依据"])
    with architecture_tab:
        st.subheader(blueprint.name)
        st.write(blueprint.purpose)
        st.write("**目标用户：** " + blueprint.target_user)
        st.write("**架构模式：** " + blueprint.pattern)
        st.write(blueprint.pattern_reason)
        st.markdown("**核心能力**")
        for capability in blueprint.capabilities:
            st.write("• " + capability)
        st.markdown("**业务工具**")
        if not blueprint.tools:
            st.write("无需外部业务工具；通过用户提供的上下文完成当前范围。")
        for spec in blueprint.tools:
            st.write(f"{spec.name} · {spec.purpose} · {spec.access}")
            st.caption(spec.approval + "（代码中为待实现占位）")
        st.markdown("**记忆策略**")
        st.write(blueprint.memory_strategy)
        st.markdown("**工作流程**")
        for index, step in enumerate(blueprint.workflow, 1):
            st.write(f"{index}. {step}")
        st.markdown("**风险与待实现部分**")
        for item in blueprint.risks + blueprint.limitations:
            st.write("• " + item)
        st.download_button("下载蓝图 JSON", blueprint.model_dump_json(indent=2),
                           file_name="blueprint.json", mime="application/json")
        st.caption("此处保留原始蓝图；Critic 意见在下方单独展示。")
    with code_tab:
        st.success("已通过 Python 语法解析与编译检查（未执行生成代码）。")
        st.info("这是起步骨架：业务工具尚未实现，长期记忆等接入也需要开发。")
        st.code(artifact.code, language="python")
        st.download_button("下载 Python 骨架", artifact.code, file_name="agent_starter.py", mime="text/x-python")
        st.caption("运行前安装 strands-agents[openai]，并设置 MODEL_API_KEY、MODEL_BASE_URL、MODEL_ID。")
    with evidence_tab:
        st.write("以下记录来自实际执行的工具，文档来源由程序记录。")
        for source in artifact.sources:
            st.markdown(f"[{source['topic']} · Strands 官方文档]({source['source']})")
            st.caption("获取时间（UTC）：" + source["retrieved_at"])
        for index, call in enumerate(artifact.trace, 1):
            with st.expander(f"{index}. {call['tool']} · {call['status']}"):
                st.json(call)

st.divider()
st.header("Critic · 架构审查")
st.caption("检查需求遗漏、工具、安全与隐私、自治程度、假设，以及代码与蓝图的一致性。")
if st.button("审查当前蓝图", key="run_critic", disabled=not current, type="primary"):
    with st.spinner("正在对照需求与代码审查…"):
        try:
            reviewed = review_design(session, artifact, st.session_state.responder, st.session_state.settings)
        except Exception:
            st.session_state.critic_failed = True
        else:
            st.session_state.critic = reviewed
            st.session_state.critic_failed = False
    st.rerun()
if not current:
    st.caption("先生成与当前已确认需求对应的蓝图，才能开始审查。")
if st.session_state.critic_failed and current:
    st.error("本次审查未完成。蓝图与需求仍保留，可以再次点击审查或修改模型连接。")
reviewed = st.session_state.critic
review_current = current and reviewed is not None and reviewed.design_fingerprint == design_fingerprint(artifact)
if reviewed and not review_current:
    st.caption("之前的审查对应旧版本，当前结果需要重新审查。")
if review_current:
    if st.session_state.critic_failed:
        st.caption("以下为上一次成功的审查结果。")
    review = reviewed.review
    high = sum(issue.severity == "high" for issue in review.issues)
    if review.issues:
        st.warning(f"发现 {len(review.issues)} 项待处理问题，其中 {high} 项高优先级。")
    else:
        st.success("本次审查未发现明确问题；不代表代码已经通过运行测试或安全认证。")
    for strength in review.strengths:
        st.write("✓ " + strength)
    severity_labels = {"high": "高", "medium": "中", "low": "低"}
    for issue in review.issues:
        with st.container(border=True):
            st.markdown(f"**[{severity_labels[issue.severity]}] {issue.title}**")
            st.write(issue.explanation)
            for evidence in issue.evidence:
                st.caption("依据：" + evidence.source + ("." + evidence.path if evidence.path else ""))
                st.text(evidence.quote)
            st.write("**建议：** " + issue.suggestion)
    st.caption("已核对引用文字确实存在；问题判断仍来自模型。原蓝图和代码未被自动修改。")
    st.download_button("下载审查报告", review.model_dump_json(indent=2),
                       file_name="critic-review.json", mime="application/json")
    package = {"requirements": session.confirmed_requirements().model_dump(),
               "blueprint": artifact.blueprint.model_dump(), "starter_code": artifact.code,
               "critic_review": review.model_dump(), "sources": artifact.sources,
               "status": "原始方案及审查意见，尚未自动修订；生成代码未执行"}
    st.download_button("下载完整方案与审查意见", json.dumps(package, ensure_ascii=False, indent=2),
                       file_name="agent-specification.json", mime="application/json")
