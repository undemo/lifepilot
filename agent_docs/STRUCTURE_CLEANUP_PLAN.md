# LifePilot 结构收敛与低风险清理计划

生成时间：2026-06-03，Asia/Shanghai。

## 1. 当前项目结构概览

| 目录 | 职责 | 分类 |
|---|---|---|
| `backend/app/api` | FastAPI 路由层，业务 API 必须保持 `/api/v1`；`mock.py` 暴露 MockAPI 调试/数字孪生能力。 | 主链路入口 |
| `backend/app/core` | 错误码、响应包装、时间、ID、常量、上下文等基础设施。 | 主链路支撑 |
| `backend/app/schemas` | 请求体和内部智能结构的 Pydantic schema。 | 契约支撑 |
| `backend/app/services` | PlanService、AgentOrchestrator、Retriever、Generator、Verifier、Executor、Recovery 等核心服务。 | 主链路核心 |
| `backend/app/rules` | 推荐 taxonomy、policy、POI feature、ranking weights 等规则权威来源。 | 主链路规则 |
| `backend/app/storage` | JSON 文件存储封装。 | 运行态支撑 |
| `backend/data` | Demo 数字孪生数据；核心 fixture 在 `fixtures/`，本地写入 store 在 `runtime/`，辅助数据仍保留根目录。 | 数据源/运行态 |
| `frontend/app` | Next.js 页面路由，首页、计划页、投票、执行、反馈、记忆、设置页。 | 用户主链路 |
| `frontend/components` | 页面组件和卡片展示层。 | 用户主链路展示 |
| `frontend/lib` | API client、幂等、trace、formatter、view-model 映射。 | 前端契约支撑 |
| `frontend/types` | TypeScript 契约类型和 ViewModel 类型。 | 前端契约支撑 |
| `tests` | 后端核心测试和 golden case。 | 验证 |
| `scripts` | 契约扫描、Mock 数据校验、P0 回归、前端 smoke runner。 | 工具/验证 |
| `tools` | 高德数据工厂、Qwen 数据工厂、规则评测等离线工具。 | 工具/实验 |
| `docs` | 00-08 权威产品/架构/Schema/API/Workflow/Mock/前端/验收文档，09-10 为补充文档。 | 权威文档 |
| `agent_docs` | Agent 接手、代码地图、状态、差距和审计报告。 | 交接/维护文档 |
| `reports` | 本地回归报告、日志、截图、临时 backend data 快照。 | 运行态产物/历史报告 |
| `experiments` | 当前工作区里已不存在；`git status` 显示 `experiments/T05_27.md` 是既有删除。 | 历史资料 |
| `exp_docs` | 实验日志和已整理实验记录。 | 历史资料 |
| `lifepilot-dev` | 本地 agent/dev skill 和辅助脚本。 | 开发辅助 |

V1 主链路是：

```text
frontend/app/page.tsx
  -> frontend/lib/api.ts api.createPlan
  -> POST /api/v1/plans/create
  -> backend/app/services/plan_service.py PlanService.create_plan
  -> backend/app/services/agent_orchestrator.py AgentOrchestrator.create_plan
  -> IntentParser
  -> ConstraintExtractor
  -> LatentIntentInterpreter / FoodSemanticAgent / ActivitySemanticAgent
  -> RetrievalIntentCompiler
  -> CandidateRetriever.retrieve
  -> CandidateCriticAgent
  -> PlanGenerator.generate
  -> PlanContractBuilder
  -> VerifierService
  -> SchemaValidator
  -> PlanRanker
  -> ExplanationAgent
  -> ResponseAssembler
  -> 保存 PlanContract
  -> frontend/app/plans/[planId]/page.tsx
```

## 2. 文件风险分级

### A. 禁止轻易动

这些文件承载主链路、核心契约、规则权威或用户关键页面。允许清理 import、注释和普通用户文案，但不要改业务逻辑、输出结构、路由、PlanContract 字段或 Agent 编排顺序。

