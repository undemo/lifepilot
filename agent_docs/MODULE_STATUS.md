# 模块状态表

状态取值：`implemented`、`partial`、`fake_or_hardcoded`、`missing`、`unknown`。

## 02/05 目标架构与当前实现对照

| 目标模块 | 当前位置 | 状态 | 说明 |
|---|---|---:|---|
| 展示层 | `frontend/app`、`frontend/components` | implemented | P0 主页面已存在，并通过后端 API 获取数据。 |
| API 层 | `backend/app/api/v1/*`、`backend/app/api/mock.py` | partial | Plan、Consensus、Vote、Feedback、Memory、Mock P0 路径存在；通用追踪、执行记录、基准评测 API 缺失。 |
| 日志与 Trace | `backend/app/services/logging_service.py` | partial | 已有 Trace 写入和 plan 维度 Trace 投影；缺通用 `/api/v1/traces/*`。 |
| Agent Orchestrator | `backend/app/services/agent_orchestrator.py` | implemented | 串起 parser、extractor、retriever、generator、builder、verifier、ranker、assembler。 |
| InputGateway | FastAPI 中间件 + `plans.py` | partial | Trace 在中间件初始化，但没有独立命名模块。 |
| IntentParser | `backend/app/services/intent_parser.py` | implemented | 规则 + 可选 Qwen；P0 场景测试通过。 |
| ConstraintExtractor | `backend/app/services/constraint_extractor.py` | implemented | 基于规则抽取人数、时间、预算、排队、饮食、情绪等约束。 |
| MemoryRetriever | `backend/app/services/life_memory_service.py` | partial | 已有 LifeMemory 读写与候选确认；规划链路主要消费反馈候选和低敏资料。 |
| CandidateRetriever | `backend/app/services/candidate_retriever.py` | implemented | 使用 MockAPI 搜索候选、状态、路线和天气。 |
| MockAPI 服务 | `backend/app/services/mock_api_service.py`、`backend/app/api/mock.py` | implemented | 06 中 11 个 Mock 路径均已实现；本次 Mock 校验通过。 |
| PlanGenerator | `backend/app/services/plan_generator.py` | partial | 能生成内部草案；主要是规则/模板，Qwen 只辅助文案。 |
| PlanContractBuilder | `backend/app/services/plan_contract_builder.py` | implemented | 草案转 PlanContract，补齐执行动作和默认 PlanB。 |
| SchemaValidator | `backend/app/services/schema_validator.py` | partial | 只做最小结构校验，不是完整 03 JSON Schema 校验器。 |
| VerifierService | `backend/app/services/verifier_service.py` | implemented | 校验时间线、路线、预算、ToolAction、状态、天气和可执行窗口。 |
| PlanRanker | `backend/app/services/plan_ranker.py` | partial | 有规则排序，没有 reward/rerank 模型。 |
| ResponseAssembler | `backend/app/services/response_assembler.py` | partial | 返回完整 contract 和用户可见投影；后续 GET 主要还是 full contract。 |
| ExecutorService | `backend/app/services/executor_service.py` | implemented | 通过 MockAPI 执行 ToolAction，支持幂等和恢复。 |
| Recovery 规划/服务 | `backend/app/services/recovery_service.py` | implemented | 版本化 Recovery，支持换 POI 或刷新窗口。 |
| ConsensusService | `backend/app/services/consensus_service.py` | implemented | 支持建会话、投票、汇总、finalize 和最终方案重验。 |
| LifeMemoryService | `backend/app/services/life_memory_service.py` | implemented | Feedback 可生成 `MemoryCandidate`，Memory API 支持确认、忽略、编辑、删除和个性化开关。 |
| 数据层 | `backend/app/storage/json_store.py`、`backend/data/*.json` | implemented | 固定 fixture 与本地 runtime 分离；提交包不带运行态快照。 |
| 可观测性/调试 | `plans/{id}/trace`、debug 页面 | partial | 计划追踪可用；通用追踪/调试 API 缺失。 |
| BenchmarkEvaluator | 无 | missing | 只有 3 条 `benchmark_samples.json`，没有 evaluator/API/指标报告。 |

