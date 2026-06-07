# 契约差距报告

生成时间：2026-05-21。对照范围：00-08 文档与当前仓库实现。

## 来源文档差异

| 差异 | 严重度 | 说明 |
|---|---:|---|
| 用户要求读取 `03_data_schema.md`，仓库实际是 `docs/03_schema.md`。 | medium | 08 文档也提到过这个命名差异；`AGENTS.md` 已记录当前仓库以 `03_schema.md` 为 03 权威文件。 |
| 原仓库缺少 `AGENTS.md`。 | low | 本次已根据当前仓库和 00-08 补了最小版。 |

## 对照 02/05 的架构差距

| 模块 | 预期 | 当前实现 | 状态 |
|---|---|---|---:|
| LifeMemory | 独立服务、检索器、候选确认、用户可控。 | 已有 `LifeMemoryService`、记忆 API、候选确认/忽略、编辑/删除和个性化开关。 | implemented |
| MemoryRetriever | `use_memory=true` 时可读取已确认记忆。 | 记忆服务可读写低敏记忆；规划链路对长期画像的深度消费仍可继续增强。 | partial |
| BenchmarkEvaluator | 可运行评测并产出报告。 | 只有 3 条 `benchmark_samples.json`，没有 evaluator/API。 | missing |
| 通用追踪 API | `/api/v1/traces/{trace_id}` 和 `/events`。 | 前端会调用，后端没路由。 | missing |
| Execution 读取 API | `/api/v1/executions/{execution_id}` 可选/内部接口。 | 缺失；执行页依赖 `sessionStorage`。 | partial |
| 完整 SchemaValidator | 按 03 JSONSchema 校验嵌套字段、枚举、`additionalProperties=false`。 | 只做顶层必填、少量状态和敏感字段校验。 | partial |
| PlanReward/Reranker | P2 可选加分能力。 | 无 reward/rerank 模型。 | missing |

## 对照 04 的 API 差距

| 路径 / 规则 | 当前实现 | 影响 |
|---|---|---|
| `GET /api/v1/traces/*` | 未实现，前端 debug 页面已调用。 | 只有带 `plan_id` 走 plan trace 时可靠。 |
| `GET /api/v1/executions/{execution_id}` | 未实现。 | 执行结果页无法只凭 execution ID 恢复。 |
| 基准评测 API | 未实现。 | 没有可复现的基准评测 API 或报告。 |
| `POST /plans/{id}/refresh-window` | 实现为固定 12 分钟 warning 窗口。 | 能支撑 Demo，但不是完整的 MockAPI 重新查询链。 |
| Vote HTTP 幂等 | 前端传 key；服务主要用 `client_vote_token`。 | Demo 可用，但与 04 的 HTTP 幂等模型不完全一致。 |

## 对照 03/04 的 Schema 与字段差距

| 检查项 | 结果 | 说明 |
|---|---:|---|
| 运行时代码旧路径 `/api/mock`、`/api/plans/create` | 无阻塞 | 本次实时 `scripts/contract_scan.py` 通过。 |
| `ToolAction.type=create_order` | 无阻塞 | 运行时代码使用 `order_item`，扫描通过。 |
| 未定义 Trace event | 无阻塞 | 代码枚举与最终 event 列表一致，扫描通过。 |
| 未定义 `PlanContract.status` | 无阻塞 | Validator 中的状态枚举与 03 一致。 |
| 未定义 `VerifierResult.status` | 无阻塞 | Verifier 只使用 `pass/warning/fail`。 |
| `ToolAction.type` 覆盖 | partial | PlanContract 当前主要生成 `book_activity`、`reserve_restaurant`；Executor 支持 `order_item/send_message`；查询类动作记为日志，不进入 ToolAction。 |
| 完整嵌套 Schema | partial | `SchemaValidator` 没有完整校验嵌套字段、枚举、ID 前缀、ISO 时间和额外字段。 |
| Recovery legacy 字段 | 基本干净 | `RecoveryService` 使用 `original/replacement/diff`；BackupPlan 仍有 `original_poi_id/new_poi_id`，这是当前 BackupPlan Schema 允许的，但容易和旧 Recovery 字段混淆。 |
| 运行时数据里出现 `session_id` 字符串 | 良性 | 命中来自 `consensus_session_id`，不是泛化 `session_id` 字段。 |