```text
backend/app/api/v1/plans.py
backend/app/services/agent_orchestrator.py
backend/app/services/candidate_retriever.py
backend/app/services/plan_generator.py
backend/app/services/plan_contract_builder.py
backend/app/services/verifier_service.py
backend/app/services/schema_validator.py
backend/app/services/mock_api_service.py
backend/app/services/plan_service.py
backend/app/services/container.py
backend/app/services/response_assembler.py
backend/app/rules/recommendation_taxonomy.py
backend/app/rules/recommendation_policy_engine.py
backend/app/rules/poi_feature_store.py
frontend/lib/api.ts
frontend/types/schema.ts
frontend/lib/view-models.ts
frontend/components/plan/PlanCards.tsx
frontend/app/page.tsx
frontend/app/plans/[planId]/page.tsx
docs/03_schema.md
docs/04_api_contract.md
```

特别说明：`backend/app/services/plan_service.py` 内部仍保留 `_build_plan_contract`、fallback `execute_plan`、fallback `recover_plan` 等旧路径。由于容器注入缺失时仍可能作为兜底，不应作为“死代码”直接删除。本轮最多标注 legacy 风险，不迁移。

### B. 可以低风险整理

```text
README.md 与 AGENTS.md 的维护说明
agent_docs 代码地图和维护规则
前端普通用户页面里的工程词文案
未使用或重复 import
明显生成的缓存、日志、系统文件
过期但无引用的临时运行产物
```

本轮建议只做文档收敛、普通用户文案收敛和运行产物删除，不做核心服务拆分。

### C. 可以考虑合并

```text
agent_docs/CODEMAP.md -> agent_docs/CODE_MAP.md
agent_docs/HANDOFF_CURRENT.md、PROJECT_STATE.md、MODULE_STATUS.md -> 后续可合并成一个当前状态文档
agent_docs/API_IMPLEMENTATION_MAP.md、DATA_FLOW_ACTUAL.md -> 后续可合并到代码地图或接口实现地图
reports/p0_code_audit_report.md、reports/p0_fix_report.md、reports/p0_frontend_smoke_report.md -> 后续可归档成 P0 历史报告索引
docs/LIFEPILOT_AUDIT.md 与 agent_docs/CONTRACT_GAP_REPORT.md -> 后续可做审计索引，保留原报告
```

合并原则：保留信息，原路径保留跳转说明至少一个迭代周期，避免后续 Agent 断链。本轮不直接删除这些历史文档。

### D. 可以考虑删除

只删除满足至少一个条件的单个文件或生成目录内容：

```text
空文件
空目录
无引用系统文件，如 .DS_Store
Python/Next/pytest 缓存
本地运行日志
脚本可重新生成的 smoke/backend/frontend 日志
未被代码、测试、README、脚本引用的 debug staging 文件
```

不删除整个 `docs/`、`agent_docs/`、`tools/`、`scripts/`、`tests/`、`backend/data/`、`experiments/`、`exp_docs/`、`reports/` 目录。

## 3. 删除候选清单

引用搜索命令排除了 `node_modules`、`.venv`、`.next`、`.git`、`__pycache__` 和 pytest cache。搜索结论按“是否引用现有文件内容”判断。

