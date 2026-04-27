# -*- coding: utf-8 -*-
"""
儿科护理急救动态分支虚拟仿真训练平台｜V1.2.5 IV dual-reassessment candidate

本版重点：
- 时间/分级/得分/复评移至左侧病例下方的运行信息区；
- 左侧病例与实时状态栏加宽，生命体征以卡片网格显示；
- 右侧操作按钮统一使用简洁短标题，不再显示冗余解释；
- 当生命体征、临床表现或分级发生变化时，相关卡片自动闪动提示；
- 训练模式保留步骤提示与原因说明；考试模式仅保留干净操作界面；
- 肌注肾上腺素需输入剂量，系统按体重核对 0.01 mg/kg 与 0.5 mg 上限。
- 每次开始/重置模拟时自动随机生成年龄与体重：年龄 2-11 岁，体重 10-35 kg。
- 按用户确认的14项评分细则校准最佳时间窗：总分20分。
- V1.0新增：访问码、单位/科室/参与者编号、自动保存结果、管理员导出CSV、操作历史即时显示。
- V1.1新增：接入Supabase云端数据库，训练结束后自动写入training_records表，管理员后台可从数据库读取并导出。
- V1.1.1新增：管理员后台增强导出：汇总CSV、操作明细CSV、完整JSONL；关键操作时间点和剂量/错误指标展开为独立字段。
- V1.1.2新增：多中心/多层级课题字段，登录登记界面居中加宽，版本说明收纳到右上角。
- V1.1.3新增：登记界面按院区/科室标准化下拉录入，按院区代码+科室代码+姓名首字母自动生成参与者编号；删除前台项目编号和第几次测试字段；评估阶段标准化为基线评估、模拟培训、培训后考核。
- V1.1.4新增：按评估阶段自动锁定流程；基线评估=考试模式+初始病例，模拟培训=训练模式+初始病例，培训后考核=考试模式+变体病例Variant A；受试者不再自行选择运行模式和病例脚本。
- V1.2.5新增：输液场景双复评逻辑、儿童肾上腺素0.3 mg上限、快速补液容量输入、再次肌注/高级支持/CPR/雾化肾上腺素条件性路径。

声明：
    本系统仅用于护理教学、培训与科研可行性验证，不用于临床诊疗决策。
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import random
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Tuple

import streamlit as st

from peds_anaphylaxis_sim.engine import Simulator, load_scenario, save_report


APP_TITLE = "儿科护理急救动态分支虚拟仿真训练平台"
APP_SUBTITLE = "Dynamic Branching Virtual Simulation Platform for Pediatric Nursing Emergency Training"
ROOT = Path(__file__).resolve().parent
SCENARIO_DIR = ROOT / "peds_anaphylaxis_sim" / "scenarios"
RUNS_DIR = Path(os.environ.get("PEDSIM_RESULTS_DIR", str(ROOT / "runs_web")))
RESULTS_INDEX_PATH = RUNS_DIR / "training_results.jsonl"
RESULTS_FULL_REPORTS_PATH = RUNS_DIR / "training_full_reports.jsonl"
APP_VERSION = "V1.2.5 IV-dual-reassessment-candidate"

DEFAULT_INSTITUTION = "本医疗机构"

CAMPUS_CODES = {
    "锦江院区": "JJYQ",
    "眉山院区": "MSYQ",
    "高新院区": "GXYQ",
}

DEPARTMENT_CODES = {
    "呼吸科": "HXK",
    "感染科": "GRK",
    "肾脏科": "SZK",
    "血液科": "XYK",
    "心血管科": "XXGK",
    "神经科": "SJK",
    "PICU": "PICU",
    "消化科": "XHK",
}

ASSESSMENT_PHASE_OPTIONS = ["基线评估", "模拟培训", "培训后考核"]

WORKFLOW_RULES = {
    "基线评估": {
        "mode": "exam",
        "script_role": "initial",
        "script_label": "初始病例",
        "display": "基线评估｜考试模式｜初始病例",
        "task": "请按考试要求独立完成初始病例处置。系统不会提供步骤原因提示。",
    },
    "模拟培训": {
        "mode": "coach",
        "script_role": "initial",
        "script_label": "初始病例",
        "display": "模拟培训｜训练模式｜初始病例",
        "task": "请在训练模式下完成初始病例。系统将提供必要的步骤提示与复盘信息。",
    },
    "培训后考核": {
        "mode": "exam",
        "script_role": "variant",
        "script_label": "变体病例 Variant A",
        "display": "培训后考核｜考试模式｜变体病例 Variant A",
        "task": "请按考试要求独立完成变体病例处置。系统不会提供步骤原因提示。",
    },
}


def workflow_for_phase(phase: str) -> Dict[str, str]:
    return WORKFLOW_RULES.get(phase, WORKFLOW_RULES["基线评估"])


def normalize_initials(text: str) -> str:
    """Keep only uppercase Latin letters/numbers from user-entered name initials."""
    cleaned = "".join(ch for ch in str(text or "").upper().replace(" ", "") if ch.isalnum())
    return cleaned[:8]


def ensure_participant_suffix() -> str:
    """Create a stable anti-duplication suffix for the current browser session."""
    suffix = str(st.session_state.get("participant_unique_suffix", "") or "").strip()
    if not suffix:
        suffix = uuid.uuid4().hex[:4].upper()
        st.session_state.participant_unique_suffix = suffix
    return suffix


def build_participant_id(campus: str, department: str, initials: str) -> str:
    campus_code = CAMPUS_CODES.get(campus, "")
    department_code = DEPARTMENT_CODES.get(department, "")
    initials_code = normalize_initials(initials)
    if not campus_code or not department_code or not initials_code:
        return ""
    return f"{campus_code}{department_code}{initials_code}-{ensure_participant_suffix()}"


def participant_code_parts(campus: str, department: str, initials: str) -> Dict[str, str]:
    return {
        "campus_code": CAMPUS_CODES.get(campus, ""),
        "department_code": DEPARTMENT_CODES.get(department, ""),
        "participant_initials": normalize_initials(initials),
    }



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


def scenario_path_by_role(role: str) -> Optional[Path]:
    """Return the scenario path matching the locked workflow script role."""
    for path in sorted(SCENARIO_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = data.get("scenario", {})
            if meta.get("script_role", "") == role:
                return path
        except Exception:
            continue
    return None


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
    patient["age_years"] = rng.randint(2, 11)
    patient["weight_kg"] = rng.randint(10, 35)
    patient["randomized_profile"] = True
    patient["randomization_rule"] = "age_years: 2-11; weight_kg: 10-35"
    return randomized


def state_key() -> str:
    return "active_simulator"


def init_session() -> None:
    defaults = {
        "participant_id": "",
        "participant_initials": "",
        "participant_unique_suffix": "",
        "campus_code": "",
        "department_code": "",
        "institution": DEFAULT_INSTITUTION,
        "campus": "",
        "department": "",
        "department_type": "",
        "nurse_level": "",
        "years_experience": 0.0,
        "professional_title": "",
        "education_level": "",
        "prior_anaphylaxis_training": "",
        "prior_simulation_experience": "",
        "real_case_experience": "",
        "training_batch": "",
        "assessment_phase": "基线评估",
        "workflow_mode": "exam",
        "workflow_script_role": "initial",
        "workflow_display": "基线评估｜考试模式｜初始病例",
        "workflow_locked": True,
        "attempt_no": 1,
        "profile_completed": False,
        "app_unlocked": False,
        "admin_unlocked": False,
        "page": "训练系统",
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
        "pending_volume_action_id": "",
        "pending_volume_action_label": "",
        "last_dose_feedback": "",
        "last_dose_feedback_level": "",
        "result_saved": False,
        "admin_export_view": "训练汇总",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v
    if not st.session_state.get("institution"):
        st.session_state.institution = DEFAULT_INSTITUTION
    ensure_participant_suffix()


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
    f = sim.state.flags
    parts = []
    if s.get("rash", 0) >= 1:
        parts.append("皮疹/风团")
    if s.get("angioedema", 0) >= 1:
        parts.append("血管性水肿")
    if s.get("wheeze", 0) >= 1:
        parts.append("喘息/喘鸣")
    if s.get("stridor", 0) >= 1:
        parts.append("喉鸣/声音改变")
    if s.get("gi", 0) >= 1:
        parts.append("胃肠道症状")
    if s.get("consciousness", 0) >= 1:
        labels = ["烦躁", "嗜睡", "反应差"]
        parts.append(labels[min(2, int(s.get("consciousness", 1)) - 1)])
    if parts:
        return "、".join(parts)
    if f.get("epi_im_given") and f.get("fluid_bolus_valid") and not f.get("bronchodilator_neb"):
        return "循环较前改善，皮疹减轻，但仍有咳嗽/轻微喘息，需继续观察呼吸道表现。"
    if f.get("bronchodilator_neb") and f.get("second_reassessment_done"):
        return "生命体征趋于稳定，咳嗽/喘息较前减轻，仍需继续严密观察。"
    return "症状较前缓解，仍需继续观察生命体征、呼吸、循环和二相反应风险"


def grade_badge(sim: Simulator) -> str:
    # Grade is retained in backend reports, but not exposed as a diagnostic hint in the participant UI.
    return "动态观察"


def get_report_download(report: Dict[str, Any]) -> bytes:
    return json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")


def get_secret_value(name: str, default: str = "") -> str:
    """Read a config value from Streamlit secrets, environment variables, or fallback default."""
    try:
        value = st.secrets.get(name, None)  # type: ignore[attr-defined]
    except Exception:
        value = None
    if value is None:
        value = os.environ.get(name, default)
    return str(value or "")


def build_session_metadata(end_reason: str = "") -> Dict[str, Any]:
    return {
        "app_version": APP_VERSION,
        "session_id": st.session_state.get("session_id", ""),
        "participant_id": st.session_state.get("participant_id", "") or "anonymous",
        "participant_initials": st.session_state.get("participant_initials", ""),
        "campus_code": st.session_state.get("campus_code", ""),
        "department_code": st.session_state.get("department_code", ""),
        "institution": st.session_state.get("institution", DEFAULT_INSTITUTION),
        "campus": st.session_state.get("campus", ""),
        "department": st.session_state.get("department", ""),
        "department_type": st.session_state.get("department_type", ""),
        "nurse_level": st.session_state.get("nurse_level", ""),
        "years_experience": st.session_state.get("years_experience", ""),
        "professional_title": st.session_state.get("professional_title", ""),
        "education_level": st.session_state.get("education_level", ""),
        "prior_anaphylaxis_training": st.session_state.get("prior_anaphylaxis_training", ""),
        "prior_simulation_experience": st.session_state.get("prior_simulation_experience", ""),
        "real_case_experience": st.session_state.get("real_case_experience", ""),
        "training_batch": st.session_state.get("training_batch", ""),
        "assessment_phase": st.session_state.get("assessment_phase", ""),
        "workflow_mode": st.session_state.get("workflow_mode", ""),
        "workflow_script_role": st.session_state.get("workflow_script_role", ""),
        "workflow_display": st.session_state.get("workflow_display", ""),
        "workflow_locked": bool(st.session_state.get("workflow_locked", True)),
        "attempt_no": st.session_state.get("attempt_no", ""),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "end_reason": end_reason,
    }


def research_metadata_from_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Fields used for multi-campus, multi-level research exports."""
    return {
        "institution": session.get("institution", ""),
        "campus": session.get("campus", ""),
        "campus_code": session.get("campus_code", ""),
        "department": session.get("department", ""),
        "department_code": session.get("department_code", ""),
        "participant_initials": session.get("participant_initials", ""),
        "department_type": session.get("department_type", ""),
        "nurse_level": session.get("nurse_level", ""),
        "years_experience": session.get("years_experience", ""),
        "professional_title": session.get("professional_title", ""),
        "education_level": session.get("education_level", ""),
        "prior_anaphylaxis_training": session.get("prior_anaphylaxis_training", ""),
        "prior_simulation_experience": session.get("prior_simulation_experience", ""),
        "real_case_experience": session.get("real_case_experience", ""),
        "training_batch": session.get("training_batch", ""),
        "assessment_phase": session.get("assessment_phase", ""),
        "workflow_mode": session.get("workflow_mode", ""),
        "workflow_script_role": session.get("workflow_script_role", ""),
        "workflow_display": session.get("workflow_display", ""),
        "workflow_locked": session.get("workflow_locked", ""),
        "attempt_no": session.get("attempt_no", ""),
    }


