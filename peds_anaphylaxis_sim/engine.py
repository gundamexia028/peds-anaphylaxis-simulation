# -*- coding: utf-8 -*-
"""
Pediatric Ward Anaphylaxis Simulator (Training v1.1)

特点（培训版）：
- 动态情景（规则驱动）：输入操作 -> 生命体征/症状随时间演化
- 操作菜单：仅显示“操作名称”，不提供引导性措辞
- 自动评分：时间窗 + 过程扣分（仅用于培训）
- 报告突出“过程性安全缺陷”（如未呼救/未给氧/未监护/未测血压/复评不足）
- 防止过早结束：成功判定需达到最短训练时长（在情景脚本 training.min_time_seconds_for_success 配置）

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

    def tick(self) -> None:
        self.state.t += self.tick_seconds

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


    def format_status(self) -> str:
        v = self.state.vitals
        s = self.state.symptoms
        g = self.state.grade
        grade_name = {1:"I",2:"II",3:"III",4:"IV"}.get(g, str(g))

        symptom_text = []
        if s.get("rash",0) >= 1: symptom_text.append("皮疹/风团")
        if s.get("angioedema",0) >= 1: symptom_text.append("血管性水肿")
        if s.get("wheeze",0) >= 1: symptom_text.append("喘鸣")
        if s.get("stridor",0) >= 1: symptom_text.append("喉鸣/声音改变")
        if s.get("gi",0) >= 1: symptom_text.append("胃肠道症状")
        if s.get("consciousness",0) >= 1: symptom_text.append(["烦躁","嗜睡","反应差"][min(2, s["consciousness"]-1)])

        prompt = self.get_guided_prompt() if self.mode == "coach" else ""
        prompt_line = f"当前提示：{prompt}\n" if prompt else ""
        return (
            f"时间：{self.state.t:>4}s | 分级：{grade_name}\n"
            + prompt_line
            + self._format_vitals_line()
            + f"症状：{('、'.join(symptom_text) if symptom_text else '无明显主观异常')}\n"
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

    def apply_action(self, action_id: str) -> None:
        action = next((a for a in self.actions if a["id"] == action_id), None)
        if not action:
            self._log("action", "unknown_action", {"action_id": action_id})
            return

        first_time = action_id not in self.action_first_time
        if first_time:
            self.action_first_time[action_id] = self.state.t

        sc = action.get("score", {})
        points = int(sc.get("points", 0))
        window = int(sc.get("time_window_seconds", 999999))
        gained = 0

        # Award score at most once per action ID (first execution only),
        # so total score cannot exceed max_score.
        if first_time and points > 0:
            gained = points if self.state.t <= window else max(0, points // 2)
            self.score += gained
            if self.score > self.max_score:
                self.score = self.max_score

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
        self.state.grade = self.compute_grade()
        self._log("action", action_id, {"label": action.get("label", ""), "gained": gained, "t": self.state.t})

    def apply_epinephrine_dose(self, dose_mg: float) -> Dict[str, Any]:
        """Apply IM epinephrine only after dose verification.

        Rule used by the web prototype:
        - Correct preset dose = 0.01 mg/kg, capped at 0.5 mg.
        - Below the calculated dose: judged ineffective, no epinephrine effect and no score.
        - Above 0.5 mg: judged as tachycardia-induced heart failure event.
        - Calculated dose through 0.5 mg: apply the original im_epinephrine action.
        """
        try:
            dose = float(dose_mg)
        except Exception:
            dose = 0.0

        weight = float(self.state.weight_kg)
        target = min(0.01 * weight, 0.5)
        target = round(target, 3)
        tolerance = 1e-9

        self.state.flags["epi_last_dose_mg"] = round(dose, 3)
        self.state.flags["epi_target_dose_mg"] = target
        self.state.flags["epi_dose_checked"] = True
        self.state.flags["epi_im_attempts"] = int(self.state.flags.get("epi_im_attempts", 0)) + 1

        if dose > 0.5 + tolerance:
            self.state.flags["epi_overdose_event"] = True
            self.state.flags["tachycardia_heart_failure"] = True
            self.state.vitals["HR"] = 220
            self.state.vitals["RR"] = max(float(self.state.vitals.get("RR", 30)), 58)
            self.state.vitals["SpO2"] = min(float(self.state.vitals.get("SpO2", 100)), 82)
            self.state.vitals["SBP"] = min(float(self.state.vitals.get("SBP", 100)), 55)
            self.state.vitals["DBP"] = min(float(self.state.vitals.get("DBP", 60)), 32)
            self.state.symptoms["consciousness"] = max(int(self.state.symptoms.get("consciousness", 0)), 2)
            self.state.grade = self.compute_grade()
            self._log(
                "action",
                "im_epinephrine_overdose",
                {
                    "dose_mg": round(dose, 3),
                    "target_dose_mg": target,
                    "max_single_mg": 0.5,
                    "result": "tachycardia_heart_failure",
                    "gained": 0,
                },
            )
            return {
                "status": "overdose",
                "message": f"剂量 {dose:.2f} mg 超过 0.5 mg：判定为心动过速致心衰事件，本次肌注肾上腺素不得分。",
                "dose_mg": dose,
                "target_dose_mg": target,
            }

        if dose < target - tolerance:
            self.state.flags["epi_underdose_event"] = True
            self._log(
                "action",
                "im_epinephrine_underdose",
                {
                    "dose_mg": round(dose, 3),
                    "target_dose_mg": target,
                    "result": "ineffective",
                    "gained": 0,
                },
            )
            return {
                "status": "underdose",
                "message": f"剂量 {dose:.2f} mg 低于本例正确剂量 {target:g} mg：判定为操作无效，生命体征不会因肾上腺素改善。",
                "dose_mg": dose,
                "target_dose_mg": target,
            }

        self.state.flags["epi_valid_dose_mg"] = round(dose, 3)
        self._log(
            "action",
            "im_epinephrine_dose_verified",
            {"dose_mg": round(dose, 3), "target_dose_mg": target, "result": "effective"},
        )
        self.apply_action("im_epinephrine")
        return {
            "status": "valid",
            "message": f"剂量 {dose:.2f} mg 已确认有效：按肌注肾上腺素处置执行。",
            "dose_mg": dose,
            "target_dose_mg": target,
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

        try:
            if safe_eval(fail, ctx):
                return True, "failure"
        except Exception:
            pass

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
        if not f.get("help_called", False):
            issues.append("未呼救")
        if not f.get("oxygen_on", False):
            issues.append("未给氧")
        if not f.get("monitor_on", False):
            issues.append("未连接监护")
        if not f.get("bp_checked", False):
            issues.append("未测量血压/灌注评估")
        if int(f.get("reassess_count", 0)) < self.min_reassess_recommended:
            issues.append("复评次数不足")
        if not f.get("family_communication", False):
            issues.append("未完成家属沟通")
        if not f.get("sbar_handoff", False):
            issues.append("未完成SBAR交接")
        if f.get("epi_underdose_event", False):
            issues.append("肾上腺素剂量不足/操作无效")
        if f.get("epi_overdose_event", False):
            issues.append("肾上腺素剂量超过0.5 mg/心动过速致心衰")
        return issues

    def build_report(self) -> Dict[str, Any]:
        grade_map = {1:"I",2:"II",3:"III",4:"IV"}
        critical_actions = [a for a in self.actions if a.get("category","").startswith("critical")]
        missing = [a["id"] for a in critical_actions if a["id"] not in self.action_first_time]

        def t_of(aid: str) -> Optional[int]:
            return self.action_first_time.get(aid)

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
            "final_symptoms": self.state.symptoms,
            "score": max(0, self.score - self.penalties),
            "raw_score": self.score,
            "penalties": self.penalties,
            "max_score": self.max_score,
            "critical_missing": missing,
            "process_safety_issues": self._process_safety_issues(),
            "key_timeline": {
                "stop_infusion": t_of("stop_infusion"),
                "call_help": t_of("call_help"),
                "oxygen": t_of("high_flow_oxygen"),
                "monitor": t_of("connect_monitor"),
                "bp_check": t_of("check_bp"),
                "epi_im": t_of("im_epinephrine"),
                "epi_last_dose_mg": self.state.flags.get("epi_last_dose_mg", None),
                "epi_target_dose_mg": self.state.flags.get("epi_target_dose_mg", None),
                "fluid": t_of("fluid_bolus"),
                "family_communication": t_of("family_explain"),
                "sbar_handoff": t_of("sbar_handoff"),
                "reassess_count": int(self.state.flags.get("reassess_count", 0)),
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
    lines.append(f"- 得分：{report['score']}/{report['max_score']}（raw {report['raw_score']}，penalties {report['penalties']}）")
    lines.append("")

    lines.append("## 过程性安全缺陷（培训评估）")
    issues = report.get("process_safety_issues", [])
    lines.append("、".join(issues) if issues else "无")
    lines.append("")

    lines.append("## 关键时间轴")
    for k, v in report["key_timeline"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")

    v = report["final_vitals"]
    lines.append("## 最终生命体征")
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
