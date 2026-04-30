# -*- coding: utf-8 -*-
"""
Pediatric Ward Anaphylaxis Simulator (V1.2.7 module-boundary scoring and baseline-post survey)

特点（V1.2.7）：
- 动态情景（规则驱动）：输入操作 -> 生命体征/症状随时间演化
- 操作菜单：仅显示“操作名称”，不提供引导性措辞
- 自动评分：前期模块化并行评分；首次肌注肾上腺素为核心分界点；肾上腺素后按模块边界顺序评分；延迟给半分，越过模块边界不再补分
- 报告突出“过程性安全缺陷”（如未呼救/未给氧/未监护/未测血压/复评不足）
- 普通考核结束：有效第一次复评 + 有效第二次复评 + 告知家属 + SBAR交接；基线阶段可接入基线后补充问卷

声明：
- 仅用于教学与科研可行性验证，不可用于临床决策。
- 任何药物剂量与处置细节均应遵循你院流程；本引擎只执行情景脚本中预置选项。

运行：
  python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training.json --mode coach
  python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training.json --mode exam
"""

from __future__ import annotations

import argparse
import json
import os
import datetime as _dt
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")

def load_scenario(path: str) -> Dict[str, Any]:
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    try:
        import yaml  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "YAML scenario requires PyYAML. Install with: pip install pyyaml\n"
            f"Original error: {e}"
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def safe_eval(expr: str, ctx: Dict[str, Any]) -> bool:
    return bool(eval(expr, {"__builtins__": {}}, ctx))

@dataclass
class SimState:
    t: int
    age_years: int
    weight_kg: float
    vitals: Dict[str, float]
    symptoms: Dict[str, int]
    flags: Dict[str, Any]
    baseline_vitals: Dict[str, float] = field(default_factory=dict)
    grade: int = 1

@dataclass
class LogEntry:
    t: int
    kind: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)


def safe_eval(expr: str, ctx: dict) -> bool:
    """
    Minimal safe evaluator for scenario expressions (done_when / rule conditions).
    Only allows reading from ctx and basic Python operators.
    """
    if not expr:
        return False
    allowed_builtins = {"min": min, "max": max, "int": int, "float": float, "bool": bool}
    return bool(eval(expr, {"__builtins__": allowed_builtins}, ctx))