def enrich_report(report: Dict[str, Any], end_reason: str = "") -> Dict[str, Any]:
    enriched = json.loads(json.dumps(report, ensure_ascii=False))
    enriched["session"] = build_session_metadata(end_reason=end_reason)
    enriched["end_reason"] = end_reason
    return enriched


def flatten_record(report: Dict[str, Any]) -> Dict[str, Any]:
    session = report.get("session", {}) or {}
    patient = report.get("patient", {}) or {}
    timeline = report.get("key_timeline", {}) or {}
    issues = report.get("process_safety_issues", []) or []
    missing = report.get("critical_missing", []) or []
    return {
        "created_at": session.get("created_at", ""),
        "session_id": session.get("session_id", ""),
        "participant_id": session.get("participant_id", ""),
        **research_metadata_from_session(session),
        "mode": report.get("mode", ""),
        "scenario_script_name": report.get("scenario_script_name", ""),
        "scenario_title": report.get("scenario_title", ""),
        "age_years": patient.get("age_years", ""),
        "weight_kg": patient.get("weight_kg", ""),
        "end_reason": report.get("end_reason", ""),
        "end_time_seconds": report.get("end_time_seconds", ""),
        "final_grade": report.get("final_grade", ""),
        "score": report.get("score", ""),
        "raw_score": report.get("raw_score", ""),
        "penalties": report.get("penalties", ""),
        "max_score": report.get("max_score", ""),
        "reassess_count": timeline.get("reassess_count", ""),
        "epi_last_dose_mg": timeline.get("epi_last_dose_mg", ""),
        "epi_target_dose_mg": timeline.get("epi_target_dose_mg", ""),
        "process_safety_issues": "；".join(map(str, issues)),
        "critical_missing": "；".join(map(str, missing)),
        "app_version": session.get("app_version", APP_VERSION),
    }


def _secret_get(*names: str, default: str = "") -> str:
    """Read secrets from Streamlit Cloud, local secrets.toml, or environment variables.

    Supported formats:
    - SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / SUPABASE_TABLE
    - [supabase] url / service_role_key / table
    """
    for name in names:
        value = None
        try:
            value = st.secrets.get(name, None)  # type: ignore[attr-defined]
        except Exception:
            value = None
        if value is not None:
            return str(value)
        value = os.environ.get(name, None)
        if value is not None:
            return str(value)
    try:
        supa = st.secrets.get("supabase", {})  # type: ignore[attr-defined]
        if isinstance(supa, dict):
            for name in names:
                key = name.lower().replace("supabase_", "")
                if key in supa and supa[key] is not None:
                    return str(supa[key])
    except Exception:
        pass
    return default


def database_configured() -> bool:
    return bool(_secret_get("SUPABASE_URL")) and bool(_secret_get("SUPABASE_SERVICE_ROLE_KEY"))


@st.cache_resource(show_spinner=False)
def get_supabase_client_cached(url: str, key: str):
    from supabase import create_client
    return create_client(url, key)


def get_supabase_client():
    url = _secret_get("SUPABASE_URL")
    key = _secret_get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    return get_supabase_client_cached(url, key)


def supabase_table_name() -> str:
    return _secret_get("SUPABASE_TABLE", default="training_records") or "training_records"


def infer_epi_dose_status(report: Dict[str, Any]) -> str:
    issues = "；".join(map(str, report.get("process_safety_issues", []) or []))
    logs = report.get("log", []) or []
    if "超过儿童单次最大0.3" in issues or "超过0.3" in issues or "心动过速致心衰" in issues:
        return "overdose"
    if "剂量不足" in issues or "操作无效" in issues:
        return "underdose"
    for item in logs:
        if not isinstance(item, dict):
            continue
        message = item.get("message", "")
        if message == "im_epinephrine_overdose":
            return "overdose"
        if message == "im_epinephrine_dose_high":
            return "dose_high"
        if message == "im_epinephrine_underdose":
            return "underdose"
        if message == "im_epinephrine_dose_verified":
            return "valid"
    timeline = report.get("key_timeline", {}) or {}
    if timeline.get("epi_last_dose_mg") is not None:
        return "valid"
    return "not_given"


def make_database_record(report: Dict[str, Any]) -> Dict[str, Any]:
    session = report.get("session", {}) or {}
    patient = report.get("patient", {}) or {}
    timeline = report.get("key_timeline", {}) or {}
    logs = report.get("log", []) or []
    action_logs = [x for x in logs if isinstance(x, dict) and x.get("kind") == "action"]
    return {
        "participant_id": str(session.get("participant_id", "anonymous") or "anonymous"),
        "hospital": str(session.get("institution", "") or ""),
        "department": str(session.get("department", "") or ""),
        "mode": str(report.get("mode", "") or ""),
        "scenario_name": str(report.get("scenario_script_name", report.get("scenario_title", "")) or ""),
        "scenario_file": str(st.session_state.get("active_scenario_path", "") or ""),
        "age_years": patient.get("age_years"),
        "weight_kg": patient.get("weight_kg"),
        "score": report.get("score"),
        "raw_score": report.get("raw_score"),
        "penalties": report.get("penalties"),
        "final_grade": str(report.get("final_grade", "") or ""),
        "end_reason": str(report.get("end_reason", "") or ""),
        "success": str(report.get("end_reason", "")) == "success",
        "epi_target_dose_mg": timeline.get("epi_target_dose_mg"),
        "epi_input_dose_mg": timeline.get("epi_last_dose_mg"),
        "epi_dose_status": infer_epi_dose_status(report),
        "action_count": len(action_logs),
        "reassessment_count": timeline.get("reassess_count"),
        "safety_issues": report.get("process_safety_issues", []) or [],
        "action_timeline": logs,
        "full_report": report,
        "app_version": session.get("app_version", APP_VERSION),
        "session_id": session.get("session_id", ""),
        "client_note": "saved_from_streamlit_v1_2_5_iv_dual_reassessment",
    }


