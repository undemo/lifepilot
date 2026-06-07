# LifePilot 代码地图

生成时间：2026-06-03，Asia/Shanghai。

本文件是后续 Agent 的快速定位入口。提交版已移除旧版 `agent_docs/CODEMAP.md`，避免重复代码地图造成评审误判。

## 用户输入在哪里处理

| 环节 | 文件 | 说明 |
|---|---|---|
| 首页输入 | `frontend/app/page.tsx` | 用户输入自然语言目标、选择快捷场景、设置区域/时间锚点。 |
| API 调用 | `frontend/lib/api.ts` | `api.createPlan` 调用 `POST /api/v1/plans/create`，统一带 trace/idempotency header。 |
| 路由入口 | `backend/app/api/v1/plans.py` | `/api/v1/plans/create` 读取请求、校验 header、调用 `PlanService.create_plan`。 |
| 服务门面 | `backend/app/services/plan_service.py` | 处理幂等、调用 orchestrator、保存主计划和候选计划。 |

## 语义解析在哪里

| 模块 | 文件 | 说明 |
|---|---|---|
| 主编排 | `backend/app/services/agent_orchestrator.py` | 串起解析、检索、生成、校验、排序、响应组装。 |
| 意图解析 | `backend/app/services/intent_parser.py` | 规则 + 可选模型，识别人群、关系、场景和偏好。 |
| 约束抽取 | `backend/app/services/constraint_extractor.py` | 抽取预算、时间、区域、排队、步行、饮食等硬/软约束。 |
| 潜在意图 | `backend/app/services/latent_intent_interpreter.py` | 将隐性情绪/关系诉求转成可计算意图。 |
| 餐饮语义 | `backend/app/services/food_semantic_agent.py` | 处理餐饮偏好、菜系、轻食、氛围等语义。 |
| 活动语义 | `backend/app/services/activity_semantic_agent.py` | 处理亲子、散步、手作、放松等活动语义。 |
| 检索意图 | `backend/app/services/retrieval_intent_compiler.py` | 把上游语义压缩成候选检索可用的 machine intent。 |

## 候选检索在哪里

| 模块 | 文件 | 说明 |
|---|---|---|
| 候选检索 | `backend/app/services/candidate_retriever.py` | 保留外部接口 `CandidateRetriever.retrieve(...)`；内部负责 POI、状态、路线、天气、预算和 PlanB 候选。 |
| 候选批评 | `backend/app/services/candidate_critic_agent.py` | 对候选组合做质量检查和降噪。 |
| MockAPI | `backend/app/services/mock_api_service.py` | 读取数字孪生 fixture，提供 POI、状态、路线、天气、口碑和执行模拟。 |
| POI 特征 | `backend/app/rules/poi_feature_store.py` | POI 特征 overlay 和 raw_poi_tag 到 machine_tag 的派生。 |
| 推荐策略 | `backend/app/rules/recommendation_policy_engine.py` | 约束、场景、避让和标签策略。 |
| taxonomy | `backend/app/rules/recommendation_taxonomy.py` | `TagDefinition`、display label、rule keyword 和标签 helper 的唯一权威来源。 |

## 计划生成在哪里

| 模块 | 文件 | 说明 |
|---|---|---|
| 草案生成 | `backend/app/services/plan_generator.py` | 保留外部接口 `PlanGenerator.generate(...)`；基于候选组合生成时间线草案。 |
| 合同构建 | `backend/app/services/plan_contract_builder.py` | 把内部草案转成 `PlanContract`，生成 ToolAction、预算、PlanB 等结构。 |
| 排序 | `backend/app/services/plan_ranker.py` | 规则化选择更稳的计划。 |
| 解释 | `backend/app/services/explanation_agent.py` | 生成用户可理解解释。 |

## 校验在哪里

| 模块 | 文件 | 说明 |
|---|---|---|
| 可执行性校验 | `backend/app/services/verifier_service.py` | 检查预算、时间窗、路线、天气、余位、排队、ToolAction 和执行窗口。 |
| Schema 校验 | `backend/app/services/schema_validator.py` | 校验 PlanContract 结构和关键字段。 |
| 执行前检查 | `backend/app/services/executor_service.py` | 执行模拟前再次依赖 Verifier 判断是否可进入执行。 |
| Recovery | `backend/app/services/recovery_service.py` | 执行受阻时生成版本化替代方案，保留 original/replacement/diff/updated_plan_id。 |

## 响应组装在哪里