| 文件路径 | 删除原因 | 引用搜索结果 | 风险等级 | 是否建议删除 |
|---|---|---|---|---|
| `.DS_Store`、`backend/.DS_Store`、`backend/app/.DS_Store`、`backend/app/api/.DS_Store` | macOS 系统文件 | 无内容引用 | 低 | 是 |
| `.codex_logs/*.log` | 本地 Codex 运行日志 | 无引用 | 低 | 是 |
| `reports/logs/*.log` | 本地 smoke/backend/frontend/安装日志 | `scripts/run_p0_frontend_smoke.py` 使用 `reports/logs/backend.log`、`frontend.log` 作为输出路径；不依赖现有内容 | 低 | 是，保留目录 |
| `reports/dev/*.log` | 本地开发服务器日志 | 无内容引用 | 低 | 是 |
| `reports/dev/*.pid` | 本地开发服务器 pid | 无内容引用 | 低 | 是 |
| `scripts/__pycache__/`、`tests/__pycache__/`、`tools/*/__pycache__/` | Python 字节码缓存 | `scripts/contract_scan.py` 只跳过 `__pycache__`；无内容引用 | 低 | 是 |
| `.pytest_cache/` | pytest 缓存 | 无内容引用 | 低 | 是 |
| `frontend/.next/` | Next.js 构建缓存/产物 | 契约扫描跳过 `.next`；无内容引用 | 低 | 是 |
| `tools/qwen_data_factory/staging/qreq_*_debug.json` | Qwen 数据工厂 staging debug 产物 | 无内容引用；保留 `staging/.gitkeep` | 低 | 是 |
| `tools/qwen_data_factory/reports/overnight_500_20260521_015825.log` | 历史运行日志 | 无内容引用 | 低-中 | 暂不删，后续可归档 |
| `reports/tmp_backend_data/*` | smoke/临时 backend data 快照 | 无内容引用，但可用于复现历史 smoke | 中 | 暂不删 |
| `reports/dev/*.png`、`reports/dev/final-demo-plan.json` | demo 截图和计划样例 | 无内容引用，但有展示/复盘价值 | 中 | 暂不删 |

## 4. 合并候选清单

| 源文件 | 目标文件 | 合并理由 | 是否保留原路径跳转说明 | 风险等级 |
|---|---|---|---|---|
| `agent_docs/CODEMAP.md` | `agent_docs/CODE_MAP.md` | 命名规范化，补齐“用户输入/语义解析/候选检索/生成/校验/展示/数据源/测试/脚本”定位 | 是 | 低 |
| `agent_docs/HANDOFF_CURRENT.md`、`agent_docs/PROJECT_STATE.md`、`agent_docs/MODULE_STATUS.md` | 后续 `agent_docs/CURRENT_STATE.md` | 都描述当前状态和交接上下文，存在重叠 | 是 | 中 |
| `agent_docs/API_IMPLEMENTATION_MAP.md`、`agent_docs/DATA_FLOW_ACTUAL.md` | 后续接口/数据流地图 | 都是实际实现映射，可合并降低查找成本 | 是 | 中 |
| `reports/p0_code_audit_report.md`、`reports/p0_fix_report.md`、`reports/p0_frontend_smoke_report.md` | 后续 `reports/P0_HISTORY_INDEX.md` | P0 历史报告可归档成索引，保留原始报告 | 是 | 中 |
| `docs/LIFEPILOT_AUDIT.md`、`agent_docs/CONTRACT_GAP_REPORT.md` | 后续审计索引 | 审计信息分散，后续可建立索引而非删原文 | 是 | 中 |

本轮只新增 `agent_docs/CODE_MAP.md`，不删除旧 `CODEMAP.md`，降低断链风险。

## 5. 命名规范问题

| 问题 | 当前观察 | 建议 |
|---|---|---|
| `scene` / `scenario` 混用 | 后端和前端主字段为 `scenario`，部分文档/语义描述会说“场景”。 | 机器字段统一 `scenario`；用户文案使用“场景”。 |
| `intent` / `goal` 边界 | `user_goal`、`intent_tags`、semantic agent 输出并存。 | `goal` 表示用户目标摘要；`intent` 表示可计算意图，不直接给普通用户展示。 |
| `tag` / `machine_tag` / `display_label` | `display_tags` 直接进入前端，`view-models.ts` 有一份中文兜底表。 | 后端 taxonomy/policy 是权威；前端只做兜底和隐藏内部枚举。新增标签必须同步 taxonomy、policy、ResponseAssembler、view-model 和测试。 |
| `debug` / `trace` / `verifier` | 普通计划页仍有 `PlanContract`、`Verifier` 等工程词；trace_id 由 `PageHeader` 展示。 | 普通页面改成用户可理解表达；trace/debug 留在评委或调试视图。 |
| `poi` / `candidate` | 后端候选和 POI 概念清楚，前端用户文案应说“地点/候选地点”。 | 代码保留 `poi`；用户文案不要展示原始 `poi_id`。 |
| `timeline_step` / `plan_step` | Schema 里是 timeline step，前端 ViewModel 是 TimelineViewItem。 | 契约字段不改；文档中统一叫“时间线节点”。 |
| `backup_plan` / `recovery_plan` | BackupPlan 是计划内备选，Recovery 是执行中版本化替代。 | 文档和 UI 保持区分：PlanB/备选 vs 恢复版本。 |

