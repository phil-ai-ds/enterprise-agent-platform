# Enterprise Agent Platform

企业级**多 Agent 平台**的可运行原型：Agent 对话与「个人 / 团队 / 组织」工作区**解耦**，
支持技能版本化、一句话创建 Agent、👍👎 反思迭代、多技能工作流、多 Agent + 人工审批流程（HITL）与用量观测。

内核：**FastAPI + LangGraph/LangChain + SQLite**；前端为原生 JS 单页应用（无构建链）；
模型走 OpenAI 兼容协议（预置 DeepSeek，可 BYOM）。

## ✨ 功能（均已实现）

| 能力 | 说明 |
|---|---|
| **Agent 工作台（工作区 × Agent 合并）** | 左栏选工作区（个人/团队/组织空间）与文件夹，右栏选 Agent 对话；Agent **记住上次工作文件夹**（按用户×Agent 记忆），手动切换即更新；多 Agent 可在同一文件夹协作 |
| **文件夹 = 工作目录** | Agent 的 `write_file / read_file / list_workspace` 以当前文件夹为基准（可用 `..` 回工作区根、不可越界）；参考文件/文件夹随消息注入上下文 |
| **一句话创建 Agent** | LLM 生成蓝图（system_prompt / agent.md / 技能装配），确认后落地：缺失技能建草稿、已有技能自动复用绑定 |
| **反思迭代闭环** | 对回复点 👍/👎 并留言 → LLM 复盘 → 自动写记忆 / 为绑定技能建 v_next 草稿 / 生成提示词建议 → 作者一键采纳 |
| **技能版本化** | draft → publish（不可变）→ 迭代再建草稿；可「发布为 API」供可见用户 invoke；可 fork 复制改造 |
| **多技能工作流** | 把多个已发布技能按步骤串联，上一步输出自动喂下一步 |
| **多 Agent + HITL 流程** | draft-review：Agent A 起草 → 人工审批门（interrupt）→ Agent B 对抗评审 或 驳回 |
| **工作区文件管理** | 上传 / 下载 / 新建 / 编辑 / 删除 / 预览，按个人-团队-组织隔离 |
| **用量观测** | 每次 LLM 调用按 token 计费落库；用户级与平台级聚合（按 user/agent/provider/model/team/day） |
| **多 LLM (BYOM)** | 管理端增配任意 OpenAI 兼容端点；内置 Mock-Offline 离线演示 |

## 🚀 快速开始

```bash
./run.sh          # 一键：建 venv + 装依赖 + uvicorn :8000
open http://localhost:8000
```

演示账号（密码均 `demo123`）：`admin`（平台管理员）· `alice`（市场团队）· `bob`（财务团队）

> LLM 配置：默认使用 DeepSeek。真实 Key **通过环境变量注入，不进仓库**（见下）。没有 Key 时可用管理端把 Provider 切到 Mock-Offline 体验全流程。

## 🔑 环境变量（前缀 `EAP_`）

| 变量 | 说明 | 默认 |
|---|---|---|
| `EAP_DEFAULT_DEEPSEEK_KEY` | DeepSeek API Key（**必填**才可真实对话） | 空 |
| `EAP_SECRET_KEY` | JWT 签名密钥，生产请更换 | dev 占位 |
| `EAP_DATA_DIR` | 工作区与运行时数据目录 | `./data` |
| `EAP_DATABASE_URL` | SQLAlchemy URL | `sqlite:///./eap.db` |

示例：`EAP_DEFAULT_DEEPSEEK_KEY=sk-xxx ./run.sh`

> 仓库内 **不包含** 任何运行时数据（`backend/data/`、`backend/eap.db` 已在 .gitignore 中）。
> 首次启动自动建表并 seed 演示数据（团队/用户/工作区/技能/Agent/README 文档）。

## 🗺 架构文档

`docs/` 下有按当前代码整理的**架构梳理文档**与 **Archify 交互式架构图**：

```
docs/index.html                       ← 主文档：API 全景 / 运行时 / 数据模型 / 关键链路 / 权限 / 边界
docs/diagrams/epa-architecture.html   ← 交互式架构图（缩放 / 明暗主题 / 聚焦视图 / 导出）
```

打开方式：直接双击 `docs/index.html`（浏览器即可，无外部依赖）。

## 📁 目录结构

```
backend/app/
  main.py               FastAPI 入口 + 前端静态托管（单进程）
  config.py / db.py / models.py / security.py / deps.py
  api_routes.py         认证 · 可见 Agent 目录 · 记忆 · 用量 · 管理端
  api_builder.py        技能全生命周期 · Agent CRUD · 工作流
  api_flows.py          Agent 对话（workspace_id+folder+refs）· ws-pref · draft-review 流程
  api_workspaces.py     工作区与文件管理
  api_ai.py             一句话建 Agent · 反思迭代 · 采纳提示词
  runtime.py            LangGraph（create_agent）运行时
  orchestration.py      LangGraph StateGraph + interrupt（HITL 审批流）
  executor.py           单技能执行 / 多技能工作流执行
  tools.py              Agent 9 工具（读写/记忆/搜索/抓取/沙箱代码）
  skills.py memory.py workspaces.py providers.py usage.py seed.py mock_llm.py
backend/data/           （运行时生成）SQLite + 工作区文件，不入库
frontend/               index.html / app.js / app.css（原生 SPA）
docs/                   架构梳理文档 + Archify 交互图
```

## 🧩 数据模型（SQLite · 17 张表）

- 主体：`users / teams / llm_providers / agents / agent_skills / workspaces / workspace_files / skills / skill_versions`
- 解耦记忆：`agent_ws_prefs`（某用户在某 Agent 上最近的工作区 + 文件夹）
- 运行：`memory_entries / reflections / llm_usage / flow_runs / workflows / workflow_runs`

## 📜 说明与边界

- 用量：LangChain `BaseCallbackHandler` 捕获 `usage_metadata`，按上下文落库；成本按 Provider 单价估算。
- 记忆：SQLite 键值 + 关键词召回（本地实现，接口可按需替换向量库）。
- 安全：内部 JWT；路径防穿越（realpath 前缀校验）；Agent 代码执行走隔离沙箱（`python -I` + 禁网 + 30s 超时）。
- 边界：单进程本地/容器部署；未做容器编排、无外部数据库/对象存储、无 WebSocket 流式、无 SSO。

## 📄 License

MIT（待定）· 供学习与演示使用；运行时数据与密钥请自行保管。