def save_result_record_local(report: Dict[str, Any]) -> None:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    with RESULTS_INDEX_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(flatten_record(report), ensure_ascii=False) + "\n")
    with RESULTS_FULL_REPORTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False, default=str) + "\n")


def save_result_record_database(report: Dict[str, Any]) -> Tuple[bool, str]:
    if not database_configured():
        return False, "数据库未配置：未检测到 SUPABASE_URL 或 SUPABASE_SERVICE_ROLE_KEY。"
    try:
        client = get_supabase_client()
        if client is None:
            return False, "数据库客户端初始化失败。"
        table = supabase_table_name()
        record = make_database_record(report)
        client.table(table).insert(record).execute()
        return True, f"已写入云端数据库表：{table}。"
    except Exception as exc:
        return False, f"数据库写入失败：{type(exc).__name__}: {exc}"


def save_result_record(report: Dict[str, Any]) -> None:
    """Save result to local JSONL backup and, when configured, Supabase database."""
    save_result_record_local(report)
    ok, msg = save_result_record_database(report)
    st.session_state["last_db_save_ok"] = ok
    st.session_state["last_db_save_message"] = msg


def load_result_records_local() -> List[Dict[str, Any]]:
    if not RESULTS_INDEX_PATH.exists():
        return []
    records: List[Dict[str, Any]] = []
    with RESULTS_INDEX_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    records.append(obj)
            except Exception:
                continue
    return records