## 6. 本轮执行边界

将执行：

```text
更新 README.md、AGENTS.md
新增 agent_docs/CODE_MAP.md
新增 agent_docs/MAINTENANCE_RULES.md
低风险调整普通用户页面工程词
删除无引用运行产物、缓存、系统文件
运行可用后端/前端验证
```

不执行：

```text
不改 docs/00_project_vision.md 到 docs/08_evaluation_design.md
不改 PlanContract 字段结构
不改 /api/v1 路由
不改 AgentOrchestrator 主编排顺序
不拆 CandidateRetriever 或 PlanGenerator 的外部接口
不删除 agent_docs/docs/reports/exp_docs/tools 下有历史价值的文档
不处理当前工作区既有的 experiments/T05_27.md 删除和 rebuild/ 未跟踪内容
```

## Core / Rules Duplicate Module Audit

审计时间：2026-06-03，第二轮低风险结构收敛。

引用搜索：

```text
grep -R "core.recommendation_taxonomy\|rules.recommendation_taxonomy\|recommendation_taxonomy" -n backend tests scripts
grep -R "core.intent_rules\|rules.intent_rules\|intent_rules" -n backend tests scripts
```

### recommendation_taxonomy

| 项目 | 结论 |
|---|---|
| 模块名 | `recommendation_taxonomy` |
| 两个路径职责 | `backend/app/rules/recommendation_taxonomy.py` 承担控制标签、开放词、场景归一、餐饮偏好抽取等业务规则；`backend/app/core/recommendation_taxonomy.py` 仅作为兼容 re-export。 |
| 当前真实运行时引用 | `backend/app/services/constraint_extractor.py`、`intent_parser.py`、`food_semantic_agent.py` 均从 `app.rules.recommendation_taxonomy` 导入。 |
| 测试引用 | `tests/test_rule_modules.py` 从 `app.rules.recommendation_taxonomy` 导入。 |
| 文档引用 | `docs/LIFEPILOT_AUDIT.md`、`agent_docs/MAINTENANCE_RULES.md`、`agent_docs/CODE_MAP.md`、`README.md` 均指向 `backend/app/rules/recommendation_taxonomy.py`。 |
| 是否存在双权威风险 | 低。core 文件已是薄 re-export，但原先缺少 deprecated 说明，容易让新代码误用 core 路径。 |
| 推荐保留路径 | 保留 `backend/app/rules/recommendation_taxonomy.py` 为唯一权威。 |
| 推荐兼容策略 | 保留 `backend/app/core/recommendation_taxonomy.py` 作为 deprecated compatibility wrapper；所有新代码继续从 `app.rules.recommendation_taxonomy` 导入。 |
| 是否建议本轮修改 | 是，已只补 deprecated wrapper 注释，不移动、不删除。 |

## Data Path Migration Plan

审计时间：2026-06-03，第三轮数据层分离与路径集中化。

引用搜索覆盖：

```text
rg -n "mock_pois\.json|mock_routes\.json|mock_status\.json|mock_inventory\.json|mock_weather\.json" backend tests scripts frontend
rg -n "plans\.json|consensus\.json|feedback\.json|traces\.json|executions\.json|idempotency\.json|mock_idempotency_store\.json" backend tests scripts frontend
rg -n "backend/data|app/data|data/" backend tests scripts frontend
```

