# 儿科药物诱发过敏反应动态分支虚拟仿真训练系统

版本：V1.1.1 export-enhanced（基于 V0.8.2 评分规则，接入 Supabase 云端数据库）

## 项目用途

本项目用于儿科病区药物诱发过敏反应/过敏性休克识别与初始处置的护理教学、培训与科研可行性验证。系统采用动态分支虚拟仿真引擎，支持实时病情变化、操作评分、肾上腺素剂量输入判定、训练模式提示、考试模式运行、单次报告下载、训练结果自动保存和管理员导出。

**声明：本系统仅用于护理教学、培训和科研可行性验证，不用于临床诊疗决策。**

## V1.1.1 新增功能

1. 保留 V1.1 的 Supabase 云端数据库写入功能。
2. 管理员后台增强为三类导出：
   - **训练汇总 CSV**：每次训练一行，适合 Excel/SPSS/R 统计。
   - **操作明细 CSV**：每个操作事件一行，适合分析操作顺序、操作延迟、加分/扣分和剂量错误。
   - **完整 JSONL**：每次训练一行完整报告，保留原始嵌套结构，适合长期归档和深度分析。
3. 汇总 CSV 中展开了关键步骤时间点，例如停止输液、呼救、给氧、连接监护、测血压、肌注肾上腺素、补液、复评、家属沟通、SBAR交接等。
4. 汇总 CSV 中增加肾上腺素剂量状态、剂量不足/超量标记、错误操作次数、高危错误次数、最终生命体征等字段。
5. 管理员后台可在“训练汇总”和“操作明细”之间切换预览。

## Streamlit Cloud 部署入口文件

```text
streamlit_app.py
```

## 依赖

```text
streamlit>=1.33,<2
supabase>=2.10,<3
```

## Secrets 配置

在 Streamlit Cloud 的 App → Settings → Secrets 中填写：

```toml
APP_ACCESS_CODE = "peds2026"
ADMIN_PASSWORD = "admin2026"

SUPABASE_URL = "https://你的项目ID.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "你的 service_role key"
SUPABASE_TABLE = "training_records"
```

注意：`SUPABASE_SERVICE_ROLE_KEY` 不要上传到 GitHub，不要截图外发。

## 数据库表

使用 Supabase 的 `training_records` 表。V1.1.1 不要求新增数据库字段；增强导出主要从 `full_report` JSON 中展开生成，因此可以直接覆盖 V1.1 代码后继续使用原表。

## 文件结构

```text
peds_web_v1_1_1_export_enhanced/
├─ streamlit_app.py
├─ requirements.txt
├─ peds_anaphylaxis_sim/
│  ├─ engine.py
│  ├─ __init__.py
│  └─ scenarios/
│     ├─ peds_ward_anaphylaxis_iv_initial.json
│     └─ peds_ward_anaphylaxis_iv_variantA.json
├─ docs/
│  └─ V0.8.2_完整评分细则.docx
├─ .streamlit/
│  ├─ config.toml
│  └─ secrets.example.toml
├─ README.md
└─ .gitignore
```

## 当前版本定位

V1.1.1 是“云端数据库 + 数据导出增强版”，适合小规模至中等规模推广试运行。正式多中心长期运行前，建议继续完善账号权限、数据字典、知情同意/伦理材料和数据库备份策略。
