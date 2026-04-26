# 儿科护理急救动态分支虚拟仿真训练平台｜V1.1.2 research-ready

本版本基于 V1.1.1 云端数据库与导出增强版继续升级，用于支撑课题方向：

> 基于动态分支虚拟仿真平台的多院区儿科护士药物诱发过敏反应识别与初始处置能力现状及影响因素研究

## 主要更新

1. 初始访问/登记界面重做：居中、加宽，更适合作为正式受试者登录与信息登记页面。
2. 版本更新说明从首页主体中移除，仅保留在右上角。
3. 新增多中心/多层级研究字段：
   - 院区/中心
   - 科室类型
   - 护理层级
   - 工作年限
   - 职称
   - 学历
   - 是否接受过过敏反应/过敏性休克培训
   - 是否参加过模拟/虚拟仿真培训
   - 是否处理过真实过敏反应病例
   - 培训批次/项目编号
   - 评估阶段
   - 第几次尝试/测试
4. 新增字段会写入完整训练报告，并在管理员导出的汇总 CSV 和操作明细 CSV 中展开。
5. 继续沿用现有 Supabase `training_records` 表；无需重新建表。
6. 保留 V0.8.2 评分规则、随机年龄体重、肾上腺素剂量输入、云端数据库写入、管理员导出功能。

## 部署说明

将本文件夹内容上传至原 GitHub 仓库根目录，覆盖旧版文件：

- `streamlit_app.py`
- `requirements.txt`
- `peds_anaphylaxis_sim/`
- `.streamlit/`
- `docs/`
- `README.md`

提交后，Streamlit Cloud 会自动重新部署。原来的 Secrets 继续使用，无需重新配置：

```toml
APP_ACCESS_CODE = "peds2026"
ADMIN_PASSWORD = "admin2026"

SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "..."
SUPABASE_TABLE = "training_records"
```

## 数据说明

V1.1.2 不向 `training_records` 表新增顶层数据库列，新增研究字段保存在 `full_report` JSON 中，并由管理员后台导出为 CSV 字段。这样可以避免破坏你已经成功运行的数据库表结构。

如果后续需要在 Supabase 表格页面直接按护理层级、院区筛选，可再升级 V1.1.3，将这些字段同步为数据库顶层列。