| 文件 | 当前路径 | 目标路径 | 读写性质 | 引用位置 | 迁移风险 | 迁移策略 |
|---|---|---|---|---|---|---|
| `mock_pois.json` | `backend/data/mock_pois.json` | `backend/data/fixtures/mock_pois.json` | 稳定 fixture，只读 | `MockAPIService`、`CandidateRetriever`、`VerifierService`、`RecoveryService`、`PlanCriticAgent`、`ExplanationAgent`、`POIFeatureStore`、`scripts/validate_mock_data.py`、`tests/test_mock_api.py`、`tests/test_poi_feature_store_overlay.py` | 高：候选检索、校验、MockAPI 都依赖 POI 主数据 | 新增 `MOCK_POIS_PATH`，通过 `JsonFileStore` 映射到 fixture；测试读取 `fixtures/` 或 store 映射。 |
| `mock_routes.json` | `backend/data/mock_routes.json` | `backend/data/fixtures/mock_routes.json` | 稳定 fixture，只读 | `MockAPIService`、`CandidateRetriever`、`VerifierService`、`scripts/validate_mock_data.py`、`tests/test_mock_api.py` | 高：路线估算和距离校验依赖 | 新增 `MOCK_ROUTES_PATH`，服务统一用常量；保留测试临时目录隔离。 |
| `mock_status.json` | `backend/data/mock_status.json` | `backend/data/fixtures/mock_status.json` | 稳定 fixture，只读覆盖 | `MockAPIService`、`VerifierService`、`RecoveryService`、`scripts/validate_mock_data.py` | 中：状态覆盖缺失时仍有确定性 Mock 引擎兜底 | 新增 `MOCK_STATUS_PATH`，读取迁到 fixture；不改状态判断逻辑。 |
| `mock_inventory.json` | `backend/data/mock_inventory.json` | `backend/data/fixtures/mock_inventory.json` | 稳定 fixture，只读覆盖 | `MockAPIService`、`scripts/validate_mock_data.py` | 中：订座/预约覆盖缺失时仍有确定性 Mock 引擎兜底 | 新增 `MOCK_INVENTORY_PATH`，读取迁到 fixture；不改库存推导逻辑。 |
| `mock_weather.json` | `backend/data/mock_weather.json` | `backend/data/fixtures/mock_weather.json` | 稳定 fixture，只读覆盖 | `MockAPIService`、`scripts/validate_mock_data.py` | 低-中：天气覆盖缺失时有确定性 Mock 引擎兜底 | 新增 `MOCK_WEATHER_PATH`，读取迁到 fixture。 |
| `plans.json` | `backend/data/plans.json` | `backend/data/runtime/plans.json` | runtime store，读写 | `PlanService`、`ExecutorService`、`RecoveryService`、`tests/test_mock_api.py`、`tests/test_verifier_service.py` | 高：PlanContract 持久化入口 | 新增 `PLANS_STORE_PATH`，服务统一写 runtime；测试通过临时目录 copy 后读写 `runtime/`。 |
| `consensus.json` | `backend/data/consensus.json` | `backend/data/runtime/consensus.json` | runtime store，读写 | `ConsensusService` | 中：朋友局投票会话和投票记录 | 新增 `CONSENSUS_STORE_PATH`，只改存储路径常量，不改投票契约。 |
| `feedback.json` | `backend/data/feedback.json` | `backend/data/runtime/feedback.json` | runtime store，读写 | `FeedbackService` | 低-中：反馈记录和记忆候选 | 新增 `FEEDBACK_STORE_PATH`，只改存储路径常量。 |
| `traces.json` | `backend/data/traces.json` | `backend/data/runtime/traces.json` | runtime store，读写 | `LoggingService`、`tests/test_mock_api.py`、`tests/test_verifier_service.py`、`tests/test_orchestrator_llm_native_flow.py` | 中：日志用于前端可见事件和测试断言 | 新增 `TRACES_STORE_PATH`，日志写 runtime；测试读 runtime 或 store 映射。 |
| `executions.json` | `backend/data/executions.json` | `backend/data/runtime/executions.json` | runtime store，读写 | `MockAPIService`、`PlanService`、`ExecutorService` | 中：执行结果和 Mock 工具执行记录 | 新增 `EXECUTIONS_STORE_PATH`，统一 runtime；不改执行结果结构。 |
| `idempotency.json` | `backend/data/idempotency.json` | `backend/data/runtime/idempotency.json` | runtime store，读写 | `IdempotencyService` | 高：业务 API 幂等语义依赖 | 新增 `IDEMPOTENCY_STORE_PATH`，只改路径，不改 fingerprint 和冲突处理。 |
| `mock_idempotency_store.json` | `backend/data/mock_idempotency_store.json` | `backend/data/runtime/mock_idempotency_store.json` | runtime store，读写 | `MockAPIService` | 中：Mock 执行动作幂等 | 新增 `MOCK_IDEMPOTENCY_STORE_PATH`，Mock 幂等写 runtime；不改 Mock 执行语义。 |
| `runtime_activity_pois.json` | `backend/data/runtime_activity_pois.json` | `backend/data/runtime/runtime_activity_pois.json` | runtime cache，读写 | `GaodeActivityProvider`、`MockAPIService`、`CandidateRetriever` | 中：高德补充活动候选进入 MockAPI POI 合并链路 | 新增 `RUNTIME_ACTIVITY_POIS_PATH`，写入 runtime；不改补充候选策略。 |

