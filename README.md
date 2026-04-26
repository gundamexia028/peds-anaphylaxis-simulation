# 儿科药物诱发过敏反应动态分支虚拟仿真训练系统

版本：v0.9 deploy-ready（基于 v0.8.2 评分规则）

## 项目用途

本项目用于儿科病区药物诱发过敏反应/过敏性休克识别与初始处置的护理教学、培训与科研可行性验证。系统采用动态分支虚拟仿真引擎，支持实时病情变化、操作评分、肾上腺素剂量输入判定、训练模式提示、考试模式运行和单次报告下载。

**声明：本系统仅用于护理教学、培训和科研可行性验证，不用于临床诊疗决策。**

## 入口文件

Streamlit Cloud 部署入口文件：

```text
streamlit_app.py
```

## 依赖

```text
streamlit>=1.33,<2
```

## 文件结构

```text
peds_web_v0_9_deploy_ready/
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
├─ .gitignore
└─ README.md
```

## 部署说明

1. 创建一个 GitHub 仓库。
2. 将本文件夹内的全部内容上传到仓库根目录。
3. 在 Streamlit Community Cloud 中新建应用。
4. 选择对应 GitHub 仓库和分支。
5. Main file path 填写：`streamlit_app.py`。
6. 点击 Deploy。

## 当前版本限制

v0.9 是可部署演示版。它可以让其他人打开网页进行训练，但当前单次报告主要通过页面下载获得。若用于大规模推广、正式培训或科研数据收集，建议后续升级：

- 参与者匿名编号必填；
- 单位/科室字段；
- 后台数据库；
- 管理员成绩汇总页；
- Excel/CSV 批量导出；
- 访问密码或账号权限；
- 数据脱敏与伦理配套说明。
