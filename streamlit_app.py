# -*- coding: utf-8 -*-
"""
儿科护理急救动态分支虚拟仿真训练平台｜网页原型 v0.8.2 scoring-table

本版重点：
- 时间/分级/得分/复评移至左侧病例下方的运行信息区；
- 左侧病例与实时状态栏加宽，生命体征以卡片网格显示；
- 右侧操作按钮统一使用简洁短标题，不再显示冗余解释；
- 当生命体征、临床表现或分级发生变化时，相关卡片自动闪动提示；
- 训练模式保留步骤提示与原因说明；考试模式仅保留干净操作界面；
- 肌注肾上腺素需输入剂量，系统按体重核对 0.01 mg/kg 与 0.5 mg 上限。
- 每次开始/重置模拟时自动随机生成年龄与体重：年龄 2-12 岁，体重 10-35 kg。
- 按用户确认的14项评分细则校准最佳时间窗：总分20分。
- 固定配合 Windows 稳定启动脚本使用 8502 端口。

声明：
    本系统仅用于护理教学、培训与科研可行性验证，不用于临床诊疗决策。
"""

from __future__ import annotations

import html
import json
import os
import random
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Set

import streamlit as st

from peds_anaphylaxis_sim.engine import Simulator, load_scenario, save_report


APP_TITLE = "儿科护理急救动态分支虚拟仿真训练平台"
APP_SUBTITLE = "Dynamic Branching Virtual Simulation Platform for Pediatric Nursing Emergency Training"
ROOT = Path(__file__).resolve().parent
SCENARIO_DIR = ROOT / "peds_anaphylaxis_sim" / "scenarios"
RUNS_DIR = ROOT / "runs_web"


def list_scenarios() -> Dict[str, Path]:
    """Only expose the two bedside scripts requested for the web prototype."""
    items = []
    role_order = {"initial": 0, "variant": 1}
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = data.get("scenario", {})
            role = meta.get("script_role", "")
            if role not in role_order:
                continue
            display_name = meta.get("display_name") or meta.get("title", path.stem)
            version = meta.get("version", "")
            label = f"{display_name}｜{version}" if version else str(display_name)
            items.append((role_order[role], label, path))
        except Exception:
            continue
    return {label: path for _, label, path in sorted(items, key=lambda x: x[0])}


def safe_filename_part(text: str) -> str:
    cleaned = str(text or "").strip()
    for ch in '\\/:*?"<>|':
        cleaned = cleaned.replace(ch, "_")
    cleaned = cleaned.replace(" ", "_")
    return cleaned or "unknown"