### intent_rules

| 项目 | 结论 |
|---|---|
| 模块名 | `intent_rules` |
| 两个路径职责 | `backend/app/rules/intent_rules.py` 承担业务意图规则；`backend/app/core/intent_rules.py` 仅作为兼容 re-export。 |
| 当前真实运行时引用 | `backend/app/services/constraint_extractor.py`、`intent_parser.py` 均从 `app.rules.intent_rules` 导入。 |
| 测试引用 | 未发现直接测试引用。 |
| 文档引用 | 未发现文档直接引用 `intent_rules`。 |
| 是否存在双权威风险 | 低。core 文件已是薄 re-export，但原先缺少 deprecated 说明。 |
| 推荐保留路径 | 保留 `backend/app/rules/intent_rules.py` 为唯一权威。 |
| 推荐兼容策略 | 保留 `backend/app/core/intent_rules.py` 作为 deprecated compatibility wrapper；所有新代码继续从 `app.rules.intent_rules` 导入。 |
| 是否建议本轮修改 | 是，已只补 deprecated wrapper 注释，不移动、不删除。 |

本轮结论：`backend/app/rules/` 已确立为 taxonomy 和 intent rules 的权威路径；`backend/app/core/` 只保留兼容 wrapper，避免破坏历史导入。

## Data Directory Fixture / Runtime Audit

审计时间：2026-06-03，第二轮低风险结构收敛。

历史说明：本节的“本轮不移动”指第二轮低风险结构收敛边界。第三轮已按后文 `Data Path Migration Plan` 将核心 fixture 迁入 `backend/data/fixtures/`，将运行态 store 迁入 `backend/data/runtime/`。

引用搜索：

```text
grep -R "mock_pois.json\|mock_routes.json\|mock_status.json\|mock_inventory.json\|mock_weather.json" -n backend tests scripts frontend
grep -R "plans.json\|consensus.json\|feedback.json\|traces.json" -n backend tests scripts frontend
grep -R "backend/data\|app/data\|data/" -n backend tests scripts frontend
```

说明：第三组原始 grep 会扫到 `backend/.venv` 和 `frontend/node_modules` 的大量依赖噪声；实际结论采用同模式但排除依赖目录后的源码引用复核。

