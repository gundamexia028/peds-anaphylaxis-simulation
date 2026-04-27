{
  "schema_version": 1,
  "scenario": {
    "id": "peds_ward_anaphylaxis_iv_initial",
    "title": "儿科药物诱发过敏反应动态分支仿真｜初始版",
    "language": "zh-CN",
    "version": "1.2.2-guided-flow-open-actions-2025-consensus",
    "source_note": "基于2025年《严重过敏反应诊断和临床管理专家共识》修订：临床表现按皮肤黏膜、呼吸/气道、胃肠、循环和意识系统随病情进展动态展示；操作按钮全部可选；标准流程仅在训练模式中作为内部引导与偏离提醒。",
    "mode_defaults": {
      "coach": true,
      "tick_seconds": 30
    },
    "script_role": "initial",
    "script_name": "initial",
    "display_name": "初始版",
    "scoring_basis": "2025中国严重过敏反应专家共识对齐版：儿童肌注肾上腺素剂量、病情进展、复评和升级处理纳入评分/记录；操作不再前台锁定，训练模式显示标准流程提醒，考试模式保持无提示。"
  },
  "patient": {
    "age_years": 3,
    "weight_kg": 15,
    "setting": "儿科普通病区（床旁）",
    "trigger": "静脉输注药物开始后约5-10分钟出现症状"
  },
  "diagnosis_criteria": {
    "criterion_1": "皮肤/黏膜症状 +（呼吸道症状 或 血压下降/器官功能不全 或 严重胃肠道症状）",
    "criterion_2": "暴露已知或可疑变应原后数分钟至数小时内出现：血压降低 或 支气管痉挛 或 喉部症状；可无典型皮肤黏膜症状",
    "hypotension_definition": {
      "infant_1m_to_1y_sbp_lt": 70,
      "age_1_to_10_sbp_lt_formula": "70 + 2*age_years",
      "age_11_to_17_sbp_lt": 90,
      "or_drop_from_baseline_pct": 30
    }
  },
  "grading": {
    "I": "皮肤/黏膜为主，生命体征稳定；无明显呼吸/循环受累",
    "II": "出现明显呼吸受累（喘鸣/喉鸣/SpO2下降等）和/或血压下降（早期）",
    "III": "重度呼吸受累或循环衰竭（严重低氧/明显低血压/意识改变等）",
    "IV": "心跳或呼吸骤停"
  },
  "baseline": {
    "time_zero_description": "儿科普通病区，患儿静脉输注药物后数分钟出现皮肤瘙痒/风团样皮疹、潮红，伴咳嗽、烦躁或诉喉部不适。请根据病情进展、生命体征和可获得信息进行处置。",
    "vitals": {
      "SpO2": 98,
      "HR": 125,
      "RR": 28,
      "SBP": 102,
      "DBP": 62,
      "Temp": 37.8
    },
    "symptoms": {
      "rash": 1,
      "angioedema": 0,
      "wheeze": 0,
      "stridor": 0,
      "gi": 0,
      "consciousness": 0,
      "cough": 1,
      "throat_tightness": 0,
      "vomiting": 0,
      "poor_perfusion": 0,
      "cyanosis": 0
    },
    "flags": {
      "infusion_running": true,
      "stopped_infusion": false,
      "help_called": false,
      "oxygen_on": false,
      "positioned": false,
      "monitor_on": false,
      "bp_checked": false,
      "iv_confirmed": true,
      "epi_im_given": false,
      "epi_im_doses": 0,
      "fluid_bolus_given": false,
      "bronchodilator_neb": false,
      "nebulized_epi": false,
      "reassess_count": 0,
      "family_communication": false,
      "sbar_handoff": false,
      "dangerous_output_event": 0,
      "epi_effect_ticks": 0,
      "fluid_effect_ticks": 0,
      "neb_epi_effect_ticks": 0,
      "bronchodilator_effect_ticks": 0,
      "iv_access": true,
      "bp_ordered": false,
      "airway_compromise": false,
      "epi_dose_checked": false,
      "epi_underdose_event": false,
      "epi_overdose_event": false,
      "tachycardia_heart_failure": false,
      "epi_im_attempts": 0,
      "epi_last_dose_mg": 0.0,
      "epi_target_dose_mg": 0.0,
      "dead": false,
      "abc_assessed": false,
      "airway_opened": false,
      "steroid_given": false,
      "repeat_epi_given": false,
      "advanced_support_called": false,
      "observation_plan": false,
      "epi_excess_dose_event": false,
      "reassessed_after_epi": false
    }
  },
  "thresholds": {
    "SpO2_low": 94,
    "SpO2_critical": 90,
    "SpO2_arrest": 70,
    "hypotension_sbp_drop_pct": 30,
    "grade_III_sbp_lt_age_threshold": true
  },
  "actions": [
    {
      "id": "stop_infusion",
      "label": "停用可疑药物/停止可疑输液（保留抢救通路）",
      "category": "critical",
      "score": {
        "points": 2,
        "time_window_seconds": 60
      },
      "effects": {
        "set_flags": {
          "stopped_infusion": true,
          "infusion_running": false,
          "iv_access": true,
          "iv_confirmed": true
        }
      }
    },
    {
      "id": "call_help",
      "label": "呼救并启动院内抢救支援",
      "category": "critical",
      "score": {
        "points": 2,
        "time_window_seconds": 60
      },
      "effects": {
        "set_flags": {
          "help_called": true
        }
      }
    },
    {
      "id": "abc_assess",
      "label": "快速ABC评估（气道/呼吸/循环）",
      "category": "assessment",
      "score": {
        "points": 1,
        "time_window_seconds": 120
      },
      "effects": {
        "set_flags": {
          "abc_assessed": true
        }
      }
    },
    {
      "id": "high_flow_oxygen",
      "label": "保持气道通畅并给氧",
      "category": "critical",
      "availability": {
        "when": "flags.help_called or flags.abc_assessed",
        "reason": "应先呼救或完成ABC快速判断后立即给氧。"
      },
      "score": {
        "points": 2,
        "time_window_seconds": 150
      },
      "effects": {
        "set_flags": {
          "oxygen_on": true,
          "airway_opened": true
        },
        "delta_vitals": {
          "SpO2": 4
        }
      }
    },
    {
      "id": "shock_position",
      "label": "平卧/抬高下肢，意识障碍头偏向一侧",
      "category": "support",
      "availability": {
        "when": "flags.stopped_infusion or flags.help_called",
        "reason": "体位管理应在去除可疑诱因或启动支援后尽早完成。"
      },
      "score": {
        "points": 1,
        "time_window_seconds": 240
      },
      "effects": {
        "set_flags": {
          "positioned": true
        },
        "delta_vitals": {
          "SBP": 4,
          "DBP": 2
        }
      }
    },
    {
      "id": "connect_monitor",
      "label": "连接心电/SpO₂监护",
      "category": "critical",
      "availability": {
        "when": "flags.help_called",
        "reason": "启动支援后应连接连续监护，便于判断病情进展。"
      },
      "score": {
        "points": 1,
        "time_window_seconds": 240
      },
      "effects": {
        "set_flags": {
          "monitor_on": true
        }
      }
    },
    {
      "id": "check_bp",
      "label": "测血压并评估末梢灌注",
      "category": "critical",
      "availability": {
        "when": "flags.monitor_on or flags.help_called",
        "reason": "血压/灌注评估应与监护或抢救支援同步进行。"
      },
      "score": {
        "points": 1,
        "time_window_seconds": 300
      },
      "effects": {
        "set_flags": {
          "bp_ordered": true
        }
      }
    },
    {
      "id": "im_epinephrine",
      "label": "肌注肾上腺素（需输入剂量）",
      "category": "critical_med",
      "availability": {
        "when": "flags.stopped_infusion and flags.help_called and (grade >= 2 or symptoms.wheeze >= 1 or symptoms.stridor >= 1 or vitals.SBP < age_sbp_threshold + 15)",
        "reason": "符合或高度疑似严重过敏反应后，应在停用可疑药物并呼救后尽早肌注肾上腺素。"
      },
      "score": {
        "points": 4,
        "time_window_seconds": 300
      },
      "effects": {
        "set_flags": {
          "epi_im_given": true,
          "epi_effect_ticks": 4
        },
        "counter_inc": {
          "epi_im_doses": 1
        },
        "delta_vitals": {
          "SBP": 10,
          "DBP": 5,
          "HR": -6,
          "SpO2": 3,
          "RR": -3
        },
        "delta_symptoms": {
          "wheeze": -1,
          "stridor": -1,
          "rash": -1,
          "angioedema": -1,
          "throat_tightness": -1,
          "consciousness": -1,
          "poor_perfusion": -1
        }
      }
    },
    {
      "id": "confirm_iv_access",
      "label": "确认/建立静脉通路",
      "category": "support",
      "availability": {
        "when": "flags.help_called",
        "reason": "启动抢救后应确认或建立静脉通路，用于补液和后续抢救。"
      },
      "score": {
        "points": 1,
        "time_window_seconds": 300
      },
      "effects": {
        "set_flags": {
          "iv_access": true,
          "iv_confirmed": true
        }
      }
    },
    {
      "id": "fluid_bolus",
      "label": "晶体液快速补液10–20 ml/kg",
      "category": "support_med",
      "availability": {
        "when": "flags.iv_access and flags.bp_checked and flags.epi_im_given",
        "reason": "确认静脉通路和血压/灌注后，可根据循环状态准备或实施晶体液快速补液。"
      },
      "score": {
        "points": 1,
        "time_window_seconds": 420,
        "score_when": "flags.iv_access and flags.bp_checked"
      },
      "effects": {
        "set_flags": {
          "fluid_bolus_given": true,
          "fluid_effect_ticks": 4
        },
        "delta_vitals": {
          "SBP": 10,
          "DBP": 5,
          "HR": -3
        },
        "delta_symptoms": {
          "poor_perfusion": -1
        }
      }
    },
    {
      "id": "bronchodilator",
      "label": "喘息/支气管痉挛时雾化支气管扩张剂",
      "category": "support_med",
      "availability": {
        "when": "flags.epi_im_given",
        "reason": "雾化支气管扩张剂为辅助处理，应在肌注肾上腺素后根据喘息/支气管痉挛情况使用。"
      },
      "score": {
        "points": 1,
        "time_window_seconds": 480
      },
      "effects": {
        "set_flags": {
          "bronchodilator_neb": true,
          "bronchodilator_effect_ticks": 2
        },
        "delta_symptoms": {
          "wheeze": -1
        },
        "delta_vitals": {
          "SpO2": 1
        }
      }
    },
    {
      "id": "nebulized_epinephrine",
      "label": "喉鸣/上气道水肿时雾化肾上腺素（辅助）",
      "category": "support_med_conditional",
      "availability": {
        "when": "flags.epi_im_given and symptoms.stridor >= 1",
        "reason": "雾化肾上腺素仅作为上气道受累辅助处理，不能替代肌注肾上腺素。"
      },
      "score": {
        "points": 0,
        "time_window_seconds": 99999
      },
      "effects": {
        "set_flags": {
          "nebulized_epi": true,
          "neb_epi_effect_ticks": 2
        },
        "delta_symptoms": {
          "stridor": -1,
          "throat_tightness": -1
        },
        "delta_vitals": {
          "SpO2": 1
        }
      }
    },
    {
      "id": "antihistamine_iv",
      "label": "抗组胺药（辅助，不能替代肾上腺素）",
      "category": "non_firstline",
      "availability": {
        "when": "flags.epi_im_given",
        "reason": "抗组胺药为辅助治疗，不能先于或替代肌注肾上腺素。"
      },
      "score": {
        "points": 0,
        "time_window_seconds": 99999,
        "penalty_if_before": "epi_im_given",
        "penalty_points": 2
      },
      "effects": {
        "delta_symptoms": {
          "rash": -1
        }
      }
    },
    {
      "id": "steroid",
      "label": "糖皮质激素（辅助，不能替代肾上腺素）",
      "category": "non_firstline",
      "availability": {
        "when": "flags.epi_im_given",
        "reason": "糖皮质激素为二线/辅助治疗，不能替代首选肌注肾上腺素。"
      },
      "score": {
        "points": 0,
        "time_window_seconds": 99999,
        "penalty_if_before": "epi_im_given",
        "penalty_points": 2
      },
      "effects": {
        "set_flags": {
          "steroid_given": true
        }
      }
    },
    {
      "id": "reassess",
      "label": "5–15 min复评并记录",
      "category": "process",
      "availability": {
        "when": "flags.epi_im_given or t >= 180",
        "reason": "复评应在关键处置后进行，重点记录呼吸、循环、意识和皮肤黏膜变化。"
      },
      "score": {
        "points": 1,
        "time_window_seconds": 600,
        "score_when": "flags.epi_im_given or t >= 180"
      },
      "effects": {
        "counter_inc": {
          "reassess_count": 1
        },
        "set_flags": {
          "reassessed_after_epi": true
        }
      }
    },
    {
      "id": "repeat_im_epinephrine",
      "label": "复评仍未缓解：再次肌注肾上腺素",
      "category": "critical_med_repeat",
      "availability": {
        "when": "flags.epi_im_given and flags.reassess_count >= 1 and (t - action_first_time.get('im_epinephrine', 999999)) >= 300 and (grade >= 2 or symptoms.wheeze >= 1 or symptoms.stridor >= 1 or vitals.SBP < age_sbp_threshold)",
        "reason": "首次肌注后5–15 min复评仍未缓解时，才考虑重复肌注肾上腺素。"
      },
      "score": {
        "points": 0,
        "time_window_seconds": 99999
      },
      "effects": {
        "set_flags": {
          "repeat_epi_given": true,
          "epi_effect_ticks": 3
        },
        "counter_inc": {
          "epi_im_doses": 1
        },
        "delta_vitals": {
          "SBP": 8,
          "DBP": 4,
          "HR": -5,
          "SpO2": 2,
          "RR": -2
        },
        "delta_symptoms": {
          "wheeze": -1,
          "stridor": -1,
          "consciousness": -1,
          "poor_perfusion": -1
        }
      }
    },
    {
      "id": "call_icu_team",
      "label": "两次肾上腺素/补液仍无缓解：联系急诊/PICU/ICU",
      "category": "escalation",
      "availability": {
        "when": "flags.epi_im_doses >= 2 and (flags.fluid_bolus_given or grade >= 3)",
        "reason": "两次肾上腺素及补液后仍无缓解，应升级至高级生命支持团队。"
      },
      "score": {
        "points": 0,
        "time_window_seconds": 99999
      },
      "effects": {
        "set_flags": {
          "advanced_support_called": true
        }
      }
    },
    {
      "id": "family_explain",
      "label": "简短告知家属当前抢救与转运安排",
      "category": "crm",
      "availability": {
        "when": "flags.help_called",
        "reason": "家属沟通应在抢救团队启动后简短进行，避免影响关键抢救。"
      },
      "score": {
        "points": 1,
        "time_window_seconds": 600,
        "score_when": "flags.help_called and flags.epi_im_given"
      },
      "effects": {
        "set_flags": {
          "family_communication": true
        }
      }
    },
    {
      "id": "sbar_handoff",
      "label": "SBAR交接与后续观察安排",
      "category": "crm",
      "availability": {
        "when": "flags.reassess_count >= 2 and grade <= 2",
        "reason": "完成连续复评并初步稳定后，再进行SBAR交接和观察安排。"
      },
      "score": {
        "points": 1,
        "time_window_seconds": 99999,
        "score_when": "flags.reassess_count >= 2 and grade <= 2"
      },
      "effects": {
        "set_flags": {
          "sbar_handoff": true,
          "observation_plan": true
        }
      }
    },
    {
      "id": "continue_infusion",
      "label": "继续输入可疑药物",
      "category": "distractor",
      "effects": {
        "set_flags": {
          "stopped_infusion": false,
          "infusion_running": true
        },
        "delta_vitals": {
          "SpO2": -4,
          "SBP": -10,
          "DBP": -5,
          "HR": 8,
          "RR": 2
        },
        "delta_symptoms": {
          "wheeze": 1,
          "stridor": 1,
          "poor_perfusion": 1
        }
      },
      "score": {
        "points": 0,
        "penalty_points_always": 3
      }
    },
    {
      "id": "remove_iv",
      "label": "拔除静脉通路",
      "category": "distractor",
      "effects": {
        "set_flags": {
          "iv_access": false,
          "iv_confirmed": false
        },
        "delta_vitals": {
          "HR": 4
        },
        "delta_symptoms": {
          "poor_perfusion": 1
        }
      },
      "score": {
        "points": 0,
        "penalty_points_always": 2
      }
    },
    {
      "id": "sedation",
      "label": "给予镇静药",
      "category": "distractor",
      "effects": {
        "delta_vitals": {
          "RR": -2,
          "SpO2": -3,
          "SBP": -4
        },
        "delta_symptoms": {
          "consciousness": 1
        }
      },
      "score": {
        "points": 0,
        "penalty_points_always": 2
      }
    }
  ],
  "dynamics": {
    "tick_seconds": 30,
    "rules": [
      {
        "name": "bp_result_available",
        "when": "flags.bp_ordered and (not flags.bp_checked) and t >= 30",
        "effects": {
          "set_flags": {
            "bp_checked": true
          },
          "delta_symptoms": {}
        }
      },
      {
        "name": "ongoing_exposure_worsens_fast",
        "when": "flags.infusion_running and t >= 30",
        "effects": {
          "delta_symptoms": {
            "rash": 1,
            "wheeze": 1,
            "cough": 1,
            "throat_tightness": 1
          },
          "delta_vitals": {
            "SpO2": -4,
            "HR": 10,
            "SBP": -10,
            "DBP": -4,
            "RR": 2
          }
        }
      },
      {
        "name": "mediator_cascade_after_stop",
        "when": "flags.stopped_infusion and (not flags.epi_im_given) and t >= 30 and t <= 180",
        "effects": {
          "delta_symptoms": {
            "wheeze": 1,
            "rash": 0,
            "cough": 1
          },
          "delta_vitals": {
            "SpO2": -2,
            "HR": 6,
            "SBP": -6,
            "DBP": -3,
            "RR": 2
          }
        }
      },
      {
        "name": "airway_worsens_without_oxygen",
        "when": "(symptoms.wheeze >= 1 or symptoms.stridor >= 1) and (not flags.oxygen_on) and t >= 60",
        "effects": {
          "delta_vitals": {
            "SpO2": -4,
            "RR": 3
          },
          "delta_symptoms": {
            "stridor": 1,
            "throat_tightness": 1
          }
        }
      },
      {
        "name": "shock_worsens_without_epi",
        "when": "(not flags.epi_im_given) and t >= 90 and (symptoms.wheeze >= 1 or symptoms.stridor >= 1 or vitals.SBP < (age_sbp_threshold + 15) or vitals.SpO2 < 94)",
        "effects": {
          "delta_vitals": {
            "SBP": -12,
            "DBP": -6,
            "HR": 8,
            "SpO2": -1,
            "RR": 1
          },
          "delta_symptoms": {
            "consciousness": 1,
            "poor_perfusion": 1
          }
        }
      },
      {
        "name": "decompensation_if_severe_no_support",
        "when": "(not flags.epi_im_given) and (not flags.oxygen_on) and t >= 150 and (vitals.SpO2 < 88 or vitals.SBP < age_sbp_threshold)",
        "effects": {
          "delta_vitals": {
            "SpO2": -6,
            "SBP": -12,
            "DBP": -6,
            "HR": 8,
            "RR": 4
          },
          "delta_symptoms": {
            "consciousness": 1,
            "cyanosis": 1,
            "poor_perfusion": 1
          }
        }
      },
      {
        "name": "oxygen_support_improves_spo2",
        "when": "flags.oxygen_on and vitals.SpO2 < 99",
        "effects": {
          "delta_vitals": {
            "SpO2": 2
          },
          "delta_symptoms": {}
        }
      },
      {
        "name": "epi_primary_effect_ticks",
        "when": "flags.epi_effect_ticks > 0",
        "effects": {
          "delta_vitals": {
            "SBP": 7,
            "DBP": 4,
            "SpO2": 4,
            "HR": -8,
            "RR": -4
          },
          "delta_symptoms": {
            "wheeze": -1,
            "stridor": -1,
            "rash": -1,
            "angioedema": -1,
            "consciousness": -1,
            "cough": -1,
            "throat_tightness": -1,
            "poor_perfusion": -1,
            "cyanosis": -1
          },
          "counter_inc": {
            "epi_effect_ticks": -1
          }
        }
      },
      {
        "name": "fluid_support_ticks",
        "when": "flags.fluid_effect_ticks > 0",
        "effects": {
          "delta_vitals": {
            "SBP": 5,
            "DBP": 3,
            "HR": -2
          },
          "counter_inc": {
            "fluid_effect_ticks": -1
          },
          "delta_symptoms": {}
        }
      },
      {
        "name": "nebulized_epi_effect_ticks",
        "when": "flags.neb_epi_effect_ticks > 0",
        "effects": {
          "delta_symptoms": {
            "stridor": -1
          },
          "delta_vitals": {
            "SpO2": 1
          },
          "counter_inc": {
            "neb_epi_effect_ticks": -1
          }
        }
      },
      {
        "name": "bronchodilator_effect_ticks",
        "when": "flags.bronchodilator_effect_ticks > 0",
        "effects": {
          "delta_symptoms": {
            "wheeze": -1
          },
          "delta_vitals": {
            "SpO2": 1
          },
          "counter_inc": {
            "bronchodilator_effect_ticks": -1
          }
        }
      },
      {
        "name": "airway_edema_progression_90_120",
        "when": "(not flags.epi_im_given) and t >= 90 and t < 120",
        "effects": {
          "set_flags": {
            "airway_compromise": true
          },
          "delta_symptoms": {
            "wheeze": 1,
            "cough": 1,
            "throat_tightness": 1
          },
          "delta_vitals": {
            "SpO2": -3,
            "RR": 2,
            "HR": 6,
            "SBP": -4,
            "DBP": -2
          }
        }
      },
      {
        "name": "airway_edema_progression_120_150",
        "when": "(not flags.epi_im_given) and t >= 120 and t < 150",
        "effects": {
          "set_flags": {
            "airway_compromise": true
          },
          "delta_symptoms": {
            "stridor": 1,
            "angioedema": 1,
            "throat_tightness": 1
          },
          "delta_vitals": {
            "SpO2": -6,
            "RR": 3,
            "HR": 8,
            "SBP": -8,
            "DBP": -4
          }
        }
      },
      {
        "name": "airway_edema_progression_150_180",
        "when": "(not flags.epi_im_given) and t >= 150 and t < 180",
        "effects": {
          "set_flags": {
            "airway_compromise": true
          },
          "delta_symptoms": {
            "consciousness": 1,
            "stridor": 1,
            "angioedema": 1,
            "cyanosis": 1,
            "poor_perfusion": 1
          },
          "delta_vitals": {
            "SpO2": -8,
            "RR": 2,
            "HR": 10,
            "SBP": -10,
            "DBP": -5
          }
        }
      },
      {
        "name": "oxygen_limited_by_airway_90_180",
        "when": "flags.oxygen_on and flags.airway_compromise and t >= 90 and t < 180",
        "effects": {
          "delta_vitals": {
            "SpO2": -1
          },
          "delta_symptoms": {}
        }
      },
      {
        "name": "asphyxia_death_after_300s_no_epi",
        "when": "(not flags.epi_im_given) and t >= 300",
        "effects": {
          "set_flags": {
            "dead": true
          },
          "set_grade": 4,
          "set_vitals": {
            "SpO2": 50,
            "HR": 40,
            "RR": 6,
            "SBP": 40,
            "DBP": 20
          },
          "delta_symptoms": {
            "consciousness": 2
          }
        }
      },
      {
        "name": "stabilization_after_control",
        "when": "flags.epi_im_given and flags.oxygen_on and flags.stopped_infusion and t >= 180 and (vitals.SpO2 < 99 or vitals.SBP < 95 or symptoms.rash >= 1 or symptoms.wheeze >= 1 or symptoms.stridor >= 1)",
        "effects": {
          "delta_vitals": {
            "SpO2": 2,
            "SBP": 2,
            "DBP": 1,
            "HR": -3,
            "RR": -2
          },
          "delta_symptoms": {
            "rash": -1,
            "wheeze": -1,
            "stridor": -1,
            "consciousness": -1,
            "cough": -1,
            "throat_tightness": -1,
            "poor_perfusion": -1,
            "cyanosis": -1
          }
        }
      },
      {
        "name": "fluid_requires_iv",
        "when": "(not flags.iv_access) and flags.fluid_bolus_given and t >= 30",
        "effects": {
          "delta_vitals": {
            "SBP": -4,
            "DBP": -2
          },
          "delta_symptoms": {}
        }
      }
    ]
  },
  "end_conditions": {
    "success_when": "not flags.dead and flags.epi_im_given and flags.stopped_infusion and flags.oxygen_on and flags.help_called and flags.monitor_on and flags.bp_checked and flags.reassess_count >= 2 and flags.family_communication and flags.sbar_handoff and grade <= 1 and vitals.SpO2 >= 95 and vitals.SBP >= age_sbp_threshold and t >= 300",
    "failure_when": "(flags.dead) or flags.epi_overdose_event",
    "max_time_seconds": 600
  },
  "reporting": {
    "observe_recommendation": {
      "resp_distress_hours": "至少6–8小时",
      "circulatory_instability_hours": "至少12–24小时"
    }
  },
  "training": {
    "min_time_seconds_for_success": 300,
    "min_reassess_count_recommended": 2,
    "guided_prompts": [
      {
        "text": "步骤1：停用可疑药物/停止可疑输液，同时保留抢救通路。",
        "reason": "立即去除可疑过敏原，同时避免误拔静脉通路影响补液和抢救用药。",
        "done_when": "flags.stopped_infusion and flags.iv_access"
      },
      {
        "text": "步骤2：呼救并启动院内抢救支援。",
        "reason": "严重过敏反应进展快，需要医生、抢救车及团队协作同步到位。",
        "done_when": "flags.help_called"
      },
      {
        "text": "步骤3：快速ABC评估。",
        "reason": "判断气道、呼吸和循环是否受累，确认是否进入严重过敏反应处置路径。",
        "done_when": "flags.abc_assessed or 'abc_assess' in action_first_time"
      },
      {
        "text": "步骤4：保持气道通畅并给氧。",
        "reason": "气道/呼吸受累可迅速恶化，应尽早给氧并持续观察SpO₂和呼吸表现。",
        "done_when": "flags.oxygen_on"
      },
      {
        "text": "步骤5：体位管理。",
        "reason": "平卧、抬高下肢有助于改善回心血量；意识障碍时头偏向一侧防误吸。",
        "done_when": "flags.positioned"
      },
      {
        "text": "步骤6：连接监护并测血压/灌注。",
        "reason": "心率、SpO₂、血压和末梢灌注是判断进展、补液和复评的依据。",
        "done_when": "flags.monitor_on and flags.bp_checked"
      },
      {
        "text": "步骤7：肌注肾上腺素。",
        "reason": "诊断或高度疑似严重过敏反应时，肌注肾上腺素是一线关键处置，不能被抗组胺药或激素替代。",
        "done_when": "flags.epi_im_given"
      },
      {
        "text": "步骤8：确认/建立静脉通路并根据循环状态补液。",
        "reason": "存在低血压、末梢灌注差或休克表现时，应尽早进行晶体液容量复苏。",
        "done_when": "flags.iv_access and (flags.fluid_bolus_given or vitals.SBP >= age_sbp_threshold)"
      },
      {
        "text": "步骤9：按表现给予辅助治疗。",
        "reason": "喘息时可雾化支气管扩张剂；喉鸣/上气道水肿时可考虑雾化肾上腺素，但均不能替代肌注肾上腺素。",
        "done_when": "flags.bronchodilator_neb or flags.nebulized_epi or (symptoms.wheeze == 0 and symptoms.stridor == 0)"
      },
      {
        "text": "步骤10：5–15 min复评并记录。",
        "reason": "复评呼吸、循环、意识和皮肤黏膜表现；若仍未缓解，需要考虑重复肌注肾上腺素。",
        "done_when": "flags.reassess_count >= 2"
      },
      {
        "text": "步骤11：必要时升级处理。",
        "reason": "两次肾上腺素及补液后仍无缓解，应呼叫急诊/PICU/ICU团队提供高级生命支持。",
        "done_when": "flags.advanced_support_called or flags.epi_im_doses < 2 or grade <= 2"
      },
      {
        "text": "步骤12：家属沟通、SBAR交接与后续观察安排。",
        "reason": "稳定后需交代诱因、时间轴、给药剂量/次数、生命体征变化、观察与转运重点。",
        "done_when": "flags.family_communication and flags.sbar_handoff"
      }
    ]
  },
  "scoring_notes": {
    "profile": "v1.2.2_guided_flow_open_actions_2025_consensus",
    "total_score": 20,
    "principle": "救命核心操作优先：去除可疑诱因、呼救、ABC、给氧、监护/血压、早期肌注肾上腺素、补液、复评与交接。辅助治疗不能替代肌注肾上腺素。",
    "dose_rule": "本系统面向2–11岁儿童模拟病例，肌注肾上腺素按0.01 mg/kg计算，单次最大0.3 mg；低于目标剂量判定为无效，高于目标剂量判定为剂量不准确，超过0.3 mg判定为严重用药安全事件。",
    "planning_rule": "所有操作按钮均保持可选，避免因前台锁定影响受试者真实操作路径；训练模式下系统依据2025共识内置标准流程，显示当前推荐步骤及偏离提醒；考试模式不显示流程提示，仅记录操作路径与评分结果。"
  },
  "clinical_progression": {
    "1": {
      "stage": "I级｜早期皮肤黏膜/前驱期",
      "manifestations": "皮肤瘙痒、潮红、风团样皮疹，可伴手足/头皮瘙痒、烦躁或轻度咳嗽；生命体征可暂时稳定。"
    },
    "2": {
      "stage": "II级｜呼吸、胃肠或早期循环受累期",
      "manifestations": "咳嗽、胸闷、喘息、喉部发紧/声音改变，或腹痛、恶心、呕吐；可出现SpO₂下降或血压较基线下降。"
    },
    "3": {
      "stage": "III级｜严重呼吸受累/循环衰竭期",
      "manifestations": "喉鸣、发绀、明显低氧、低血压、末梢灌注差、嗜睡或反应差，提示休克或重要器官灌注不足。"
    },
    "4": {
      "stage": "IV级｜心跳或呼吸骤停期",
      "manifestations": "呼吸骤停或心跳骤停，意识丧失，需立即就地心肺复苏并启动高级生命支持。"
    }
  },
  "clinical_manifestation_display": {
    "principle": "当前临床表现不再仅显示固定标签，而是根据症状、生命体征、监护/血压可见性和治疗反应，按皮肤黏膜、呼吸/气道、胃肠、循环、神经/意识五个系统动态生成。",
    "basis": "2025严重过敏反应共识关于临床表现和病程进展的描述。"
  }
}