def randomize_patient_profile(scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Create a per-run patient profile without modifying the source JSON file.

    Randomization is performed only when the user clicks start/reset. Streamlit
    reruns caused by button clicks or UI refreshes will keep the active patient's
    age and weight unchanged.
    """
    rng = random.SystemRandom()
    randomized = json.loads(json.dumps(scenario, ensure_ascii=False))
    patient = randomized.setdefault("patient", {})
    patient["age_years"] = rng.randint(2, 12)
    patient["weight_kg"] = rng.randint(10, 35)
    patient["randomized_profile"] = True
    patient["randomization_rule"] = "age_years: 2-12; weight_kg: 10-35"
    return randomized


def state_key() -> str:
    return "active_simulator"


def init_session() -> None:
    defaults = {
        "participant_id": "",
        "mode": "coach",
        "scenario_label": "",
        "seed": -1,
        "active_simulator": None,
        "active_scenario": None,
        "active_scenario_path": "",
        "active_script_name": "",
        "session_id": "",
        "ended": False,
        "end_reason": "",
        "last_report": None,
        "last_report_paths": None,
        "show_raw_log": False,
        "last_ui_snapshot": None,
        "pending_dose_action_id": "",
        "pending_dose_action_label": "",
        "last_dose_feedback": "",
        "last_dose_feedback_level": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def visible_vitals(sim: Simulator) -> Dict[str, str]:
    v = sim.state.vitals
    f = sim.state.flags
    out = {"体温": f"{v.get('Temp', 0):.1f} ℃"}
    if f.get("monitor_on", False):
        out.update({
            "SpO₂": f"{v.get('SpO2', 0):.0f} %",
            "HR": f"{v.get('HR', 0):.0f} /min",
            "RR": f"{v.get('RR', 0):.0f} /min",
        })
    else:
        out.update({"SpO₂": "未连接监护", "HR": "未连接监护", "RR": "未连接监护"})
    if f.get("bp_checked", False):
        out["BP"] = f"{v.get('SBP', 0):.0f}/{v.get('DBP', 0):.0f} mmHg"
    else:
        out["BP"] = "未测量"
    return out


def symptoms_text(sim: Simulator) -> str:
    s = sim.state.symptoms
    parts = []
    if s.get("rash", 0) >= 1:
        parts.append("皮疹/风团")
    if s.get("angioedema", 0) >= 1:
        parts.append("血管性水肿")
    if s.get("wheeze", 0) >= 1:
        parts.append("喘鸣")
    if s.get("stridor", 0) >= 1:
        parts.append("喉鸣/声音改变")
    if s.get("gi", 0) >= 1:
        parts.append("胃肠道症状")
    if s.get("consciousness", 0) >= 1:
        labels = ["烦躁", "嗜睡", "反应差"]
        parts.append(labels[min(2, int(s.get("consciousness", 1)) - 1)])
    return "、".join(parts) if parts else "无明显主观异常"


def grade_badge(sim: Simulator) -> str:
    name = {1: "I", 2: "II", 3: "III", 4: "IV"}.get(sim.state.grade, str(sim.state.grade))
    return f"分级 {name}"


def get_report_download(report: Dict[str, Any]) -> bytes:
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def start_simulation(scenario_path: Path, mode: str, seed: int, participant_id: str) -> None:
    scenario_source = load_scenario(str(scenario_path))
    scenario = randomize_patient_profile(scenario_source)
    sim = Simulator(scenario, mode=mode, seed=seed)
    meta = scenario.get("scenario", {})
    mode_name = "training" if mode == "coach" else "exam"
    script_name = safe_filename_part(meta.get("script_name") or scenario_path.stem)
    participant = safe_filename_part(participant_id or "anonymous")
    st.session_state.active_simulator = sim
    st.session_state.active_scenario = scenario
    st.session_state.active_scenario_path = str(scenario_path)
    st.session_state.active_script_name = script_name
    st.session_state.session_id = f"{mode_name}_{script_name}_{participant}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    st.session_state.ended = False
    st.session_state.end_reason = ""
    st.session_state.last_report = None
    st.session_state.last_report_paths = None
    st.session_state.last_ui_snapshot = None
    st.session_state.pending_dose_action_id = ""
    st.session_state.pending_dose_action_label = ""
    st.session_state.last_dose_feedback = ""
    st.session_state.last_dose_feedback_level = ""


def finalize_if_done() -> None:
    sim = st.session_state.active_simulator
    if sim is None or st.session_state.ended:
        return
    done, why = sim.is_done()
    if done:
        report = sim.build_report()
        out_dir = RUNS_DIR / st.session_state.session_id
        json_path, md_path = save_report(report, str(out_dir))
        st.session_state.ended = True
        st.session_state.end_reason = why
        st.session_state.last_report = report
        st.session_state.last_report_paths = (json_path, md_path)


def render_sidebar() -> None:
    st.sidebar.title("训练设置")
    scenarios = list_scenarios()
    default_label = next(iter(scenarios.keys()), "")
    if not st.session_state.scenario_label:
        st.session_state.scenario_label = default_label

    st.session_state.participant_id = st.sidebar.text_input(
        "护士/参与者编号",
        value=st.session_state.participant_id,
        placeholder="例如 P01 / N1-001",
    )

    st.session_state.mode = st.sidebar.radio(
        "运行模式",
        options=["coach", "exam"],
        format_func=lambda x: "训练模式（逐步提示）" if x == "coach" else "考试模式（选项随机）",
        index=0 if st.session_state.mode == "coach" else 1,
    )

    st.session_state.scenario_label = st.sidebar.selectbox(
        "情景脚本",
        options=list(scenarios.keys()),
        index=list(scenarios.keys()).index(st.session_state.scenario_label)
        if st.session_state.scenario_label in scenarios else 0,
    )

    st.session_state.seed = st.sidebar.number_input(
        "随机种子（-1为按当前时间随机）",
        min_value=-1,
        value=int(st.session_state.seed),
        step=1,
    )

    if st.sidebar.button("开始/重置本次模拟", type="primary", use_container_width=True):
        start_simulation(
            scenario_path=scenarios[st.session_state.scenario_label],
            mode=st.session_state.mode,
            seed=int(st.session_state.seed),
            participant_id=st.session_state.participant_id.strip(),
        )
        st.rerun()

    st.sidebar.divider()
    st.sidebar.caption("声明：仅用于护理教学、培训与科研可行性验证，不用于临床诊疗决策。")


def inject_compact_css() -> None:
    """Compact, clinical-monitor-like layout plus flash animation for changes."""
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 0.55rem !important;
            padding-bottom: 0.75rem !important;
            padding-left: 1.05rem !important;
            padding-right: 1.05rem !important;
            max-width: 100% !important;
        }
        h1, h2, h3, h4 {
            margin-top: 0.05rem !important;
            margin-bottom: 0.12rem !important;
        }
        h1 {font-size: 1.22rem !important;}
        h2 {font-size: 1.08rem !important;}
        h3 {font-size: 1.02rem !important;}
        p, li, .stMarkdown, .stCaption, label {
            font-size: 0.86rem !important;
        }
        div[data-testid="stVerticalBlock"] { gap: 0.52rem !important; }
        div[data-testid="stHorizontalBlock"] { gap: 0.72rem !important; }
        div[data-testid="stVerticalBlockBorderWrapper"] { padding: 0.76rem !important; }
        .stAlert { padding: 0.24rem 0.45rem !important; }
        hr { margin: 0.22rem 0 !important; }
        [data-testid="stSidebar"] .block-container { padding-top: 0.65rem !important; }

        .app-title {
            font-weight: 700;
            font-size: 1.02rem;
            line-height: 1.15;
            margin-bottom: 0.08rem;
        }
        .app-subtitle {
            color: #68717d;
            font-size: 0.72rem;
            line-height: 1.1;
        }
        .status-panel {
            border: 1px solid #dfe4ec;
            border-radius: 0.78rem;
            background: #ffffff;
            padding: 0.72rem 0.82rem;
            margin-top: 0.78rem;
            margin-bottom: 0.42rem;
        }
        .status-panel-title {
            font-size: 0.88rem;
            font-weight: 750;
            color: #111827;
            margin-bottom: 0.52rem;
        }
        .top-strip {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.58rem;
            margin-bottom: 0.0rem;
        }
        .top-card {
            min-height: 3.05rem;
            border: 1px solid #e5e8ed;
            background: #f9fafc;
            border-radius: 0.62rem;
            padding: 0.48rem 0.58rem;
        }
        .top-card .label {
            color: #667085;
            font-size: 0.76rem;
            line-height: 1.0;
            margin-bottom: 0.30rem;
        }
        .top-card .value {
            color: #111827;
            font-weight: 780;
            font-size: 1.02rem;
            line-height: 1.05;
        }
        .session-line {
            color: #667085;
            font-size: 0.72rem;
            line-height: 1.25;
            text-align: left;
            margin-top: 0.48rem;
        }
        .patient-panel {
            border: 1px solid #d9dee7;
            border-radius: 0.90rem;
            background: #ffffff;
            padding: 1.18rem 1.24rem 1.16rem 1.24rem;
        }
        .patient-head {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 1.0rem;
            margin-bottom: 0.44rem;
        }
        .patient-title {
            font-weight: 800;
            font-size: 1.34rem;
            line-height: 1.2;
            white-space: nowrap;
        }
        .patient-meta {
            color: #334155;
            font-size: 1.10rem;
            font-weight: 650;
            line-height: 1.35;
            text-align: right;
        }
        .baseline-box {
            color: #374151;
            font-size: 1.05rem;
            line-height: 1.58;
            margin-bottom: 0.72rem;
        }
        .clinical-card {
            border-radius: 0.74rem;
            border: 1px solid #e5e7eb;
            background: #f8fafc;
            padding: 0.86rem 0.92rem;
            margin-bottom: 0.70rem;
        }
        .clinical-card .label {
            color: #667085;
            font-size: 0.92rem;
            margin-bottom: 0.24rem;
        }
        .clinical-card .value {
            color: #111827;
            font-weight: 820;
            font-size: 1.58rem;
            line-height: 1.38;
        }
        .vital-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.66rem;
        }
        .vital-card {
            min-height: 4.72rem;
            border-radius: 0.76rem;
            border: 1px solid #e5e7eb;
            background: #fbfcfe;
            padding: 0.78rem 0.82rem;
        }
        .vital-card .label {
            color: #667085;
            font-size: 0.94rem;
            line-height: 1.0;
            margin-bottom: 0.32rem;
        }
        .vital-card .value {
            color: #101828;
            font-weight: 850;
            font-size: 1.62rem;
            line-height: 1.12;
        }
        .vital-card.warn { border-color: #f6c768; background: #fffbeb; }
        .vital-card.danger { border-color: #f2a0a0; background: #fff5f5; }
        .change-banner {
            margin-top: 0.45rem;
            padding: 0.30rem 0.46rem;
            border-radius: 0.50rem;
            border: 1px solid #ffd18a;
            background: #fff7e6;
            color: #8a4b00;
            font-size: 0.74rem;
            font-weight: 700;
        }
        @keyframes clinicalFlash {
            0%   { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.60); transform: translateY(0); }
            45%  { box-shadow: 0 0 0 5px rgba(245, 158, 11, 0.22); transform: translateY(-1px); }
            100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.00); transform: translateY(0); }
        }
        .flash {
            animation: clinicalFlash 0.80s ease-in-out 0s 2;
            border-color: #f59e0b !important;
            background: #fff7e6 !important;
        }
        .section-caption {
            color: #667085;
            font-size: 0.72rem;
            line-height: 1.1;
        }
        .action-head {
            display:flex;
            align-items:baseline;
            justify-content:space-between;
            gap:0.65rem;
            margin-bottom:0.62rem;
        }
        .action-title {
            font-weight:800;
            font-size:1.12rem;
        }
        .action-note {
            color:#667085;
            font-size:0.82rem;
            text-align:right;
        }
        .stButton > button {
            min-height: 3.08rem !important;
            padding: 0.50rem 0.58rem !important;
            font-size: 1.03rem !important;
            line-height: 1.22 !important;
            border-radius: 0.66rem !important;
            white-space: normal !important;
        }
        .dose-card {
            border: 1px solid #c7d2fe;
            background: #eef2ff;
            border-radius: 0.78rem;
            padding: 0.76rem 0.86rem;
            margin-bottom: 0.76rem;
        }
        .dose-card .title {
            font-weight: 800;
            font-size: 1.02rem;
            color: #1e3a8a;
            margin-bottom: 0.26rem;
        }
        .dose-card .text {
            font-size: 0.90rem;
            color: #334155;
            line-height: 1.40;
        }
        .coach-prompt {
            border: 1px solid #ffd18a;
            background: #fff8e8;
            border-radius: 0.70rem;
            padding: 0.62rem 0.76rem;
            margin-top: 0.50rem;
            margin-bottom: 0.38rem;
        }
        .coach-prompt .title {
            font-size: 0.86rem;
            font-weight: 750;
            color: #8a4b00;
            margin-bottom: 0.22rem;
        }
        .coach-prompt .text {
            font-size: 0.92rem;
            font-weight: 700;
            color: #111827;
            line-height: 1.35;
        }
        .coach-prompt .reason {
            font-size: 0.80rem;
            color: #6b4e16;
            line-height: 1.35;
            margin-top: 0.26rem;
        }
        div[data-testid="stExpander"] details {
            border-radius: 0.55rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def compact_header() -> None:
    st.markdown(
        f"<div class='app-title'>{html.escape(APP_TITLE)}</div>"
        f"<div class='app-subtitle'>动态分支 · 实时状态 · 操作评分 · 报告导出</div>",
        unsafe_allow_html=True,
    )


def make_ui_snapshot(sim: Simulator) -> Dict[str, Any]:
    return {
        "time": sim.state.t,
        "grade": grade_badge(sim),
        "score": f"{max(0, sim.score - sim.penalties)}/{sim.max_score}",
        "reassess": int(sim.state.flags.get("reassess_count", 0)),
        "symptoms": symptoms_text(sim),
        "vitals": visible_vitals(sim),
    }


def detect_ui_changes(sim: Simulator) -> Dict[str, Any]:
    current = make_ui_snapshot(sim)
    previous = st.session_state.get("last_ui_snapshot")
    changes: Dict[str, Any] = {"grade": False, "symptoms": False, "score": False, "reassess": False, "vitals": set()}

    if isinstance(previous, dict):
        changes["grade"] = previous.get("grade") != current.get("grade")
        changes["symptoms"] = previous.get("symptoms") != current.get("symptoms")
        changes["score"] = previous.get("score") != current.get("score")
        changes["reassess"] = previous.get("reassess") != current.get("reassess")
        prev_vitals = previous.get("vitals", {}) or {}
        cur_vitals = current.get("vitals", {}) or {}
        changed_vitals: Set[str] = set()
        for key, value in cur_vitals.items():
            if prev_vitals.get(key) != value:
                changed_vitals.add(key)
        changes["vitals"] = changed_vitals

    st.session_state.last_ui_snapshot = current
    return changes


def flash_class(condition: bool) -> str:
    return " flash" if condition else ""


def vital_severity_class(sim: Simulator, key: str) -> str:
    """Visual cue only; formal scoring still comes from the simulation engine."""
    v = sim.state.vitals
    f = sim.state.flags
    if key == "SpO₂" and f.get("monitor_on", False):
        spo2 = float(v.get("SpO2", 100))
        if spo2 < 90:
            return " danger"
        if spo2 < 95:
            return " warn"
    if key == "BP" and f.get("bp_checked", False):
        sbp = float(v.get("SBP", 120))
        if sbp < sim.age_sbp_threshold():
            return " danger"
    if key == "HR" and f.get("monitor_on", False):
        hr = float(v.get("HR", 0))
        if hr >= 180:
            return " warn"
    return ""


def compact_action_label(label: str, max_chars: int = 24) -> str:
    cleaned = " ".join(str(label).split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1] + "…"


def render_top_status(sim: Simulator, changes: Dict[str, Any]) -> None:
    score_text = f"{max(0, sim.score - sim.penalties)}/{sim.max_score}"
    items = [
        ("时间", f"{sim.state.t}s", False),
        ("分级", grade_badge(sim), bool(changes.get("grade"))),
        ("得分", score_text, bool(changes.get("score"))),
        ("复评", str(int(sim.state.flags.get("reassess_count", 0))), bool(changes.get("reassess"))),
    ]
    html_items = []
    for label, value, changed in items:
        html_items.append(
            f"<div class='top-card{flash_class(changed)}'>"
            f"<div class='label'>{html.escape(label)}</div>"
            f"<div class='value'>{html.escape(value)}</div>"
            f"</div>"
        )
    st.markdown(
        f"<div class='status-panel'>"
        f"<div class='status-panel-title'>运行信息</div>"
        f"<div class='top-strip'>{''.join(html_items)}</div>"
        f"<div class='session-line'>"
        f"模式：{'训练模式' if sim.mode == 'coach' else '考试模式'}｜"
        f"参与者：{html.escape(st.session_state.participant_id or 'anonymous')}｜"
        f"Session：{html.escape(st.session_state.session_id[-13:] if st.session_state.session_id else '')}"
        f"</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def render_patient_status(sim: Simulator, scenario: Dict[str, Any], changes: Dict[str, Any]) -> None:
    patient = scenario.get("patient", {})
    patient_meta = (
        f"{patient.get('setting','')}｜{patient.get('age_years','')}岁｜"
        f"{patient.get('weight_kg','')} kg｜{patient.get('trigger','')}"
    )
    baseline = scenario.get("baseline", {}).get("time_zero_description", "")
    symptom_now = symptoms_text(sim)
    changed_vitals: Set[str] = changes.get("vitals", set()) or set()
    any_clinical_change = bool(changes.get("symptoms")) or bool(changes.get("grade")) or bool(changed_vitals)

    vital_cards = []
    for key, value in visible_vitals(sim).items():
        cls = "vital-card" + vital_severity_class(sim, key) + flash_class(key in changed_vitals)
        vital_cards.append(
            f"<div class='{cls}'>"
            f"<div class='label'>{html.escape(key)}</div>"
            f"<div class='value'>{html.escape(value)}</div>"
            f"</div>"
        )

    banner = ""
    if any_clinical_change:
        changed_names = []
        if changes.get("grade"):
            changed_names.append("分级")
        if changes.get("symptoms"):
            changed_names.append("临床表现")
        if changed_vitals:
            changed_names.append("生命体征")
        banner = f"<div class='change-banner flash'>⚠ {' / '.join(changed_names)} 已更新，请立即复评判断。</div>"

    st.markdown(
        f"""
        <div class='patient-panel'>
            <div class='patient-head'>
                <div class='patient-title'>病例与实时状态</div>
                <div class='patient-meta'>{html.escape(patient_meta)}</div>
            </div>
            <div class='baseline-box'>{html.escape(baseline)}</div>
            <div class='clinical-card{flash_class(bool(changes.get('symptoms')))}'>
                <div class='label'>当前症状</div>
                <div class='value'>{html.escape(symptom_now)}</div>
            </div>
            <div class='vital-grid'>{''.join(vital_cards)}</div>
            {banner}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_intro() -> None:
    compact_header()
    st.info("请先在左侧设置参与者编号、模式和情景脚本，然后点击“开始/重置本次模拟”。")
    left, right = st.columns([1.1, 1])
    with left:
        st.markdown(
            """
            **v0.8 随机年龄体重版目标**

            - 把原有 Python 动态分支引擎封装成网页端操作界面；
            - 时间/分级/得分/复评移至左侧病例下方，避免占用顶部横向空间；
            - 左侧实时病情区域加宽，并进一步放大病例信息、当前症状和生命体征；
            - 右侧操作按钮采用统一短标题，不显示冗余解释，并增大按钮高度与字号；
            - 肌注肾上腺素需要输入总剂量，系统按 0.01 mg/kg 和 0.5 mg 上限判定有效、无效或药物不良事件；
            - 每次点击“开始/重置本次模拟”时随机生成患儿年龄和体重：年龄 2-12 岁，体重 10-35 kg；
            - 肾上腺素目标剂量会随随机体重自动变化；
            - 为后续病例库、护士账号、后台统计和科研数据导出预留结构。
            """
        )
    with right:
        st.container(border=True).markdown(
            """
            **当前建议使用方式**  
            双击“启动_稳定版_推荐先点这个.cmd”，浏览器访问 `http://127.0.0.1:8502`。  
            训练期间不要关闭黑色窗口，否则网页会连接中断。
            """
        )



def render_epinephrine_dose_panel(sim: Simulator) -> bool:
    """Render dose-confirmation panel for IM epinephrine.

    Returns True when an epinephrine dose is pending; the caller can keep
    the operation area focused and avoid accidental double-click processing.
    """
    pending_id = st.session_state.get("pending_dose_action_id", "")
    if pending_id != "im_epinephrine":
        return False

    weight = float(getattr(sim.state, "weight_kg", 0) or 0)
    target_mg = round(0.01 * weight, 3)
    max_single_mg = 0.5
    st.markdown(
        "<div class='dose-card'>"
        "<div class='title'>肌注肾上腺素：请输入本次总剂量</div>"
        "<div class='text'>单位为 mg。确认后系统会按情景规则判断剂量是否有效。</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if sim.mode == "coach":
        st.caption(f"训练提示：本例体重 {weight:g} kg；预设正确剂量为 0.01 mg/kg，即 {target_mg:g} mg；单次上限 {max_single_mg:g} mg。")

    dose_key = f"epi_dose_mg_{st.session_state.session_id}_{sim.state.t}"
    dose_mg = st.number_input(
        "本次肌注总剂量（mg）",
        min_value=0.0,
        max_value=5.0,
        value=0.0,
        step=0.01,
        format="%.2f",
        key=dose_key,
    )
    c_ok, c_cancel = st.columns([1, 1], gap="medium")
    if c_ok.button("确认剂量并执行", type="primary", use_container_width=True):
        result = sim.apply_epinephrine_dose(float(dose_mg))
        st.session_state.last_dose_feedback = str(result.get("message", ""))
        st.session_state.last_dose_feedback_level = str(result.get("status", ""))
        st.session_state.pending_dose_action_id = ""
        st.session_state.pending_dose_action_label = ""
        sim.tick()
        finalize_if_done()
        st.rerun()
    if c_cancel.button("取消输入", use_container_width=True):
        st.session_state.pending_dose_action_id = ""
        st.session_state.pending_dose_action_label = ""
        st.rerun()
    return True



def render_simulation() -> None:
    sim: Simulator = st.session_state.active_simulator
    scenario: Dict[str, Any] = st.session_state.active_scenario

    changes = detect_ui_changes(sim)

    compact_header()

    finalize_if_done()
    if st.session_state.ended:
        render_report()
        return

    left, right = st.columns([1.05, 1.20], gap="large")

    with left:
        render_patient_status(sim, scenario, changes)
        render_top_status(sim, changes)

        if sim.mode == "coach":
            item = sim.get_guided_prompt_item() if hasattr(sim, "get_guided_prompt_item") else {"text": sim.get_guided_prompt(), "reason": ""}
            prompt = str(item.get("text", ""))
            reason = str(item.get("reason", ""))
            if prompt:
                reason_html = f"<div class='reason'>{html.escape(reason)}</div>" if reason else ""
                st.markdown(
                    f"<div class='coach-prompt'>"
                    f"<div class='title'>训练提示</div>"
                    f"<div class='text'>{html.escape(prompt)}</div>"
                    f"{reason_html}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

        with st.expander("完整状态文本", expanded=False):
            st.code(sim.format_status(), language="text")

    with right:
        with st.container(border=True):
            st.markdown(
                f"<div class='action-head'>"
                f"<div class='action-title'>请选择下一步操作</div>"
                f"<div class='action-note'>每次操作后自动推进 {sim.tick_seconds}s</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

            if st.session_state.get("last_dose_feedback"):
                level = st.session_state.get("last_dose_feedback_level", "")
                msg = st.session_state.get("last_dose_feedback", "")
                if level == "valid":
                    st.success(msg)
                elif level == "overdose":
                    st.error(msg)
                elif level == "underdose":
                    st.warning(msg)
                else:
                    st.info(msg)

            dose_pending = render_epinephrine_dose_panel(sim)

            actions = sim.actions
            option_cols = 4
            for idx in range(0, len(actions), option_cols):
                row = st.columns(option_cols, gap="medium")
                for local_index, (col, action) in enumerate(zip(row, actions[idx: idx + option_cols])):
                    full_label = action.get("label", action.get("id", ""))
                    short_label = compact_action_label(full_label, max_chars=18)
                    aid = action.get("id")
                    button_text = f"{idx + local_index + 1}. {short_label}"
                    with col:
                        if st.button(
                            button_text,
                            key=f"action_{aid}_{sim.state.t}_{idx}_{local_index}",
                            use_container_width=True,
                            disabled=dose_pending,
                        ):
                            st.session_state.last_dose_feedback = ""
                            st.session_state.last_dose_feedback_level = ""
                            if aid == "im_epinephrine":
                                st.session_state.pending_dose_action_id = aid
                                st.session_state.pending_dose_action_label = full_label
                                st.rerun()
                            else:
                                sim.apply_action(aid)
                                sim.tick()
                                finalize_if_done()
                                st.rerun()

            st.divider()
            c1, c2, c3 = st.columns([1.0, 1.05, 2.25], gap="medium")
            if c1.button(f"时间流逝 {sim.tick_seconds}s", use_container_width=True):
                sim.tick()
                finalize_if_done()
                st.rerun()

            if sim.mode != "exam":
                if c2.button("结束并生成报告", use_container_width=True):
                    report = sim.build_report()
                    out_dir = RUNS_DIR / st.session_state.session_id
                    json_path, md_path = save_report(report, str(out_dir))
                    st.session_state.ended = True
                    st.session_state.end_reason = "manual_end"
                    st.session_state.last_report = report
                    st.session_state.last_report_paths = (json_path, md_path)
                    st.rerun()
            c3.caption("训练模式可手动结束；考试模式需达到系统结束条件。")


def render_report() -> None:
    report = st.session_state.last_report
    if not report:
        report = st.session_state.active_simulator.build_report()
        st.session_state.last_report = report

    st.success(f"情景结束：{st.session_state.end_reason}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("结束时间", f"{report.get('end_time_seconds')}s")
    c2.metric("最终分级", report.get("final_grade", ""))
    c3.metric("得分", f"{report.get('score')}/{report.get('max_score')}")
    c4.metric("扣分", report.get("penalties", 0))

    left, right = st.columns([1, 1])
    with left:
        st.markdown("**关键时间轴**")
        timeline = report.get("key_timeline", {})
        st.table([{"指标": k, "时间/次数": v} for k, v in timeline.items()])
    with right:
        st.markdown("**问题汇总**")
        issues = report.get("process_safety_issues", [])
        missing = report.get("critical_missing", [])
        st.write("过程性安全缺陷：" + ("无" if not issues else "、".join(issues)))
        st.write("缺失关键动作：" + ("无" if not missing else "、".join(missing)))

        st.download_button(
            "下载本次 JSON 报告",
            data=get_report_download(report),
            file_name=f"{st.session_state.session_id}_report.json",
            mime="application/json",
            use_container_width=True,
        )

    st.session_state.show_raw_log = st.checkbox("显示完整操作日志", value=st.session_state.show_raw_log)
    if st.session_state.show_raw_log:
        st.json(report.get("log", []))


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    inject_compact_css()
    init_session()
    render_sidebar()
    if st.session_state.active_simulator is None:
        render_intro()
    else:
        render_simulation()


if __name__ == "__main__":
    main()