## P0 产品链路状态

| 链路 | 状态 | 说明 |
|---|---:|---|
| 自然语言 -> PlanContract | implemented | 后端测试脚本通过家庭、朋友、纪念日、单人散心创建用例。 |
| PlanContract -> Verifier -> 可执行窗口 | implemented | Verifier 和窗口字段存在，支持刷新窗口。 |
| 用户确认 -> Executor -> Mock 凭证 | implemented | 执行链路调用 MockAPI 并保存 `ExecutionResult`。 |
| 执行失败 -> Recovery | implemented | `NO_TABLE_AVAILABLE`、`ACTIVITY_FULL` 自动恢复；窗口过期恢复已测试。 |
| 朋友投票 -> Consensus -> 最终 PlanContract | implemented | 投票和 finalize 可用。 |
| Feedback -> MemoryCandidate | implemented | Feedback 可生成候选，Memory API 支持候选生命周期。 |
| LifeMemory 管理 | implemented | UI 和后端 API 已接通。 |
| 调试追踪 | partial | 计划追踪可用，通用追踪端点缺失。 |

## 前端模块状态

| 前端模块 | 状态 | 说明 |
|---|---:|---|
| 首页输入 | implemented | 支持 P0 预设和自定义输入。 |
| 生成中页面 | implemented | 展示规划服务事件流和补充偏好状态。 |
| 计划结果页 | implemented | 用 ViewModel 从 `PlanContract` 渲染。 |
| 时间线 | implemented | 常见标签已中文映射，普通页避免展示内部工程词。 |
| 可行性检查摘要 | implemented | 普通页压缩成 6 阶段；调试页可看脱敏 JSON。 |
| 投票页 | implemented | 支持提交和基础校验。 |
| 共识页 | implemented | 支持 finalize 和最终计划展示。 |
| 执行结果页 | partial | 依赖 `sessionStorage`，没有 `/executions/{id}` 后端读取接口。 |
| 反馈页 | partial | 能调用已实现的反馈接口。 |
| Memory 页 | implemented | 支持候选记忆确认、忽略和低敏资料展示。 |
| 调试页 | partial | Mock Center 可用；Trace 页面依赖缺失的通用追踪 API，除非带 `plan_id`。 |

## 数据与 Mock 状态

| 数据模块 | 状态 | 说明 |
|---|---:|---|
| 固定区域覆盖 | implemented | 500 个 POI 基本均分到下沙、金沙湖、高教园区。 |
| 数字孪生类别 | implemented | 活动、餐厅、散步点、服务点、交通锚点都存在。 |
| 场景化标签 | partial | 每个 POI 都标了三个 P0 场景，区分度不足。 |
| 路线图 | partial | 261 条路线足够 Demo 选链路，但不是完整区域图。 |
| 失败注入 | partial | 必需错误码存在；抽样看到的失败固定数据顶层目标字段不够细。 |
| 口碑信号 | partial | 固定数据和 API 存在，但当前主流程未充分集成。 |

## 测试与评测状态

| 评测项 | 状态 | 说明 |
|---|---:|---|
| 静态契约扫描 | implemented | `scripts/contract_scan.py`，本次实时运行通过。 |
| Mock 数据校验 | implemented | `scripts/validate_mock_data.py`，本次实时运行通过。 |
| 后端 P0 测试脚本 | implemented | `scripts/run_backend_p0_tests.py`，本次实时运行 8/8 通过。 |
| Pytest suite | unknown | 当前环境直接跑 `pytest`/`python -m pytest --version` 会 139 崩溃。 |
| Playwright E2E | implemented | 用例和历史通过报告存在；本次 X-Ray 未重跑前端长流程。 |
| Golden cases | partial | 只有 3 个基础 P0 样例，不是 08 里的 15 类基准评测。 |
| Contract tests | partial | 有静态扫描和后端测试，但没有完整 OpenAPI/Schema 契约套件。 |
| 可复现完整基准评测 | missing | 没有评测器、分数汇总或基准评测 API。 |
