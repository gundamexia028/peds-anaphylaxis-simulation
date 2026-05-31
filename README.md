# 护理动态分支虚拟仿真教学与培训系统｜V1.3.3

V1.3.3 基于 **V1.3.2 学院过敏性休克抢救教学聚焦版** 修正学院模式结构：学院模式不再被写死为单一模块，而是恢复为“学院情景库”框架；当前情景库中仅开放 **严重过敏反应/过敏性休克抢救** 这一项。

## 一、版本定位

- **临床模式**：保留原系统逻辑，用于临床护士、低年资护士及科室培训对象的严重过敏反应识别与处置训练。
- **学院模式**：面向高职/大专、本科、实习前及见习护生。进入学院模式后先选择教学情景；当前仅开放“严重过敏反应/过敏性休克抢救”情景，后续可在同一框架下增加输液反应、低血糖、跌倒/坠床、气道梗阻等其他情景。

## 二、V1.3.3 主要更新

1. 输入访问码后仍先选择：临床模式 / 学院模式。
2. 选择学院模式后，新增“学院模式｜护理基础能力情景库”选择页。
3. 当前情景库仅开放一个情景：`academy_anaphylaxis_rescue`，显示名称为“严重过敏反应/过敏性休克抢救”。
4. 学院模式登记页不再写死“过敏性休克模块”，而是显示当前已选情景、情景类别、适用课程与难度层级。
5. 学院数据新增情景字段：
   - `academy_scenario_id`
   - `academy_scenario_name`
   - `academy_scenario_category`
   - `academy_course_type`
   - `academy_difficulty`
6. 一人一行配对分析按 `system_mode + academy_scenario_id + participant_id + collection_mode` 分组，为后续多情景扩展预留统计结构。
7. 临床模式、临床病例、临床评分、V1.2.11正式采集质控逻辑均不改变。
8. 学院模式当前仍使用两份病例脚本：
   - `peds_ward_allergy_academy_initial.json`
   - `peds_ward_allergy_academy_variant.json`

## 三、当前流程

```text
输入访问码
↓
选择模式
├── 临床模式
│   └── 原临床培训/考核流程不变
└── 学院模式
    ↓
    学院情景库
    └── 严重过敏反应/过敏性休克抢救（当前唯一开放）
        ↓
        在校护生信息登记
        ↓
        课前测评 / 模拟训练 / 课后考核
```

## 四、运行方式

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

默认访问码：

```text
peds2026
```

## 五、文件结构

```text
.streamlit/
docs/
  V1.2.11_research_collection_locked_notes.md
  V1.3.1_dual_mode_qc_update.md
  V1.3.2_academy_anaphylaxis_rescue_update.md
  V1.3.3_academy_scenario_library_update.md
peds_anaphylaxis_sim/
  engine.py
  scenarios/
    peds_ward_anaphylaxis_iv_initial.json
    peds_ward_anaphylaxis_iv_variantA.json
    peds_ward_allergy_academy_initial.json
    peds_ward_allergy_academy_variant.json
streamlit_app.py
requirements.txt
README.md
tests/
```

## 六、使用提醒

- 临床模式用于临床护士培训/考核，不建议让在校护生直接使用该模式。
- 学院模式采用“情景库”结构，但当前只开放过敏性休克抢救情景，不急于扩展其他场景。
- 学院模式不用于评价护生独立完成完整临床抢救的能力，而是评价其识别、停药、呼救、给氧监测、抢救配合、复评、沟通与汇报能力。
- 两类数据通过 `system_mode` 字段区分；学院模式内部通过 `academy_scenario_id` 区分不同教学情景。

## 七、声明

本系统仅用于护理教学、培训、科研数据采集及成果转化验证，不用于真实临床诊疗决策。

## V1.3.5 更新摘要

V1.3.5 在 V1.3.3 学院情景库框架基础上，新增推广版单位权限后台、学院模式课后SUS与教学体验问卷、学院测评/考核阶段中性按钮标签、临床医院全称字段和学习阶段简化。临床基础引擎与临床模式评分逻辑保持不变。

详见：`docs/V1.3.5_promotion_admin_academy_flow_update.md`


## V1.3.5 更新说明（基于 V1.3.4 继续叠加）

本版本未新开学院模式版本线，而是在 V1.3.4 推广版权限与学院流程增强版基础上继续叠加。

主要变更：

1. 临床模式保持不动，继续沿用原临床护士严重过敏反应动态分支处置引擎。
2. 学院模式病例脚本升级为护生能力评价逻辑：不考独立抢救，重点考识别、呼救、初步处置、抢救配合、复评和SBAR汇报。
3. 学院初始病例固定为5岁男童静脉用药后出现皮疹、咳嗽、喘息和血压下降。
4. 学院课后变体病例固定为7岁女童静脉用药后先出现咳嗽、胸闷、声音嘶哑，随后出现口唇肿胀和皮疹。
5. 学院评分结构调整为100分：识别15分、抢救启动与呼救20分、ABC支持与循环监测25分、肾上腺素认知与抢救配合15分、病情复评10分、沟通与SBAR汇报15分。
6. 新增教学性错误分支：继续观察不暂停输入、直接拔除静脉通路、先询问病史、让家属去找人、只准备糖皮质激素/抗组胺药、护生独立注射急救药物、只旁观等待。
7. 新增风险标签：延迟识别、延迟去除可疑诱因、呼救方式不当、急救药物优先级错误、护生身份边界风险、用药安全风险、抢救配合不足、复评不足、SBAR不完整等。
8. 学院病例固定年龄体重，便于教师内容效度审核和预试运行；临床病例仍保留原随机年龄体重规则。

运行方式不变：

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```