| 文件 | 当前用途 | 读写方式 | 引用位置 | 是否可以移动 | 建议目标路径 | 风险等级 |
|---|---|---|---|---|---|---|
| `mock_pois.json` | mock source / 数字孪生 POI fixture | 运行时只读；测试复制后只读 | `MockAPIService`、`VerifierService`、`CandidateRetriever`、`RecoveryService`、`PlanCriticAgent`、`ExplanationAgent`、`POIFeatureStore`、`tests/test_mock_api.py`、`tests/test_poi_feature_store_overlay.py`、`scripts/validate_mock_data.py` | 本轮不移动。引用分散，且 `CandidateRetriever` 多处直接按文件名读取。 | `backend/data/fixtures/mock_pois.json` | 中 |
| `mock_routes.json` | mock source / 路线 fixture | 运行时只读；测试复制后只读 | `MockAPIService`、`VerifierService`、`CandidateRetriever`、`tests/test_mock_api.py`、`scripts/validate_mock_data.py` | 本轮不移动。移动需集中路径常量并同步 verifier route 存在性校验。 | `backend/data/fixtures/mock_routes.json` | 中 |
| `mock_status.json` | mock source / POI 状态覆盖 fixture | 运行时只读；测试复制后只读 | `MockAPIService`、`VerifierService`、`RecoveryService`、`scripts/validate_mock_data.py` | 本轮不移动。状态查询与恢复校验直接读取文件名。 | `backend/data/fixtures/mock_status.json` | 中 |
| `mock_inventory.json` | mock source / 余位余票 fixture | 运行时只读；测试复制后只读 | `MockAPIService`、`scripts/validate_mock_data.py` | 本轮不移动。移动需同步 mock 执行动作和校验脚本。 | `backend/data/fixtures/mock_inventory.json` | 中 |
| `mock_weather.json` | mock source / 天气 fixture | 运行时只读；测试复制后只读 | `MockAPIService` | 本轮不移动。引用少，但应和其他 mock fixture 一起迁移。 | `backend/data/fixtures/mock_weather.json` | 低-中 |
| `plans.json` | runtime store / 用户计划和候选计划 | 运行时读写；测试复制后读写，部分测试直接改文件制造异常 | `PlanService.FILE`、`RecoveryService.FILE`、`ExecutorService.PLANS_FILE`、`tests/test_verifier_service.py`、`tests/test_mock_api.py` | 本轮不移动。虽然服务端引用集中，但测试直接路径读写，且当前文件已积累到 MB 级运行态数据。 | `backend/data/runtime/plans.json` | 中 |
| `consensus.json` | runtime store / 共识会话与投票 | 运行时读写；测试复制后读写 | `ConsensusService.FILE` | 本轮不移动。服务引用集中，但应与 vote page / consensus 测试一起迁移。 | `backend/data/runtime/consensus.json` | 低-中 |
| `feedback.json` | runtime store / 用户反馈 | 运行时写入 | `FeedbackService.FILE` | 本轮不移动。引用集中，后续可和 runtime store 一起迁移。 | `backend/data/runtime/feedback.json` | 低 |
| `traces.json` | runtime store / trace 与 verifier log | 运行时追加写入；测试复制后读取 | `LoggingService.FILE`、`tests/test_orchestrator_llm_native_flow.py`、`tests/test_verifier_service.py`、`tests/test_mock_api.py` | 本轮不移动。测试直接读 `data_dir / "traces.json"`，且文件已积累到 MB 级运行态数据。 | `backend/data/runtime/traces.json` | 中 |

补充观察：

```text
backend/data/idempotency.json
backend/data/mock_idempotency_store.json
backend/data/executions.json
```

这些文件不在本轮指定清单中，但同样是 runtime store，且当前体积明显大于 fixture。后续若拆分 `fixtures/` 和 `runtime/`，应一并纳入 runtime 目录和测试隔离策略。

建议后续目标结构：

```text
backend/data/fixtures/
  mock_pois.json
  mock_routes.json
  mock_status.json
  mock_inventory.json
  mock_weather.json

backend/data/runtime/
  plans.json
  consensus.json
  feedback.json
  traces.json
  idempotency.json
  mock_idempotency_store.json
  executions.json
```

本轮结论：不移动任何 data 文件。下一轮如要移动，先增加集中路径常量或 JsonFileStore 路由层，再同步服务、测试 fixture 复制逻辑、`scripts/validate_mock_data.py`、README / CODE_MAP / MAINTENANCE_RULES，并重新跑全量验证。