def normalize_database_record(row: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten Supabase rows into an expanded one-row-per-session summary."""
    report = full_report_from_database_row(row)
    summary = report_to_summary_record(report, storage_source="supabase")
    # Prefer database-level fields when present because they are indexed and stable.
    summary["created_at"] = row.get("created_at", summary.get("created_at", ""))
    summary["session_id"] = row.get("session_id", summary.get("session_id", ""))
    summary["participant_id"] = row.get("participant_id", summary.get("participant_id", ""))
    summary["institution"] = row.get("hospital", summary.get("institution", ""))
    summary["department"] = row.get("department", summary.get("department", ""))
    summary["app_version"] = row.get("app_version", summary.get("app_version", APP_VERSION))
    return summary


def load_result_rows_database(limit: int = 10000) -> Tuple[List[Dict[str, Any]], str]:
    """Return raw Supabase rows, preserving full_report JSON for enhanced exports."""
    if not database_configured():
        return [], "数据库未配置。"
    try:
        client = get_supabase_client()
        if client is None:
            return [], "数据库客户端初始化失败。"
        table = supabase_table_name()
        response = client.table(table).select("*").order("created_at", desc=True).limit(limit).execute()
        data = response.data or []
        rows = [x for x in data if isinstance(x, dict)]
        return rows, f"已从云端数据库读取 {len(rows)} 条记录。"
    except Exception as exc:
        return [], f"数据库读取失败：{type(exc).__name__}: {exc}"


def load_result_records_database(limit: int = 10000) -> Tuple[List[Dict[str, Any]], str]:
    rows, message = load_result_rows_database(limit=limit)
    if not rows:
        return [], message
    return [normalize_database_record(x) for x in rows], message


def load_full_reports_local() -> List[Dict[str, Any]]:
    if not RESULTS_FULL_REPORTS_PATH.exists():
        return []
    reports: List[Dict[str, Any]] = []
    with RESULTS_FULL_REPORTS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    reports.append(obj)
            except Exception:
                continue
    return reports


def load_result_records() -> List[Dict[str, Any]]:
    db_records, _ = load_result_records_database()
    if db_records:
        return list(reversed(db_records))
    full_local = load_full_reports_local()
    if full_local:
        return build_summary_records_from_reports(full_local, storage_source="local")
    return load_result_records_local()

def _json_compact(value: Any) -> str:
    """Compact JSON string for CSV cells when a value is a list/dict."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _csv_ready_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: _json_compact(v) for k, v in row.items()}


def records_to_csv_bytes(records: List[Dict[str, Any]]) -> bytes:
    if not records:
        return "".encode("utf-8-sig")
    fieldnames: List[str] = []
    for row in records:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows([_csv_ready_row(r) for r in records])
    return buf.getvalue().encode("utf-8-sig")


def records_to_jsonl_bytes(records: List[Dict[str, Any]]) -> bytes:
    if not records:
        return b""
    return "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in records).encode("utf-8")


ACTION_LABELS_CN = {
    "stop_infusion": "停用可疑药物",
    "call_help": "呼救",
    "abc_assess": "ABC评估",
    "high_flow_oxygen": "开放气道给氧",
    "shock_position": "体位管理",
    "connect_monitor": "连接监护",
    "check_bp": "测血压",
    "im_epinephrine": "肌注肾上腺素",
    "fluid_bolus": "快速补液",
    "fluid_bolus_volume_verified": "快速补液容量确认",
    "fluid_bolus_under": "补液量不足",
    "fluid_bolus_over": "补液量过量",
    "fluid_bolus_invalid_no_iv": "补液无有效通路",
    "reassess_first": "第一次复评",
    "bronchodilator": "雾化支扩",
    "reassess_second": "第二次复评",
    "family_explain": "告知家属",
    "sbar_handoff": "SBAR交接",
    "repeat_epinephrine": "再次肌注肾上腺素",
    "repeat_epinephrine_valid": "再次肌注肾上腺素",
    "repeat_epinephrine_not_indicated": "非必要再次肌注",
    "repeat_epinephrine_premature": "再次肌注时机过早",
    "advanced_support": "联系高级支持",
    "nebulized_epinephrine": "雾化肾上腺素",
    "cpr": "CPR",
    "antihistamine_iv": "抗组胺药",
    "steroid": "糖皮质激素",
    "continue_infusion": "继续输注可疑药物",
    "remove_iv": "拔除静脉通路",
    "sedation": "镇静药",
    "im_epinephrine_dose_verified": "肌注肾上腺素剂量确认",
    "im_epinephrine_underdose": "肌注肾上腺素剂量不足",
    "im_epinephrine_dose_high": "肌注肾上腺素剂量偏高",
    "im_epinephrine_overdose": "肌注肾上腺素过量",
}

KEY_ACTION_COLUMNS = [
    ("stop_infusion_time", "stop_infusion"),
    ("call_help_time", "call_help"),
    ("abc_assess_time", "abc_assess"),
    ("oxygen_time", "oxygen"),
    ("position_time", "position"),
    ("monitor_time", "monitor"),
    ("bp_check_time", "bp_check"),
    ("epi_time", "epi_im"),
    ("fluid_time", "fluid"),
    ("first_reassessment_time", "first_reassessment"),
    ("bronchodilator_time", "bronchodilator"),
    ("second_reassessment_time", "second_reassessment"),
    ("family_communication_time", "family_communication"),
    ("sbar_time", "sbar_handoff"),
]


def _get_logs(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    logs = report.get("log", []) or []
    return [x for x in logs if isinstance(x, dict)]


def _first_log_time(report: Dict[str, Any], message: str) -> Any:
    for entry in _get_logs(report):
        if entry.get("kind") == "action" and entry.get("message") == message:
            return entry.get("t")
    return None


def _action_attempt_count(report: Dict[str, Any], message: str) -> int:
    return sum(1 for entry in _get_logs(report) if entry.get("kind") == "action" and entry.get("message") == message)


def _timeline_value(report: Dict[str, Any], key: str) -> Any:
    timeline = report.get("key_timeline", {}) or {}
    return timeline.get(key, None)


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _yes_no(value: bool) -> str:
    return "是" if bool(value) else "否"


def _issue_text(report: Dict[str, Any]) -> str:
    return "；".join(map(str, report.get("process_safety_issues", []) or []))


def _missing_text(report: Dict[str, Any]) -> str:
    return "；".join(map(str, report.get("critical_missing", []) or []))


def full_report_from_database_row(row: Dict[str, Any]) -> Dict[str, Any]:
    report = row.get("full_report") or {}
    if not isinstance(report, dict):
        report = {}
    # Merge database-level fields back when older reports lack session metadata.
    session = report.setdefault("session", {})
    if isinstance(session, dict):
        session.setdefault("created_at", row.get("created_at", ""))
        session.setdefault("session_id", row.get("session_id", ""))
        session.setdefault("participant_id", row.get("participant_id", ""))
        session.setdefault("institution", row.get("hospital", ""))
        session.setdefault("campus", "")
        session.setdefault("department", row.get("department", ""))
        session.setdefault("department_type", "")
        session.setdefault("nurse_level", "")
        session.setdefault("years_experience", "")
        session.setdefault("professional_title", "")
        session.setdefault("education_level", "")
        session.setdefault("prior_anaphylaxis_training", "")
        session.setdefault("prior_simulation_experience", "")
        session.setdefault("real_case_experience", "")
        session.setdefault("training_batch", "")
        session.setdefault("assessment_phase", "")
        session.setdefault("workflow_mode", "")
        session.setdefault("workflow_script_role", "")
        session.setdefault("workflow_display", "")
        session.setdefault("workflow_locked", "")
        session.setdefault("attempt_no", "")
        session.setdefault("app_version", row.get("app_version", APP_VERSION))
    report.setdefault("mode", row.get("mode", ""))
    report.setdefault("scenario_script_name", row.get("scenario_name", ""))
    report.setdefault("end_reason", row.get("end_reason", ""))
    report.setdefault("score", row.get("score", ""))
    report.setdefault("raw_score", row.get("raw_score", ""))
    report.setdefault("penalties", row.get("penalties", ""))
    report.setdefault("final_grade", row.get("final_grade", ""))
    patient = report.setdefault("patient", {})
    if isinstance(patient, dict):
        patient.setdefault("age_years", row.get("age_years", ""))
        patient.setdefault("weight_kg", row.get("weight_kg", ""))
    return report


def report_to_summary_record(report: Dict[str, Any], storage_source: str = "supabase") -> Dict[str, Any]:
    session = report.get("session", {}) or {}
    patient = report.get("patient", {}) or {}
    timeline = report.get("key_timeline", {}) or {}
    final_vitals = report.get("final_vitals", {}) or {}
    issues = _issue_text(report)
    missing = _missing_text(report)

    score = _safe_number(report.get("score", 0))
    max_score = _safe_number(report.get("max_score", 20), 20)
    epi_time = timeline.get("epi_im", _first_log_time(report, "im_epinephrine"))
    end_time = report.get("end_time_seconds", "")

    record: Dict[str, Any] = {
        "created_at": session.get("created_at", ""),
        "session_id": session.get("session_id", ""),
        "participant_id": session.get("participant_id", ""),
        **research_metadata_from_session(session),
        "mode": report.get("mode", ""),
        "scenario_script_name": report.get("scenario_script_name", ""),
        "scenario_title": report.get("scenario_title", ""),
        "age_years": patient.get("age_years", ""),
        "weight_kg": patient.get("weight_kg", ""),
        "end_reason": report.get("end_reason", ""),
        "success": _yes_no(report.get("end_reason", "") == "success"),
        "end_time_seconds": end_time,
        "final_grade": report.get("final_grade", ""),
        "score": report.get("score", ""),
        "raw_score": report.get("raw_score", ""),
        "penalties": report.get("penalties", ""),
        "max_score": report.get("max_score", ""),
        "score_percent": round(score / max_score * 100, 1) if max_score else "",
        "reassess_count": timeline.get("reassess_count", ""),
        "action_count": sum(1 for e in _get_logs(report) if e.get("kind") == "action" and e.get("message") != "penalty"),
        "wrong_action_count": sum(1 for e in _get_logs(report) if e.get("kind") == "action" and e.get("message") == "penalty"),
        "harmful_action_count": sum(_action_attempt_count(report, x) for x in ["continue_infusion", "sedation", "remove_iv", "im_epinephrine_overdose"]),
        "epi_target_dose_mg": timeline.get("epi_target_dose_mg", ""),
        "epi_input_dose_mg": timeline.get("epi_last_dose_mg", ""),
        "epi_dose_status": infer_epi_dose_status(report),
        "epi_delay_seconds": epi_time if epi_time is not None else "",
        "underdose_epi": _yes_no("剂量不足" in issues or _action_attempt_count(report, "im_epinephrine_underdose") > 0),
        "dose_high_epi": _yes_no("剂量高于目标剂量" in issues or _action_attempt_count(report, "im_epinephrine_dose_high") > 0),
        "overdose_epi": _yes_no("超过儿童单次最大0.3" in issues or _action_attempt_count(report, "im_epinephrine_overdose") > 0),
        "fluid_bolus_volume_ml": timeline.get("fluid_bolus_volume_ml", ""),
        "fluid_min_ml": timeline.get("fluid_min_ml", ""),
        "fluid_max_ml": timeline.get("fluid_max_ml", ""),
        "fluid_bolus_valid": _yes_no(bool(timeline.get("fluid_bolus_valid", False))),
        "repeat_epinephrine_time": timeline.get("repeat_epinephrine", ""),
        "advanced_support_time": timeline.get("advanced_support", ""),
        "cpr_time": timeline.get("cpr", ""),
        "final_spo2": final_vitals.get("SpO2", ""),
        "final_hr": final_vitals.get("HR", ""),
        "final_rr": final_vitals.get("RR", ""),
        "final_sbp": final_vitals.get("SBP", ""),
        "final_dbp": final_vitals.get("DBP", ""),
        "process_safety_issues": issues,
        "critical_missing": missing,
        "completed_key_steps": "",
        "total_action_sequence": "",
        "app_version": session.get("app_version", APP_VERSION),
        "storage_source": storage_source,
    }

    # Key timeline columns.
    for column_name, timeline_key in KEY_ACTION_COLUMNS:
        record[column_name] = timeline.get(timeline_key, "")

    # Extra action-time columns not present in key_timeline.
    record["nebulized_epinephrine_time"] = timeline.get("nebulized_epinephrine", _first_log_time(report, "nebulized_epinephrine"))
    record["reassessment_first_time"] = timeline.get("first_reassessment", _first_log_time(report, "reassess_first"))
    record["reassessment_second_time"] = timeline.get("second_reassessment", _first_log_time(report, "reassess_second"))

    required_steps = [
        "stop_infusion_time", "call_help_time", "abc_assess_time", "oxygen_time", "position_time",
        "monitor_time", "bp_check_time", "epi_time", "fluid_time", "first_reassessment_time",
        "bronchodilator_time", "second_reassessment_time", "family_communication_time", "sbar_time"
    ]
    record["completed_key_steps"] = sum(1 for k in required_steps if record.get(k) not in ("", None))

    sequence = []
    for entry in _get_logs(report):
        if entry.get("kind") == "action" and entry.get("message") != "penalty":
            msg = str(entry.get("message", ""))
            sequence.append(ACTION_LABELS_CN.get(msg, msg))
    record["total_action_sequence"] = " → ".join(sequence)
    return record


def report_to_action_detail_records(report: Dict[str, Any], storage_source: str = "supabase") -> List[Dict[str, Any]]:
    session = report.get("session", {}) or {}
    patient = report.get("patient", {}) or {}
    rows: List[Dict[str, Any]] = []
    action_index = 0
    for entry in _get_logs(report):
        if entry.get("kind") != "action":
            continue
        action_index += 1
        data = entry.get("data", {}) or {}
        msg = str(entry.get("message", ""))
        action_id = str(data.get("action_id") or msg)
        if msg == "penalty":
            action_name = ACTION_LABELS_CN.get(action_id, action_id)
            event_type = "扣分"
        elif msg in ["im_epinephrine_dose_verified", "im_epinephrine_underdose", "im_epinephrine_dose_high", "im_epinephrine_overdose", "fluid_bolus_volume_verified", "fluid_bolus_under", "fluid_bolus_over", "fluid_bolus_invalid_no_iv"]:
            action_name = ACTION_LABELS_CN.get(msg, msg)
            event_type = "剂量判定"
        else:
            action_name = str(data.get("label") or ACTION_LABELS_CN.get(msg, msg))
            event_type = "操作"
        rows.append({
            "created_at": session.get("created_at", ""),
            "session_id": session.get("session_id", ""),
            "participant_id": session.get("participant_id", ""),
            **research_metadata_from_session(session),
            "mode": report.get("mode", ""),
            "scenario_script_name": report.get("scenario_script_name", ""),
            "age_years": patient.get("age_years", ""),
            "weight_kg": patient.get("weight_kg", ""),
            "action_index": action_index,
            "time_seconds": entry.get("t", ""),
            "event_type": event_type,
            "action_id": action_id,
            "action_name": action_name,
            "gained": data.get("gained", ""),
            "penalty": data.get("penalty", ""),
            "dose_mg": data.get("dose_mg", ""),
            "target_dose_mg": data.get("target_dose_mg", ""),
            "result": data.get("result", ""),
            "reason": data.get("reason", ""),
            "raw_message": msg,
            "raw_data_json": data,
            "end_reason": report.get("end_reason", ""),
            "final_score": report.get("score", ""),
            "storage_source": storage_source,
        })
    return rows


def build_summary_records_from_reports(reports: List[Dict[str, Any]], storage_source: str = "supabase") -> List[Dict[str, Any]]:
    return [report_to_summary_record(r, storage_source=storage_source) for r in reports if isinstance(r, dict)]


def build_action_detail_records_from_reports(reports: List[Dict[str, Any]], storage_source: str = "supabase") -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for report in reports:
        if isinstance(report, dict):
            rows.extend(report_to_action_detail_records(report, storage_source=storage_source))
    return rows


def action_label_map(sim: Simulator) -> Dict[str, str]:
    return {str(a.get("id", "")): str(a.get("label", a.get("id", ""))) for a in sim.actions}


def get_action_history_rows(sim: Simulator) -> List[Dict[str, Any]]:
    labels = action_label_map(sim)
    rows: List[Dict[str, Any]] = []
    for entry in sim.log:
        if entry.kind != "action":
            continue
        if entry.message == "penalty":
            continue
        data = entry.data or {}
        msg = entry.message
        result = ""
        display = data.get("label") or labels.get(msg, msg)
        if msg == "im_epinephrine_dose_verified":
            display = "肌注肾上腺素剂量确认"
            result = f"有效剂量 {data.get('dose_mg', '')} mg"
        elif msg == "im_epinephrine_underdose":
            display = "肌注肾上腺素剂量不足"
            result = f"无效：{data.get('dose_mg', '')} mg，目标 {data.get('target_dose_mg', '')} mg"
        elif msg == "im_epinephrine_dose_high":
            display = "肌注肾上腺素剂量偏高"
            result = f"偏高：{data.get('dose_mg', '')} mg，目标 {data.get('target_dose_mg', '')} mg"
        elif msg == "im_epinephrine_overdose":
            display = "肌注肾上腺素过量"
            result = f"过量：{data.get('dose_mg', '')} mg"
        elif msg in ["fluid_bolus_volume_verified", "fluid_bolus_under", "fluid_bolus_over", "fluid_bolus_invalid_no_iv"]:
            display = ACTION_LABELS_CN.get(msg, msg)
            result = f"{data.get('result', '')}｜{data.get('volume_ml', '')} ml"
        elif data.get("result"):
            result = str(data.get("result", ""))
        elif data.get("gained") is not None:
            result = f"得分 +{data.get('gained')}"
        rows.append({"时间": f"{entry.t}s", "操作": str(display), "结果": str(result)})
    return rows


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
    st.session_state.result_saved = False


def finalize_if_done() -> None:
    sim = st.session_state.active_simulator
    if sim is None or st.session_state.ended:
        return
    done, why = sim.is_done()
    if done:
        report = enrich_report(sim.build_report(), end_reason=why)
        out_dir = RUNS_DIR / st.session_state.session_id
        json_path, md_path = save_report(report, str(out_dir))
        if not st.session_state.get("result_saved", False):
            save_result_record(report)
            st.session_state.result_saved = True
        st.session_state.ended = True
        st.session_state.end_reason = why
        st.session_state.last_report = report
        st.session_state.last_report_paths = (json_path, md_path)


def profile_required_missing() -> List[str]:
    required = {
        "campus": "院区/中心",
        "department": "科室细分",
        "participant_initials": "姓名首字母",
        "participant_id": "系统生成参与者编号",
        "nurse_level": "护理层级",
        "years_experience": "工作年限",
        "prior_anaphylaxis_training": "既往过敏反应培训",
        "assessment_phase": "评估阶段",
    }
    missing = []
    for key, label in required.items():
        value = st.session_state.get(key, "")
        if value is None or str(value).strip() == "":
            missing.append(label)
    return missing

def render_version_corner() -> None:
    st.markdown(
        f"<div class='version-corner'>版本：{html.escape(APP_VERSION)}｜仅用于护理教学、培训与科研</div>",
        unsafe_allow_html=True,
    )


def render_participant_entry_page() -> None:
    """Centered, wide research-registration page before entering the simulator."""
    render_version_corner()
    st.markdown(
        f"""
        <div class='login-hero'>
            <div class='login-title'>{html.escape(APP_TITLE)}</div>
            <div class='login-subtitle'>多院区 · 多科室 · 多护理层级｜药物诱发过敏反应识别与初始处置能力评价</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    outer_left, center, outer_right = st.columns([0.08, 0.84, 0.08])
    with center:
        st.markdown(
            "<div class='login-card-title'>受试者信息登记</div>"
            "<div class='login-card-desc'>请按院区、科室和姓名首字母完成登记。系统将自动生成匿名参与者编号，并写入训练报告和云端数据库。</div>",
            unsafe_allow_html=True,
        )

        with st.form("participant_profile_form", clear_on_submit=False):
            st.markdown("##### 基本身份信息")

            campus_options = [""] + list(CAMPUS_CODES.keys())
            department_options = [""] + list(DEPARTMENT_CODES.keys())

            c1, c2, c3 = st.columns([1, 1, 1], gap="large")
            campus = c1.selectbox(
                "院区/中心（必填）",
                campus_options,
                index=campus_options.index(st.session_state.campus) if st.session_state.campus in campus_options else 0,
            )
            department = c2.selectbox(
                "科室细分（必填）",
                department_options,
                index=department_options.index(st.session_state.department) if st.session_state.department in department_options else 0,
            )
            participant_initials = c3.text_input(
                "姓名首字母（必填）",
                value=st.session_state.participant_initials,
                placeholder="例如 王思席填 WSX",
                max_chars=8,
            )

            preview_id = build_participant_id(campus, department, participant_initials)
            code_parts = participant_code_parts(campus, department, participant_initials)
            id_col, note_col = st.columns([1.1, 1], gap="large")
            id_col.text_input(
                "系统生成参与者编号（自动生成，不需手动填写）",
                value=preview_id,
                disabled=True,
            )
            note_col.markdown(
                f"""
                <div class='id-help-box'>
                    编码规则：院区代码 + 科室代码 + 姓名首字母 + 防重复后缀<br>
                    当前代码：{html.escape(code_parts.get('campus_code', '') or '待选择')} / {html.escape(code_parts.get('department_code', '') or '待选择')}
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("##### 护理层级与背景")
            n1, n2, n3 = st.columns([1, 1, 1], gap="large")
            nurse_levels = ["", "N0/CN0", "N1/CN1", "N2/CN2", "N3/CN3", "N4/CN4", "护士长/护理管理者", "其他"]
            nurse_level = n1.selectbox(
                "护理层级（必填）",
                nurse_levels,
                index=nurse_levels.index(st.session_state.nurse_level) if st.session_state.nurse_level in nurse_levels else 0,
            )
            years_experience = n2.number_input(
                "工作年限（年，必填）",
                min_value=0.0,
                max_value=50.0,
                value=float(st.session_state.years_experience or 0.0),
                step=0.5,
                format="%.1f",
            )
            titles = ["", "护士", "护师", "主管护师", "副主任护师", "主任护师", "其他"]
            professional_title = n3.selectbox(
                "职称",
                titles,
                index=titles.index(st.session_state.professional_title) if st.session_state.professional_title in titles else 0,
            )

            n4, n5, n6 = st.columns([1, 1, 1], gap="large")
            edu_options = ["", "中专", "大专", "本科", "硕士及以上", "其他"]
            education_level = n4.selectbox(
                "最高学历",
                edu_options,
                index=edu_options.index(st.session_state.education_level) if st.session_state.education_level in edu_options else 0,
            )
            yn_options = ["", "是", "否", "不确定"]
            prior_anaphylaxis_training = n5.selectbox(
                "是否接受过过敏反应/过敏性休克培训（必填）",
                yn_options,
                index=yn_options.index(st.session_state.prior_anaphylaxis_training) if st.session_state.prior_anaphylaxis_training in yn_options else 0,
            )
            prior_simulation_experience = n6.selectbox(
                "是否参加过模拟/虚拟仿真培训",
                yn_options,
                index=yn_options.index(st.session_state.prior_simulation_experience) if st.session_state.prior_simulation_experience in yn_options else 0,
            )

            n7, n8 = st.columns([1, 1], gap="large")
            real_case_experience = n7.selectbox(
                "是否处理过真实过敏反应病例",
                yn_options,
                index=yn_options.index(st.session_state.real_case_experience) if st.session_state.real_case_experience in yn_options else 0,
            )
            assessment_phase = n8.selectbox(
                "评估阶段（必填）",
                ASSESSMENT_PHASE_OPTIONS,
                index=ASSESSMENT_PHASE_OPTIONS.index(st.session_state.assessment_phase)
                if st.session_state.assessment_phase in ASSESSMENT_PHASE_OPTIONS else 0,
            )

            st.markdown(
                "<div class='form-note'>说明：项目编号与第几次测试不再由受试者填写；系统将在后台保留版本号、Session ID 和默认尝试序号用于数据追踪。</div>",
                unsafe_allow_html=True,
            )

            submitted = st.form_submit_button("保存信息并进入训练系统", type="primary", use_container_width=True)

        if submitted:
            initials_clean = normalize_initials(participant_initials)
            generated_id = build_participant_id(campus, department, initials_clean)
            parts = participant_code_parts(campus, department, initials_clean)

            st.session_state.participant_initials = initials_clean
            st.session_state.participant_id = generated_id
            st.session_state.campus_code = parts.get("campus_code", "")
            st.session_state.department_code = parts.get("department_code", "")
            st.session_state.institution = DEFAULT_INSTITUTION
            st.session_state.campus = campus.strip()
            st.session_state.department = department.strip()
            st.session_state.department_type = department.strip()
            st.session_state.nurse_level = nurse_level.strip()
            st.session_state.years_experience = years_experience
            st.session_state.professional_title = professional_title.strip()
            st.session_state.education_level = education_level.strip()
            st.session_state.prior_anaphylaxis_training = prior_anaphylaxis_training.strip()
            st.session_state.prior_simulation_experience = prior_simulation_experience.strip()
            st.session_state.real_case_experience = real_case_experience.strip()
            st.session_state.training_batch = ""
            st.session_state.assessment_phase = assessment_phase.strip()
            workflow = workflow_for_phase(st.session_state.assessment_phase)
            st.session_state.workflow_mode = workflow.get("mode", "exam")
            st.session_state.workflow_script_role = workflow.get("script_role", "initial")
            st.session_state.workflow_display = workflow.get("display", "")
            st.session_state.workflow_locked = True
            st.session_state.mode = st.session_state.workflow_mode
            st.session_state.attempt_no = 1

            missing = profile_required_missing()
            if missing:
                st.error("请先完整填写：" + "、".join(missing))
            else:
                st.session_state.profile_completed = True
                st.success(f"登记信息已保存。系统生成参与者编号：{generated_id}")
                st.rerun()

def render_sidebar() -> None:
    st.sidebar.title("V1.2.5 控制台")
    st.session_state.page = st.sidebar.radio(
        "页面",
        options=["训练系统", "管理员后台"],
        index=0 if st.session_state.page == "训练系统" else 1,
    )

    if st.session_state.page == "管理员后台":
        st.sidebar.caption("管理员后台用于查看并导出训练记录。")
        return

    if not st.session_state.get("profile_completed", False):
        st.sidebar.info("请先在主界面完成受试者信息登记。")
        return

    st.sidebar.subheader("受试者摘要")
    st.sidebar.caption(
        f"编号：{st.session_state.participant_id}  \n"
        f"单位：{st.session_state.institution}｜{st.session_state.campus}  \n"
        f"科室：{st.session_state.department}  \n"
        f"层级：{st.session_state.nurse_level}｜年限：{st.session_state.years_experience}年"
    )
    if st.sidebar.button("重新填写受试者信息", use_container_width=True):
        st.session_state.profile_completed = False
        st.session_state.active_simulator = None
        st.session_state.ended = False
        st.rerun()

    st.sidebar.subheader("本阶段任务")
    workflow = workflow_for_phase(st.session_state.get("assessment_phase", "基线评估"))
    st.session_state.workflow_mode = workflow.get("mode", "exam")
    st.session_state.workflow_script_role = workflow.get("script_role", "initial")
    st.session_state.workflow_display = workflow.get("display", "")
    st.session_state.workflow_locked = True
    st.session_state.mode = st.session_state.workflow_mode

    st.sidebar.markdown(
        f"""
        <div style="border:1px solid #E5E7EB;border-radius:14px;padding:0.85rem 0.9rem;background:#F8FAFC;margin-bottom:0.75rem;">
            <div style="font-size:0.85rem;color:#64748B;margin-bottom:0.25rem;">评估阶段</div>
            <div style="font-size:1.05rem;font-weight:700;color:#0F172A;margin-bottom:0.55rem;">{html.escape(st.session_state.get('assessment_phase', ''))}</div>
            <div style="font-size:0.85rem;color:#64748B;margin-bottom:0.25rem;">锁定流程</div>
            <div style="font-size:0.98rem;font-weight:650;color:#1E293B;margin-bottom:0.55rem;">{html.escape(workflow.get('display', ''))}</div>
            <div style="font-size:0.82rem;color:#475569;line-height:1.45;">{html.escape(workflow.get('task', ''))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    scenario_path = scenario_path_by_role(workflow.get("script_role", "initial"))
    if scenario_path is None:
        st.sidebar.error("未找到本阶段对应的病例脚本，请检查 scenarios 文件夹。")
    elif st.sidebar.button("开始/重置本阶段任务", type="primary", use_container_width=True):
        missing = profile_required_missing()
        if missing:
            st.sidebar.error("请先完整填写：" + "、".join(missing))
        else:
            start_simulation(
                scenario_path=scenario_path,
                mode=workflow.get("mode", "exam"),
                seed=-1,
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

        .history-panel {
            border: 1px solid #d9dee7;
            background: #ffffff;
            border-radius: 0.72rem;
            padding: 0.70rem 0.78rem;
            margin-top: 0.72rem;
            margin-bottom: 0.64rem;
        }
        .history-title {
            font-size: 1.00rem;
            font-weight: 800;
            color: #111827;
            margin-bottom: 0.42rem;
        }
        .history-empty {
            color: #667085;
            font-size: 0.92rem;
            line-height: 1.35;
        }
        .history-list {
            display: grid;
            gap: 0.38rem;
            max-height: 15.5rem;
            overflow-y: auto;
            padding-right: 0.20rem;
        }
        .history-item {
            display: grid;
            grid-template-columns: 4.5rem 1fr auto;
            gap: 0.55rem;
            align-items: center;
            border: 1px solid #eef1f5;
            background: #f8fafc;
            border-radius: 0.56rem;
            padding: 0.45rem 0.55rem;
        }
        .history-time {color:#475569; font-size:0.86rem; font-weight:700;}
        .history-action {color:#111827; font-size:0.94rem; font-weight:750;}
        .history-result {color:#667085; font-size:0.82rem; text-align:right;}
        div[data-testid="stExpander"] details {
            border-radius: 0.55rem !important;
        }
        
        .version-corner {
            position: fixed;
            top: 0.55rem;
            right: 1.15rem;
            z-index: 999;
            color: #667085;
            font-size: 0.76rem;
            background: rgba(255,255,255,0.92);
            border: 1px solid #e5e7eb;
            border-radius: 999px;
            padding: 0.28rem 0.72rem;
            box-shadow: 0 2px 10px rgba(15, 23, 42, 0.06);
        }
        .login-hero {
            width: min(1120px, 92vw);
            margin: 1.2rem auto 0.8rem auto;
            text-align: center;
            padding-top: 0.3rem;
        }
        .login-title {
            font-size: 2.05rem;
            line-height: 1.24;
            font-weight: 850;
            color: #0f172a;
            letter-spacing: -0.02em;
        }
        .login-subtitle {
            margin-top: 0.42rem;
            color: #475569;
            font-size: 1.05rem;
            line-height: 1.45;
        }
        .login-card-title {
            margin-top: 0.35rem;
            font-size: 1.32rem;
            line-height: 1.3;
            font-weight: 820;
            color: #111827;
            border: 1px solid #e5e7eb;
            border-bottom: 0;
            border-radius: 1rem 1rem 0 0;
            background: #ffffff;
            padding: 1.05rem 1.25rem 0.4rem 1.25rem;
        }
        .id-help-box {
            min-height: 3.15rem;
            border: 1px solid #dbeafe;
            border-radius: 0.8rem;
            background: #eff6ff;
            color: #1e3a8a;
            font-size: 0.88rem;
            line-height: 1.55;
            padding: 0.78rem 0.95rem;
            margin-top: 1.55rem;
        }
        .form-note {
            color: #667085;
            background: #f8fafc;
            border: 1px dashed #cbd5e1;
            border-radius: 0.8rem;
            padding: 0.72rem 0.9rem;
            font-size: 0.9rem;
            line-height: 1.55;
            margin: 0.2rem 0 0.85rem 0;
        }
        .login-card-desc {
            font-size: 0.94rem;
            color: #667085;
            line-height: 1.5;
            border-left: 1px solid #e5e7eb;
            border-right: 1px solid #e5e7eb;
            background: #ffffff;
            padding: 0 1.25rem 0.8rem 1.25rem;
            margin-bottom: -0.1rem;
        }
        div[data-testid="stForm"] {
            border: 1px solid #e5e7eb !important;
            border-top: 0 !important;
            border-radius: 0 0 1rem 1rem !important;
            padding: 0.95rem 1.25rem 1.15rem 1.25rem !important;
            background: #ffffff !important;
            box-shadow: 0 14px 38px rgba(15, 23, 42, 0.07) !important;
        }
        .access-card {
            width: min(620px, 92vw);
            margin: 8vh auto 0 auto;
            border: 1px solid #e5e7eb;
            border-radius: 1.1rem;
            background: #ffffff;
            padding: 1.6rem 1.7rem;
            box-shadow: 0 16px 45px rgba(15, 23, 42, 0.08);
            text-align: center;
        }
        .access-card-title {
            font-size: 1.62rem;
            font-weight: 850;
            line-height: 1.25;
            color: #111827;
            margin-bottom: 0.38rem;
        }
        .access-card-desc {
            font-size: 0.95rem;
            color: #667085;
            line-height: 1.5;
            margin-bottom: 0.85rem;
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
        "clinical": symptoms_text(sim),
        "score": f"{max(0, sim.score - sim.penalties)}/{sim.max_score}",
        "reassess": int(sim.state.flags.get("reassess_count", 0)),
        "symptoms": symptoms_text(sim),
        "vitals": visible_vitals(sim),
    }


def detect_ui_changes(sim: Simulator) -> Dict[str, Any]:
    current = make_ui_snapshot(sim)
    previous = st.session_state.get("last_ui_snapshot")
    changes: Dict[str, Any] = {"clinical": False, "symptoms": False, "score": False, "reassess": False, "vitals": set()}

    if isinstance(previous, dict):
        changes["clinical"] = previous.get("clinical") != current.get("clinical")
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
    action_count = sum(1 for e in sim.log if e.kind == "action" and e.message != "penalty")
    items = [
        ("时间", f"{sim.state.t}s", False),
        ("得分", score_text, bool(changes.get("score"))),
        ("有效复评", str(int(sim.state.flags.get("reassess_count", 0))), bool(changes.get("reassess"))),
        ("操作数", str(action_count), False),
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
    any_clinical_change = bool(changes.get("symptoms")) or bool(changes.get("clinical")) or bool(changed_vitals)

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
        if changes.get("clinical"):
            changed_names.append("病情")
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
    st.success("受试者信息已登记。请在左侧查看本阶段任务，然后点击“开始/重置本阶段任务”。")

    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown("#### 当前登记信息")
        info_rows = [
            {"项目": "参与者编号", "内容": st.session_state.get("participant_id", "")},
            {"项目": "单位/医院", "内容": st.session_state.get("institution", "")},
            {"项目": "院区/中心", "内容": st.session_state.get("campus", "")},
            {"项目": "院区代码", "内容": st.session_state.get("campus_code", "")},
            {"项目": "科室细分", "内容": st.session_state.get("department", "")},
            {"项目": "科室代码", "内容": st.session_state.get("department_code", "")},
            {"项目": "姓名首字母", "内容": st.session_state.get("participant_initials", "")},
            {"项目": "护理层级", "内容": st.session_state.get("nurse_level", "")},
            {"项目": "工作年限", "内容": f"{st.session_state.get('years_experience', '')} 年"},
            {"项目": "评估阶段", "内容": st.session_state.get("assessment_phase", "")},
        ]
        st.dataframe(info_rows, use_container_width=True, hide_index=True)

    with right:
        st.container(border=True).markdown(
            """
            **V1.2.5 输液场景双复评定版候选**

            本版在流程锁定基础上，加入输液场景双复评、快速补液容量输入、儿童肾上腺素0.3 mg上限及特殊路径条件性记录。系统按院区、科室和姓名首字母自动生成匿名参与者编号，并在训练报告、Supabase 云端数据库和管理员导出表中记录护理层级、工作年限、院区、既往培训经历、评估阶段等字段。

            管理员后台仍支持三类导出：训练汇总CSV、操作明细CSV、完整JSONL。
            """
        )


def require_app_access() -> bool:
    access_code = get_secret_value("APP_ACCESS_CODE", "peds2026")
    if not access_code:
        return True
    if st.session_state.get("app_unlocked", False):
        return True

    render_version_corner()
    st.markdown(
        f"""
        <div class='access-card'>
            <div class='access-card-title'>进入虚拟仿真训练系统</div>
            <div class='access-card-desc'>请输入访问码。系统用于儿科护士药物诱发过敏反应识别与初始处置能力评价，不用于临床诊疗决策。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, center, right = st.columns([0.32, 0.36, 0.32])
    with center:
        code = st.text_input("访问码", type="password", placeholder="请输入访问码", label_visibility="collapsed")
        if st.button("进入系统", type="primary", use_container_width=True):
            if code == access_code:
                st.session_state.app_unlocked = True
                st.rerun()
            else:
                st.error("访问码不正确。")
    return False


def render_action_history(sim: Simulator) -> None:
    rows = get_action_history_rows(sim)
    if not rows:
        st.markdown(
            "<div class='history-panel'>"
            "<div class='history-title'>已执行操作</div>"
            "<div class='history-empty'>当前尚未执行任何操作。每次点击选项后，操作记录会显示在这里。</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return
    html_rows = []
    for row in rows[-12:]:
        html_rows.append(
            "<div class='history-item'>"
            f"<div class='history-time'>{html.escape(str(row.get('时间','')))}</div>"
            f"<div class='history-action'>{html.escape(str(row.get('操作','')))}</div>"
            f"<div class='history-result'>{html.escape(str(row.get('结果','')))}</div>"
            "</div>"
        )
    st.markdown(
        "<div class='history-panel'>"
        f"<div class='history-title'>已执行操作（{len(rows)}项）</div>"
        "<div class='history-list'>" + "".join(html_rows) + "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_admin_page() -> None:
    compact_header()
    st.markdown("### 管理员后台｜V1.2.5 研究质控与导出增强版")
    admin_password = get_secret_value("ADMIN_PASSWORD", "admin2026")
    if not st.session_state.get("admin_unlocked", False):
        st.caption("请输入管理员密码后查看和导出训练记录。")
        pwd = st.text_input("管理员密码", type="password")
        if st.button("进入管理员后台", type="primary"):
            if pwd == admin_password:
                st.session_state.admin_unlocked = True
                st.rerun()
            else:
                st.error("管理员密码不正确。")
        return

    raw_db_rows, db_message = load_result_rows_database()
    local_full_reports = load_full_reports_local()
    local_summary_records = load_result_records_local()

    if database_configured():
        if raw_db_rows:
            st.success("云端数据库已连接：" + db_message)
        else:
            st.warning("已配置云端数据库，但当前未读取到记录或读取失败：" + db_message)
    else:
        st.info("当前未配置 Supabase 云端数据库，系统将仅显示本地备用记录。")

    if raw_db_rows:
        full_reports = [full_report_from_database_row(x) for x in raw_db_rows]
        summary_records = [normalize_database_record(x) for x in raw_db_rows]
        action_detail_records = build_action_detail_records_from_reports(full_reports, storage_source="supabase")
        raw_jsonl_records = full_reports
        storage_label = "supabase"
    elif local_full_reports:
        full_reports = local_full_reports
        summary_records = build_summary_records_from_reports(local_full_reports, storage_source="local")
        action_detail_records = build_action_detail_records_from_reports(local_full_reports, storage_source="local")
        raw_jsonl_records = local_full_reports
        storage_label = "local_full_report"
    else:
        full_reports = []
        summary_records = local_summary_records
        action_detail_records = []
        raw_jsonl_records = local_summary_records
        storage_label = "local_summary_only"

    if local_summary_records and raw_db_rows:
        st.caption(f"本地备用摘要记录：{len(local_summary_records)} 条；当前后台优先显示云端数据库记录。")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("训练记录数", len(summary_records))
    if summary_records:
        scores = []
        success_count = 0
        epi_invalid_count = 0
        for r in summary_records:
            try:
                scores.append(float(r.get("score", 0)))
            except Exception:
                pass
            if str(r.get("end_reason", "")) == "success" or str(r.get("success", "")) == "是":
                success_count += 1
            if str(r.get("epi_dose_status", "")) in ["underdose", "overdose"]:
                epi_invalid_count += 1
        c2.metric("平均得分", f"{sum(scores)/len(scores):.1f}" if scores else "-")
        c3.metric("Success次数", success_count)
        c4.metric("肾上腺素剂量错误", epi_invalid_count)
    else:
        c2.metric("平均得分", "-")
        c3.metric("Success次数", "-")
        c4.metric("肾上腺素剂量错误", "-")

    st.markdown("#### 数据导出")
    st.caption("汇总CSV适合Excel/SPSS/R做统计；操作明细CSV适合分析每一步操作路径；完整JSONL用于保留原始过程数据。")

    d1, d2, d3 = st.columns(3)
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    d1.download_button(
        "导出汇总 CSV（每次训练一行）",
        data=records_to_csv_bytes(summary_records),
        file_name=f"peds_sim_summary_{storage_label}_{now}.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=not summary_records,
    )
    d2.download_button(
        "导出操作明细 CSV（每个操作一行）",
        data=records_to_csv_bytes(action_detail_records),
        file_name=f"peds_sim_action_details_{storage_label}_{now}.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=not action_detail_records,
    )
    d3.download_button(
        "导出完整 JSONL（每次训练一行）",
        data=records_to_jsonl_bytes(raw_jsonl_records),
        file_name=f"peds_sim_full_reports_{storage_label}_{now}.jsonl",
        mime="application/json",
        use_container_width=True,
        disabled=not raw_jsonl_records,
    )

    st.divider()
    view = st.radio(
        "查看数据表",
        ["训练汇总", "操作明细"],
        index=0 if st.session_state.get("admin_export_view", "训练汇总") == "训练汇总" else 1,
        horizontal=True,
    )
    st.session_state.admin_export_view = view

    if view == "训练汇总":
        if summary_records:
            st.markdown("**训练汇总预览（最近200条）**")
            st.dataframe(list(reversed(summary_records[-200:])), use_container_width=True, hide_index=True)
        else:
            st.warning("尚未产生训练汇总记录。")
    else:
        if action_detail_records:
            st.markdown("**操作明细预览（最近500条操作事件）**")
            st.dataframe(list(reversed(action_detail_records[-500:])), use_container_width=True, hide_index=True)
        else:
            st.warning("尚未产生可展开的操作明细。旧版本仅保存摘要时，可能无法展开。")

    with st.expander("字段说明", expanded=False):
        st.markdown(
            """
            - **汇总 CSV**：每次训练一行，已将关键步骤时间点、肾上腺素剂量状态、错误操作次数、最终生命体征等展开为单独字段。
            - **操作明细 CSV**：每个操作事件一行，包含操作时间、操作名称、加分、扣分、剂量、结果等，适合分析操作顺序和延迟。
            - **完整 JSONL**：一行是一份完整训练报告，保留嵌套结构，适合长期归档和后续深度分析。
            """
        )


def render_epinephrine_dose_panel(sim: Simulator) -> bool:
    """Render dose-confirmation panel for IM epinephrine or repeat IM epinephrine."""
    pending_id = st.session_state.get("pending_dose_action_id", "")
    if pending_id not in ("im_epinephrine", "repeat_epinephrine"):
        return False

    weight = float(getattr(sim.state, "weight_kg", 0) or 0)
    target_mg = round(min(0.01 * weight, 0.3), 3)
    max_single_mg = 0.3
    title = "再次肌注肾上腺素：请输入本次总剂量" if pending_id == "repeat_epinephrine" else "肌注肾上腺素：请输入本次总剂量"
    st.markdown(
        "<div class='dose-card'>"
        f"<div class='title'>{html.escape(title)}</div>"
        "<div class='text'>单位为 mg。确认后系统会按情景规则判断剂量是否有效。</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if sim.mode == "coach":
        st.caption(f"训练提示：本例体重 {weight:g} kg；剂量为 0.01 mg/kg，即 {target_mg:g} mg；儿童单次最大 {max_single_mg:g} mg。")

    dose_key = f"epi_dose_mg_{pending_id}_{st.session_state.session_id}_{sim.state.t}"
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
        result = sim.apply_epinephrine_dose(float(dose_mg), action_id=pending_id)
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


def render_fluid_bolus_panel(sim: Simulator) -> bool:
    """Render volume-confirmation panel for crystalloid bolus."""
    pending_id = st.session_state.get("pending_volume_action_id", "")
    if pending_id != "fluid_bolus":
        return False

    weight = float(getattr(sim.state, "weight_kg", 0) or 0)
    min_ml = round(10 * weight, 1)
    max_ml = round(min(20 * weight, 500), 1)
    st.markdown(
        "<div class='dose-card'>"
        "<div class='title'>快速补液：请输入本次晶体液容量</div>"
        "<div class='text'>单位为 ml。确认后系统会按体重判断容量是否合理。</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    if sim.mode == "coach":
        st.caption(f"训练提示：本例体重 {weight:g} kg；合理范围 {min_ml:g}–{max_ml:g} ml（10–20 ml/kg，单次最大500 ml）。")

    volume_key = f"fluid_volume_ml_{st.session_state.session_id}_{sim.state.t}"
    volume_ml = st.number_input(
        "本次快速补液容量（ml）",
        min_value=0.0,
        max_value=2000.0,
        value=0.0,
        step=10.0,
        format="%.0f",
        key=volume_key,
    )
    c_ok, c_cancel = st.columns([1, 1], gap="medium")
    if c_ok.button("确认容量并执行", type="primary", use_container_width=True):
        result = sim.apply_fluid_bolus_volume(float(volume_ml))
        st.session_state.last_dose_feedback = str(result.get("message", ""))
        st.session_state.last_dose_feedback_level = str(result.get("status", ""))
        st.session_state.pending_volume_action_id = ""
        st.session_state.pending_volume_action_label = ""
        sim.tick()
        finalize_if_done()
        st.rerun()
    if c_cancel.button("取消输入", use_container_width=True):
        st.session_state.pending_volume_action_id = ""
        st.session_state.pending_volume_action_label = ""
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
                elif level in ["overdose", "invalid", "over"]:
                    st.error(msg)
                elif level in ["underdose", "dose_high", "under", "not_indicated"]:
                    st.warning(msg)
                else:
                    st.info(msg)

            dose_pending = render_epinephrine_dose_panel(sim)
            volume_pending = render_fluid_bolus_panel(sim)

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
                            disabled=(dose_pending or volume_pending),
                        ):
                            st.session_state.last_dose_feedback = ""
                            st.session_state.last_dose_feedback_level = ""
                            if aid in ("im_epinephrine", "repeat_epinephrine"):
                                st.session_state.pending_dose_action_id = aid
                                st.session_state.pending_dose_action_label = full_label
                                st.rerun()
                            elif aid == "fluid_bolus":
                                st.session_state.pending_volume_action_id = aid
                                st.session_state.pending_volume_action_label = full_label
                                st.rerun()
                            else:
                                sim.apply_action(aid)
                                sim.tick()
                                finalize_if_done()
                                st.rerun()

            render_action_history(sim)

            st.divider()
            c1, c2, c3 = st.columns([1.0, 1.05, 2.25], gap="medium")
            if c1.button(f"时间流逝 {sim.tick_seconds}s", use_container_width=True):
                sim.tick()
                finalize_if_done()
                st.rerun()

            if sim.mode != "exam":
                if c2.button("结束并生成报告", use_container_width=True):
                    report = enrich_report(sim.build_report(), end_reason="manual_end")
                    out_dir = RUNS_DIR / st.session_state.session_id
                    json_path, md_path = save_report(report, str(out_dir))
                    if not st.session_state.get("result_saved", False):
                        save_result_record(report)
                        st.session_state.result_saved = True
                    st.session_state.ended = True
                    st.session_state.end_reason = "manual_end"
                    st.session_state.last_report = report
                    st.session_state.last_report_paths = (json_path, md_path)
                    st.rerun()
            c3.caption("训练模式可手动结束；考试模式需达到系统结束条件。")


def render_report() -> None:
    report = st.session_state.last_report
    if not report:
        report = enrich_report(st.session_state.active_simulator.build_report(), end_reason=st.session_state.end_reason)
        st.session_state.last_report = report

    st.success(f"情景结束：{st.session_state.end_reason}")
    session_meta = report.get("session", {}) or {}
    st.caption(
        f"参与者：{session_meta.get('participant_id', '')}｜单位：{session_meta.get('institution', '')}"
        f"｜院区：{session_meta.get('campus', '')}｜科室：{session_meta.get('department', '')}"
        f"｜层级：{session_meta.get('nurse_level', '')}｜Session：{session_meta.get('session_id', '')}"
    )
    if st.session_state.get("last_db_save_message"):
        if st.session_state.get("last_db_save_ok"):
            st.success(st.session_state.get("last_db_save_message"))
        else:
            st.warning(st.session_state.get("last_db_save_message"))

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
    if not require_app_access():
        return
    render_sidebar()
    if st.session_state.page == "管理员后台":
        render_admin_page()
        return
    if not st.session_state.get("profile_completed", False):
        render_participant_entry_page()
        return
    if st.session_state.active_simulator is None:
        render_intro()
    else:
        render_simulation()


if __name__ == "__main__":
    main()
