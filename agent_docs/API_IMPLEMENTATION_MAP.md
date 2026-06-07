# API 实现对照表

当前代码里的业务 API 基础路径是 `/api/v1`。

## 已实现接口

| 契约区域 | 路径 | 控制器 | 服务层 | 状态 |
|---|---|---|---|---:|
| Plan | `POST /api/v1/plans/create` | `backend/app/api/v1/plans.py` | `PlanService` -> `AgentOrchestrator` | implemented |
| Plan | `GET /api/v1/plans/{plan_id}` | 同上 | `PlanService.get_plan_payload` | implemented |
| Plan | `POST /api/v1/plans/{plan_id}/verify` | 同上 | `PlanService.verify_plan` -> `VerifierService` | implemented |
| Plan | `POST /api/v1/plans/{plan_id}/execute` | 同上 | `ExecutorService.execute_plan` | implemented |
| Plan | `POST /api/v1/plans/{plan_id}/recover` | 同上 | `RecoveryService.recover_plan` | implemented |
| Plan | `POST /api/v1/plans/{plan_id}/refresh-window` | 同上 | `PlanService.refresh_window` | partial |
| Plan Trace | `GET /api/v1/plans/{plan_id}/trace` | 同上 | `LoggingService.list_for_plan` | implemented |
| Consensus | `POST /api/v1/consensus/create` | `backend/app/api/v1/consensus.py` | `ConsensusService.create_session` | implemented |
| Consensus | `GET /api/v1/consensus/{consensus_session_id}` | 同上 | `ConsensusService.get_session_payload` | implemented |
| Consensus | `POST /api/v1/consensus/{consensus_session_id}/vote` | 同上 | `ConsensusService.vote` | implemented |
| Consensus | `POST /api/v1/consensus/{consensus_session_id}/finalize` | 同上 | `ConsensusService.finalize` | implemented |
| Consensus | `GET /api/v1/consensus/{consensus_session_id}/summary` | 同上 | `ConsensusService.summary` | implemented |
| 投票页 | `GET /api/v1/vote-pages/{vote_page_id}` | `backend/app/api/v1/vote_pages.py` | `ConsensusService.get_vote_page` | implemented |
| Feedback | `GET /api/v1/feedback/questions?plan_id=...` | `backend/app/api/v1/feedback.py` | `FeedbackService.questions` | implemented |
| Feedback | `POST /api/v1/feedback` | 同上 | `FeedbackService.submit` | implemented |
| Memory | `GET /api/v1/memory` | `backend/app/api/v1/memory.py` | `LifeMemoryService.get_memory` | implemented |
| Memory | `GET /api/v1/memory/candidates` | 同上 | `LifeMemoryService.get_candidates` | implemented |
| Memory | `POST /api/v1/memory/candidates/{candidate_id}/confirm` | 同上 | `LifeMemoryService.confirm_candidate` | implemented |
| Memory | `POST /api/v1/memory/candidates/{candidate_id}/ignore` | 同上 | `LifeMemoryService.ignore_candidate` | implemented |
| Memory | `PATCH /api/v1/memory/{memory_id}` | 同上 | `LifeMemoryService.update_memory` | implemented |
| Memory | `DELETE /api/v1/memory/{memory_id}` | 同上 | `LifeMemoryService.delete_memory` | implemented |
| Memory | `POST /api/v1/memory/personalization/disable` | 同上 | `LifeMemoryService.set_personalization` | implemented |
| Memory | `POST /api/v1/memory/personalization/enable` | 同上 | `LifeMemoryService.set_personalization` | implemented |
| Mock | `GET /api/v1/mock/poi/search` | `backend/app/api/mock.py` | `MockAPIService.search_pois` | implemented |
| Mock | `GET /api/v1/mock/restaurants/search` | 同上 | `MockAPIService.search_restaurants` | implemented |
| Mock | `GET /api/v1/mock/poi/{poi_id}/status` | 同上 | `MockAPIService.poi_status` | implemented |
| Mock | `GET /api/v1/mock/restaurants/{poi_id}/status` | 同上 | `MockAPIService.restaurant_status` | implemented |
| Mock | `GET /api/v1/mock/routes/estimate` | 同上 | `MockAPIService.estimate_route` | implemented |
| Mock | `GET /api/v1/mock/weather` | 同上 | `MockAPIService.weather` | implemented |
| Mock | `POST /api/v1/mock/activities/{poi_id}/book` | 同上 | `MockAPIService.book_activity` | implemented |
| Mock | `POST /api/v1/mock/restaurants/{poi_id}/reserve` | 同上 | `MockAPIService.reserve_restaurant` | implemented |
| Mock | `POST /api/v1/mock/orders/create` | 同上 | `MockAPIService.order_item` | implemented |
| Mock | `POST /api/v1/mock/messages/send` | 同上 | `MockAPIService.send_message` | implemented |
| Mock | `GET /api/v1/mock/social-signals/{poi_id}` | 同上 | `MockAPIService.social_signal` | implemented / P1 |

