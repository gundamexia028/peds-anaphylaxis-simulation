# 儿科病区过敏性休克（输液诱发）动态模拟引擎（培训版 v1.1.2）

> 仅用于培训与科研可行性验证，不可用于临床决策。

## 你提出的三项改进已落实
1. **所有操作仅保留“名称”**：不含“立即/按流程/必要时/提示”等引导性词语。
2. **“肌注肾上腺素”操作去除“按标准药物卡”字样**。
3. **补液/雾化肾上腺素/雾化支气管扩张剂**等操作不再写“若…则…并发症…”，并发症相关内容已前置到情景“临床表现演变”中，由受训者根据表现自行判断。

## v1.1.2 额外培训增强
- 成功结局需满足最短训练时长：**300s**（防止 1–2 分钟就退出导致“看不到演变”）。
- 报告新增“过程性安全缺陷（培训评估）”：未呼救/未给氧/未监护/未测血压/复评不足等会被单独列出。

## 运行
### 教练模式
python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training.json --mode coach

### 考试模式
python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training.json --mode exam

报告输出在 runs/：
- *_report.md
- *_report.json

## 快速演变参数（v1.1.2）
- 未及时处理时：SpO₂、血压在 1–3 分钟内可出现明显下降（符合严重过敏反应快速去代偿特点）。
- 处理后：生命体征改善幅度更明显，但避免不合理“过冲”。


## 建议的20人研究流程（全科护士｜Pre–Train–Post）
- Pre-test（考试）：使用主脚本
- Training（训练）：教练模式
- Post-test（考试）：使用“变体A脚本”（减少记忆效应）

### 命令示例（以P01为例）
Pre-test：
python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training.json --mode exam --out runs/P01_pre

Training：
python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training.json --mode coach --out runs/P01_train

Post-test（变体A）：
python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training_variantA.json --mode exam --out runs/P01_post


## v1.1.4 关键修正（对应你反馈的“看起来流程/结果不对”）
- **考试模式禁止提前退出**：避免在 300s/510s 手动结束导致“情景未演变完全、但报告已生成”的误读。
- **加强病情进展逻辑**：新增“停止输液后仍可能继续进展”的介质瀑布规则（0–3min），未肌注肾上腺素时更易进入低氧/循环不稳。
- **成功结局更严格**：必须完成关键链条（停药、呼救、给氧、监护、测压、肾上腺素、复评≥2）且稳定到 ≥300s 才会自动结束。

## 重要执行口径（研究用）
- Pre-test 与 Post-test：**不要手动结束**，让系统自动结束并生成报告。


## v1.2 你提出的5项改进已实现
1) **题干不出现并发症/走向**：题干仅描述“当前表现”；后续变化只通过生命体征与症状逐步呈现。
2) **考试模式选项顺序随机**：同一场景答案一致，但每次考试选项序号会不同；报告中记录 seed 与 action_order 便于追溯。
3) **增加干扰项**：加入若干可能加重病情/影响处置的选项（带惩罚与负向效应）。
4) **生命体征分级呈现**：初始仅显示体温；连接监护后才显示 SpO₂/HR/RR；测量血压/灌注后“下一次表现”才显示 BP。
5) **90s后未肌注肾上腺素**：开始出现进行性气道受累表现与SpO₂进行性下降（即使给氧也可下降），直到完成关键处置并复评稳定。

### 运行（建议）
Pre-test / Post-test（考试）：
python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training.json --mode exam --out runs/P01_pre

如需固定选项顺序用于复测，可加 --seed：
python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training.json --mode exam --seed 123 --out runs/P01_pre

## v1.2.1 热修复
- 修复 Windows 运行时出现的 `SyntaxError: unterminated f-string/string literal`（格式化输出字符串被意外断行）。


## v1.2.4 训练模式“逐条提示”引导
- 仅在 **coach 模式**显示：每次只显示1条“当前提示”，当系统判定该提示满足后自动切换到下一条，直至完成全部提示。
- 提示内容来源于场景文件中的 `training.guided_prompts`，可按科室流程自行修改顺序与文案。


## v1.2.6 关键处置时间底限（训练/考试一致）
- **肌注肾上腺素时间底限：180s**（与“6个动作/6步”一致，按30s/步计算）。
- 若 **t≥180s 仍未完成肌注肾上腺素**：系统进入“喉头水肿/窒息”终末事件并判定失败结束。
- 90–180s 期间持续出现进行性气道受累与SpO₂下降（即使给氧也可能继续下降），用于促使受训者基于表现做出关键决策。



## v1.2.7 分阶段恶化（90–180s）与变体后测说明
### 分阶段恶化（仅在未完成 IM 肾上腺素时触发）
- 90–120s：早期气道受累加重（SpO₂下降、RR/HR上升）
- 120–150s：喉头水肿进展（出现/加重喉鸣、面唇/黏膜肿胀表现，SpO₂下降更快）
- 150–180s：重度气道受累/意识受影响（SpO₂快速下降，循环进一步恶化）
- ≥180s：仍未肌注肾上腺素 → 终末事件（窒息死亡结局，情景提前终止）

### 变体后测（Post-test）怎么跑
- Pre-test（基础版）：
  python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training.json --mode exam --out runs/P01_pre
- Post-test（变体A：皮肤表现不典型）：
  python engine.py --scenario scenarios/peds_ward_anaphylaxis_iv_v1_1_training_variantA.json --mode exam --out runs/P01_post


## v1.2.8 计分上限修复
- 计分仅在每个动作第一次执行时生效（同一动作重复执行不再重复加分），从机制上保证总分不超过满分（25分）。


## Hotfix 1.2.8.1
- Added baseline flag `airway_compromise` to prevent rule_eval_error and enable oxygen limitation rule.


## V1.2.6c 说明

本版新增糖皮质激素剂量输入与5分计分，删除抗组胺药按钮，并将气道梗阻、球囊面罩加压给氧、高级生命支持和CPR作为条件性危重分支单独记录。