class Simulator:
    def __init__(self, scenario: Dict[str, Any], mode: str = "coach", seed: int = -1):
        self.scenario = scenario
        self.mode = mode
        # Guided prompts (coach mode): show one prompt at a time, advance when satisfied
        self.guided_prompts = scenario.get('training', {}).get('guided_prompts', []) if mode == 'coach' else []
        self.guided_index = 0
        self.actions = scenario["actions"]
        # Randomization: shuffle option order in exam mode to avoid patterned sequences
        self.seed = seed if seed is not None else -1
        if self.seed == -1:
            self.seed = int(_dt.datetime.now().timestamp())
        if mode == "exam":
            rnd = __import__("random").Random(self.seed)
            self.actions = list(self.actions)
            rnd.shuffle(self.actions)
        self.action_order_labels = [a.get("id", "") for a in self.actions]

        # V1.2.7: module-boundary scoring. Boundaries are used for
        # scoring and timing attribution, not as hard UI locks. Early actions
        # may be completed in parallel; the first effective IM epinephrine is
        # the main transition point into ordered post-epinephrine management.
        self.module_scoring = {
            "module1_rescue_activation": {
                "name": "抢救启动模块",
                "max_points": 20,
                "actions": ["stop_infusion", "call_help"],
                "boundary": "病例开始后0-60秒为按时，61-120秒为延迟，超过120秒不再补分。",
            },
            "module2_initial_support_assessment": {
                "name": "初始支持与评估模块",
                "max_points": 20,
                "actions": ["abc_assess", "high_flow_oxygen", "shock_position", "connect_monitor", "check_bp"],
                "boundary": "首次有效肌注肾上腺素前为按时；肌注后至第一次有效复评前为延迟；第一次有效复评后不再补分。",
            },
            "module3_first_im_epinephrine": {
                "name": "首次肌注肾上腺素关键模块",
                "max_points": 25,
                "actions": ["im_epinephrine"],
                "boundary": "药物、途径和剂量正确后计分，并作为前后流程分界点。",
            },
            "module4_post_epinephrine_management": {
                "name": "肾上腺素后标准处理模块",
                "max_points": 20,
                "actions": ["fluid_bolus", "reassess_first", "bronchodilator", "steroid"],
                "boundary": "首次有效肌注肾上腺素后开始，快速补液和第一次复评优先，辅助治疗位于第一次复评后。",
            },
            "module5_reassessment_handoff_communication": {
                "name": "复评、交班与沟通模块",
                "max_points": 15,
                "actions": ["reassess_second", "family_explain", "sbar_handoff"],
                "boundary": "第一次有效复评且病情改善后开放，第二次复评、家属沟通和SBAR完成后普通考核结束。",
            },
        }
        self.action_module_map = {
            aid: module_id
            for module_id, meta in self.module_scoring.items()
            for aid in meta.get("actions", [])
        }
        self.standard_flow_order = {
            "stop_infusion": 1,
            "call_help": 2,
            "abc_assess": 3,
            "high_flow_oxygen": 4,
            "shock_position": 5,
            "connect_monitor": 6,
            "check_bp": 7,
            "im_epinephrine": 8,
            "fluid_bolus": 9,
            "reassess_first": 10,
            "bronchodilator": 11,
            "steroid": 12,
            "reassess_second": 13,
            "family_explain": 14,
            "sbar_handoff": 15,
        }

        base = scenario["baseline"]

        self.state = SimState(
            t=0,
            age_years=int(scenario["patient"]["age_years"]),
            weight_kg=float(scenario["patient"]["weight_kg"]),
            vitals={k: float(v) for k, v in base["vitals"].items()},
            symptoms={k: int(v) for k, v in base["symptoms"].items()},
            flags=dict(base["flags"]),
            baseline_vitals={k: float(v) for k, v in base["vitals"].items()},
            grade=1,
        )
        self.log: List[LogEntry] = []
        self.score = 0
        self.max_score = self._compute_max_score()
        self.penalties = 0
        self.action_first_time: Dict[str, int] = {}

        self.tick_seconds = int(self.scenario["dynamics"].get("tick_seconds", 30))
        self.min_time_for_success = int(self.scenario.get("training", {}).get("min_time_seconds_for_success", 0))
        self.min_reassess_recommended = int(self.scenario.get("training", {}).get("min_reassess_count_recommended", 2))

        self._log("system", "simulation_start", {
            "scenario_id": scenario["scenario"]["id"],
            "scenario_version": scenario["scenario"].get("version", ""),
            "mode": mode,
            "tick_seconds": self.tick_seconds,
            "min_time_for_success": self.min_time_for_success
        })

    def _compute_max_score(self) -> int:
        s = 0
        for a in self.actions:
            pts = int(a.get("score", {}).get("points", 0))
            s += max(0, pts)
        return s

    def _log(self, kind: str, message: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.log.append(LogEntry(t=self.state.t, kind=kind, message=message, data=data or {}))

    def age_sbp_threshold(self) -> float:
        age = self.state.age_years
        hypo = self.scenario["diagnosis_criteria"]["hypotension_definition"]
        if age < 1:
            return float(hypo["infant_1m_to_1y_sbp_lt"])
        if 1 <= age <= 10:
            return float(70 + 2 * age)
        return float(hypo["age_11_to_17_sbp_lt"])

    def compute_grade(self) -> int:
        v = self.state.vitals
        s = self.state.symptoms
        flags = self.state.flags

        if flags.get("cardiac_arrest", False) or v.get("SpO2", 100) <= self.scenario["thresholds"]["SpO2_arrest"]:
            return 4

        sbp_thr = self.age_sbp_threshold()
        if v.get("SBP", 999) < sbp_thr or s.get("consciousness", 0) >= 2:
            return 3
        if (s.get("stridor", 0) >= 2 or s.get("wheeze", 0) >= 2) and v.get("SpO2", 100) < self.scenario["thresholds"]["SpO2_critical"]:
            return 3

        baseline_sbp = self.state.baseline_vitals.get("SBP", v.get("SBP", 100))
        drop_pct = 100 * (baseline_sbp - v.get("SBP", baseline_sbp)) / max(1.0, baseline_sbp)
        if drop_pct >= self.scenario["thresholds"]["hypotension_sbp_drop_pct"]:
            return 2
        if v.get("SpO2", 100) < self.scenario["thresholds"]["SpO2_low"]:
            return 2
        if s.get("wheeze", 0) >= 1 or s.get("stridor", 0) >= 1 or s.get("gi", 0) >= 2:
            return 2

        return 1

    def apply_effects(self, effects: Dict[str, Any]) -> None:
        # Direct setters (used for terminal events like asphyxia death)
        sv = effects.get("set_vitals")
        if isinstance(sv, dict):
            for k, val in sv.items():
                self.state.vitals[k] = float(val)
        sg = effects.get("set_grade")
        if sg is not None:
            try:
                self.state.grade = int(sg)
            except Exception:
                pass
        for k, v in effects.get("set_flags", {}).items():
            self.state.flags[k] = v
        for k, inc in effects.get("counter_inc", {}).items():
            self.state.flags[k] = int(self.state.flags.get(k, 0)) + int(inc)
        for k, dv in effects.get("delta_vitals", {}).items():
            self.state.vitals[k] = float(self.state.vitals.get(k, 0)) + float(dv)
        for k, ds in effects.get("delta_symptoms", {}).items():
            self.state.symptoms[k] = int(self.state.symptoms.get(k, 0)) + int(ds)

        self.state.vitals["SpO2"] = clamp(self.state.vitals.get("SpO2", 100), 40, 100)
        self.state.vitals["HR"] = clamp(self.state.vitals.get("HR", 120), 40, 220)
        self.state.vitals["RR"] = clamp(self.state.vitals.get("RR", 30), 5, 80)
        self.state.vitals["SBP"] = clamp(self.state.vitals.get("SBP", 90), 30, 160)
        self.state.vitals["DBP"] = clamp(self.state.vitals.get("DBP", 55), 20, 110)
        for k in list(self.state.symptoms.keys()):
            self.state.symptoms[k] = int(clamp(self.state.symptoms[k], 0, 3))
        self._enforce_physiologic_vital_bounds()

    def _normal_recovery_bounds(self) -> Dict[str, float]:
        """Age-adapted display bounds for the standard recovery branch.

        These are not clinical decision cutoffs. They prevent stacked positive
        effects from creating impossible recovery values such as HR 64/min,
        RR 5/min, BP 160/109 mmHg, or SpO2 100% during ordinary stabilization.
        """
        age = int(getattr(self.state, "age_years", 6) or 6)
        if age <= 3:
            hr_min, rr_min = 110.0, 24.0
        elif age <= 5:
            hr_min, rr_min = 105.0, 22.0
        else:
            hr_min, rr_min = 100.0, 20.0
        sbp_cap = min(120.0, max(100.0, 100.0 + 2.0 * age))
        dbp_cap = min(80.0, max(65.0, 60.0 + age))
        return {"hr_min": hr_min, "rr_min": rr_min, "sbp_cap": sbp_cap, "dbp_cap": dbp_cap}

    def _enforce_physiologic_vital_bounds(self) -> None:
        """Keep vital signs physiologically plausible after cumulative effects.

        V1.2.6e separates three states:
        1) cardiac arrest/death: values are displayed by the arrest overlay;
        2) post-arrest ROSC: measurable but unstable values, not full normalization;
        3) standard recovery: no over-correction below/above plausible ranges.
        """
        f = self.state.flags
        v = self.state.vitals

        if f.get("dead", False) or f.get("cardiac_arrest", False):
            return

        if f.get("resuscitation_rosc", False):
            v["SpO2"] = clamp(float(v.get("SpO2", 88)), 88, 94)
            v["HR"] = clamp(float(v.get("HR", 145)), 120, 160)
            # RR may be displayed as artificial ventilation support, but keep the
            # stored number within an unstable post-arrest range.
            v["RR"] = clamp(float(v.get("RR", 30)), 24, 40)
            v["SBP"] = clamp(float(v.get("SBP", 75)), 65, 100)
            v["DBP"] = clamp(float(v.get("DBP", 45)), 35, 65)
            return

        # In non-arrest states, 100% saturation after every supportive action is
        # too perfect for this scenario. Keep it below a realistic display cap.
        v["SpO2"] = min(float(v.get("SpO2", 98)), 98.0)

        standard_recovery = bool(
            f.get("epi_im_given", False)
            and f.get("stopped_infusion", False)
            and f.get("oxygen_on", False)
            and not f.get("epi_overdose_event", False)
            and not f.get("tachycardia_heart_failure", False)
            and not f.get("airway_obstruction_triggered", False)
        )
        if standard_recovery:
            b = self._normal_recovery_bounds()
            v["HR"] = max(float(v.get("HR", 120)), b["hr_min"])
            v["RR"] = max(float(v.get("RR", 28)), b["rr_min"])
            v["SBP"] = min(float(v.get("SBP", 100)), b["sbp_cap"])
            v["DBP"] = min(float(v.get("DBP", 62)), b["dbp_cap"])

    def tick(self) -> None:
        if self.state.flags.get("dead", False):
            self.state.grade = self.compute_grade()
            return

        self.state.t += self.tick_seconds
        self._refresh_process_flags()

        # If cardiac arrest was already present and another time step passes
        # without CPR, record death. A newly triggered arrest still leaves the
        # learner one immediate next-operation opportunity.
        f = self.state.flags
        if f.get("cardiac_arrest", False) and not f.get("cpr_done", False):
            arrest_t = f.get("cardiac_arrest_time_sec", self.state.t)
            if self.state.t > arrest_t:
                self._mark_death_after_arrest_without_cpr("time_elapsed_without_cpr")
                self.state.grade = self.compute_grade()
                return

        ctx = {
            "t": self.state.t,
            "vitals": SimpleNamespace(**self.state.vitals),
            "symptoms": SimpleNamespace(**self.state.symptoms),
            "flags": SimpleNamespace(**self.state.flags),
            "age_sbp_threshold": self.age_sbp_threshold(),
        }

        for rule in self.scenario["dynamics"]["rules"]:
            when = rule.get("when", "")
            if not when:
                continue
            try:
                if safe_eval(when, ctx):
                    self.apply_effects(rule.get("effects", {}))
                    self._log("tick", "rule_applied", {"rule": rule.get("name", "")})
            except Exception as e:
                self._log("system", "rule_eval_error", {"rule": rule.get("name", ""), "error": str(e)})

        self._enforce_physiologic_vital_bounds()
        self._refresh_process_flags()
        self.state.grade = self.compute_grade()


    def get_guided_prompt_item(self) -> Dict[str, str]:
        """Return the current coach-mode prompt with optional reason text.

        The UI uses this to keep the operation buttons clean while still showing
        step rationale in training mode only.
        """
        if not self.guided_prompts:
            return {"text": "", "reason": ""}
        # advance index while conditions are satisfied
        while self.guided_index < len(self.guided_prompts):
            item = self.guided_prompts[self.guided_index]
            expr = item.get('done_when', '')
            ctx = {
                "t": self.state.t,
                "vitals": SimpleNamespace(**self.state.vitals),
                "symptoms": SimpleNamespace(**self.state.symptoms),
                "flags": SimpleNamespace(**self.state.flags),
                "age_sbp_threshold": self.age_sbp_threshold(),
                "grade": self.state.grade,
                "action_first_time": self.action_first_time,
            }
            try:
                done = safe_eval(expr, ctx)
            except Exception:
                done = False
            if done:
                self.guided_index += 1
                continue
            return {"text": str(item.get('text', '')), "reason": str(item.get('reason', ''))}
        return {"text": "已完成全部关键步骤，可继续复评观察。", "reason": "继续按院内流程观察呼吸、循环、皮肤黏膜表现及二相反应风险。"}

    def get_guided_prompt(self) -> str:
        return self.get_guided_prompt_item().get("text", "")


    def _format_vitals_line(self) -> str:
        """
        控制生命体征的可见性：
        - 初始仅显示体温
        - 连接监护后显示 SpO₂/HR/RR（BP 仍隐藏）
        - 选择测量血压/灌注后，在下一次 tick 才显示 BP
        """
        v = self.state.vitals
        f = self.state.flags
        temp = v.get("Temp", None)
        temp_txt = f"体温 {temp:.1f}℃" if isinstance(temp, (int, float)) else "体温 --"

        arrest_display = self._resuscitation_vitals_display()
        if arrest_display and f.get("monitor_on", False):
            return (
                f"生命体征：{temp_txt} | SpO₂ {arrest_display['SpO₂']} | "
                f"HR {arrest_display['HR']} | RR {arrest_display['RR']} | BP {arrest_display['BP']}\n"
            )

        if not f.get("monitor_on", False):
            return f"生命体征：{temp_txt}\n"

        spo2 = v.get("SpO2", 0)
        hr = v.get("HR", 0)
        rr = v.get("RR", 0)

        if not f.get("bp_checked", False):
            return f"生命体征：{temp_txt} | SpO₂ {spo2:.0f}% | HR {hr:.0f}/min | RR {rr:.0f}/min | BP --/-- mmHg\n"

        sbp = v.get("SBP", 0)
        dbp = v.get("DBP", 0)
        return f"生命体征：{temp_txt} | SpO₂ {spo2:.0f}% | HR {hr:.0f}/min | RR {rr:.0f}/min | BP {sbp:.0f}/{dbp:.0f} mmHg\n"


    def _clinical_symptom_text(self) -> str:
        """Human-facing objective symptom text for participant UI.

        V1.2.6c rule:
        - exam UI must only describe what is observed; it must not tell the learner
          what action to take, especially in airway/CPR branches;
        - symptom text should progress with vitals and pathway flags, so that
          deterioration is visible in the clinical presentation, not only in the
          numeric vital signs.
        """
        s = self.state.symptoms
        f = self.state.flags
        v = self.state.vitals

        if f.get("dead", False):
            return "患儿意识丧失，呼之不应，无有效自主呼吸，脉搏未触及。"
        if f.get("cardiac_arrest", False) and not f.get("resuscitation_rosc", False):
            return "患儿意识丧失，呼之不应，无有效自主呼吸，脉搏未触及。"
        if f.get("resuscitation_rosc", False):
            return "患儿恢复可触及脉搏，高级生命支持团队已接手，拟转入PICU进一步治疗。"

        spo2 = float(v.get("SpO2", 100))
        sbp = float(v.get("SBP", 120))
        consciousness = int(s.get("consciousness", 0))
        sbp_thr = self.age_sbp_threshold()
        airway_flag = bool(f.get("airway_obstruction_triggered", False) or f.get("bvm_required", False))

        # Severe non-arrest deterioration: objective descriptors only.
        if airway_flag and (spo2 < 88 or consciousness >= 2):
            return "患儿呼吸费力，面色发绀，吸气性呼吸困难，反应差。"
        if spo2 <= 70 or sbp <= 45 or consciousness >= 3:
            return "患儿面色发绀，反应差，呼吸浅弱或不规则，四肢湿冷。"
        if spo2 < 85 or sbp < sbp_thr:
            return "患儿喘息加重，面色苍白或发绀，烦躁或反应迟钝，末梢灌注差。"
        if spo2 < 92 or int(s.get("wheeze", 0)) >= 2 or int(s.get("stridor", 0)) >= 1:
            parts = ["咳嗽/喘息较前加重", "呼吸急促"]
            if int(s.get("rash", 0)) >= 1:
                parts.append("皮疹/风团明显")
            if int(s.get("angioedema", 0)) >= 1:
                parts.append("局部血管性水肿")
            if int(s.get("stridor", 0)) >= 1:
                parts.append("喉鸣或声音改变")
            return "、".join(parts) + "。"

        symptom_text = []
        if s.get("rash", 0) >= 1:
            symptom_text.append("皮疹/风团")
        if s.get("angioedema", 0) >= 1:
            symptom_text.append("血管性水肿")
        if s.get("wheeze", 0) >= 1:
            symptom_text.append("咳嗽/喘息")
        if s.get("stridor", 0) >= 1:
            symptom_text.append("喉鸣/声音改变")
        if s.get("gi", 0) >= 1:
            symptom_text.append("胃肠道症状")
        if consciousness >= 1:
            symptom_text.append(["烦躁", "嗜睡", "反应差"][min(2, consciousness - 1)])

        if symptom_text:
            return "、".join(symptom_text) + "。"

        if f.get("epi_im_given") and f.get("fluid_bolus_valid") and not f.get("bronchodilator_neb"):
            return "循环较前改善，皮疹减轻，但仍有咳嗽/轻微喘息。"
        if f.get("bronchodilator_neb") and f.get("second_reassessment_done"):
            return "生命体征趋于稳定，咳嗽/喘息较前减轻。"
        return "患儿仍有轻度皮肤不适和呼吸道不适表现。"

    def format_status(self) -> str:
        prompt = self.get_guided_prompt() if self.mode == "coach" else ""
        prompt_line = f"当前提示：{prompt}\n" if prompt else ""
        return (
            f"时间：{self.state.t:>4}s\n"
            + prompt_line
            + self._format_vitals_line()
            + f"当前临床表现：{self._clinical_symptom_text()}\n"
        )

    def print_coach_hint(self) -> None:
        if self.mode != "coach":
            return
        hints = []
        if not self.state.flags.get("stopped_infusion", False):
            hints.append("提示：停止致敏源。")
        if not self.state.flags.get("help_called", False):
            hints.append("提示：呼救并获得支援。")
        if not self.state.flags.get("oxygen_on", False):
            hints.append("提示：给氧并评估通气。")
        if self.state.grade >= 2 and not self.state.flags.get("epi_im_given", False):
            hints.append("提示：考虑肾上腺素肌注。")
        if hints:
            print("教练提示：")
            for h in hints[:3]:
                print(" -", h)
            print()

    def _find_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        return next((a for a in self.actions if a.get("id") == action_id), None)

    def _first_attempt(self, action_id: str) -> bool:
        first_time = action_id not in self.action_first_time
        if first_time:
            self.action_first_time[action_id] = self.state.t
        return first_time

    def _standard_score_action_id(self, action_id: str) -> str:
        aliases = {
            "im_epinephrine_dose_verified": "im_epinephrine",
            "fluid_bolus_volume_verified": "fluid_bolus",
            "steroid_dose_verified": "steroid",
        }
        return aliases.get(action_id, action_id)

    def _is_delayed_standard_action(self, action_id: str) -> bool:
        """Backward-compatible helper for older callers.

        V1.2.7 uses module-boundary scoring. This helper reports whether an
        action would receive delayed half-score under the current module rules.
        """
        _gained, status, _reason = self._module_score_adjustment(action_id, 1)
        return status == "delayed"

    def _later_standard_action_attempted(self, action_id: str, later_ids: List[str]) -> bool:
        canonical_later = {self._standard_score_action_id(x) for x in later_ids}
        for aid in self.action_first_time:
            if self._standard_score_action_id(aid) in canonical_later:
                return True
        return False

    def _module_score_adjustment(self, action_id: str, points: int) -> Tuple[int, str, str]:
        """Return awarded points, status, and reason using V1.2.7 module boundaries.

        Status values:
        - full: full module score
        - delayed: half score, rounded down
        - no_score: completed outside the accepted scoring boundary
        """
        points = int(points)
        if points <= 0:
            return 0, "no_score", "该动作未设置普通路径分值。"

        canonical = self._standard_score_action_id(action_id)
        f = self.state.flags
        t = int(self.state.t)

        module1 = {"stop_infusion", "call_help"}
        module2 = {"abc_assess", "high_flow_oxygen", "shock_position", "connect_monitor", "check_bp"}
        module4_aux = {"bronchodilator", "steroid"}

        if canonical in module1:
            if t <= 60:
                return points, "full", "抢救启动模块60秒内完成。"
            if t <= 120:
                return max(0, points // 2), "delayed", "抢救启动模块61-120秒完成，按延迟半分。"
            return 0, "no_score", "超过抢救启动模块120秒评分边界，不再补分。"

        if canonical in module2:
            if not f.get("epi_im_given", False):
                return points, "full", "首次有效肌注肾上腺素前完成初始支持/评估。"
            if not f.get("first_reassessment_done", False):
                return max(0, points // 2), "delayed", "肌注肾上腺素后、第一次有效复评前补做，按延迟半分。"
            return 0, "no_score", "第一次有效复评后才补做初始支持/评估，不再补分。"

        if canonical == "im_epinephrine":
            if self._later_standard_action_attempted(canonical, ["fluid_bolus", "reassess_first", "bronchodilator", "steroid", "reassess_second", "family_explain", "sbar_handoff"]):
                return max(0, points // 2), "delayed", "肾上腺素在后续处理之后才完成，按延迟半分。"
            return points, "full", "首次肌注肾上腺素作为核心分界点完成。"

        if canonical == "fluid_bolus":
            if not f.get("epi_im_given", False):
                return 0, "no_score", "未先完成有效肌注肾上腺素，快速补液不计入标准顺序分。"
            if f.get("first_reassessment_done", False):
                return max(0, points // 2), "delayed", "第一次有效复评后才补做快速补液，按延迟半分。"
            return points, "full", "肌注肾上腺素后、第一次复评前完成快速补液。"

        if canonical == "reassess_first":
            if self._later_standard_action_attempted(canonical, ["bronchodilator", "steroid", "reassess_second", "family_explain", "sbar_handoff"]):
                return max(0, points // 2), "delayed", "第一次复评晚于后续处理，按延迟半分。"
            return points, "full", "快速补液后完成第一次有效复评。"

        if canonical in module4_aux:
            if not (f.get("epi_im_given", False) and f.get("fluid_bolus_valid", False)):
                return 0, "no_score", "未完成肾上腺素和有效快速补液前，辅助治疗不计入标准模块分。"
            if not f.get("first_reassessment_done", False):
                return max(0, points // 2), "delayed", "第一次有效复评前提前完成辅助治疗，按延迟半分。"
            if f.get("second_reassessment_done", False):
                return max(0, points // 2), "delayed", "第二次复评后才补做辅助治疗，按延迟半分。"
            return points, "full", "第一次复评后完成相应辅助治疗。"

        if canonical == "reassess_second":
            if not f.get("first_reassessment_done", False):
                return 0, "no_score", "第一次有效复评前不能计入第二次复评分。"
            if f.get("family_communication", False):
                return 0, "no_score", "家属沟通后才进行第二次复评，不计入告知前复评分。"
            return points, "full", "第一次复评后、家属沟通前完成第二次复评。"

        if canonical == "family_explain":
            if not f.get("second_reassessment_done", False):
                return 0, "no_score", "第二次有效复评前的家属沟通仅记录，不计入标准收尾分。"
            return points, "full", "第二次复评后完成家属沟通。"

        if canonical == "sbar_handoff":
            if not (f.get("second_reassessment_done", False) and f.get("family_communication", False)):
                return 0, "no_score", "第二次复评和家属沟通前的SBAR仅记录，不计入标准收尾分。"
            return points, "full", "第二次复评和家属沟通后完成SBAR交接。"

        # Fallback for legacy standard actions not explicitly mapped above.
        order = getattr(self, "standard_flow_order", {})
        if canonical not in order:
            return points, "full", "非模块映射动作，按原始分值处理。"
        idx = int(order[canonical])
        for aid in self.action_first_time:
            other = self._standard_score_action_id(aid)
            if other != canonical and other in order and int(order[other]) > idx:
                return max(0, points // 2), "delayed", "晚于后续标准动作完成，按延迟半分。"
        return points, "full", "按标准顺序完成。"

    def _apply_delay_rule(self, action_id: str, points: int) -> Tuple[int, str, str]:
        return self._module_score_adjustment(action_id, int(points))

    def _record_score_award(self, score_key: str, action_id: str, max_points: int, gained: int, status: str, reason: str) -> None:
        canonical = self._standard_score_action_id(action_id or score_key)
        self.state.flags.setdefault("score_awards", [])
        self.state.flags["score_awards"].append({
            "t": int(self.state.t),
            "module_id": self.action_module_map.get(canonical, ""),
            "score_key": score_key,
            "action_id": canonical,
            "max_points": int(max_points),
            "awarded_points": int(gained),
            "status": status,
            "reason": reason,
        })
        if status == "delayed":
            self.state.flags.setdefault("delayed_actions", [])
            self.state.flags["delayed_actions"].append(canonical)
        elif status == "no_score" and int(max_points) > 0:
            self.state.flags.setdefault("out_of_boundary_actions", [])
            self.state.flags["out_of_boundary_actions"].append(canonical)

    def _award_points_once(self, score_key: str, points: int, action_id: Optional[str] = None) -> int:
        """Award points once using V1.2.7 module-boundary scoring."""
        if points <= 0:
            return 0
        flag = f"_score_awarded_{score_key}"
        if self.state.flags.get(flag, False):
            return 0
        score_action = action_id or score_key
        gained, status, reason = self._apply_delay_rule(score_action, int(points))
        self.score += int(gained)
        if self.score > self.max_score:
            self.score = self.max_score
        self.state.flags[flag] = True
        self._record_score_award(score_key, score_action, int(points), int(gained), status, reason)
        return int(gained)

    def _award_action_score(self, action_id: str, action: Dict[str, Any], first_time: bool) -> int:
        sc = action.get("score", {})
        points = int(sc.get("points", 0))
        if not first_time or points <= 0:
            return 0
        gained, status, reason = self._apply_delay_rule(action_id, points)
        self.score += gained
        if self.score > self.max_score:
            self.score = self.max_score
        self._record_score_award(action_id, action_id, points, gained, status, reason)
        return gained

    def _apply_action_effects_only(self, action_id: str) -> None:
        action = self._find_action(action_id)
        if action:
            self.apply_effects(action.get("effects", {}))
            self._refresh_process_flags()
            self.state.grade = self.compute_grade()

    def _core_steps_before_epinephrine_count(self) -> int:
        f = self.state.flags
        checks = [
            bool(f.get("stopped_infusion", False) and f.get("iv_access", True)),
            bool(f.get("help_called", False)),
            "abc_assess" in self.action_first_time,
            bool(f.get("oxygen_on", False)),
            bool(f.get("positioned", False)),
            bool(f.get("monitor_on", False)),
            bool(f.get("bp_checked", False) or "check_bp" in self.action_first_time),
        ]
        return int(sum(checks))

    def _cardiac_arrest_criteria(self) -> bool:
        """Return True only when the scenario has progressed from pre-arrest shock
        to a cardiac-arrest-like state.

        V1.2.6a/V1.2.6b separates:
        - pre-arrest decompensation: HR may be very high, BP/SpO2 very low;
        - cardiac arrest: no effective circulation/breathing, CPR becomes indicated.
        Very low SpO2 alone is not enough if circulation is still effective.
        """
        f = self.state.flags
        if f.get("dead", False) or f.get("resuscitation_rosc", False):
            return False
        if f.get("cardiac_arrest", False):
            return True
        v = self.state.vitals
        s = self.state.symptoms
        spo2 = float(v.get("SpO2", 100))
        sbp = float(v.get("SBP", 120))
        hr = float(v.get("HR", 120))
        rr = float(v.get("RR", 30))
        arrest_spo2 = float(self.scenario.get("thresholds", {}).get("SpO2_arrest", 70))

        severe_hypoxia = spo2 <= arrest_spo2
        profound_shock = sbp <= 45 or (sbp < self.age_sbp_threshold() and s.get("consciousness", 0) >= 3)
        ineffective_breathing = rr <= 8 or s.get("consciousness", 0) >= 3
        decompensated_airway = bool(f.get("airway_obstruction_triggered", False) and spo2 <= arrest_spo2)
        extreme_pre_arrest_tachy = bool(hr >= 210 and sbp <= 45 and spo2 <= arrest_spo2)

        return bool(
            (severe_hypoxia and (profound_shock or ineffective_breathing or decompensated_airway))
            or extreme_pre_arrest_tachy
        )

    def _enter_cardiac_arrest_if_needed(self) -> None:
        f = self.state.flags
        if self._cardiac_arrest_criteria() and not f.get("cardiac_arrest", False):
            f["cardiac_arrest"] = True
            f["cpr_required"] = True
            f["cpr_indicated"] = True
            f["bvm_required"] = True
            f["advanced_support_indicated"] = True
            f["advanced_support_indicated_current"] = True
            f["advanced_support_indicated_ever"] = True
            f["advanced_support_indicated_reason"] = f.get("advanced_support_indicated_reason") or "cardiac_arrest"
            f["advanced_support_indicated_time_sec"] = f.get("advanced_support_indicated_time_sec") or self.state.t
            f["advanced_support_current_reason"] = "cardiac_arrest"
            f["resuscitation_required"] = True
            f["cardiac_arrest_time_sec"] = self.state.t
            self._log("system", "cardiac_arrest_triggered", {
                "reason": "severe_hypoxia_with_circulatory_or_ventilatory_failure",
                "SpO2": self.state.vitals.get("SpO2"),
                "HR": self.state.vitals.get("HR"),
                "RR": self.state.vitals.get("RR"),
                "SBP": self.state.vitals.get("SBP"),
            })

    def _mark_death_after_arrest_without_cpr(self, attempted_action_id: str = "") -> None:
        """Terminal event: cardiac arrest occurred and the next learner action was not CPR.

        V1.2.6d rule: once the patient has entered cardiac arrest, the immediate
        expected branch is CPR. If the next operation is anything other than CPR,
        record death and stop the scenario.
        """
        f = self.state.flags
        if f.get("dead", False) or f.get("resuscitation_rosc", False):
            return
        f["dead"] = True
        f["death_event"] = True
        f["death_after_arrest_without_cpr"] = True
        f["cpr_omission_death"] = True
        f["death_time_sec"] = self.state.t
        f["death_reason"] = "cardiac_arrest_next_action_not_cpr"
        f["outcome_class"] = "death_after_cardiac_arrest_without_cpr"
        f["scenario_terminal_death"] = True
        f["resuscitation_in_progress"] = False
        self.state.vitals["SpO2"] = min(float(self.state.vitals.get("SpO2", 40)), 40.0)
        self.state.vitals["SBP"] = min(float(self.state.vitals.get("SBP", 30)), 30.0)
        self.state.vitals["DBP"] = min(float(self.state.vitals.get("DBP", 20)), 20.0)
        self.state.symptoms["consciousness"] = 3
        self._log("system", "death_after_arrest_without_cpr", {
            "attempted_action_id": attempted_action_id,
            "cardiac_arrest_time_sec": f.get("cardiac_arrest_time_sec", None),
            "death_time_sec": self.state.t,
        })

    def _update_resuscitation_status(self) -> None:
        """Update post-arrest resuscitation flags.

        ROSC is not tied to post-arrest IM epinephrine. In this ward-nurse
        simulation, correct basic resuscitation is CPR + BVM ventilation + ALS
        contact. ALS arrival is represented narratively by ROSC and handoff.
        """
        f = self.state.flags
        if f.get("dead", False) or f.get("resuscitation_rosc", False):
            return
        if f.get("cardiac_arrest", False) and f.get("cpr_done", False) and f.get("bvm_done", False) and f.get("advanced_support_contacted", False):
            f["resuscitation_initiated_correctly"] = True
            f["resuscitation_rosc"] = True
            f["cardiac_arrest"] = False
            f["resuscitation_in_progress"] = False
            f["resuscitation_rosc_time_sec"] = self.state.t
            f["post_arrest_care_required"] = True
            f["critical_resuscitated_transfer_picu"] = True
            f["critical_transfer_picu"] = True
            f["scenario_terminal_critical_transfer"] = True
            f["outcome_class"] = "critical_resuscitated_transfer_picu"
            # After ROSC, values become measurable again but remain unstable;
            # do not display full normalization.
            self.state.vitals["SpO2"] = max(float(self.state.vitals.get("SpO2", 0)), 88.0)
            self.state.vitals["HR"] = 145.0
            self.state.vitals["RR"] = 30.0
            self.state.vitals["SBP"] = max(float(self.state.vitals.get("SBP", 0)), 70.0)
            self.state.vitals["DBP"] = max(float(self.state.vitals.get("DBP", 0)), 40.0)
            self.state.symptoms["consciousness"] = min(int(self.state.symptoms.get("consciousness", 0)), 2)
            self._log("system", "rosc_after_basic_resuscitation", {
                "cpr_done": True,
                "bvm_done": True,
                "advanced_support_contacted": True,
            })

    def _resuscitation_vitals_display(self) -> Optional[Dict[str, str]]:
        f = self.state.flags
        if f.get("dead", False):
            return {"SpO₂": "无可靠波形/不可测", "HR": "无脉搏/不可测", "RR": "无有效自主呼吸", "BP": "不可测"}
        if f.get("cardiac_arrest", False) and not f.get("resuscitation_rosc", False):
            return {"SpO₂": "无可靠波形/不可测", "HR": "无脉搏/不可测", "RR": "无有效自主呼吸", "BP": "不可测"}
        if f.get("resuscitation_rosc", False):
            v = self.state.vitals
            return {
                "SpO₂": f"{v.get('SpO2', 0):.0f}%（波形恢复）",
                "HR": f"{v.get('HR', 0):.0f}/min（可触及脉搏）",
                "RR": "人工通气支持",
                "BP": f"{v.get('SBP', 0):.0f}/{v.get('DBP', 0):.0f} mmHg",
            }
        return None

    def _refresh_process_flags(self) -> None:
        """Refresh derived pathway flags used by dynamics and reports.

        V1.2.6 uses a step-node trigger: deterioration before IM epinephrine
        is intentionally slower while the learner is completing the first seven
        basic actions, and accelerates when most core steps have been completed
        or the action order has reached the epinephrine decision node without
        effective IM epinephrine.
        """
        f = self.state.flags
        core_count = self._core_steps_before_epinephrine_count()
        f["pre_epi_core_steps_completed"] = core_count
        f["operation_count"] = len(self.action_first_time)
        if not f.get("epi_im_given", False):
            delay_node = bool(
                len(self.action_first_time) >= 8
                or f.get("fluid_bolus_given", False)
                or f.get("steroid_given", False)
                or f.get("first_reassessment_done", False)
            )
            if delay_node:
                f["epinephrine_delay_after_core_steps"] = True
        self._enter_cardiac_arrest_if_needed()
        # airway/BVM derived flags remain event-based because once the patient
        # has reached these critical branches they should be retained for
        # branch analysis. ALS indication, however, is refreshed as a CURRENT
        # need to avoid a stable standard-path case being flagged at the end
        # merely because a transient early vital-sign threshold was crossed.
        if self._airway_obstruction_indicated():
            f["airway_obstruction_triggered"] = True
        if self._bvm_indicated():
            f["bvm_required"] = True
        if f.get("cardiac_arrest", False):
            f["cpr_required"] = True
            f["cpr_indicated"] = True
            f["bvm_required"] = True
        self._refresh_advanced_support_flags()
        self._update_resuscitation_status()
        self._refresh_advanced_support_flags()

    def _airway_obstruction_indicated(self) -> bool:
        v = self.state.vitals
        s = self.state.symptoms
        f = self.state.flags
        return bool(
            f.get("airway_obstruction_triggered", False)
            or (f.get("airway_compromise", False) and (s.get("stridor", 0) >= 2 or v.get("SpO2", 100) < 88))
            or (s.get("stridor", 0) >= 2 and v.get("SpO2", 100) < 92)
        )

    def _bvm_indicated(self) -> bool:
        v = self.state.vitals
        s = self.state.symptoms
        f = self.state.flags
        return bool(
            f.get("bvm_required", False)
            or f.get("cardiac_arrest", False)
            or (self._airway_obstruction_indicated() and (v.get("SpO2", 100) < 88 or s.get("consciousness", 0) >= 2 or v.get("RR", 30) < 10))
        )

    def _is_unresolved_after_initial_support(self) -> bool:
        v = self.state.vitals
        s = self.state.symptoms
        if v.get("SpO2", 100) < 95:
            return True
        if v.get("SBP", 999) < self.age_sbp_threshold():
            return True
        if s.get("stridor", 0) >= 1:
            return True
        if s.get("wheeze", 0) >= 2:
            return True
        if s.get("consciousness", 0) >= 1:
            return True
        if s.get("angioedema", 0) >= 2:
            return True
        return False

    def _advanced_support_status(self) -> Tuple[bool, str]:
        """Return whether advanced life support is CURRENTLY indicated and why.

        V1.2.6f separates current indication from historical/transient triggers.
        A short early SpO2/BP dip that later resolves should be retained only as
        an analysis trace, not as a final process-safety defect.
        """
        v = self.state.vitals
        s = self.state.symptoms
        f = self.state.flags
        if f.get("critical_resuscitated_transfer_picu", False) or f.get("resuscitation_rosc", False):
            return True, "post_arrest_transfer_picu"
        if f.get("cardiac_arrest", False):
            return True, "cardiac_arrest"
        if f.get("bvm_required", False):
            return True, "bvm_required_or_ventilation_failure"
        if f.get("airway_obstruction_triggered", False):
            return True, "airway_obstruction"
        if v.get("SpO2", 100) < 90:
            return True, "current_severe_hypoxemia"
        if v.get("SBP", 999) < self.age_sbp_threshold():
            return True, "current_hypotension_below_age_threshold"
        if s.get("stridor", 0) >= 2:
            return True, "current_significant_stridor"
        if s.get("consciousness", 0) >= 2:
            return True, "current_altered_consciousness"
        if f.get("repeat_epi_given", False) and self._is_unresolved_after_initial_support():
            return True, "unresolved_after_repeat_epinephrine"
        return False, ""

    def _advanced_support_indicated(self) -> bool:
        return self._advanced_support_status()[0]

    def _refresh_advanced_support_flags(self) -> None:
        f = self.state.flags
        indicated, reason = self._advanced_support_status()
        f["advanced_support_indicated_current"] = bool(indicated)
        # Backward-compatible alias now means CURRENT indication, not ever.
        f["advanced_support_indicated"] = bool(indicated)
        f["advanced_support_current_reason"] = reason
        if indicated:
            f["advanced_support_indicated_ever"] = True
            f["advanced_support_latest_reason"] = reason
            f["advanced_support_latest_time_sec"] = self.state.t
            if not f.get("advanced_support_indicated_time_sec"):
                f["advanced_support_indicated_time_sec"] = self.state.t
                f["advanced_support_indicated_reason"] = reason
        else:
            f["advanced_support_current_reason"] = ""

    def apply_action(self, action_id: str) -> None:
        action = self._find_action(action_id)
        if not action:
            self._log("action", "unknown_action", {"action_id": action_id})
            return

        # V1.2.6d: after cardiac arrest, the immediate next action must be CPR.
        # Any non-CPR action records a terminal death event.
        if (
            self.state.flags.get("cardiac_arrest", False)
            and not self.state.flags.get("cpr_done", False)
            and action_id != "cpr"
        ):
            self._first_attempt(action_id)
            self._mark_death_after_arrest_without_cpr(action_id)
            self.state.grade = self.compute_grade()
            self._log("action", action_id, {
                "label": action.get("label", ""),
                "gained": 0,
                "status": "death_after_arrest_without_cpr",
                "result": "心肺骤停后未立即进行CPR，死亡事件已记录。"
            })
            return

        # Custom actions whose score depends on prerequisites, not just first click.
        if action_id == "reassess_first":
            self._first_attempt(action_id)
            if self.state.flags.get("epi_im_given", False) and self.state.flags.get("fluid_bolus_valid", False):
                self.state.flags["first_reassessment_done"] = True
                self.state.flags["initial_circulation_support_complete"] = True
                self.state.flags["reassess_count"] = max(int(self.state.flags.get("reassess_count", 0)), 1)
                unresolved = self._is_unresolved_after_initial_support()
                self.state.flags["repeat_epi_indicated"] = bool(unresolved)
                gained = self._award_points_once("reassess_first", int(action.get("score", {}).get("points", 0)), "reassess_first")
                self._log("action", action_id, {
                    "label": action.get("label", ""),
                    "gained": gained,
                    "status": "valid",
                    "repeat_epinephrine_indicated": unresolved,
                    "result": "有效第一次复评"
                })
            else:
                self.state.flags["premature_first_reassessment"] = True
                self._log("action", action_id, {
                    "label": action.get("label", ""),
                    "gained": 0,
                    "status": "premature",
                    "result": "已记录复评，但肌注肾上腺素和/或快速补液尚未有效完成，本次不计为有效第一次复评。"
                })
            return

        if action_id == "reassess_second":
            self._first_attempt(action_id)
            if not self.state.flags.get("first_reassessment_done", False):
                self.state.flags["premature_second_reassessment"] = True
                self._log("action", action_id, {
                    "label": action.get("label", ""),
                    "gained": 0,
                    "status": "premature",
                    "result": "已记录复评，但第一次有效复评尚未完成，本次不计为有效第二次复评。"
                })
            elif self.state.flags.get("family_communication", False):
                self.state.flags["late_second_reassessment"] = True
                self._log("action", action_id, {
                    "label": action.get("label", ""),
                    "gained": 0,
                    "status": "late",
                    "result": "已记录复评，但已发生在告知家属之后，不计为告知前第二次复评。"
                })
            else:
                self.state.flags["second_reassessment_done"] = True
                self.state.flags["reassess_count"] = max(int(self.state.flags.get("reassess_count", 0)), 2)
                gained = self._award_points_once("reassess_second", int(action.get("score", {}).get("points", 0)), "reassess_second")
                self._log("action", action_id, {
                    "label": action.get("label", ""),
                    "gained": gained,
                    "status": "valid",
                    "result": "有效第二次复评"
                })
            return

        if action_id == "family_explain":
            self._first_attempt(action_id)
            self.apply_effects(action.get("effects", {}))
            if self.state.flags.get("second_reassessment_done", False):
                gained = self._award_points_once("family_explain", int(action.get("score", {}).get("points", 0)), "family_explain")
                status = "valid"
                result = "第二次复评后完成家属沟通，计入收尾模块得分。"
            else:
                self.state.flags["family_before_second_reassess"] = True
                gained = 0
                status = "conditional_not_met"
                result = "已记录家属告知；但发生在第二次复评之前，不计入标准收尾分。"
            self._refresh_process_flags()
            self._log("action", action_id, {
                "label": action.get("label", ""),
                "gained": gained,
                "status": status,
                "result": result,
            })
            return

        if action_id == "sbar_handoff":
            self._first_attempt(action_id)
            self.apply_effects(action.get("effects", {}))
            valid = self.state.flags.get("family_communication", False) and self.state.flags.get("second_reassessment_done", False)
            if valid:
                self.state.flags["family_sbar_completed"] = True
                gained = self._award_points_once("sbar_handoff", int(action.get("score", {}).get("points", 0)), "sbar_handoff")
                status = "valid"
                result = "第二次复评和家属沟通后完成SBAR交接，计入收尾模块得分。"
            else:
                gained = 0
                status = "conditional_not_met"
                result = "已记录SBAR交接；需在第二次复评和家属告知后完成，才计入标准收尾分。"
            self._refresh_process_flags()
            self._log("action", action_id, {"label": action.get("label", ""), "gained": gained, "status": status, "result": result})
            return

        if action_id == "advanced_support":
            self._first_attempt(action_id)
            indicated, reason = self._advanced_support_status()
            self.state.flags["advanced_support_contacted"] = True
            self.state.flags["advanced_support_contact_time_sec"] = self.state.t
            self.state.flags["advanced_support_contact_reason"] = reason if indicated else "not_currently_indicated"
            self._refresh_process_flags()
            self.state.grade = self.compute_grade()
            self._log("action", action_id, {
                "label": action.get("label", ""),
                "gained": 0,
                "status": "indicated" if indicated else "recorded_not_required",
                "reason": reason,
                "result": "高级生命支持联系已记录。" if indicated else "已记录联系高级生命支持；当前未达到规范升级条件。"
            })
            return

        if action_id == "cpr":
            self._first_attempt(action_id)
            self._enter_cardiac_arrest_if_needed()
            indicated = bool(self.state.flags.get("cardiac_arrest", False) or self.state.flags.get("cpr_required", False))
            self.state.flags["cpr_done"] = True
            self.state.flags["cpr_indicated"] = indicated
            if indicated:
                self.state.flags["resuscitation_in_progress"] = True
            self._refresh_process_flags()
            self.state.grade = self.compute_grade()
            self._log("action", action_id, {
                "label": action.get("label", ""),
                "gained": 0,
                "status": "indicated" if indicated else "not_indicated",
                "result": "CPR操作已记录。" if indicated else "当前未达到心肺骤停条件，CPR记录为不适用操作。"
            })
            return

        if action_id == "bvm_ventilation":
            self._first_attempt(action_id)
            indicated = self._bvm_indicated()
            self.state.flags["bvm_done"] = True
            self.state.flags["bvm_required"] = bool(indicated)
            if indicated:
                self.apply_effects(action.get("effects", {}))
                self.state.flags["advanced_support_indicated_ever"] = True
                self.state.flags["advanced_support_latest_reason"] = "bvm_ventilation_done_for_critical_branch"
                status = "indicated"
                result = "球囊面罩加压给氧已记录。"
            else:
                self.state.flags["bvm_not_indicated"] = True
                status = "not_indicated"
                result = "当前尚未达到球囊面罩加压给氧条件，本次记录为不适用操作。"
            self._refresh_process_flags()
            self.state.grade = self.compute_grade()
            self._log("action", action_id, {"label": action.get("label", ""), "gained": 0, "status": status, "result": result})
            return

        if action_id == "nebulized_epinephrine":
            first_time = self._first_attempt(action_id)
            has_upper_airway = self.state.symptoms.get("stridor", 0) >= 1 or self.state.flags.get("airway_compromise", False)
            after_epi = self.state.flags.get("epi_im_given", False)
            if after_epi and has_upper_airway:
                self.apply_effects(action.get("effects", {}))
                status = "valid_adjunct"
                result = "存在上气道受累表现，雾化肾上腺素作为辅助处理已记录。"
            else:
                self.state.flags["nebulized_epi_not_indicated"] = True
                status = "not_indicated" if after_epi else "used_before_first_line"
                result = "当前未见明确喉鸣/上气道梗阻表现，雾化肾上腺素暂非标准得分路径。"
                if not after_epi:
                    result = "未先完成肌注肾上腺素，雾化肾上腺素不能替代一线治疗。"
            # keep existing secondary-drug penalty if before epinephrine
            if not after_epi:
                self.penalties += int(action.get("score", {}).get("penalty_points", 0))
            self._log("action", action_id, {"label": action.get("label", ""), "gained": 0, "status": status, "result": result})
            return

        if action_id in ("repeat_epinephrine", "im_epinephrine", "fluid_bolus", "steroid"):
            # In the web UI these require a dose/volume panel. Direct CLI use only records the attempt.
            self._first_attempt(action_id)
            self._log("action", action_id, {
                "label": action.get("label", ""),
                "gained": 0,
                "status": "input_required",
                "result": "该操作需要输入剂量或容量后才能判定。"
            })
            return

        first_time = self._first_attempt(action_id)
        gained = self._award_action_score(action_id, action, first_time)

        sc = action.get("score", {})
        if "penalty_points_always" in sc:
            p = int(sc.get("penalty_points_always", 0))
            if p:
                self.penalties += p
                self._log("action", "penalty", {"action_id": action_id, "penalty": p, "reason": "penalty_always"})

        if "penalty_if_before" in sc:
            flag_name = sc["penalty_if_before"]
            if not self.state.flags.get(flag_name, False):
                p = int(sc.get("penalty_points", 0))
                self.penalties += p
                self._log("action", "penalty", {"action_id": action_id, "penalty": p, "reason": f"used_before_{flag_name}"})

        self.apply_effects(action.get("effects", {}))
        self._refresh_process_flags()
        self.state.grade = self.compute_grade()
        self._log("action", action_id, {"label": action.get("label", ""), "gained": gained, "t": self.state.t})

    def apply_epinephrine_dose(self, dose_mg: float, action_id: str = "im_epinephrine") -> Dict[str, Any]:
        """Apply IM epinephrine after dose verification.

        V1.2.5 rules:
        - 1:1000 IM epinephrine, 0.01 mg/kg, single pediatric maximum 0.3 mg.
        - Correct range: target dose ±0.01 mg.
        - Below target range: ineffective underdose, no first-line effect or score.
        - Above target range but <=0.3 mg: inaccurate high dose; effect is recorded, score is not awarded.
        - >0.3 mg: serious medication safety event.
        """
        try:
            dose = float(dose_mg)
        except Exception:
            dose = 0.0

        if action_id not in ("im_epinephrine", "repeat_epinephrine"):
            action_id = "im_epinephrine"

        action = self._find_action(action_id)
        if not action:
            return {"status": "error", "message": "未找到对应的肾上腺素操作。", "dose_mg": dose, "target_dose_mg": None}

        self._first_attempt(action_id)

        if self.state.flags.get("cardiac_arrest", False) and not self.state.flags.get("cpr_done", False):
            self._mark_death_after_arrest_without_cpr(action_id)
            self.state.grade = self.compute_grade()
            return {"status": "death_after_arrest_without_cpr", "message": "心肺骤停后未立即进行CPR，死亡事件已记录。", "dose_mg": dose, "target_dose_mg": None}

        weight = float(self.state.weight_kg)
        target = round(min(0.01 * weight, 0.3), 3)
        max_single = 0.3
        tolerance = 0.01

        self.state.flags["epi_last_dose_mg"] = round(dose, 3)
        self.state.flags["epi_target_dose_mg"] = target
        self.state.flags["epi_dose_checked"] = True
        self.state.flags["epi_im_attempts"] = int(self.state.flags.get("epi_im_attempts", 0)) + 1

        is_repeat = action_id == "repeat_epinephrine"
        if is_repeat:
            if not (self.state.flags.get("epi_im_given", False) and self.state.flags.get("fluid_bolus_valid", False) and self.state.flags.get("first_reassessment_done", False)):
                self.state.flags["repeat_epi_premature"] = True
                self._log("action", "repeat_epinephrine_premature", {"dose_mg": round(dose, 3), "target_dose_mg": target, "gained": 0, "result": "premature"})
                return {
                    "status": "not_indicated",
                    "message": "再次肌注肾上腺素属于特殊路径：需先完成首次肌注、快速补液和第一次复评。",
                    "dose_mg": dose,
                    "target_dose_mg": target,
                }
            if not self._is_unresolved_after_initial_support():
                self.state.flags["repeat_epi_not_indicated"] = True
                self._log("action", "repeat_epinephrine_not_indicated", {"dose_mg": round(dose, 3), "target_dose_mg": target, "gained": 0, "result": "not_indicated"})
                return {
                    "status": "not_indicated",
                    "message": "当前复评提示病情较前稳定，暂不需要再次肌注肾上腺素；本次记录为非必要重复。",
                    "dose_mg": dose,
                    "target_dose_mg": target,
                }

        if dose > max_single + 1e-9:
            self.state.flags["epi_overdose_event"] = True
            self.state.flags["serious_medication_error"] = True
            self.state.flags["tachycardia_heart_failure"] = True
            self.state.vitals["HR"] = 220
            self.state.vitals["RR"] = max(float(self.state.vitals.get("RR", 30)), 58)
            self.state.vitals["SpO2"] = min(float(self.state.vitals.get("SpO2", 100)), 82)
            self.state.vitals["SBP"] = min(float(self.state.vitals.get("SBP", 100)), 55)
            self.state.vitals["DBP"] = min(float(self.state.vitals.get("DBP", 60)), 32)
            self.state.symptoms["consciousness"] = max(int(self.state.symptoms.get("consciousness", 0)), 2)
            self.state.grade = self.compute_grade()
            self._log("action", "im_epinephrine_overdose" if not is_repeat else "repeat_epinephrine_overdose", {
                "dose_mg": round(dose, 3),
                "target_dose_mg": target,
                "max_single_mg": max_single,
                "result": "serious_medication_error",
                "gained": 0,
            })
            return {
                "status": "overdose",
                "message": f"剂量 {dose:.2f} mg 超过儿童单次最大 {max_single:g} mg：判定为严重用药安全事件，本次不得分。",
                "dose_mg": dose,
                "target_dose_mg": target,
            }

        if dose < target - tolerance:
            self.state.flags["epi_underdose_event"] = True
            self._log("action", "im_epinephrine_underdose" if not is_repeat else "repeat_epinephrine_underdose", {
                "dose_mg": round(dose, 3),
                "target_dose_mg": target,
                "result": "ineffective",
                "gained": 0,
            })
            return {
                "status": "underdose",
                "message": f"剂量 {dose:.2f} mg 低于本例正确剂量范围（约 {target:g} mg）：判定为剂量不足，生命体征不会因本次肾上腺素改善。",
                "dose_mg": dose,
                "target_dose_mg": target,
            }

        dose_high = dose > target + tolerance
        if dose_high:
            self.state.flags["epi_dose_high_event"] = True

        # Apply clinical effect. Initial epinephrine may score only if dose is correct.
        self._apply_action_effects_only("im_epinephrine")
        if is_repeat:
            self.state.flags["repeat_epi_given"] = True
            self.state.flags["repeat_epi_indicated"] = True
            log_msg = "repeat_epinephrine_valid" if not dose_high else "repeat_epinephrine_dose_high"
            gained = 0
        else:
            log_msg = "im_epinephrine_dose_verified" if not dose_high else "im_epinephrine_dose_high"
            self.state.flags["epi_valid_dose_mg"] = round(dose, 3)
            gained = 0 if dose_high else self._award_points_once("im_epinephrine", int(action.get("score", {}).get("points", 0)), "im_epinephrine")

        self._log("action", log_msg, {
            "dose_mg": round(dose, 3),
            "target_dose_mg": target,
            "result": "dose_high_effect_recorded" if dose_high else "effective",
            "gained": gained,
        })
        if dose_high:
            return {
                "status": "dose_high",
                "message": f"剂量 {dose:.2f} mg 高于本例目标剂量 {target:g} mg，但未超过儿童单次最大0.3 mg：已记录为剂量不准确/用药安全缺陷，本次不给予肾上腺素剂量得分。",
                "dose_mg": dose,
                "target_dose_mg": target,
            }
        return {
            "status": "valid",
            "message": f"剂量 {dose:.2f} mg 已确认有效：按肌注肾上腺素处置执行。",
            "dose_mg": dose,
            "target_dose_mg": target,
        }

    def apply_fluid_bolus_volume(self, volume_ml: float) -> Dict[str, Any]:
        """Apply rapid crystalloid bolus after volume verification.

        V1.2.5 rules:
        - Pediatric crystalloid bolus: 10-20 ml/kg.
        - Single bolus maximum: 500 ml.
        - The existing IV access must be preserved.
        """
        action_id = "fluid_bolus"
        action = self._find_action(action_id)
        if not action:
            return {"status": "error", "message": "未找到快速补液操作。"}

        self._first_attempt(action_id)
        if self.state.flags.get("cardiac_arrest", False) and not self.state.flags.get("cpr_done", False):
            self._mark_death_after_arrest_without_cpr(action_id)
            self.state.grade = self.compute_grade()
            return {"status": "death_after_arrest_without_cpr", "message": "心肺骤停后未立即进行CPR，死亡事件已记录。", "volume_ml": volume_ml}
        try:
            volume = float(volume_ml)
        except Exception:
            volume = 0.0

        weight = float(self.state.weight_kg)
        min_ml = round(10 * weight, 1)
        max_ml = round(min(20 * weight, 500), 1)
        self.state.flags["fluid_bolus_volume_ml"] = round(volume, 1)
        self.state.flags["fluid_min_ml"] = min_ml
        self.state.flags["fluid_max_ml"] = max_ml
        self.state.flags["fluid_bolus_given"] = True

        if not self.state.flags.get("iv_access", True):
            self.state.flags["fluid_bolus_valid"] = False
            self._log("action", "fluid_bolus_invalid_no_iv", {
                "volume_ml": round(volume, 1),
                "min_ml": min_ml,
                "max_ml": max_ml,
                "gained": 0,
                "result": "no_iv_access"
            })
            return {
                "status": "invalid",
                "message": "已记录补液操作，但静脉通路此前被拔除，流程矛盾，本次补液不计为有效。",
                "volume_ml": volume,
                "min_ml": min_ml,
                "max_ml": max_ml,
            }

        if not self.state.flags.get("epi_im_given", False):
            self.state.flags["fluid_without_epi"] = True
            self.state.flags["fluid_bolus_valid"] = False
            self._log("action", "fluid_bolus_before_epinephrine", {
                "volume_ml": round(volume, 1),
                "min_ml": min_ml,
                "max_ml": max_ml,
                "gained": 0,
                "result": "used_before_first_line_epinephrine"
            })
            return {
                "status": "timing_error",
                "message": "已记录补液操作，但尚未完成有效肌注肾上腺素。普通评分路径要求肌注肾上腺素后再进行快速补液，本次不计入有效快速补液。",
                "volume_ml": volume,
                "min_ml": min_ml,
                "max_ml": max_ml,
            }

        if volume < min_ml:
            self.state.flags["fluid_bolus_under"] = True
            self.state.flags["fluid_bolus_valid"] = False
            self._log("action", "fluid_bolus_under", {"volume_ml": round(volume, 1), "min_ml": min_ml, "max_ml": max_ml, "gained": 0, "result": "insufficient_volume"})
            return {
                "status": "under",
                "message": f"补液量 {volume:.0f} ml 低于本例最低合理量 {min_ml:.0f} ml（10 ml/kg），判定为循环支持不足。",
                "volume_ml": volume,
                "min_ml": min_ml,
                "max_ml": max_ml,
            }

        if volume > max_ml:
            self.state.flags["fluid_bolus_over"] = True
            self.state.flags["fluid_bolus_valid"] = False
            if not self.state.flags.get("epi_im_given", False):
                self.state.flags["fluid_without_epi"] = True
            self._log("action", "fluid_bolus_over", {"volume_ml": round(volume, 1), "min_ml": min_ml, "max_ml": max_ml, "gained": 0, "result": "excessive_volume"})
            return {
                "status": "over",
                "message": f"补液量 {volume:.0f} ml 超过本例合理上限 {max_ml:.0f} ml（20 ml/kg且单次最大500 ml），判定为补液不当/容量风险。",
                "volume_ml": volume,
                "min_ml": min_ml,
                "max_ml": max_ml,
            }

        self.state.flags["fluid_bolus_valid"] = True
        self._apply_action_effects_only(action_id)
        gained = self._award_points_once("fluid_bolus", int(action.get("score", {}).get("points", 0)), "fluid_bolus")
        self._log("action", "fluid_bolus_volume_verified", {
            "volume_ml": round(volume, 1),
            "min_ml": min_ml,
            "max_ml": max_ml,
            "gained": gained,
            "result": "valid_volume"
        })
        return {
            "status": "valid",
            "message": f"补液量 {volume:.0f} ml 位于本例合理范围 {min_ml:.0f}–{max_ml:.0f} ml，按快速补液处置执行。",
            "volume_ml": volume,
            "min_ml": min_ml,
            "max_ml": max_ml,
        }

    def apply_steroid_dose(self, dose_mg: float) -> Dict[str, Any]:
        """Apply glucocorticoid after dose verification.

        V1.2.6 default standardizes the scored steroid option as IV
        methylprednisolone: 1-2 mg/kg, single maximum 40 mg.
        Steroid is a scored adjunct only after effective IM epinephrine and
        rapid fluid expansion; it must not replace first-line epinephrine.
        """
        action_id = "steroid"
        action = self._find_action(action_id)
        if not action:
            return {"status": "error", "message": "未找到糖皮质激素操作。"}
        self._first_attempt(action_id)
        if self.state.flags.get("cardiac_arrest", False) and not self.state.flags.get("cpr_done", False):
            self._mark_death_after_arrest_without_cpr(action_id)
            self.state.grade = self.compute_grade()
            return {"status": "death_after_arrest_without_cpr", "message": "心肺骤停后未立即进行CPR，死亡事件已记录。", "dose_mg": dose_mg}
        try:
            dose = float(dose_mg)
        except Exception:
            dose = 0.0

        weight = float(self.state.weight_kg)
        min_mg = round(1.0 * weight, 1)
        max_mg = round(min(2.0 * weight, 40.0), 1)
        f = self.state.flags
        f["steroid_given"] = True
        f["steroid_dose_checked"] = True
        f["steroid_dose_mg"] = round(dose, 1)
        f["steroid_min_mg"] = min_mg
        f["steroid_max_mg"] = max_mg

        timing_valid = bool(f.get("fluid_bolus_valid", False))
        after_epi = bool(f.get("epi_im_given", False))
        dose_valid = bool(min_mg <= dose <= max_mg)
        f["steroid_timing_valid"] = timing_valid
        if not timing_valid:
            f["steroid_before_fluid"] = True
        if not after_epi:
            f["steroid_without_epi"] = True
        if dose < min_mg:
            f["steroid_under"] = True
        if dose > max_mg:
            f["steroid_over"] = True

        f["steroid_valid"] = bool(timing_valid and after_epi and dose_valid)
        base_points = int(action.get("score", {}).get("points", 0)) if f["steroid_valid"] else 0
        if not f.get("_score_awarded_steroid", False) and base_points > 0:
            gained, status_score, reason_score = self._apply_delay_rule("steroid", base_points)
            self.score += int(gained)
            if self.score > self.max_score:
                self.score = self.max_score
            f["_score_awarded_steroid"] = True
            self._record_score_award("steroid", "steroid", base_points, int(gained), status_score, reason_score)
        else:
            gained = 0

        if f["steroid_valid"]:
            # Steroids are scored as an adjunct and dose-calculation item. They
            # should not immediately lower HR/RR or raise BP/SpO2 like
            # epinephrine, oxygen, ventilation, or crystalloid expansion.
            f["steroid_effect_ticks"] = 0
            status = "valid"
            message = f"糖皮质激素剂量 {dose:.0f} mg 位于本例合理范围 {min_mg:.0f}–{max_mg:.0f} mg，且使用时机正确，计入标准路径。"
        elif not timing_valid:
            status = "timing_error"
            message = "已记录糖皮质激素，但必须在有效快速扩容后使用；本次不能作为完整标准路径。"
        elif not after_epi:
            status = "used_before_first_line"
            message = "已记录糖皮质激素，但未先完成有效肌注肾上腺素，不能替代一线急救治疗。"
        elif dose < min_mg:
            status = "under"
            message = f"糖皮质激素剂量 {dose:.0f} mg 低于本例合理范围下限 {min_mg:.0f} mg。"
        else:
            status = "over"
            message = f"糖皮质激素剂量 {dose:.0f} mg 超过本例合理范围上限 {max_mg:.0f} mg。"

        self._log("action", "steroid_dose_verified" if f["steroid_valid"] else "steroid_dose_issue", {
            "dose_mg": round(dose, 1),
            "min_mg": min_mg,
            "max_mg": max_mg,
            "timing_valid": timing_valid,
            "after_epinephrine": after_epi,
            "dose_valid": dose_valid,
            "gained": gained,
            "status": status,
        })
        self._refresh_process_flags()
        self.state.grade = self.compute_grade()
        return {
            "status": status,
            "message": message,
            "dose_mg": dose,
            "min_mg": min_mg,
            "max_mg": max_mg,
        }

    def is_done(self) -> Tuple[bool, str]:
        ctx = {
            "t": self.state.t,
            "vitals": SimpleNamespace(**self.state.vitals),
            "symptoms": SimpleNamespace(**self.state.symptoms),
            "flags": SimpleNamespace(**self.state.flags),
            "grade": self.state.grade,
            "age_sbp_threshold": self.age_sbp_threshold(),
        }
        succ = self.scenario["end_conditions"]["success_when"]
        fail = self.scenario["end_conditions"]["failure_when"]

        if self.state.flags.get("critical_resuscitated_transfer_picu", False):
            return True, "critical_resuscitated_transfer_picu"

        try:
            if safe_eval(fail, ctx):
                return True, "failure"
        except Exception:
            pass

        # V1.2.6g ordinary assessment stop: once the learner has completed
        # effective first reassessment, effective second reassessment, family
        # communication, and SBAR handoff, the ordinary exam ends. Any standard
        # actions not completed by this point remain 0 and cannot be made up.
        ordinary_completed = bool(
            self.state.flags.get("first_reassessment_done", False)
            and self.state.flags.get("second_reassessment_done", False)
            and self.state.flags.get("family_communication", False)
            and self.state.flags.get("sbar_handoff", False)
            and not self.state.flags.get("cardiac_arrest", False)
            and not self.state.flags.get("dead", False)
        )
        if ordinary_completed:
            self.state.flags["standard_assessment_completed"] = True
            self.state.flags["ordinary_exam_terminal"] = True
            if self.score >= self.max_score and self.state.grade <= 2:
                self.state.flags["standard_pathway_full_score"] = True
            return True, "standard_assessment_completed"

        try:
            if safe_eval(succ, ctx) and (self.state.t >= self.min_time_for_success):
                return True, "success"
        except Exception:
            pass

        if self.state.t >= int(self.scenario["end_conditions"].get("max_time_seconds", 1200)):
            return True, "timeout"

        return False, ""

    def _process_safety_issues(self) -> List[str]:
        issues = []
        f = self.state.flags
        if not f.get("stopped_infusion", False):
            issues.append("未停用可疑药物/输液")
        if not f.get("iv_access", True):
            issues.append("拔除静脉通路，影响后续抢救用药和补液")
        if not f.get("help_called", False):
            issues.append("未呼救")
        if "abc_assess" not in self.action_first_time:
            issues.append("未进行ABC评估")
        if not f.get("oxygen_on", False):
            issues.append("未开放气道给氧")
        if not f.get("positioned", False):
            issues.append("未完成体位管理")
        if not f.get("monitor_on", False):
            issues.append("未连接监护")
        if not (f.get("bp_checked", False) or "check_bp" in self.action_first_time):
            issues.append("未测量血压/评估循环状态")
        if not f.get("epi_im_given", False):
            issues.append("未完成有效肌注肾上腺素")
        if f.get("epi_underdose_event", False):
            issues.append("肾上腺素剂量不足/操作无效")
        if f.get("epi_dose_high_event", False):
            issues.append("肾上腺素剂量高于目标剂量/用药安全缺陷")
        if f.get("epi_overdose_event", False):
            issues.append("肾上腺素剂量超过儿童单次最大0.3 mg/严重用药安全事件")
        if not f.get("fluid_bolus_valid", False):
            issues.append("未完成有效快速补液")
        if f.get("fluid_bolus_under", False):
            issues.append("补液量低于10 ml/kg，循环支持不足")
        if f.get("fluid_bolus_over", False):
            issues.append("补液量超过20 ml/kg或单次500 ml，存在容量风险")
        if f.get("fluid_without_epi", False) and not f.get("epi_im_given", False):
            issues.append("仅补液但未有效肌注肾上腺素，不能替代一线治疗")
        if not f.get("first_reassessment_done", False):
            issues.append("未完成有效第一次复评")
        if not f.get("bronchodilator_neb", False):
            issues.append("持续咳嗽/喘息时未进行雾化支扩")
        if not f.get("steroid_valid", False):
            issues.append("未完成符合时机和剂量要求的糖皮质激素辅助治疗")
        if f.get("steroid_before_fluid", False):
            issues.append("糖皮质激素使用早于有效快速扩容")
        if f.get("steroid_without_epi", False):
            issues.append("糖皮质激素不能替代一线肌注肾上腺素")
        if f.get("steroid_under", False):
            issues.append("糖皮质激素剂量不足")
        if f.get("steroid_over", False):
            issues.append("糖皮质激素剂量超过建议范围")
        if f.get("airway_obstruction_triggered", False) and not f.get("advanced_support_contacted", False):
            issues.append("出现气道梗阻/严重低氧风险但未联系高级支持")
        if f.get("bvm_required", False) and not f.get("bvm_done", False):
            issues.append("达到球囊面罩加压给氧条件但未执行")
        if not f.get("second_reassessment_done", False):
            issues.append("未完成告知家属前第二次复评")
        if f.get("family_before_second_reassess", False):
            issues.append("家属告知早于第二次复评")
        if not f.get("family_communication", False):
            issues.append("未完成家属告知")
        if not f.get("sbar_handoff", False):
            issues.append("未完成SBAR交接")
        if f.get("repeat_epi_premature", False):
            issues.append("再次肌注肾上腺素时机过早")
        if f.get("repeat_epi_not_indicated", False):
            issues.append("病情已较前稳定时进行了非必要再次肌注")
        if f.get("nebulized_epi_not_indicated", False):
            issues.append("雾化肾上腺素使用条件不充分或替代一线治疗倾向")
        als_current = bool(f.get("advanced_support_indicated_current", f.get("advanced_support_indicated", False)))
        if (
            als_current
            and not f.get("advanced_support_contacted", False)
            and not f.get("airway_obstruction_triggered", False)
            and not f.get("bvm_required", False)
            and not f.get("cpr_required", False)
            and not f.get("cardiac_arrest", False)
        ):
            issues.append("当前仍达到高级支持条件但未联系高级支持")
        if (f.get("cpr_required", False) or f.get("cpr_indicated", False)) and not f.get("cpr_done", False):
            issues.append("达到心肺复苏条件但未CPR")
        if f.get("cardiac_arrest", False) and not f.get("resuscitation_rosc", False) and f.get("cpr_done", False) and not f.get("bvm_done", False):
            issues.append("心肺复苏已启动但未进行球囊面罩通气支持")
        if f.get("cardiac_arrest", False) and not f.get("resuscitation_rosc", False) and f.get("cpr_done", False) and not f.get("advanced_support_contacted", False):
            issues.append("心肺复苏已启动但未联系高级生命支持")
        if f.get("death_after_arrest_without_cpr", False):
            issues.append("心肺骤停后下一步未选择CPR，已记录死亡事件")
        return issues

    def _module_score_summary(self) -> Dict[str, Any]:
        awards = list(self.state.flags.get("score_awards", []) or [])
        summary: Dict[str, Any] = {}
        for module_id, meta in self.module_scoring.items():
            module_awards = [a for a in awards if a.get("module_id") == module_id]
            awarded = int(sum(int(a.get("awarded_points", 0) or 0) for a in module_awards))
            max_points = int(meta.get("max_points", 0) or 0)
            summary[module_id] = {
                "name": meta.get("name", module_id),
                "max_points": max_points,
                "awarded_points": min(awarded, max_points),
                "completion_percent": round(min(awarded, max_points) / max_points * 100, 1) if max_points else 0,
                "boundary": meta.get("boundary", ""),
                "actions": meta.get("actions", []),
                "awards": module_awards,
            }
        return summary

    def build_report(self) -> Dict[str, Any]:
        grade_map = {1: "I", 2: "II", 3: "III", 4: "IV"}
        critical_actions = [a for a in self.actions if a.get("category", "").startswith("critical")]
        missing = []
        for a in critical_actions:
            aid = a.get("id", "")
            if aid == "fluid_bolus":
                if not self.state.flags.get("fluid_bolus_valid", False):
                    missing.append(aid)
            elif aid == "reassess_first":
                if not self.state.flags.get("first_reassessment_done", False):
                    missing.append(aid)
            elif aid == "reassess_second":
                if not self.state.flags.get("second_reassessment_done", False):
                    missing.append(aid)
            elif aid == "im_epinephrine":
                if not self.state.flags.get("epi_im_given", False):
                    missing.append(aid)
            elif aid and aid not in self.action_first_time:
                missing.append(aid)

        def t_of(aid: str) -> Optional[int]:
            return self.action_first_time.get(aid)

        def first_log_time(message: str) -> Optional[int]:
            for e in self.log:
                if e.kind == "action" and e.message == message:
                    return e.t
            return None

        f = self.state.flags
        report = {
            "scenario_id": self.scenario["scenario"]["id"],
            "scenario_title": self.scenario["scenario"]["title"],
            "scenario_version": self.scenario["scenario"].get("version", ""),
            "scenario_script_name": self.scenario["scenario"].get("script_name", self.scenario["scenario"].get("id", "scenario")),
            "patient": {
                "age_years": self.state.age_years,
                "weight_kg": self.state.weight_kg,
                "setting": self.scenario.get("patient", {}).get("setting", ""),
                "trigger": self.scenario.get("patient", {}).get("trigger", ""),
                "randomized_profile": self.scenario.get("patient", {}).get("randomized_profile", False),
                "randomization_rule": self.scenario.get("patient", {}).get("randomization_rule", ""),
            },
            "mode": self.mode,
            "end_time_seconds": self.state.t,
            "final_grade": grade_map.get(self.state.grade, str(self.state.grade)),
            "final_vitals": self.state.vitals,
            "final_vitals_display": self._resuscitation_vitals_display(),
            "final_symptoms": self.state.symptoms,
            "outcome_class": f.get("outcome_class", ""),
            "death_event": bool(f.get("death_event", False)),
            "death_after_arrest_without_cpr": bool(f.get("death_after_arrest_without_cpr", False)),
            "death_time_sec": f.get("death_time_sec", None),
            "death_reason": f.get("death_reason", ""),
            "score": self.score,
            "raw_score": self.score,
            "penalties": self.penalties,
            "penalties_not_subtracted_from_main_score": True,
            "max_score": self.max_score,
            "critical_missing": missing,
            "process_safety_issues": self._process_safety_issues(),
            "module_score_summary": self._module_score_summary(),
            "clinical_pathway_flags": {
                "initial_circulation_support_complete": bool(f.get("initial_circulation_support_complete", False)),
                "repeat_epi_indicated": bool(f.get("repeat_epi_indicated", False)),
                "repeat_epi_given": bool(f.get("repeat_epi_given", False)),
                "advanced_support_indicated": bool(f.get("advanced_support_indicated", False)),
                "advanced_support_indicated_current": bool(f.get("advanced_support_indicated_current", f.get("advanced_support_indicated", False))),
                "advanced_support_indicated_ever": bool(f.get("advanced_support_indicated_ever", False)),
                "advanced_support_indicated_time_sec": f.get("advanced_support_indicated_time_sec", None),
                "advanced_support_indicated_reason": f.get("advanced_support_indicated_reason", ""),
                "advanced_support_current_reason": f.get("advanced_support_current_reason", ""),
                "advanced_support_contacted": bool(f.get("advanced_support_contacted", False)),
                "advanced_support_contact_time_sec": f.get("advanced_support_contact_time_sec", None),
                "advanced_support_contact_reason": f.get("advanced_support_contact_reason", ""),
                "cardiac_arrest": bool(f.get("cardiac_arrest", False)),
                "cpr_required": bool(f.get("cpr_required", False)),
                "cpr_indicated": bool(f.get("cpr_indicated", False)),
                "cpr_done": bool(f.get("cpr_done", False)),
                "resuscitation_in_progress": bool(f.get("resuscitation_in_progress", False)),
                "resuscitation_initiated_correctly": bool(f.get("resuscitation_initiated_correctly", False)),
                "resuscitation_rosc": bool(f.get("resuscitation_rosc", False)),
                "critical_resuscitated_transfer_picu": bool(f.get("critical_resuscitated_transfer_picu", False)),
                "critical_transfer_picu": bool(f.get("critical_transfer_picu", False)),
                "death_after_arrest_without_cpr": bool(f.get("death_after_arrest_without_cpr", False)),
                "family_sbar_completed": bool(f.get("family_sbar_completed", False)),
                "standard_assessment_completed": bool(f.get("standard_assessment_completed", False)),
                "ordinary_exam_terminal": bool(f.get("ordinary_exam_terminal", False)),
                "standard_pathway_full_score": bool(f.get("standard_pathway_full_score", False)),
                "delayed_actions": list(f.get("delayed_actions", []) or []),
                "out_of_boundary_actions": list(f.get("out_of_boundary_actions", []) or []),
                "score_awards": list(f.get("score_awards", []) or []),
                "steroid_valid": bool(f.get("steroid_valid", False)),
                "airway_obstruction_triggered": bool(f.get("airway_obstruction_triggered", False)),
                "bvm_required": bool(f.get("bvm_required", False)),
                "bvm_done": bool(f.get("bvm_done", False)),
                "epinephrine_delay_after_core_steps": bool(f.get("epinephrine_delay_after_core_steps", False)),
                "pre_epi_core_steps_completed": int(f.get("pre_epi_core_steps_completed", 0)),
            },
            "key_timeline": {
                "stop_infusion": t_of("stop_infusion"),
                "call_help": t_of("call_help"),
                "abc_assess": t_of("abc_assess"),
                "oxygen": t_of("high_flow_oxygen"),
                "position": t_of("shock_position"),
                "monitor": t_of("connect_monitor"),
                "bp_check": t_of("check_bp"),
                "epi_im": t_of("im_epinephrine"),
                "epi_last_dose_mg": f.get("epi_last_dose_mg", None),
                "epi_target_dose_mg": f.get("epi_target_dose_mg", None),
                "epi_dose_high_event": bool(f.get("epi_dose_high_event", False)),
                "serious_medication_error": bool(f.get("serious_medication_error", False)),
                "fluid": t_of("fluid_bolus"),
                "fluid_bolus_volume_ml": f.get("fluid_bolus_volume_ml", None),
                "fluid_min_ml": f.get("fluid_min_ml", None),
                "fluid_max_ml": f.get("fluid_max_ml", None),
                "fluid_bolus_valid": bool(f.get("fluid_bolus_valid", False)),
                "first_reassessment": t_of("reassess_first"),
                "second_reassessment": t_of("reassess_second"),
                "reassess_count": int(f.get("reassess_count", 0)),
                "bronchodilator": t_of("bronchodilator"),
                "steroid": t_of("steroid"),
                "steroid_dose_mg": f.get("steroid_dose_mg", None),
                "steroid_min_mg": f.get("steroid_min_mg", None),
                "steroid_max_mg": f.get("steroid_max_mg", None),
                "steroid_valid": bool(f.get("steroid_valid", False)),
                "nebulized_epinephrine": t_of("nebulized_epinephrine"),
                "repeat_epinephrine": t_of("repeat_epinephrine"),
                "advanced_support": t_of("advanced_support"),
                "advanced_support_indicated_time_sec": f.get("advanced_support_indicated_time_sec", None),
                "advanced_support_indicated_reason": f.get("advanced_support_indicated_reason", ""),
                "advanced_support_current_reason": f.get("advanced_support_current_reason", ""),
                "bvm_ventilation": t_of("bvm_ventilation"),
                "cpr": t_of("cpr"),
                "cardiac_arrest_time_sec": f.get("cardiac_arrest_time_sec", None),
                "resuscitation_rosc_time_sec": f.get("resuscitation_rosc_time_sec", None),
                "epinephrine_delay_after_core_steps": bool(f.get("epinephrine_delay_after_core_steps", False)),
                "airway_obstruction_triggered": bool(f.get("airway_obstruction_triggered", False)),
                "bvm_required": bool(f.get("bvm_required", False)),
                "family_communication": t_of("family_explain"),
                "sbar_handoff": t_of("sbar_handoff"),
                "im_epinephrine_dose_verified_time": first_log_time("im_epinephrine_dose_verified"),
                "fluid_bolus_volume_verified_time": first_log_time("fluid_bolus_volume_verified"),
            },
            "observe_recommendation": self.scenario.get("reporting", {}).get("observe_recommendation", {}),
            "log": [dict(t=e.t, kind=e.kind, message=e.message, data=e.data) for e in self.log],
        }
        return report

def run_interactive(sim: Simulator) -> Dict[str, Any]:
    print("\n=== 情景开始 ===")
    print(sim.scenario["baseline"]["time_zero_description"])
    print()

    while True:
        print(sim.format_status())
        sim.print_coach_hint()

        done, why = sim.is_done()
        if done:
            print(f"=== 情景结束：{why} ===\n")
            break

        for i, a in enumerate(sim.actions, start=1):
            print(f"{i:>2}. {a['label']}")
        print(f"{'T':>2}. 时间流逝 {sim.tick_seconds}s")
        if sim.mode != "exam":
            print(f"{'Q':>2}. 结束并生成报告")

        choice = input("请选择操作编号：").strip().lower()
        if choice == "t":
            sim.tick()
            continue
        if choice == "q":
            if sim.mode == "exam":
                print("考试模式不支持提前结束，请继续完成情景。\n")
                continue
            break

        if not choice.isdigit() or not (1 <= int(choice) <= len(sim.actions)):
            print("输入无效，请重试。\n")
            continue

        action = sim.actions[int(choice) - 1]
        sim.apply_action(action["id"])
        sim.tick()

    return sim.build_report()

def load_script_actions(path: str) -> List[str]:
    acts = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            acts.append(line)
    return acts

def run_script(sim: Simulator, script_actions: List[str]) -> Dict[str, Any]:
    sim._log("system", "script_mode", {"script_len": len(script_actions)})
    for act in script_actions:
        done, _ = sim.is_done()
        if done:
            break
        if act == "TICK":
            sim.tick()
            continue
        sim.apply_action(act)
        sim.tick()
    return sim.build_report()

def safe_filename_part(text: str) -> str:
    cleaned = str(text or "").strip()
    for ch in '\\/:*?"<>|':
        cleaned = cleaned.replace(ch, "_")
    cleaned = cleaned.replace(" ", "_")
    return cleaned or "unknown"


def save_report(report: Dict[str, Any], out_dir: str) -> Tuple[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    stamp = now_stamp()
    mode_part = safe_filename_part(report.get("mode", "mode"))
    script_part = safe_filename_part(report.get("scenario_script_name") or report.get("scenario_id", "scenario"))
    file_stem = f"{mode_part}_{script_part}_{stamp}_analysis_report"
    json_path = os.path.join(out_dir, f"{file_stem}.json")
    md_path = os.path.join(out_dir, f"{file_stem}.md")

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    lines = []
    lines.append(f"# 模拟复盘报告：{report['scenario_title']}")
    lines.append("")
    lines.append(f"- 结束时间：{report['end_time_seconds']}s")
    lines.append(f"- 最终分级：{report['final_grade']}")
    lines.append(f"- 得分：{report['score']}/{report['max_score']}（raw {report['raw_score']}，penalties记录但不扣主分：{report['penalties']}）")
    lines.append("")

    lines.append("## 过程性安全缺陷（培训评估）")
    issues = report.get("process_safety_issues", [])
    lines.append("、".join(issues) if issues else "无")
    lines.append("")

    lines.append("## 关键时间轴")
    for k, v in report["key_timeline"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    v_display = report.get("final_vitals_display")
    v = report["final_vitals"]
    lines.append("## 最终生命体征")
    if isinstance(v_display, dict) and v_display:
        lines.append(f"- SpO₂ {v_display.get('SpO₂','')} | HR {v_display.get('HR','')} | RR {v_display.get('RR','')} | BP {v_display.get('BP','')}")
    else:
        lines.append(f"- SpO₂ {v['SpO2']:.0f}% | HR {v['HR']:.0f}/min | RR {v['RR']:.0f}/min | BP {v['SBP']:.0f}/{v['DBP']:.0f} mmHg")
    lines.append("")

    lines.append("## 观察建议（教学用）")
    obs = report.get("observe_recommendation", {})
    if obs:
        lines.append(f"- 呼吸困难：{obs.get('resp_distress_hours','')}")
        lines.append(f"- 循环不稳定：{obs.get('circulatory_instability_hours','')}")
    else:
        lines.append("- 以本院流程为准。")
    lines.append("")

    lines.append("## 缺失关键动作")
    lines.append(", ".join(report["critical_missing"]) if report["critical_missing"] else "无")
    lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return json_path, md_path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True, help="Scenario JSON/YAML")
    ap.add_argument("--mode", choices=["coach","exam"], default="coach")
    ap.add_argument("--script", default="", help="Optional script file with action ids per line; use 'TICK'")
    ap.add_argument("--out", default="runs")
    ap.add_argument("--seed", type=int, default=-1, help="Random seed (exam option shuffle). -1 uses current time.")
    args = ap.parse_args()

    scenario = load_scenario(args.scenario)
    sim = Simulator(scenario, mode=args.mode, seed=args.seed)

    if args.script:
        report = run_script(sim, load_script_actions(args.script))
    else:
        report = run_interactive(sim)

    json_path, md_path = save_report(report, args.out)
    print("报告已生成：")
    print(" -", json_path)
    print(" -", md_path)

if __name__ == "__main__":
    main()
