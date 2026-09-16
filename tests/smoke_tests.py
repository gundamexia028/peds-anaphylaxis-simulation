from pathlib import Path
import sys
import types


class DummySessionState(dict):
    def __getattr__(self, key):
        return self.get(key, "")

    def __setattr__(self, key, value):
        self[key] = value


def _cache_passthrough(*args, **kwargs):
    def wrapper(func):
        return func
    return wrapper


class DummyStreamlit(types.SimpleNamespace):
    def __getattr__(self, name):
        def noop(*args, **kwargs):
            return None
        return noop


if "streamlit" not in sys.modules:
    sys.modules["streamlit"] = DummyStreamlit(
        session_state=DummySessionState(),
        secrets={},
        cache_resource=_cache_passthrough,
        cache_data=_cache_passthrough,
    )


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from peds_anaphylaxis_sim.engine import Simulator, load_scenario  # noqa: E402
from streamlit_app import build_data_quality_records, build_participant_analysis_records  # noqa: E402


SCENARIO = ROOT / "peds_anaphylaxis_sim" / "scenarios" / "peds_ward_anaphylaxis_iv_initial.json"


def tick_action(sim: Simulator, action_id: str) -> None:
    sim.apply_action(action_id)
    sim.tick()


def run_standard_path() -> Simulator:
    scenario = load_scenario(str(SCENARIO))
    sim = Simulator(scenario, mode="exam", seed=123)
    for action_id in [
        "stop_infusion",
        "call_help",
        "abc_assess",
        "high_flow_oxygen",
        "shock_position",
        "connect_monitor",
        "check_bp",
    ]:
        tick_action(sim, action_id)
    sim.apply_epinephrine_dose(0.14)
    sim.tick()
    sim.apply_fluid_bolus_volume(200)
    sim.tick()
    tick_action(sim, "reassess_first")
    tick_action(sim, "bronchodilator")
    sim.apply_steroid_dose(20)
    sim.tick()
    tick_action(sim, "reassess_second")
    tick_action(sim, "family_explain")
    tick_action(sim, "sbar_handoff")
    return sim


def test_standard_path_full_score() -> None:
    sim = run_standard_path()
    done, why = sim.is_done()
    report = sim.build_report()
    assert done is True
    assert why == "standard_assessment_completed"
    assert report["score"] == 100
    assert report["max_score"] == 100
    assert report["critical_missing"] == []
    assert report["process_safety_issues"] == []


def test_invalid_steroid_is_missing() -> None:
    scenario = load_scenario(str(SCENARIO))
    sim = Simulator(scenario, mode="exam", seed=123)
    for action_id in [
        "stop_infusion",
        "call_help",
        "abc_assess",
        "high_flow_oxygen",
        "shock_position",
        "connect_monitor",
        "check_bp",
    ]:
        tick_action(sim, action_id)
    sim.apply_epinephrine_dose(0.14)
    sim.tick()
    sim.apply_fluid_bolus_volume(200)
    sim.tick()
    tick_action(sim, "reassess_first")
    tick_action(sim, "bronchodilator")
    sim.apply_steroid_dose(1)
    sim.tick()
    report = sim.build_report()
    assert "steroid" in report["critical_missing"]
    assert report["clinical_pathway_flags"]["steroid_valid"] is False


def test_epinephrine_underdose_subscore_policy() -> None:
    scenario = load_scenario(str(SCENARIO))
    sim = Simulator(scenario, mode="exam", seed=123)
    for action_id in [
        "stop_infusion",
        "call_help",
        "abc_assess",
        "high_flow_oxygen",
        "shock_position",
        "connect_monitor",
        "check_bp",
    ]:
        tick_action(sim, action_id)
    before = sim.score
    result = sim.apply_epinephrine_dose(0.01)
    assert result["status"] == "underdose"
    assert sim.state.flags.get("epi_im_given") is False
    assert sim.score == before + 17
    subscores = sim.state.flags.get("epinephrine_subscores", {})
    assert subscores["drug_selection"]["awarded_points"] == 10
    assert subscores["route_correct"]["awarded_points"] == 5
    assert subscores["timing"]["awarded_points"] == 2
    assert "dose_correct" not in subscores


