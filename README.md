# 儿科护理急救动态分支虚拟仿真训练平台｜V1.2.1 research-quality

本版本基于 **V1.1.4 评估阶段流程锁定版** 继续升级，用于支撑课题方向：

> 基于动态分支虚拟仿真平台的多院区儿科护士药物诱发过敏反应识别与初始处置能力现状及影响因素研究

## 一、V1.2.1 版本定位

V1.2.1 不再只是“训练网页”，而是面向课题、伦理、软著和论文分析的 **研究质控与分析版**。

本版合并了此前规划的三个方向：

1. **V1.1.5 数据质量增强**：阶段完成状态、重复作答识别、阶段顺序核查、数据有效性标记。
2. **V1.1.6 管理后台质控**：按院区、科室、参与者查看完成情况和异常数据。
3. **V1.2.1 研究分析字段**：自动导出识别能力、关键处置能力、用药安全和流程完整性指标。

## 二、保留的 V1.1.4 核心逻辑

系统继续根据评估阶段自动锁定运行流程：

| 评估阶段 | 自动运行模式 | 自动病例脚本 |
|---|---|---|
| 基线评估 | 考试模式 | 初始病例 |
| 模拟培训 | 训练模式 | 初始病例 |
| 培训后考核 | 考试模式 | 变体病例 Variant A |

受试者不能自行选择运行模式、病例脚本或随机种子。左侧仅显示本阶段任务、开始/重置按钮和阶段完成状态。

## 三、V1.2.1 新增数据质量字段

管理员导出的汇总 CSV 中新增：

| 字段 | 含义 |
|---|---|
| `record_validity` | 数据有效性标记：有效 / 需核查 |
| `validity_note` | 数据异常说明 |
| `is_repeated_attempt` | 是否同一参与者同一阶段重复作答 |
| `attempt_order` | 同一参与者同一阶段第几次记录 |
| `stage_sequence_status` | 阶段顺序是否合理 |
| `previous_completed_stages` | 当前记录之前已完成的阶段 |
| `missing_required_previous_stage` | 缺少的前序阶段 |

系统不会强制阻断受试者进入下一阶段，而是采用“提醒 + 标记”的方式，避免因网络中断、重新登录或组织流程差异导致现场无法继续。

## 四、V1.2.1 新增研究分析字段

汇总 CSV 中新增适合 SPSS/R 分析的能力维度指标，包括：

### 1. 识别能力

- `recognition_time_sec`
- `recognized_anaphylaxis`
- `stop_infusion_done`
- `call_help_done`

### 2. 关键处置能力

- `epinephrine_given`
- `epinephrine_time_sec`
- `epinephrine_dose_correct`
- `oxygen_given`
- `oxygen_time_sec`
- `monitoring_connected`
- `monitoring_time_sec`
- `bp_assessment_done`
- `fluid_resuscitation_given`

### 3. 用药安全

- `epinephrine_under_dose`
- `epinephrine_over_dose`
- `serious_medication_error`

### 4. 流程完整性

- `abc_assessment_done`
- `reassessment_done`
- `reassessment_count_analysis`
- `family_communication_done`
- `sbar_handoff_done`
- `critical_step_completion_count`
- `critical_step_completion_rate`

## 五、管理员后台新增质控概览

管理员后台新增“数据质控概览”，包括：

1. **按院区**：查看各院区基线评估、模拟培训、培训后考核记录数，三阶段完整完成率，需核查记录数。
2. **按科室**：查看各科室完成情况和异常数据。
3. **按参与者**：查看每个参与者三阶段完成情况、重复阶段和需核查记录数。

## 六、数据库兼容性说明

V1.2.1 **不要求重新创建 Supabase 表**。

为了避免破坏已经成功运行的 `training_records` 表，本版本新增内容主要写入：

- `full_report` JSON 字段；
- 管理员后台导出的 CSV；
- 本地 JSONL 备用记录。

因此原有 Supabase Secrets 可继续使用：

```toml
APP_ACCESS_CODE = "peds2026"
ADMIN_PASSWORD = "admin2026"

SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "..."
SUPABASE_TABLE = "training_records"
```

## 七、部署说明

将本文件夹内容上传至原 GitHub 仓库根目录，覆盖旧版文件：

- `streamlit_app.py`
- `requirements.txt`
- `peds_anaphylaxis_sim/`
- `.streamlit/`
- `docs/`
- `README.md`

提交后，Streamlit Cloud 会自动重新部署。Secrets 不需要重新配置，Supabase 表不需要重新创建。

## 八、上线后建议测试

1. 选择“基线评估”，确认自动进入考试模式 + 初始病例。
2. 选择“模拟培训”，确认自动进入训练模式 + 初始病例，并能看到阶段顺序提醒。
3. 选择“培训后考核”，确认自动进入考试模式 + Variant A。
4. 完成一次训练，确认 Supabase 写入成功。
5. 进入管理员后台，确认出现“数据质控概览”。
6. 导出汇总 CSV，确认出现 `record_validity`、`stage_sequence_status`、`recognition_time_sec`、`epinephrine_time_sec`、`critical_step_completion_rate` 等字段。


## V1.2.1 2025共识对齐版新增

- 病情进展按 I–IV 级动态展示，临床表现细化到皮肤黏膜、呼吸、胃肠、循环和意识改变。
- 儿童肌注肾上腺素按 0.01 mg/kg、单次最大 0.3 mg 进行剂量核对。
- 操作选项加入步骤规划限制，避免二线药替代一线药、未复评即重复给药、未确认循环状态即补液等不合规路径。
- 新增重复肌注肾上腺素、难治性路径升级至急诊/PICU/ICU、高级支持与后续观察安排等节点。
- 新增消化科选项，保留后续扩展院区/医院的结构。
