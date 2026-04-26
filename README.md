# 儿科药物诱发过敏反应动态分支虚拟仿真训练系统

版本：V1.0 promotion-ready（基于 V0.8.2 评分规则）

## 项目用途

本项目用于儿科病区药物诱发过敏反应/过敏性休克识别与初始处置的护理教学、培训与科研可行性验证。系统采用动态分支虚拟仿真引擎，支持实时病情变化、操作评分、肾上腺素剂量输入判定、训练模式提示、考试模式运行、单次报告下载、训练结果自动保存和管理员导出。

**声明：本系统仅用于护理教学、培训和科研可行性验证，不用于临床诊疗决策。**

## V1.0 新增功能

1. 访问码入口：进入系统前需输入访问码。
2. 受试者信息：参与者编号、单位/医院、科室/病区为必填项。
3. 自动保存结果：每次情景结束后自动保存一条训练记录。
4. 管理员后台：可查看训练记录，并导出 CSV 或 JSONL。
5. 操作历史显示：受试者每次执行操作后，右侧选项下方会显示已执行操作、时间和得分/剂量结果。

## Streamlit Cloud 部署入口文件

```text
streamlit_app.py
```

## 依赖

```text
streamlit>=1.33,<2
```

## 访问码与管理员密码

V1.0 默认值：

```text
APP_ACCESS_CODE = peds2026
ADMIN_PASSWORD = admin2026
```

正式推广前建议在 Streamlit Cloud 的 Secrets 中修改：

```toml
APP_ACCESS_CODE = "你的访问码"
ADMIN_PASSWORD = "你的管理员密码"
```

## 当前版本数据保存说明

V1.0 为轻量数据留存版，训练记录保存在应用运行环境的 `runs_web/training_results.jsonl` 中，适合试运行、小范围培训和功能验证。

如果后续要进行多医院、大规模、长期科研数据收集，建议升级为数据库版本，例如 Supabase、PostgreSQL、SQLite 持久化存储或医院服务器数据库。

## 文件结构

```text
peds_web_v1_0_promote_ready/
├─ streamlit_app.py
├─ requirements.txt
├─ peds_anaphylaxis_sim/
│  ├─ __init__.py
│  ├─ engine.py
│  ├─ README.md
│  └─ scenarios/
│     ├─ peds_ward_anaphylaxis_iv_initial.json
│     └─ peds_ward_anaphylaxis_iv_variantA.json
├─ docs/
│  └─ V0.8.2_儿科药物诱发过敏反应动态分支虚拟仿真训练系统_完整评分细则.docx
├─ .streamlit/
│  └─ config.toml
├─ README.md
└─ .gitignore
```


## V1.1 Supabase 数据库配置

在 Streamlit Cloud 的 App settings → Secrets 中添加：

```toml
APP_ACCESS_CODE = "peds2026"
ADMIN_PASSWORD = "admin2026"
SUPABASE_URL = "https://your-project-ref.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
SUPABASE_TABLE = "training_records"
```

注意：`SUPABASE_SERVICE_ROLE_KEY` 仅可放在 Streamlit Secrets 中，不能写入 GitHub 仓库，不能截图公开。
