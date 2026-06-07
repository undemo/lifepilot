# LifePilot Agent 协作说明

## 项目范围

这个仓库是 LifePilot 本地生活时间导航 Agent 的比赛 Demo 实现。

## 文档优先级

1. `docs/03_schema.md` 是当前仓库里的数据 Schema 文件，对应文档中提到的 `03_data_schema.md`。
2. `docs/04_api_contract.md` 定义 HTTP 路径、标准响应、幂等和错误处理规则。
3. `docs/05_agent_workflow.md` 定义 Agent 编排流程和模块边界。
4. `docs/06_mock_api_design.md` 定义 MockAPI 和数字孪生数据要求。
5. `docs/07_frontend_design.md` 定义前端路由、ViewModel 和调试信息可见性规则。
6. `docs/08_evaluation_design.md` 定义测试、契约扫描和验收标准。
7. `docs/02_system_architecture.md`、`docs/01_prd.md`、`docs/00_project_vision.md` 分别提供架构、产品范围和愿景背景。

## 工作规则

- 没有明确要求时，不修改 `docs/00_project_vision.md` 到 `docs/08_evaluation_design.md`。
- 审计或文档任务中，不改业务逻辑。
- `PlanContract` 是核心契约；不要把内部 `DraftPlan` 或 `PlanBuildCandidate` 暴露成用户可见 API/UI 数据。
- 不要随意改 `PlanContract` 字段结构、`/api/v1` 路由、标准响应格式或幂等语义。
- 不要绕过 `VerifierService`、`SchemaValidator` 或 `PlanContractBuilder` 直接把内部草案保存为用户计划。
- 不要改变 `AgentOrchestrator` 主编排顺序，除非任务明确要求并同步测试。
- 业务 API 使用 `/api/v1` 路径；Mock 能力必须清楚标注为 Mock/模拟。
- 不要让 LLM 直接决定真实营业状态、路线、排队、余位、预算或执行成功；这些状态必须经过 MockAPI / 数字孪生数据 / Verifier。
- Recovery 采用版本化策略，保留 `original`、`replacement`、`diff`、`updated_plan_id`。
- `backend/data/fixtures/` 是稳定 Mock source；`backend/data/runtime/` 是本地运行态写入。新增或迁移 data JSON 路径必须先走 `backend/app/core/data_paths.py`。
- 测试应复制 fixture 或使用临时 data 目录，不要直接污染真实 `backend/data/runtime/`。
- 普通用户页不要展示 `failure_injection`、Prompt、API Key、模型推理链等底层调试信息。
- 普通用户页尽量避免展示 `trace_id`、内部 payload、原始机器标签、`Verifier`、`ToolAction`、`PlanContract` 等工程词；调试页或评委模式可以展示脱敏摘要。
- 标签权威来源是 `backend/app/rules/recommendation_taxonomy.py`；新增标签必须同步 `TagDefinition`、`display_label`、`keywords`、policy 使用点、ResponseAssembler、frontend fallback 和相关测试，避免同一个标签多处维护不同中文名。
- `machine_tag` 不等于 `raw_poi_tag`；测试不要散落复制关键词列表，优先复用 taxonomy helper（如 `get_tag_keywords()`）。
- 新增场景时优先补测试和规则边界，不要直接把大量条件堆进 `CandidateRetriever`。
- 删除文件前必须先用 `rg` 搜索引用；只删除空文件、缓存、日志、明确无引用临时产物或已完整归档的历史文件。
- 不删除整个 `docs/`、`agent_docs/`、`tools/`、`scripts/`、`tests/`、`backend/data/`、`exp_docs/`、`reports/` 目录。

## 维护入口

- `agent_docs/STRUCTURE_CLEANUP_PLAN.md` 记录结构清理审计、风险分级、删除候选和合并候选。
- `agent_docs/CODE_MAP.md` 是当前建议优先阅读的代码地图。
- `agent_docs/MAINTENANCE_RULES.md` 记录删除、文档合并、标签新增、场景新增和契约变更规则。