| 模块 | 文件 | 说明 |
|---|---|---|
| 响应组装 | `backend/app/services/response_assembler.py` | 输出完整 contract 和用户可见投影，不暴露 DraftPlan。 |
| 标准响应 | `backend/app/core/responses.py` | 统一 `success/data/error/trace_id` 格式。 |
| 错误处理 | `backend/app/core/errors.py` | 统一 AppError、错误码、recoverable 和 user_message。 |

## 前端在哪里展示

| 页面/组件 | 文件 | 说明 |
|---|---|---|
| 首页 | `frontend/app/page.tsx` | 输入目标并发起创建。 |
| 生成页 | `frontend/app/plans/creating/page.tsx` | 展示前端体验进度，最终以 API 计划为准。 |
| 计划页 | `frontend/app/plans/[planId]/page.tsx` | 加载计划和可见 trace 摘要，展示目标、时间线、路线、预算、风险、PlanB、工具摘要。 |
| 计划卡片 | `frontend/components/plan/PlanCards.tsx` | 计划页核心展示组件。 |
| 执行页 | `frontend/app/execution/[executionId]/page.tsx` | 展示模拟执行结果、凭证和恢复记录。 |
| 投票/共识 | `frontend/app/vote/[votePageId]/page.tsx`、`frontend/app/consensus/[consensusSessionId]/page.tsx` | 朋友局投票和最终共识方案。 |
| ViewModel | `frontend/lib/view-models.ts` | 前端只做展示兜底和内部词隐藏；标签中文 fallback 不作为业务权威。 |
| 类型 | `frontend/types/schema.ts`、`frontend/types/view-model.ts` | 手写 TS 契约类型和展示类型。 |

## 数据源在哪里

| 数据 | 文件/目录 | 说明 |
|---|---|---|
| 路径常量 | `backend/app/core/data_paths.py` | data JSON 路径唯一集中入口。 |
| fixture 目录 | `backend/data/fixtures/` | 稳定 Mock source，不承载运行态写入。 |
| POI | `backend/data/fixtures/mock_pois.json` | Demo POI fixture。 |
| 状态 | `backend/data/fixtures/mock_status.json` | 餐厅/活动等状态快照。 |
| 库存 | `backend/data/fixtures/mock_inventory.json` | 余桌、余票、场次等 Mock 库存。 |
| 路线 | `backend/data/fixtures/mock_routes.json` | 模拟路线和转场时长。 |
| 天气 | `backend/data/fixtures/mock_weather.json` | 区域天气窗口。 |
| 失败场景 | `backend/data/mock_failure_scenarios.json` | 执行失败和恢复触发 fixture。 |
| 运行态 | `backend/data/runtime/plans.json`、`consensus.json`、`feedback.json`、`executions.json`、`traces.json`、`idempotency.json`、`runtime_activity_pois.json` | 本地 Demo 运行态数据。 |
| 高德工具输出 | `tools/gaode_data_factory/`、`reports/gaode_dryrun_20260524/` | 数据采集、转换和历史 dry-run。 |
| Qwen 工具输出 | `tools/qwen_data_factory/` | 数据生成实验和报告。 |

## 测试在哪里

| 类型 | 文件/命令 | 说明 |
|---|---|---|
| 后端全量 | `python -m pytest tests` | 后端测试集合。 |
| P0 后端 | `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/run_backend_p0_tests.py` | 项目自带 P0 回归。 |
| 契约扫描 | `PYTHONPATH=backend python3 scripts/contract_scan.py` | 扫旧路径、旧字段、禁止文案。 |
| Mock 数据校验 | `PYTHONPATH=backend python3 scripts/validate_mock_data.py` | 检查 Mock 数据完整性。 |
| 前端类型 | `cd frontend && npm run typecheck` | TS 类型检查。 |
| 前端 lint | `cd frontend && npm run lint` | ESLint CLI，使用 Next 配置。 |
| 前端 e2e | `cd frontend && npm run e2e` | Playwright 用例。 |

## 脚本在哪里

| 脚本 | 说明 |
|---|---|
| `scripts/run_backend_p0_tests.py` | 后端 P0 测试集合。 |
| `scripts/contract_scan.py` | 契约和禁止词扫描。 |
| `scripts/validate_mock_data.py` | Mock 数据校验。 |
| `scripts/run_p0_frontend_smoke.py` | 启动前后端并跑 smoke。 |
| `scripts/run_phase0_golden_cases.py` | golden case runner。 |
| `scripts/verify_submission.sh` | 提交版聚合验证。 |
| `scripts/check_submission_clean.sh` | 提交前清洁检查。 |
| `tools/gaode_data_factory/*` | 高德数据生成、比较和 viewer。 |
| `tools/qwen_data_factory/*` | Qwen 数据工厂和离线生成。 |