def test_participant_pair_export() -> None:
    records = [
        {
            "participant_id": "P001",
            "collection_mode": "正式采集",
            "collection_mode_code": "formal",
            "assessment_phase": "基线评估",
            "session_id": "baseline_1",
            "created_at": "2026-05-27T10:00:00",
            "score": 70,
            "score_percent": 70,
            "valid_epi_time": 180,
            "success": "是",
        },
        {
            "participant_id": "P001",
            "collection_mode": "正式采集",
            "collection_mode_code": "formal",
            "assessment_phase": "模拟培训",
            "session_id": "training_1",
            "created_at": "2026-05-27T10:30:00",
            "score": 100,
            "score_percent": 100,
            "success": "是",
        },
        {
            "participant_id": "P001",
            "collection_mode": "正式采集",
            "collection_mode_code": "formal",
            "assessment_phase": "培训后考核",
            "session_id": "post_1",
            "created_at": "2026-05-27T11:00:00",
            "score": 90,
            "score_percent": 90,
            "valid_epi_time": 120,
            "success": "是",
        },
    ]
    paired = build_participant_analysis_records(records)
    assert len(paired) == 1
    assert paired[0]["pre_post_pair_ready"] == "是"
    assert paired[0]["all_three_stages_recorded"] == "是"
    assert paired[0]["formal_analysis_ready"] == "是"
    assert paired[0]["score_change_post_minus_baseline"] == 20.0
    assert paired[0]["epi_time_change_baseline_minus_post"] == 60.0
    quality = build_data_quality_records(records)
    assert not any(item["assessment_phase"] == "模拟培训" and item["quality_issue"] == "缺少该阶段记录" for item in quality)


def test_academy_scenario_pair_export() -> None:
    records = [
        {
            "system_mode": "academy",
            "academy_scenario_id": "academy_anaphylaxis_rescue",
            "academy_scenario_name": "严重过敏反应/过敏性休克抢救",
            "participant_id": "ACAD001",
            "collection_mode": "正式采集",
            "collection_mode_code": "formal",
            "assessment_phase": "课前测评",
            "session_id": "pre_1",
            "created_at": "2026-05-31T10:00:00",
            "score": 60,
        },
        {
            "system_mode": "academy",
            "academy_scenario_id": "academy_anaphylaxis_rescue",
            "academy_scenario_name": "严重过敏反应/过敏性休克抢救",
            "participant_id": "ACAD001",
            "collection_mode": "正式采集",
            "collection_mode_code": "formal",
            "assessment_phase": "模拟训练",
            "session_id": "training_1",
            "created_at": "2026-05-31T10:20:00",
            "score": 90,
        },
        {
            "system_mode": "academy",
            "academy_scenario_id": "academy_anaphylaxis_rescue",
            "academy_scenario_name": "严重过敏反应/过敏性休克抢救",
            "participant_id": "ACAD001",
            "collection_mode": "正式采集",
            "collection_mode_code": "formal",
            "assessment_phase": "课后考核",
            "session_id": "post_1",
            "created_at": "2026-05-31T10:40:00",
            "score": 85,
        },
    ]
    paired = build_participant_analysis_records(records)
    assert len(paired) == 1
    assert paired[0]["academy_scenario_id"] == "academy_anaphylaxis_rescue"
    assert paired[0]["all_three_stages_recorded"] == "是"
    assert paired[0]["formal_analysis_ready"] == "是"
    assert paired[0]["score_change_post_minus_baseline"] == 25.0


def test_missing_training_not_formal_analysis_ready() -> None:
    records = [
        {
            "participant_id": "P002",
            "collection_mode": "正式采集",
            "collection_mode_code": "formal",
            "assessment_phase": "基线评估",
            "session_id": "baseline_1",
            "created_at": "2026-05-27T10:00:00",
            "score": 70,
        },
        {
            "participant_id": "P002",
            "collection_mode": "正式采集",
            "collection_mode_code": "formal",
            "assessment_phase": "培训后考核",
            "session_id": "post_1",
            "created_at": "2026-05-27T11:00:00",
            "score": 90,
        },
    ]
    paired = build_participant_analysis_records(records)
    assert len(paired) == 1
    assert paired[0]["pre_post_pair_ready"] == "是"
    assert paired[0]["all_three_stages_recorded"] == "否"
    assert paired[0]["formal_analysis_ready"] == "否"
    quality = build_data_quality_records(records)
    assert any(item["assessment_phase"] == "模拟培训" for item in quality)


if __name__ == "__main__":
    tests = [
        test_standard_path_full_score,
        test_invalid_steroid_is_missing,
        test_epinephrine_underdose_subscore_policy,
        test_participant_pair_export,
        test_academy_scenario_pair_export,
        test_missing_training_not_formal_analysis_ready,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