## 对照 06 的 Mock 数据差距

| 要求 | 当前实现 | 状态 |
|---|---|---:|
| 固定数字孪生区域：下沙/金沙湖/高教园区 | 500 个 POI，三地基本均分。 | implemented |
| 不能只是随机 POI 列表 | 名称、区域、类别、状态、路线、天气都成层存在。 | partial |
| 生活时间线类别 | `activity`、`restaurant`、`walk_spot`、`service`、`transport_anchor` 都有。 | implemented |
| 场景化真实感 | 每个 POI 都适配三个 P0 场景，区分度不足。 | partial |
| 失败场景 | 必需错误码存在，校验通过。 | partial |
| Mock 透明性 | 广泛使用 `mock_only` 或 `source:"mock_api"`；测试也检查查询不返回凭证。 | implemented |
| SocialSignal P1 | 固定数据和 API 存在；当前主计划流里集成不充分。 | partial |

结论：Mock 数据已经不是“随机 POI”级别，它具备区域、类别、状态、路线、天气、库存和失败层。但它仍偏合成，场景标签过宽，路线图也不是完整区域图。

## 对照 07 的前端差距

| 要求 | 当前实现 | 状态 |
|---|---|---:|
| 前端不得消费 `DraftPlan` | 未发现前端直接消费。 | implemented |
| 只渲染完整 `PlanContract` 或合法投影 | 计划页从 `PlanContract` 通过 ViewModel 渲染；创建响应也有 `UserVisiblePlanProjection`。 | implemented |
| 不展示原始机器标签 | E2E 覆盖主要 raw tag；ViewModel 已映射常见标签。 | mostly implemented |
| 英文/技术标签 | 普通页面已通过 ViewModel 和展示文案收敛工程词；契约类型仍保留在代码层。 | mostly implemented |
| 普通页不展示调试信息 | 原始 payload、失败注入、prompt 未展示；普通页展示检查摘要，调试细节留在调试/评委路径。 | implemented |
| Memory UI 用户可控 | UI 与后端 Memory API 已接通，候选记忆可确认或忽略。 | implemented |
| 执行页按 `execution_id` 可恢复 | 没有后端读取 API，依赖 sessionStorage。 | partial |

## 对照 08 的评测差距

| 要求 | 当前实现 | 状态 |
|---|---|---:|
| 静态契约扫描 | `scripts/contract_scan.py`，本次实时通过。 | implemented |
| Mock 数据校验 | `scripts/validate_mock_data.py`，本次实时通过。 | implemented |
| 后端 P0 测试脚本 | `scripts/run_backend_p0_tests.py`，本次实时 8/8 通过。 | implemented |
| Pytest suite | 当前环境直接运行 `pytest` 139 崩溃。 | unknown |
| E2E 冒烟测试 | Playwright 用例存在，历史报告通过。 | implemented，但本次未重跑 |
| Golden / benchmark cases | 只有家庭、朋友、纪念日 3 个样例。 | partial |
| 15 类 LifePilot-Bench | 未实现。 | missing |
| Contract tests | 有静态扫描和后端测试；没有完整 schema/OpenAPI 契约套件。 | partial |
| 可复现指标报告 | 有历史冒烟报告；没有基准评测指标运行器。 | partial |

## 最主要的实际风险

1. Memory 是最大的产品缺口：UI 和契约有了，但后端服务与 API 没有。
2. Schema 校验太浅，不符合“契约驱动”的强度。
3. 运行时 JSON 和固定数据混在一起，演示复现性会受影响。
4. 普通页面仍有技术词；适合评委解释，但产品化不够干净。
5. 通用 Trace 和 Execution 读取 API 缺失，刷新和深链体验不完整。
6. 基准评测范围远小于 08：只有 3 个 golden case，没有评测器。