## 契约里有、当前没接上的接口

| 契约路径 | 前端是否调用 | 后端状态 | 影响 |
|---|---:|---:|---|
| `GET /api/v1/executions/{execution_id}` | 否 | missing | 执行结果页只能从 `sessionStorage` 或 plan payload 恢复。 |
| `GET /api/v1/executions/{execution_id}/actions` | 否 | missing | 没有独立的 action 级执行记录读取接口。 |
| `GET /api/v1/traces/{trace_id}` | 是 | missing | 调试追踪页只有带 `plan_id` 走计划追踪时可靠。 |
| `GET /api/v1/traces/{trace_id}/events` | 是 | missing | 同上。 |
| `GET /api/v1/plans/{plan_id}/debug` | 否 | missing | P1 调试端点缺失。 |
| `GET /api/v1/benchmarks/samples` | 否 | missing | 没有基准评测 API。 |
| `POST /api/v1/benchmarks/run` | 否 | missing | 没有评测执行器。 |
| `GET /api/v1/benchmarks/runs/{run_id}` | 否 | missing | 没有评测运行记录 API。 |

## 请求与响应契约

| 关注点 | 当前实现 | 状态 |
|---|---|---:|
| 标准响应结构 | `success`、`trace_id`、`data`、`error` 由统一 helper 生成。 | implemented |
| 基础路径 | 前后端都使用 `/api/v1`。 | implemented |
| Trace ID | 中间件缺失时生成 `trace_`；前端会生成 `trace_web_*`。 | implemented |
| Execute 幂等 | `ExecutorService` 强制要求 `X-Idempotency-Key`，缺失返回 `BAD_REQUEST`。 | implemented |
| Mock 执行幂等 | `MockAPIService` 强制执行幂等并检测冲突。 | implemented |
| Plan create 幂等 | 有 key 时缓存；不是强制。 | implemented |
| Consensus create 幂等 | 有 key 时缓存；不是强制。 | implemented |
| Vote 幂等 | 主要靠 `client_vote_token` 更新投票；HTTP 幂等键没有成为核心存储键。 | partial |
| 调试信息可见性 | 计划追踪默认返回用户可见投影；调试页可请求更多。 | partial |

## Schema 与字段契约

| 项目 | 预期 | 当前实现 | 状态 |
|---|---|---|---:|
| `PlanContract.status` | 03 枚举 | 代码枚举与 03 一致。 | implemented |
| `PlanStep.type` | 03 枚举含 `transport/activity/restaurant/walk/service/message/buffer/return_home` | 当前生成 `activity/transport/restaurant/walk/service`；Validator 不完整校验枚举。 | partial |
| `ToolAction.type` | 03 枚举含查询和执行动作 | 当前计划动作只生成 `book_activity`、`reserve_restaurant`；Executor 支持 `order_item/send_message`；查询动作作为日志而非 ToolAction。 | partial |
| `VerifierResult.status` | `pass/warning/fail` | Verifier 和 Validator 都按这三类处理。 | implemented |
| `TraceLog.event_type` | 03/05 最终枚举 | `TraceEventType` 与最终枚举一致，契约扫描通过。 | implemented |
| `RecoveryResult` 字段 | `original`、`replacement`、`diff`、`updated_plan_id` | `RecoveryService` 输出该结构，并校验旧字段。 | implemented |
| 完整 JSON Schema | Draft 2020-12，嵌套 schema，`additionalProperties=false` | `SchemaValidator` 只是最小结构校验，没有完整覆盖嵌套字段和枚举。 | partial |

## 前端 API 超前点

`frontend/lib/api.ts` 的记忆调用已有对应后端路由。通用追踪页如果没有 `plan_id` 查询参数，仍会因为 `/api/v1/traces/*` 缺失而失败。
