# 07_frontend_design.md

## 1.文档信息

| 项目 | 内容 |
| --- | --- |
| 文档名称 | LifePilot前端设计文档 |
| 产品名称 | LifePilot |
| 产品定位 | 生活时间导航Agent |
| 核心隐喻 | 高德导航一段路，LifePilot导航一段生活时间 |
| 技术假设 | React/Next.js Web Demo，移动端优先，桌面端适配 |
| 主要读者 | 前端、后端、Agent、Mock、测试、评委Demo负责人 |
| 权威来源 | `00_project_vision.md`、`01_prd.md`、`02_system_architecture.md`、`03_schema.md`、`04_api_contract.md`、`05_agent_workflow.md`、`06_mock_api_design.md` |
| 本文定位 | 07只定义前端如何组织页面、组件、状态、接口联调、错误展示、Mock呈现和验收，不重新定义领域Schema或HTTP契约 |

## 2.文档目标与边界

本文回答LifePilot Web Demo前端如何把“自然语言目标到可执行生活时间导航”的闭环做成可用界面。

前端承担的角色：

| 问题 | 07中的回答 |
| --- | --- |
| 前端在系统中做什么 | 把完整`PlanContract`或合法`UserVisiblePlanProjection`映射为用户可理解的时间线、窗口、风险、PlanB、工具链和执行结果 |
| 页面如何组织 | 使用Next.js App Router组织首页、生成页、计划页、投票页、共识页、执行页、反馈页、Memory页、Debug Trace页 |
| 状态如何流转 | 页面级UI state只服务展示，不替代`PlanContract.status`、`ToolAction.status`、`ExecutionResult.status` |
| API如何调用 | 所有业务接口使用04最终`/api/v1`路径，统一解析`success/data/error`，关键写操作携带`trace_id`和`X-Idempotency-Key` |
| Mock如何展示 | 明确标注“Mock/模拟”，普通用户不看到`failure_injection`，不伪装真实平台能力 |
| Recovery如何展示 | 显示`RecoveryResult.original/replacement/diff`和`updated_plan_id`，不把新方案写成原计划原地覆盖 |
| LifeMemory如何展示 | 低打扰、可审计、用户可控；候选需用户确认或忽略，不偷偷写画像 |
| 测试如何验收 | 给出页面、数据契约、错误处理、Mock边界、移动端、Debug的验收清单 |

本文不做：

| 不做 | 原因 |
| --- | --- |
| 不复制03完整Schema | 字段、必填项、枚举以03为准 |
| 不复制04完整API契约 | 路径、响应、错误码、幂等以04为准 |
| 不重新写Agent编排 | Agent主链路以05为准 |
| 不定义MockAPI实现 | Mock接口和fixture边界以06为准 |
| 不设计原生App | 当前技术假设是React/Next.js Web Demo |
| 不承诺真实交易或真实第三方能力 | P0只做Mock执行和Mock口碑 |

## 3.来源文档与契约优先级

| 优先级 | 来源 | 07使用方式 |
| ---: | --- | --- |
| 1 | `03_schema.md` | 字段名、ID前缀、对象、状态、Trace事件名、ToolAction.type最终权威 |
| 2 | `04_api_contract.md` | HTTP路径、标准响应、错误码、请求头、trace_id、幂等和Debug边界最终权威 |
| 3 | `05_agent_workflow.md` | Agent主链路、DraftPlan边界、Verifier闸门、Executor、Recovery、Consensus、LifeMemory流程 |
| 4 | `06_mock_api_design.md` | Mock标识、Mock展示文案、failure_injection可见性、Mock凭证边界 |
| 5 | `01_prd.md` | 页面范围、用户流程、P0/P1/P2范围、页面需求 |
| 6 | `02_system_architecture.md` | React/Next.js Web Demo、移动端优先、模块分层、前端在架构中的位置 |
| 7 | `00_project_vision.md` | 产品定位、核心隐喻、三类P0场景、价值表达 |

冲突处理：

| 冲突 | 处理 |
| --- | --- |
| 01/02早期路径与04冲突 | 统一使用04的`/api/v1`路径 |
| 01/02早期字段与03冲突 | 统一使用03字段 |
| 早期共识字段与03冲突 | 使用`consensus_session_id`、`vote_page_id`、`plan_group_id`、`vote_id` |
| 早期Recovery字段与03冲突 | 使用`original`、`replacement`、`diff`、`updated_plan_id` |
| Trace事件旧名与03/04/05冲突 | 只使用`input_log`、`intent_log`、`constraint_log`、`memory_log`、`poi_log`、`tool_log`、`verifier_log`、`recovery_log`、`executor_log`、`feedback_log`、`error_log` |
| 前端ViewModel与领域对象混淆 | ViewModel只命名为`PlanContractView`、`PlanSummary`、`UserVisiblePlanProjection`、`TimelineViewItem`、`ToolTraceViewItem`、`RecoveryDiffView`，不进入03 Schema |

## 4.前端总体设计原则

LifePilot前端不是聊天壳，而是PlanContract驱动的生活时间导航界面。用户输入一句话后，前端要让用户看到系统如何把目标理解为一段可执行的生活时间，而不是只展示一段LLM回答。

核心原则：

| 原则 | 前端落地 |
| --- | --- |
| PlanContract驱动 | 计划结果页只渲染完整`PlanContract`或合法`UserVisiblePlanProjection` |
| 时间线优先 | 页面围绕“这一段时间怎么过”组织，不做地点列表堆叠 |
| 移动端优先 | 375px宽度可完整演示，桌面端用居中移动端容器和辅助Debug面板 |
| 用户能理解 | 展示目标理解、时间线、路线、预算、风险、PlanB、可执行窗口、工具调用摘要 |
| 用户能确认 | 只有窗口有效、Verifier通过或warning可接受时，确认执行按钮可用 |
| 用户能追踪 | 所有关键流程展示或可进入`trace_id`，普通页展示简化工具链 |
| 用户不被误导 | Mock状态、Mock凭证、SocialSignalMock都显式标识，不伪装真实平台能力 |
| 用户隐私可控 | MemoryCandidate只做候选展示，确认/忽略由用户决定，高敏不展示不保存 |
| 评委可快速理解 | 3分钟内能跑通家庭亲子、朋友局共识、纪念日情绪导航中的至少一条完整闭环 |

前端必须写清楚并遵守：

```text
前端不直接渲染LLM DraftPlan；
前端不消费Agent内部DraftPlan或PlanBuildCandidate；
前端计划结果页只渲染完整PlanContract或合法UserVisiblePlanProjection；
前端执行只基于plan_id和ToolAction，不基于自然语言文案；
前端不能自行判断余位、票务、路线、天气或执行成功。
```

前端不得直接读写JSON、SQLite或Mock fixture。Demo存储由后端负责，前端只通过`/api/v1`接口交互。

## 5.前端在LifePilot架构中的位置

```text
User
  ↓
Next.js Web Demo
  ├── Page Router / App Router
  ├── Component Layer
  ├── ViewModel Mapper
  ├── API Client
  └── Debug/Trace Panel
  ↓
Backend API Service /api/v1
  ├── Plan APIs
  ├── Consensus APIs
  ├── Execution/Recovery
  ├── Feedback/Memory
  └── Trace APIs
  ↓
Agent Orchestrator / Verifier / Executor / Recovery / MockAPI
```

职责边界：

| 层 | 负责 | 不负责 |
| --- | --- | --- |
| 前端页面 | 输入、展示、确认、投票、反馈、Debug摘要 | 生成PlanContract、判断余位、执行真实动作 |
| 前端ViewModel | 字段格式化、排序、分组、用户可见投影 | 修改03领域对象语义 |
| API Client | 标准请求头、幂等键、错误解析、trace传递 | 绕过后端直接调用fixture |
| Backend API | 聚合Agent/Mock/Verifier结果并返回契约对象 | 暴露Prompt和推理链 |
| Agent/Mock/Verifier | 生成、校验、执行、恢复 | 让前端自行补状态 |

## 6.信息架构与页面路由

以下路由是前端UI路由，不是后端API。route param可使用驼峰，但对应领域字段必须使用03/04蛇形字段，例如`planId`对应`plan_id`。

| 前端路由 | 页面 | P0 | 入口 | 主要API | 读取对象 | 可见性 |
| --- | --- | ---: | --- | --- | --- | --- |
| `/` | 首页/一句话输入页 | 是 | 直接访问 | `POST /api/v1/plans/create` | UserGoal输入、创建响应 | 普通用户 |
| `/plans/creating` | 计划生成中页面 | 是 | 首页提交后 | 创建请求结果或本地进度投影 | Trace摘要、PlanContract返回 | 普通用户 |
| `/plans/[planId]` | 计划结果页 | 是 | 创建成功、共识最终方案、执行返回 | `GET /api/v1/plans/{plan_id}`、`POST /api/v1/plans/{plan_id}/verify`、`POST /api/v1/plans/{plan_id}/refresh-window`、`POST /api/v1/plans/{plan_id}/execute`、`GET /api/v1/plans/{plan_id}/trace` | PlanContract、TraceLog投影 | 普通用户 |
| `/vote/[votePageId]` | 朋友投票页 | 是 | 分享链接/二维码/模拟分享卡 | `GET /api/v1/vote-pages/{vote_page_id}`、`POST /api/v1/consensus/{consensus_session_id}/vote` | ConsensusSession投影、候选PlanSummary、ConsensusVote | 普通用户 |
| `/consensus/[consensusSessionId]` | 共识结果页 | 是 | 发起人查看或投票完成后 | `POST /api/v1/consensus/{consensus_session_id}/finalize`、`GET /api/v1/plans/{final_plan_id}`，可选`GET /api/v1/consensus/{consensus_session_id}/summary` | ConsensusSummary、PlanContract | 普通用户 |
| `/execution/[executionId]` | 执行结果页 | 是 | 确认执行后 | `GET /api/v1/plans/{plan_id}`，若04可用则`GET /api/v1/executions/{execution_id}` | ExecutionResult、RecoveryResult、ToolAction | 普通用户 |
| `/feedback/[planId]` | 低打扰反馈页 | 是 | 执行结果页 | `GET /api/v1/feedback/questions?plan_id=...`、`POST /api/v1/feedback`、`GET /api/v1/memory/candidates` | MemoryCandidate、Feedback问题 | 普通用户 |
| `/memory` | LifeMemory管理页 | P1，P0可预留入口 | 反馈页、设置入口 | `GET /api/v1/memory`、`GET /api/v1/memory/candidates`、Memory确认/忽略/编辑/删除接口 | LifeMemory、MemoryCandidate | 普通用户本人 |
| `/debug/traces/[traceId]` | Debug/评委工具调用链页面 | 评委模式 | Debug按钮、query、环境变量 | `GET /api/v1/traces/{trace_id}`、`GET /api/v1/traces/{trace_id}/events`、`GET /api/v1/plans/{plan_id}/trace` | TraceLog、ToolTraceViewItem | Debug/评委 |

页面通用要求：

| 状态 | 展示规则 |
| --- | --- |
| loading | 使用`LoadingSkeleton`，不要只显示空白页 |
| error | 普通用户只展示`error.user_message` |
| empty | 用`EmptyState`说明下一步动作 |
| trace | 页面底部或Debug入口显示`trace_id`摘要 |
| Mock | 普通页弱提示“Demo模拟数据”或“Mock/模拟凭证”，Debug页显示`source:"mock_api"`等脱敏字段 |

## 7.前端目录结构与技术栈建议

技术栈建议：

| 类别 | 建议 |
| --- | --- |
| 框架 | Next.js App Router |
| 语言 | TypeScript |
| 样式 | Tailwind CSS |
| 组件 | shadcn/ui或轻量自建组件 |
| 图标 | lucide-react |
| 请求状态 | React Query或SWR |
| 局部状态 | Zustand或轻量Context |
| 测试 | Playwright、Vitest、Testing Library |

建议目录：

```text
frontend/
├── app/
│   ├── page.tsx
│   ├── plans/
│   │   ├── creating/page.tsx
│   │   └── [planId]/page.tsx
│   ├── vote/[votePageId]/page.tsx
│   ├── consensus/[consensusSessionId]/page.tsx
│   ├── execution/[executionId]/page.tsx
│   ├── feedback/[planId]/page.tsx
│   ├── memory/page.tsx
│   └── debug/traces/[traceId]/page.tsx
├── components/
│   ├── plan/
│   ├── execution/
│   ├── consensus/
│   ├── memory/
│   ├── debug/
│   └── common/
├── lib/
│   ├── api.ts
│   ├── idempotency.ts
│   ├── trace.ts
│   ├── formatters.ts
│   ├── view-models.ts
│   └── constants.ts
├── types/
│   ├── schema.ts
│   ├── api.ts
│   └── view-model.ts
└── tests/
    ├── e2e/
    ├── components/
    └── fixtures/
```

`types/schema.ts`应从03 Schema手动同步或生成，不得随意改字段。前端展示层新增字段只能放入`types/view-model.ts`，并明确不进入03领域Schema或04 HTTP契约。

## 8.API Client、trace_id与幂等设计

### 8.1API Client基础封装

建议文件：

| 文件 | 职责 |
| --- | --- |
| `frontend/lib/api.ts` | 封装`request<T>()`、HTTP方法、标准响应解析、错误归一 |
| `frontend/lib/idempotency.ts` | 生成、复用、保存`idem_`前缀幂等键 |
| `frontend/lib/trace.ts` | 保存当前`trace_id`，支持页面间传递和Debug入口 |
| `frontend/lib/formatters.ts` | ISO时间、金额、距离、状态文案格式化 |
| `frontend/lib/view-models.ts` | 把03对象映射为前端ViewModel |

请求封装要求：

| 要求 | 规则 |
| --- | --- |
| Base Path | 所有业务请求使用`/api/v1` |
| Content-Type | 自动附带`Content-Type: application/json`和`Accept: application/json` |
| Demo用户 | 可选附带`X-Demo-User-Id` |
| trace | 写操作可附带`X-Trace-Id`；计划后续操作复用`PlanContract.trace_id` |
| 幂等 | 写操作生成或复用`X-Idempotency-Key`；执行类请求必须携带 |
| 响应 | 统一解析`success/data/error` |
| 用户错误 | 普通用户只展示`error.user_message` |
| Debug错误 | Debug面板可展示脱敏`error.details` |
| 时间 | 原始对象保留ISO 8601，展示层格式化 |

标准错误对象按04处理：

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "NO_TABLE_AVAILABLE",
    "message": "当前时间段4人位已满",
    "user_message": "原餐厅已满，我会尝试为你切换到备选餐厅。",
    "recoverable": true,
    "details": {}
  }
}
```

普通用户页面只展示`error.user_message`，不展示`error.message`或`details`。

### 8.2幂等键规则

| 接口 | 前端规则 |
| --- | --- |
| GET查询接口 | 天然幂等，不生成幂等键 |
| `POST /api/v1/plans/create` | 建议携带`X-Idempotency-Key` |
| `POST /api/v1/plans/{plan_id}/execute` | 必须携带`X-Idempotency-Key` |
| `POST /api/v1/plans/{plan_id}/recover` | 按04要求必须携带或至少强烈建议携带；前端实现按必须处理 |
| `POST /api/v1/consensus/{consensus_session_id}/vote` | 建议携带或使用`client_vote_token`支持更新 |
| Memory候选确认/忽略 | 建议携带，防止重复点击 |

前端可以生成`idem_`前缀幂等键并保存在页面状态或`sessionStorage`中，但不得把它写成03领域Schema字段。

执行按钮规则：

1. 点击确认执行后立即进入loading/disabled。
2. 同一个执行动作重复点击，不得生成新的幂等键。
3. 页面刷新后，如果已有`execution_id`或本地幂等记录，应恢复当前执行状态，而不是重复执行。
4. `ToolAction.idempotency_key`不能替代HTTP Header `X-Idempotency-Key`。
5. `IDEMPOTENCY_CONFLICT`只提示不要重复提交，提供刷新或返回计划页入口。

### 8.3关键API调用表

| 页面 | API | 触发时机 | 幂等 | 成功后 |
| --- | --- | --- | --- | --- |
| 首页 | `POST /api/v1/plans/create` | 点击生成 | 建议 | 保存`plan_id`、`trace_id`，进入生成页或计划页 |
| 计划页 | `GET /api/v1/plans/{plan_id}` | 首屏和刷新 | GET天然幂等 | 渲染PlanContract |
| 计划页 | `POST /api/v1/plans/{plan_id}/verify` | 手动重新校验或Debug复验 | POST接口，逻辑幂等 | 更新Verifier摘要，不绕过后端 |
| 计划页 | `POST /api/v1/plans/{plan_id}/refresh-window` | 窗口过期后点击刷新 | 建议 | 更新PlanContract或可执行窗口 |
| 计划页 | `POST /api/v1/plans/{plan_id}/execute` | 点击确认执行 | 必须 | 进入执行页，保存`execution_id`和`active_plan_id` |
| 执行页 | `POST /api/v1/plans/{plan_id}/recover` | 执行失败后手动恢复或自动恢复兜底 | 必须 | 展示`RecoveryResult`和`updated_plan_id` |
| 计划页/Debug | `GET /api/v1/plans/{plan_id}/trace` | 展开工具链 | GET天然幂等 | 渲染用户可见Trace摘要 |
| 投票页 | `GET /api/v1/vote-pages/{vote_page_id}` | 首屏 | GET天然幂等 | 渲染候选方案 |
| 投票页 | `POST /api/v1/consensus/{consensus_session_id}/vote` | 提交投票 | 建议 | 展示已提交 |
| 共识页 | `POST /api/v1/consensus/{consensus_session_id}/finalize` | 发起人生成最终方案 | 建议 | 展示`ConsensusSummary`和最终计划 |
| 执行页 | `GET /api/v1/plans/{plan_id}` | 首屏/刷新 | GET天然幂等 | 展示执行摘要和Recovery |
| 反馈页 | `GET /api/v1/feedback/questions?plan_id=...` | 首屏 | GET天然幂等 | 渲染最多2个问题 |
| 反馈页 | `POST /api/v1/feedback` | 提交/跳过 | 建议 | 展示MemoryCandidate |
| Memory页 | `GET /api/v1/memory`、`GET /api/v1/memory/candidates` | 首屏 | GET天然幂等 | 渲染记忆列表和候选 |
| Debug页 | `GET /api/v1/traces/{trace_id}`、`GET /api/v1/traces/{trace_id}/events` | 首屏 | GET天然幂等 | 渲染脱敏Trace |

## 9.前端数据模型与ViewModel映射

### 9.1前端消费对象

前端必须直接或间接消费以下03对象，但不修改对象本体：

```text
PlanContract
PlanStep
Participant
ConstraintSet
ExecutableWindow
Budget
Risk
BackupPlan
ToolAction
VerifierResult
ExecutionResult
RecoveryResult
POI
POIStatus
RestaurantStatus
RouteEstimate
WeatherStatus
ConsensusSession
ConsensusVote
ConsensusSummary
MemoryCandidate
LifeMemory
SocialSignalMock
TraceLog
```

允许的前端ViewModel：

```text
PlanContractView
PlanSummary
UserVisiblePlanProjection
TimelineViewItem
ToolTraceViewItem
RecoveryDiffView
```

这些ViewModel只存在于前端展示层，不进入03 Schema或04 HTTP契约。

### 9.2PlanContract渲染映射

| 03字段 | 前端组件 | 展示方式 |
| --- | --- | --- |
| `user_goal.goal_summary` | `PlanGoalSummary` | 顶部目标理解 |
| `participants` | `PlanGoalSummary` | 同行人标签 |
| `constraints` | `PlanGoalSummary` | 距离/饮食/预算/排队约束 |
| `timeline` | `PlanTimeline` | 纵向生活时间线 |
| `timeline[].estimated_route` | `MapRoutePanel` | 路线耗时、交通方式、转场说明 |
| `budget` | `BudgetCard` | 总预算、人均、拆分 |
| `executable_window` | `ExecutableWindowCard` | 倒计时、有效期、原因 |
| `risks` | `RiskCard` | 风险轻提示 |
| `backup_plans` | `BackupPlanCard` | PlanB/改道 |
| `tool_actions` | `ToolTracePanel`或Debug | 用户可见动作摘要，Debug显示脱敏payload |
| `verifier_result` | `ToolTracePanel`/Debug | 校验结果摘要 |
| `recovery_results` | `RecoveryDiffCard` | 恢复记录与差异 |
| `execution_summary` | `ExecutionVoucherCard` | 执行结果和Mock凭证 |
| `memory_usage` | `MemoryUsageNotice` | 本次使用记忆解释 |
| `social_signals` | `SocialSignalMockCard` | 口碑雷达Mock卡 |

前端可生成`UserVisiblePlanProjection`用于页面首屏或分享页，但完整执行仍依赖完整`PlanContract`和`plan_id`。

### 9.3ToolAction.type展示映射

| ToolAction.type | 用户可见文案 | Debug说明 |
| --- | --- | --- |
| `get_poi_status` | 已检查活动状态 | MockAPIService状态查询摘要 |
| `get_restaurant_status` | 已检查餐厅余位 | 不展示底层fixture |
| `estimate_route` | 已估算路线时间 | 展示路线耗时和交通模式 |
| `get_weather` | 已检查天气风险 | 展示天气风险摘要 |
| `book_activity` | 活动预约Mock处理中 | 成功后显示“Mock预约号已生成” |
| `reserve_restaurant` | 餐厅订座Mock处理中 | 成功后显示“Mock订座号已生成” |
| `order_item` | 订单Mock处理中 | 成功后显示“Mock订单号已生成” |
| `send_message` | 模拟消息生成中 | 成功后显示“模拟消息已生成” |

不得使用`create_order`作为`ToolAction.type`。

## 10.首页/一句话输入页设计

### 首页/一句话输入页

#### 页面定位

首页是LifePilot主闭环入口。用户用一句自然语言表达“这一段生活时间想怎么过”，前端提交给Plan API，由后端Agent生成并验证`PlanContract`。

#### 是否P0

是。

#### 页面路由

`/`

#### 入口与出口

| 入口 | 出口 |
| --- | --- |
| 用户直接打开Web Demo | 提交成功进入`/plans/creating`，创建完成后进入`/plans/[planId]` |

#### 依赖API

`POST /api/v1/plans/create`

#### 读取对象

用户输入、创建响应中的`plan_id`、`trace_id`、`plan_contract`、可选`candidate_plan_ids`、`memory_candidates`。

#### 页面模块

| 模块 | 说明 |
| --- | --- |
| `HomeInputCard` | 一句话输入框和提交按钮 |
| `ScenarioQuickCards` | 三个P0快捷卡片：家庭亲子、朋友局、纪念日 |
| 隐私提示 | “记忆低打扰、可审计、用户可控” |
| Demo说明弱提示 | “本Demo使用模拟状态与Mock凭证” |

#### 核心交互

1. 支持自然语言输入。
2. 支持三个快捷卡片：家庭亲子、朋友局、纪念日。
3. 空输入和少于5字时禁用按钮或提示补充目标。
4. 点击生成调用`POST /api/v1/plans/create`。
5. 前端生成并复用`X-Idempotency-Key`。
6. 快捷卡片传`scenario_hint`只作为参考，Agent仍需校验。
7. 提交后进入计划生成中页面。
8. 不展示底层模型状态、Prompt或推理链。

#### 状态机

以下为前端UI state，不进入03 Schema：

```text
idle
input_invalid
submitting
submitted
failed
```

#### 错误处理

| 错误码 | 展示 |
| --- | --- |
| `BAD_REQUEST` | 展示`error.user_message`，保留输入 |
| `TRACE_ID_MISSING` | 提示系统追踪异常，请重试 |
| `IDEMPOTENCY_CONFLICT` | 提示不要重复提交，刷新或重新输入 |
| `PLAN_SCHEMA_INVALID` | 提示计划结构生成失败，可重试 |
| `RATE_LIMITED` | 提示稍后再试 |

#### Mock与隐私边界

首页可以说明Demo使用模拟状态，但不得写“已接入真实商家”“已实时抓取平台”。隐私提示只能表达可控候选，不写“系统已自动记住你的家庭情况”。

#### 组件拆分

`AppShell`、`MobileFrame`、`HomeInputCard`、`ScenarioQuickCards`、`ErrorState`、`LoadingSkeleton`。

#### 示例文案

```text
开始导航这一段生活时间
```

```text
告诉我你想怎么过这一段时间，例如：今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。
```

#### 验收标准

1. 三个P0快捷卡片可填充输入。
2. 少于5字不能提交或有明确提示。
3. 请求路径为`POST /api/v1/plans/create`。
4. 请求建议携带`X-Idempotency-Key`。
5. 成功后保存`trace_id`和`plan_id`。
6. 不展示Prompt、模型链路或Mock fixture。

## 11.计划生成中页面设计

### 计划生成中页面

#### 页面定位

生成页展示LifePilot正在把自然语言目标转为结构化、可验证、可执行的生活时间计划。它不是普通loading spinner，而是结构化进度投影。

#### 是否P0

是。

#### 页面路由

`/plans/creating`

#### 入口与出口

| 入口 | 出口 |
| --- | --- |
| 首页提交成功后进入 | Plan创建成功进入`/plans/[planId]`；失败停留并展示重试 |

#### 依赖API

接收`POST /api/v1/plans/create`结果。若采用异步体验，前端可展示本地进度，但最终必须以API返回的`PlanContract`为准。

#### 读取对象

创建请求状态、`trace_id`、`PlanContract`、用户可见工具调用摘要。

#### 页面模块

| 模块 | 说明 |
| --- | --- |
| `GenerationProgress` | 展示结构化步骤 |
| `ToolTracePanel`简版 | 展示用户可见工具调用摘要 |
| `LoadingSkeleton` | 计划页骨架 |
| `ErrorState` | 失败重试 |

#### 核心交互

展示步骤：

```text
understanding：理解目标
extracting_constraints：抽取约束
retrieving_candidates：检索候选
checking_status：查询Mock状态
verifying：Verifier检查
building_plan：生成PlanB和PlanContract
completed：完成
failed：失败
```

这些状态是前端体验投影，不进入03 Schema。进度条可以按时间推进，但不得伪造工具真实结果。工具结果、可执行窗口、余位、票务、路线、天气必须以API最终返回对象为准。

#### 状态机

```text
understanding
extracting_constraints
retrieving_candidates
checking_status
verifying
building_plan
completed
failed
```

#### 错误处理

失败只展示`error.user_message`。`recoverable=true`展示“重试生成”；`recoverable=false`展示“返回首页”或“联系Demo负责人”。

#### Mock与隐私边界

可展示“正在检查当前模拟状态”，不展示`failure_injection`、底层Prompt、LLM推理链或API Key。

#### 组件拆分

`GenerationProgress`、`ToolTracePanel`、`LoadingSkeleton`、`ErrorState`。

#### 示例文案

```text
正在把你的目标拆成时间线、约束和可执行动作。
```

```text
正在检查当前模拟状态：活动余票、餐厅余位、路线时间和天气风险。
```

#### 验收标准

1. 至少展示4个进度步骤。
2. 最终跳转以API返回`plan_id`为准。
3. 不渲染LLM DraftPlan。
4. 不展示底层模型异常。
5. 不伪造真实状态结果。

## 12.计划结果页设计

### 计划结果页

#### 页面定位

计划结果页把完整`PlanContract`或合法`UserVisiblePlanProjection`渲染成用户可理解、可确认、可执行的一段生活时间导航。

#### 是否P0

是。

#### 页面路由

`/plans/[planId]`

#### 入口与出口

| 入口 | 出口 |
| --- | --- |
| 创建计划成功、共识最终方案、Recovery新方案 | 确认执行进入`/execution/[executionId]`；发起投票进入`/vote/[votePageId]`；窗口过期停留并刷新 |

#### 依赖API

```text
GET /api/v1/plans/{plan_id}
POST /api/v1/plans/{plan_id}/verify
POST /api/v1/plans/{plan_id}/refresh-window
POST /api/v1/plans/{plan_id}/execute
GET /api/v1/plans/{plan_id}/trace
POST /api/v1/consensus/create
```

#### 读取对象

`PlanContract`、`PlanStep`、`ExecutableWindow`、`Budget`、`Risk`、`BackupPlan`、`ToolAction`、`VerifierResult`、`TraceLog`投影、`SocialSignalMock`。

#### 页面模块

| 区块 | 组件 | 内容 |
| --- | --- | --- |
| 目标理解区 | `PlanGoalSummary` | `user_goal`、`participants`、`constraints` |
| 时间线区 | `PlanTimeline`、`TimelineStepCard` | `timeline` |
| 地图/路线区 | `MapRoutePanel` | `RouteEstimate`、转场说明 |
| 可执行窗口区 | `ExecutableWindowCard` | 倒计时、`expire_at`、原因、置信度 |
| 预算区 | `BudgetCard` | 总预算、人均、拆分 |
| 风险与PlanB区 | `RiskCard`、`BackupPlanCard` | `risks`、`backup_plans` |
| 工具调用链区 | `ToolTracePanel` | 用户可见Trace和ToolAction摘要 |
| Mock说明区 | `MockBadge` | Demo模拟数据、Mock凭证说明 |
| 确认执行区 | `ConfirmExecuteBar` | 刷新窗口、确认执行、发起投票 |

#### 核心交互

1. 首屏调用`GET /api/v1/plans/{plan_id}`。
2. 展示可执行窗口倒计时。
3. 倒计时过期后禁用确认执行按钮，状态进入`window_expired`。
4. 点击刷新窗口调用`POST /api/v1/plans/{plan_id}/refresh-window`。
5. 点击确认执行调用`POST /api/v1/plans/{plan_id}/execute`。
6. 执行中按钮disabled，不允许重复提交。
7. 如果返回`NO_TABLE_AVAILABLE`或`ACTIVITY_FULL`，进入Recovery展示。
8. 如果返回`updated_plan_id`或`active_plan_id`指向新计划，跳转或切换到新计划视图。
9. 不展示`failure_injection`细节。

#### 状态机

前端UI state，不替代领域状态：

```text
loading
ready
window_expired
refreshing_window
executing
execution_failed
recovered
error
```

#### 错误处理

| 错误码 | 前端处理 |
| --- | --- |
| `PLAN_EXECUTABLE_WINDOW_EXPIRED` | 提示窗口过期，展示刷新按钮，调用`POST /api/v1/plans/{plan_id}/refresh-window` |
| `NO_TABLE_AVAILABLE` | 展示“原餐厅已满，正在切换备选”，进入Recovery进度 |
| `ACTIVITY_FULL` | 展示“当前活动满员，正在找替代活动”，进入Recovery进度 |
| `SOCIAL_SIGNAL_MISSING` | 隐藏口碑卡，不阻断主流程 |
| `IDEMPOTENCY_CONFLICT` | 提示不要重复提交，刷新或返回计划页 |
| `TOOL_ACTION_INVALID` | 阻断执行，展示重新生成或联系Demo负责人 |

#### Mock与隐私边界

普通页只显示“Demo模拟数据”“当前模拟状态”“Mock/模拟凭证”。SocialSignalMock必须显示“口碑雷达Mock”。不展示Mock接口路径、fixture、failure_injection、高敏MemoryCandidate。

#### 组件拆分

`PlanGoalSummary`、`PlanTimeline`、`TimelineStepCard`、`MapRoutePanel`、`ExecutableWindowCard`、`BudgetCard`、`RiskCard`、`BackupPlanCard`、`ToolTracePanel`、`MockBadge`、`ConfirmExecuteBar`、`ErrorState`、`LoadingSkeleton`。

#### 示例文案

```text
当前方案可执行窗口约18分钟，确认后可模拟锁定活动预约和餐厅订座。
```

```text
已检查餐厅余位、活动状态、路线时间和天气风险。
```

#### 验收标准

1. 消费完整`PlanContract`或合法`UserVisiblePlanProjection`。
2. 展示目标理解、时间线、地图/路线、可执行窗口、预算、风险、PlanB、工具调用链。
3. 可执行窗口过期后禁用执行按钮。
4. 刷新窗口调用最终04路径。
5. 确认执行请求必须有`X-Idempotency-Key`。
6. 不让前端自行判断是否有位。

## 13.可执行窗口与刷新窗口交互设计

`ExecutableWindow`表达“这套安排现在还能成立多久”。前端要把它做成计划结果页的关键决策区。

| 字段 | 展示 |
| --- | --- |
| `window_minutes` | 主视觉倒计时 |
| `confidence` | 置信度进度或标签 |
| `expire_at` | 展示为具体过期时间 |
| `reasons` | 说明当前可执行的原因 |
| `risk_factors` | 轻量风险标签 |
| `lockable_resources` | 可模拟锁定的资源 |
| `display_message` | 用户可读说明 |

交互规则：

1. 前端以`expire_at`计算倒计时，但不自行重新判断余位或票务。
2. 倒计时到0后，`ConfirmExecuteBar`禁用确认执行。
3. 过期后展示“当前窗口已过期，需要重新检查”。
4. 点击刷新调用`POST /api/v1/plans/{plan_id}/refresh-window`。
5. 刷新成功后使用后端返回的新PlanContract或窗口字段更新界面。
6. 刷新失败只展示`error.user_message`。
7. `PLAN_EXECUTABLE_WINDOW_EXPIRED`来自后端时，前端进入`window_expired`。

## 14.工具调用链与Trace展示设计

普通用户页展示简化工具调用链，目标是让用户理解系统经过了检查，而不是暴露底层日志。

普通用户可见示例：

```text
已检查餐厅余位
已估算路线时间
已检查活动余票
已完成可执行性校验
```

Trace事件名只能使用：

```text
input_log
intent_log
constraint_log
memory_log
poi_log
tool_log
verifier_log
recovery_log
executor_log
feedback_log
error_log
```

禁止展示或依赖：

```text
mock_call
mock_log
api_log
```

展示规则：

| 场景 | 可展示 | 不展示 |
| --- | --- | --- |
| 普通用户页 | `visible_to_user=true`的摘要、工具中文状态、Mock弱提示 | payload详情、fixture、failure_injection、Prompt、推理链 |
| Debug/评委模式 | trace_id、event_type、module、created_at、tool_name、API路径摘要、状态摘要、error_code、Recovery链路、updated_plan_id、Mock标识、脱敏payload | API Key、底层Prompt、LLM推理链、高敏MemoryCandidate、未脱敏个人信息 |

MockAPIService调用统一来自`tool_log`。CandidateRetriever候选摘要可来自`poi_log`。

## 15.执行确认与执行结果页设计

### 执行结果页

#### 页面定位

执行结果页展示Executor基于`ToolAction`完成了哪些模拟动作、哪些失败、是否触发Recovery，以及当前应继续查看哪个计划版本。

#### 是否P0

是。

#### 页面路由

`/execution/[executionId]`

#### 入口与出口

| 入口 | 出口 |
| --- | --- |
| 计划页点击确认执行 | 成功后进入反馈页；有`updated_plan_id`时进入新方案；失败可返回计划页 |

#### 依赖API

```text
GET /api/v1/plans/{plan_id}
GET /api/v1/executions/{execution_id}
GET /api/v1/executions/{execution_id}/actions
POST /api/v1/plans/{plan_id}/recover
GET /api/v1/plans/{plan_id}/trace
```

若Execution详情接口未实现，P0可用`GET /api/v1/plans/{plan_id}`中的`execution_summary`替代。

#### 读取对象

`ExecutionResult`、`ToolAction`、`RecoveryResult`、`PlanContract.execution_summary`、`active_plan_id`、`updated_plan_id`。

#### 页面模块

| 模块 | 内容 |
| --- | --- |
| `ExecutionProgress` | 执行动作进度 |
| `ToolTracePanel` | 每个ToolAction执行状态 |
| `ExecutionVoucherCard` | Mock预约、订座、订单、消息凭证 |
| `RecoveryDiffCard` | 失败动作与恢复差异 |
| `GroupMessageCard` | 可复制模拟消息 |
| 下一步入口 | 继续查看新方案、返回计划页、进入低打扰反馈 |

#### 核心交互

1. 展示每个`ToolAction.status`：`pending/running/success/failed/recovered/skipped`。
2. 展示活动预约Mock凭证、餐厅订座/排号Mock凭证、订单Mock凭证、模拟消息凭证。
3. 失败动作展示`error_code`的用户侧文案，不展示底层details。
4. 有Recovery时展示`RecoveryResult`和`updated_plan_id`。
5. `active_plan_id`与当前plan不同，则提供“继续查看新方案”。
6. 执行成功或recovered后提供低打扰反馈入口。

#### 状态机

前端UI state，不替代`ExecutionResult.status`：

```text
executing
partial_success
success
failed
recovering
recovered
completed
```

#### 错误处理

| 错误码 | 前端处理 |
| --- | --- |
| `NO_TABLE_AVAILABLE` | 展示失败动作，进入Recovery |
| `ACTIVITY_FULL` | 展示失败动作，进入Recovery |
| `PLAN_EXECUTABLE_WINDOW_EXPIRED` | 返回计划页刷新窗口 |
| `TOOL_ACTION_INVALID` | 展示执行动作不完整，阻断执行 |
| `IDEMPOTENCY_CONFLICT` | 提示不要重复提交，刷新恢复状态 |

#### Mock与隐私边界

凭证必须使用以下文案：

```text
Mock预约号已生成
Mock订座号已生成
Mock订单号已生成
模拟消息已生成
```

不得写：

```text
已真实支付
已真实发送微信/短信
餐厅已真实订座
票务已真实锁定
```

#### 组件拆分

`ExecutionProgress`、`ExecutionVoucherCard`、`RecoveryDiffCard`、`ToolTracePanel`、`GroupMessageCard`、`MockBadge`、`ErrorState`。

#### 示例文案

```text
Mock预约号已生成：BOOK-MOCK-1024
```

```text
模拟消息已生成，可复制到群聊。
```

#### 验收标准

1. 展示ToolAction执行进度。
2. 展示Mock凭证，且都含“Mock”或“模拟”。
3. 展示失败动作。
4. 展示Recovery Diff。
5. 有`updated_plan_id`时明确这是新计划版本。
6. 不写真实执行文案。

## 16.Recovery前端展示设计

Recovery是版本化修复，不是原地覆盖。

前端必须展示：

| RecoveryResult字段 | 组件 | 展示 |
| --- | --- | --- |
| `recovery_id` | `RecoveryDiffCard`/Debug | Debug或折叠详情 |
| `trigger` | `RecoveryDiffCard` | 触发原因，例如`NO_TABLE_AVAILABLE` |
| `status` | `RecoveryDiffCard` | success/failed/partial |
| `original` | `RecoveryDiffCard` | 原节点/原POI |
| `replacement` | `RecoveryDiffCard` | 替换节点/新POI |
| `diff` | `RecoveryDiffCard` | 路线、预算、排队、距离、时间差异 |
| `updated_plan_id` | `RecoveryDiffCard` | 新计划版本入口 |
| `verifier_result` | Debug/摘要 | 恢复后重新Verifier结果 |
| `user_explanation` | `RecoveryDiffCard` | 用户可读说明 |

`RecoveryDiffView`是前端ViewModel，不进入03 Schema。它只做字段格式化，例如把`route_extra_minutes:4`展示为“路线多4分钟”。

交互规则：

1. 执行失败且`recoverable=true`时，先展示Recovery进度。
2. 后端返回`updated_plan_id`后，前端展示“已生成新计划版本”。
3. 用户可点击查看新方案，跳转`/plans/[updatedPlanId]`。
4. 原计划页保留恢复记录，不把原`PlanContract`直接替换成新对象。
5. Debug可展示Recovery链路和脱敏payload。

示例文案：

```text
原餐厅已满，已切换到同区域低卡轻食餐厅。路线多4分钟，预算不变，排队风险更低。
```

## 17.朋友投票页设计

### 朋友投票页

#### 页面定位

投票页让朋友用低摩擦方式表达偏好，把群聊拉扯压缩成结构化投票，供ConsensusService生成最终方案。

#### 是否P0

是。

#### 页面路由

`/vote/[votePageId]`

#### 入口与出口

| 入口 | 出口 |
| --- | --- |
| 计划页创建投票后生成可复制链接/二维码/模拟分享卡 | 提交成功显示已提交；finalize后可进入共识结果页 |

#### 依赖API

```text
GET /api/v1/vote-pages/{vote_page_id}
POST /api/v1/consensus/{consensus_session_id}/vote
```

#### 读取对象

`ConsensusSession`投影、候选`PlanSummary`、`ConsensusVote`。

#### 页面模块

| 模块 | 说明 |
| --- | --- |
| `VotePlanCard` | 候选方案卡片 |
| `VoteForm` | 多选喜欢、反选不想要、预算、时间偏好、步行/排队接受度、文字反馈 |
| `ErrorState` | 投票冲突、已关闭、已finalize |
| `MockBadge` | 可复制链接/二维码/模拟分享卡说明 |

#### 核心交互

1. 使用`vote_page_id`读取投票页，响应必须包含`consensus_session_id`。
2. 候选方案卡片展示摘要，不展示完整ToolAction payload。
3. 支持多选喜欢。
4. 支持反选不想要。
5. 支持预算输入、时间偏好、步行接受度、排队接受度、文字反馈。
6. 提交前校验`liked_plan_ids`和`disliked_plan_ids`不能重叠。
7. `liked_plan_ids`、`disliked_plan_ids`、`free_text`至少一个有效。
8. finalize后不可再投。
9. 适合微信内打开的移动端体验。
10. 不要求真实微信分享，只生成可复制链接/二维码/模拟分享卡。

#### 状态机

```text
loading
ready
submitting_vote
submitted
closed
invalid
error
```

这些是前端UI state，不替代`ConsensusSession.status`。

#### 错误处理

| 错误码 | 前端处理 |
| --- | --- |
| `CONSENSUS_VOTE_INVALID` | 保留表单，展示`error.user_message` |
| `RESOURCE_NOT_FOUND` | 展示投票页不存在 |
| `IDEMPOTENCY_CONFLICT` | 提示不要重复提交，可刷新 |
| `BAD_REQUEST` | 提示投票内容有误 |

#### Mock与隐私边界

投票页不展示Debug payload，不展示参与者内部ID。分享只写“可复制链接已生成”或“模拟分享卡”。

#### 组件拆分

`VotePlanCard`、`VoteForm`、`LoadingSkeleton`、`ErrorState`、`EmptyState`。

#### 示例文案

```text
可复制投票链接已生成，发给朋友后他们可以直接选偏好。
```

```text
同一个方案不能同时选择喜欢和不想选，请修改后提交。
```

#### 验收标准

1. 路由参数为`votePageId`，领域字段为`vote_page_id`。
2. API响应中使用`consensus_session_id`，不使用泛化`sessionId`。
3. 只反选、只写文字、只喜欢均可提交。
4. 喜欢和反选重叠必须阻断。
5. finalize后不可再投。

## 18.共识结果页设计

### 共识结果页

#### 页面定位

共识结果页把多人反馈压缩成最终可执行方案，展示投票统计、冲突识别、共识解释、最终`PlanContract`和可复制群聊消息。

#### 是否P0

是。

#### 页面路由

`/consensus/[consensusSessionId]`

#### 入口与出口

| 入口 | 出口 |
| --- | --- |
| 发起人从计划页或投票管理入口进入 | finalize后进入最终计划页或直接执行 |

#### 依赖API

```text
POST /api/v1/consensus/{consensus_session_id}/finalize
GET /api/v1/plans/{final_plan_id}
```

可选读取：

```text
GET /api/v1/consensus/{consensus_session_id}/summary
```

#### 读取对象

`ConsensusSummary`、`ConsensusSession`、最终`PlanContract`、`GroupMessageCard`内容。

#### 页面模块

| 模块 | 内容 |
| --- | --- |
| `ConsensusSummaryPanel` | 投票统计、支持/反对、冲突识别 |
| 共识解释 | `ConsensusSummary.explanation` |
| 最终方案摘要 | 最终`PlanContract`或`UserVisiblePlanProjection` |
| `GroupMessageCard` | 可复制群聊消息 |
| 继续执行入口 | 跳转计划页或执行 |

#### 核心交互

1. 未finalize时展示实时统计或提示生成共识方案。
2. 点击生成共识调用`POST /api/v1/consensus/{consensus_session_id}/finalize`。
3. finalize后展示`ConsensusSummary`。
4. 最终方案必须重新Verifier。
5. 完整计划通过`GET /api/v1/plans/{final_plan_id}`读取。
6. 群聊消息只做可复制或模拟消息，不写“已真实发送微信群”。

#### 状态机

前端可使用：

```text
loading
ready
finalizing
finalized
error
```

#### 错误处理

| 错误码 | 前端处理 |
| --- | --- |
| `CONSENSUS_VOTE_INVALID` | 提示当前还没有有效投票或投票内容有冲突 |
| `CONSENSUS_CONFLICT` | P1/P2预留，提示存在强冲突，可继续收集偏好 |
| `PLAN_SCHEMA_INVALID` | 提示最终方案生成失败，可重试 |
| `VERIFIER_RESULT_INVALID` | 提示校验异常，不允许执行 |

#### Mock与隐私边界

不展示匿名参与者真实身份，不展示内部投票解析Prompt。群聊只展示“模拟消息已生成”或“可复制消息已生成”。

#### 组件拆分

`ConsensusSummaryPanel`、`PlanGoalSummary`、`PlanTimeline`、`GroupMessageCard`、`ConfirmExecuteBar`、`ErrorState`。

#### 示例文案

```text
大家反馈里“不想走太多”和“别排队”优先级最高，所以最终方案选择低步行、低排队的室内朋友局。
```

```text
模拟消息已生成，可复制到群聊。
```

#### 验收标准

1. 展示投票统计。
2. 展示冲突压缩。
3. 展示共识解释。
4. 最终方案重新Verifier。
5. 使用`consensusSessionId`路由参数，对应领域字段`consensus_session_id`。
6. 不写真实微信群发送。

## 19.低打扰反馈与LifeMemory页面设计

### 低打扰反馈页

#### 页面定位

执行后以最少打扰收集反馈，并把可能有用的偏好生成`MemoryCandidate`候选，由用户确认、忽略或稍后处理。

#### 是否P0

是，P0做候选闭环；P1做完整管理。

#### 页面路由

`/feedback/[planId]`

#### 入口与出口

| 入口 | 出口 |
| --- | --- |
| 执行结果页点击“给一点反馈” | 提交后展示MemoryCandidate；可返回首页或Memory页 |

#### 依赖API

```text
GET /api/v1/feedback/questions?plan_id=...
POST /api/v1/feedback
GET /api/v1/memory/candidates
POST /api/v1/memory/candidates/{candidate_id}/confirm
POST /api/v1/memory/candidates/{candidate_id}/ignore
```

#### 读取对象

反馈问题、`MemoryCandidate`、可选`LifeMemory`。

#### 页面模块

| 模块 | 内容 |
| --- | --- |
| `FeedbackCard` | 满意/一般/不满意或场景问题 |
| `MemoryCandidateCard` | 候选记忆内容、来源、敏感度、确认/忽略/稍后 |
| 隐私说明 | 高敏不保存，中敏需确认，关闭个性化入口 |

#### 核心交互

1. 行程后轻量反馈。
2. 满意/一般/不满意或最多2个问题。
3. 最多一个追问；用户可跳过。
4. 提交`POST /api/v1/feedback`。
5. 展示返回的`MemoryCandidate`。
6. 用户可确认、忽略、稍后。
7. 高敏信息不展示、不保存。
8. 中敏信息必须用户确认。
9. 提供关闭个性化入口。
10. 展示本次使用了哪些记忆的解释，不展示内部权重。

#### 状态机

```text
loading
ready
submitting
submitted
skipped
error
```

#### 错误处理

| 错误码 | 前端处理 |
| --- | --- |
| `MEMORY_PRIVACY_VIOLATION` | 展示“该信息不会被自动保存”，不展示高敏细节 |
| `MEMORY_UNAVAILABLE` | 不阻断反馈，提示记忆服务暂不可用 |
| `BAD_REQUEST` | 保留反馈内容，展示用户提示 |

#### Mock与隐私边界

不得写：

```text
系统已自动记住你的家庭情况
系统已自动判断你有车/收入/婚姻状态
```

推荐文案：

```text
我可以把“偏好低排队/低预算/低卡餐厅”作为下次规划参考，你可以确认或忽略。
```

#### 组件拆分

`FeedbackCard`、`MemoryCandidateCard`、`ErrorState`、`LoadingSkeleton`。

#### 验收标准

1. 反馈问题不超过2个。
2. 用户可以跳过。
3. MemoryCandidate需要用户确认或忽略。
4. 高敏信息不保存。
5. 中敏信息需要确认。
6. 不偷偷写画像。

### LifeMemory管理页

#### 页面定位

LifeMemory页展示系统已经启用或待确认的长期记忆，让用户查看来源、确认、编辑、删除或关闭个性化。

#### 是否P0

P1完整，P0可提供候选展示和确认/忽略入口预留。

#### 页面路由

`/memory`

#### 依赖API

```text
GET /api/v1/memory
GET /api/v1/memory/candidates
POST /api/v1/memory/candidates/{candidate_id}/confirm
POST /api/v1/memory/candidates/{candidate_id}/ignore
PATCH /api/v1/memory/{memory_id}
DELETE /api/v1/memory/{memory_id}
POST /api/v1/memory/personalization/disable
POST /api/v1/memory/personalization/enable
```

#### 页面模块

`MemoryList`、`MemoryCandidateCard`、个性化开关、空状态、错误状态。

#### 验收标准

1. 展示记忆内容、来源、敏感度、状态。
2. 支持候选确认/忽略。
3. P1支持编辑、删除、关闭个性化。
4. 删除后不得静默恢复。
5. 关闭个性化后提示本次不使用长期记忆。

## 20.SocialSignalMock与Mock标识展示设计

前端必须按对象类型展示Mock标识：

| 对象 | 普通用户页 | Debug/评委模式 |
| --- | --- | --- |
| Mock POI | “Demo模拟数据”弱提示 | 可显示`mock_only:true` |
| Mock状态 | “当前模拟状态” | 可显示`source:"mock_api"` |
| Mock凭证 | 必须显示“Mock”或“模拟” | 可显示凭证字段和`mock_only:true` |
| SocialSignalMock | 必须显示“口碑雷达Mock” | 可显示`is_mock:true`、`source_type:"mock_social_signal"` |
| Mock消息 | “模拟消息已生成”或“可复制消息已生成” | 可显示`message_id`和脱敏payload |

必须使用的文案：

```text
Mock预约号已生成
Mock订座号已生成
Mock订单号已生成
模拟消息已生成
口碑雷达Mock
```

不得使用的文案：

```text
餐厅已真实订座
票务已真实锁定
订单已真实支付
微信已发送
短信已发送
已实时抓取小红书/抖音/点评
```

`failure_injection`只允许Debug/测试/评委模式展示，不得出现在普通用户页。

## 21.Debug/评委模式设计

Debug/评委模式用于证明LifePilot不是静态样板，而是有Trace、工具调用、Verifier、Executor和Recovery链路。

开启方式：

| 方式 | 说明 |
| --- | --- |
| 环境变量 | `NEXT_PUBLIC_DEBUG_MODE=true` |
| Query参数 | `?debug=1`，仅Demo环境 |
| 页面开关 | 评委模式按钮，仅开发/评委可见 |

Debug默认隐藏。普通用户页永远不显示`failure_injection`。

### DebugTracePanel

可展示：

| 字段/内容 | 来源 |
| --- | --- |
| `trace_id` | TraceLog/API响应 |
| `event_type` | TraceLog最终枚举 |
| `module` | TraceLog |
| `created_at` | TraceLog |
| `visible_to_user` | TraceLog |
| `tool_name` | 脱敏payload |
| API路径摘要 | Debug投影 |
| 状态摘要 | ToolAction/TraceLog |
| `error_code` | Error/TraceLog |
| Recovery链路 | RecoveryResult |
| `updated_plan_id` | RecoveryResult |
| Mock标识 | Mock对象 |
| 脱敏payload | Debug接口 |

不可展示：

| 内容 |
| --- |
| 底层Prompt |
| LLM推理链 |
| API Key |
| 高敏MemoryCandidate |
| 未脱敏个人信息 |
| 普通用户页的`failure_injection` |

Debug页可调用：

```text
GET /api/v1/traces/{trace_id}
GET /api/v1/traces/{trace_id}/events
GET /api/v1/plans/{plan_id}/trace
GET /api/v1/plans/{plan_id}/debug
```

若`GET /api/v1/plans/{plan_id}/debug`未实现，Debug页只展示Trace事件和计划trace投影，不阻断普通Demo。

## 22.错误处理、空状态与降级体验

### 22.1错误码白名单

前端P0 active错误码必须来自04：

```text
PLAN_SCHEMA_INVALID
PLAN_TIMELINE_INVALID
PLAN_STEP_POI_NOT_FOUND
TOOL_ACTION_INVALID
MOCK_STATUS_MISSING
VERIFIER_RESULT_INVALID
RECOVERY_RESULT_INVALID
MEMORY_PRIVACY_VIOLATION
CONSENSUS_VOTE_INVALID
SOCIAL_SIGNAL_MOCK_REQUIRED
TRACE_ID_MISSING
VERSION_NOT_SUPPORTED
PLAN_EXECUTABLE_WINDOW_EXPIRED
NO_TABLE_AVAILABLE
ACTIVITY_FULL
BAD_REQUEST
UNAUTHORIZED_DEMO_USER
RESOURCE_NOT_FOUND
IDEMPOTENCY_CONFLICT
RATE_LIMITED
INTERNAL_ERROR
```

P1/P2 reserved错误码：

```text
ROUTE_DELAY
WEATHER_RISK_HIGH
BUDGET_EXCEEDED
CONSENSUS_CONFLICT
SOCIAL_SIGNAL_MISSING
MEMORY_UNAVAILABLE
```

禁止新增：

```text
MOCK_API_FAILED
PLAN_CREATE_FAILED
RESTAURANT_FULL
TICKET_SOLD_OUT
UNKNOWN_STATUS
```

### 22.2错误展示策略

| 错误码 | 普通用户展示 | 处理 |
| --- | --- | --- |
| `PLAN_EXECUTABLE_WINDOW_EXPIRED` | 当前窗口已过期，需要重新检查 | 引导刷新窗口 |
| `NO_TABLE_AVAILABLE` | 原餐厅已满，正在切换备选 | 进入Recovery进度 |
| `ACTIVITY_FULL` | 当前活动满员，正在找替代活动 | 进入Recovery进度 |
| `SOCIAL_SIGNAL_MISSING` | 不展示口碑卡 | 不阻断主流程 |
| `MEMORY_PRIVACY_VIOLATION` | 该信息不会被自动保存 | 不展示高敏细节 |
| `IDEMPOTENCY_CONFLICT` | 请勿重复提交，刷新后再试 | 恢复已有状态 |
| `recoverable=true` | 展示重试、刷新、自动恢复入口 | 保留用户输入和上下文 |
| `recoverable=false` | 返回首页或联系Demo负责人 | 不暴露底层异常 |

### 22.3空状态

| 页面 | 空状态 |
| --- | --- |
| 计划页 | 计划不存在：返回首页重新生成 |
| 投票页 | 候选方案为空：提示链接异常 |
| 共识页 | 暂无投票：可基于已有反馈或继续收集 |
| 执行页 | 执行记录暂不可用：返回计划页 |
| Memory页 | 还没有长期记忆：本次不会影响规划 |
| Debug页 | 无Trace事件：检查`trace_id`或Debug模式 |

## 23.移动端适配与Demo演示体验

视觉与交互风格：

| 方向 | 建议 |
| --- | --- |
| 整体 | 移动端App感Web Demo，桌面端居中展示手机宽度 |
| 核心视觉 | 纵向时间线，突出起点、节点、转场、可执行窗口、PlanB改道 |
| 布局 | 卡片化但不堆叠过多层级；底部固定确认栏 |
| 状态 | 关键状态高亮，如可执行窗口、Recovery、Mock凭证 |
| 风险 | 用轻提示表达，不制造焦虑 |
| Mock | 标签清晰但不破坏体验 |
| 投票 | 单手可完成，多选/反选低摩擦 |
| 纪念日 | 文案自然，不油腻，不夸张 |
| 家庭亲子 | 强调“不赶、不远、不排长队” |
| 朋友局 | 强调“压缩群聊拉扯” |

移动端验收：

1. 375px宽度可完整操作。
2. 底部确认执行按钮不遮挡主要内容。
3. 时间线可滚动。
4. 投票页单手可完成。
5. Debug面板可折叠，不影响普通Demo。
6. 3分钟评委Demo能完成输入、计划、执行或投票共识主链路。

## 24.组件清单与Props来源

组件props应来自03对象或前端ViewModel，不得直接依赖Agent内部`DraftPlan`或`PlanBuildCandidate`。

| 组件 | Props来源 | 说明 |
| --- | --- | --- |
| `AppShell` | app state、debug mode | 页面外壳 |
| `MobileFrame` | layout props | 移动端容器 |
| `HomeInputCard` | 本地输入state | 一句话输入 |
| `ScenarioQuickCards` | 常量scenario_hint | 三类P0快捷入口 |
| `GenerationProgress` | 前端UI state、Trace摘要 | 生成进度 |
| `PlanGoalSummary` | `PlanContract.user_goal`、`participants`、`constraints` | 目标理解 |
| `PlanTimeline` | `TimelineViewItem[]` from `PlanContract.timeline` | 时间线 |
| `TimelineStepCard` | `PlanStep`、`POI`投影 | 单个节点 |
| `ExecutableWindowCard` | `ExecutableWindow` | 可执行窗口 |
| `BudgetCard` | `Budget` | 预算 |
| `RiskCard` | `Risk[]` | 风险 |
| `BackupPlanCard` | `BackupPlan[]` | PlanB |
| `MapRoutePanel` | `RouteEstimate`、`TimelineViewItem[]` | 路线/转场 |
| `POIStatusCard` | `POIStatus`、`RestaurantStatus`、`WeatherStatus`投影 | 当前模拟状态 |
| `ToolTracePanel` | `ToolTraceViewItem[]`、`ToolAction[]`摘要 | 工具调用链 |
| `MockBadge` | Mock标识ViewModel | Mock弱提示 |
| `ConfirmExecuteBar` | `plan_id`、`ExecutableWindow`、UI state | 确认执行 |
| `ExecutionProgress` | `ExecutionResult`、`ToolAction[]` | 执行进度 |
| `ExecutionVoucherCard` | `ExecutionResult.vouchers`或action result | Mock凭证 |
| `RecoveryDiffCard` | `RecoveryResult`或`RecoveryDiffView` | 恢复差异 |
| `VotePlanCard` | `PlanSummary` | 候选方案 |
| `VoteForm` | `ConsensusVote`表单state | 投票 |
| `ConsensusSummaryPanel` | `ConsensusSummary` | 统计与冲突 |
| `GroupMessageCard` | `PlanContract.messages`或finalize响应 | 可复制模拟消息 |
| `FeedbackCard` | Feedback问题响应、本地state | 低打扰反馈 |
| `MemoryCandidateCard` | `MemoryCandidate` | 候选记忆 |
| `MemoryList` | `LifeMemory[]` | 记忆管理 |
| `DebugTracePanel` | `TraceLog[]`、Debug投影 | 工具链Debug |
| `ErrorState` | 标准错误响应 | 错误展示 |
| `EmptyState` | 页面空状态ViewModel | 空状态 |
| `LoadingSkeleton` | 页面类型 | 骨架屏 |

## 25.前端测试与验收标准

### 25.1页面验收

| 页面 | 标准 |
| --- | --- |
| 首页 | 能提交家庭亲子、朋友局、纪念日三类P0示例 |
| 计划生成页 | 展示至少4个进度步骤 |
| 计划结果页 | 展示目标理解、时间线、预算、风险、PlanB、可执行窗口、工具调用链 |
| 朋友投票页 | 能提交喜欢、反选、预算、文字反馈 |
| 共识结果页 | 能展示投票统计、冲突压缩和最终方案 |
| 执行结果页 | 能展示Mock凭证和Recovery Diff |
| Feedback页 | 能展示MemoryCandidate候选 |
| Debug页 | 能展示Trace摘要 |

### 25.2数据契约验收

| 验收项 | 标准 |
| --- | --- |
| DraftPlan | 前端不渲染DraftPlan |
| PlanContract | 字段来自03 |
| API路径 | 路径来自04，全部使用`/api/v1` |
| 错误码 | 只使用04定义错误码 |
| Trace事件 | 只使用03/04/05定义事件名 |
| 时间 | ISO输入，展示层格式化 |
| ToolAction.type | 不使用`create_order` |
| Mock路径 | 普通用户业务流程不直接调用Mock接口；不得使用旧路径 |
| Consensus字段 | 不使用泛化`session_id`替代`consensus_session_id` |
| ID前缀 | 使用`vpage_`、`plangrp_`、`cs_`等03前缀 |

### 25.3错误处理验收

| 错误 | 标准 |
| --- | --- |
| `PLAN_EXECUTABLE_WINDOW_EXPIRED` | 触发刷新窗口UI |
| `NO_TABLE_AVAILABLE` | 进入Recovery展示 |
| `ACTIVITY_FULL` | 进入Recovery展示 |
| `SOCIAL_SIGNAL_MISSING` | 隐藏口碑卡 |
| `IDEMPOTENCY_CONFLICT` | 提示不要重复提交 |
| 普通用户错误 | 不展示`error.details` |
| failure_injection | 普通用户页不展示 |

### 25.4Mock边界验收

| 验收项 | 标准 |
| --- | --- |
| Mock凭证 | 所有凭证显示“Mock”或“模拟” |
| 禁止文案 | 不出现真实支付、真实短信、真实微信、真实订座、真实票务、真实爬取文案 |
| SocialSignalMock | 必须标注“口碑雷达Mock” |
| Mock POI | 普通页弱提示Demo模拟数据，Debug可显示`mock_only:true` |

### 25.5移动端验收

| 验收项 | 标准 |
| --- | --- |
| 375px | 可完整操作 |
| 底部按钮 | 不遮挡主要内容 |
| 时间线 | 可滚动 |
| 投票页 | 单手可完成 |
| Debug | 可折叠，不影响普通Demo |

### 25.6建议自动化测试

| 类型 | 用例 |
| --- | --- |
| E2E | 首页提交家庭亲子输入，进入计划页，确认执行，展示Mock凭证 |
| E2E | 朋友局创建投票，提交反选和free_text，finalize生成最终方案 |
| E2E | 执行返回`NO_TABLE_AVAILABLE`，展示Recovery Diff和`updated_plan_id` |
| 组件 | `ExecutableWindowCard`过期禁用按钮 |
| 组件 | `VoteForm`喜欢/反选重叠报错 |
| 组件 | `MemoryCandidateCard`高敏不展示细节 |
| 快照 | 普通用户页不出现`failure_injection` |
| 文案扫描 | 禁止真实支付、真实微信/短信、真实订座、真实票务、真实爬取 |
| 契约扫描 | 不出现`create_order`、旧路径、未定义错误码、未定义Trace事件名 |

## 26.不做什么与安全边界

前端明确不做：

1. 不做聊天壳式自由回答页面。
2. 不消费LLM DraftPlan或Agent内部PlanBuildCandidate。
3. 不重新定义`PlanContract`、`POI`、`POIStatus`、`WeatherStatus`、`ExecutionResult`字段。
4. 不使用旧API路径。
5. 不把`create_order`写成`ToolAction.type`，下单模拟使用`order_item`。
6. 不让普通用户页直接调用MockAPI完成业务流程，普通页主要调用Plan/Consensus/Execution聚合API。
7. 不自行判断餐厅余位、活动票务、路线时间、天气或执行成功。
8. 不展示底层Prompt、LLM推理链、API Key。
9. 不向普通用户展示`failure_injection`。
10. 不把Mock凭证写成真实执行结果。
11. 不把SocialSignalMock写成真实爬取能力。
12. 不把Recovery写成原地覆盖PlanContract。
13. 不使用泛化`sessionId`表示共识会话；前端route param使用`consensusSessionId`，领域字段使用`consensus_session_id`。
14. 不使用早期ID示意替代03前缀。
15. 不新增错误码。
16. 不新增Trace事件名。
17. 不把展示层ViewModel误写成03 Schema字段。
18. 不让LifeMemory像偷偷画像；必须强调低打扰、可审计、用户可控。

## 27.附录：页面-API-组件-数据对象速查表

| 页面 | 路由 | API | 组件 | 数据对象 |
| --- | --- | --- | --- | --- |
| 首页 | `/` | `POST /api/v1/plans/create` | `HomeInputCard`、`ScenarioQuickCards` | 创建响应、`trace_id`、`plan_id` |
| 计划生成中 | `/plans/creating` | `POST /api/v1/plans/create`结果 | `GenerationProgress`、`ToolTracePanel` | Trace摘要、`PlanContract` |
| 计划结果 | `/plans/[planId]` | `GET /api/v1/plans/{plan_id}`、`POST /api/v1/plans/{plan_id}/verify`、`POST /api/v1/plans/{plan_id}/refresh-window`、`POST /api/v1/plans/{plan_id}/execute`、`GET /api/v1/plans/{plan_id}/trace` | `PlanGoalSummary`、`PlanTimeline`、`ExecutableWindowCard`、`BudgetCard`、`RiskCard`、`BackupPlanCard`、`ConfirmExecuteBar` | `PlanContract`、`ExecutableWindow`、`Risk`、`BackupPlan`、`ToolAction` |
| 朋友投票 | `/vote/[votePageId]` | `GET /api/v1/vote-pages/{vote_page_id}`、`POST /api/v1/consensus/{consensus_session_id}/vote` | `VotePlanCard`、`VoteForm` | `ConsensusSession`、`ConsensusVote`、`PlanSummary` |
| 共识结果 | `/consensus/[consensusSessionId]` | `POST /api/v1/consensus/{consensus_session_id}/finalize`、`GET /api/v1/plans/{final_plan_id}` | `ConsensusSummaryPanel`、`GroupMessageCard`、计划组件 | `ConsensusSummary`、`PlanContract` |
| 执行结果 | `/execution/[executionId]` | `GET /api/v1/plans/{plan_id}`、`POST /api/v1/plans/{plan_id}/recover`、可选`GET /api/v1/executions/{execution_id}` | `ExecutionProgress`、`ExecutionVoucherCard`、`RecoveryDiffCard` | `ExecutionResult`、`ToolAction`、`RecoveryResult` |
| 反馈 | `/feedback/[planId]` | `GET /api/v1/feedback/questions?plan_id=...`、`POST /api/v1/feedback`、Memory候选接口 | `FeedbackCard`、`MemoryCandidateCard` | `MemoryCandidate` |
| LifeMemory | `/memory` | `GET /api/v1/memory`、`GET /api/v1/memory/candidates`、Memory管理接口 | `MemoryList`、`MemoryCandidateCard` | `LifeMemory`、`MemoryCandidate` |
| Debug Trace | `/debug/traces/[traceId]` | `GET /api/v1/traces/{trace_id}`、`GET /api/v1/traces/{trace_id}/events`、`GET /api/v1/plans/{plan_id}/trace` | `DebugTracePanel` | `TraceLog`、`ToolTraceViewItem` |

上线前重点自查：

| 检查项 | 结果要求 |
| --- | --- |
| API路径 | 全部为`/api/v1/...` |
| 旧路径 | 不使用旧路径 |
| ToolAction | 不出现`create_order` |
| Plan渲染 | 只消费完整`PlanContract`或合法展示投影 |
| failure_injection | 普通用户页不展示 |
| Mock文案 | 凭证使用“Mock/模拟” |
| 错误展示 | 普通用户只展示`error.user_message` |
| Recovery | 版本化展示`updated_plan_id` |
| 枚举 | 不新增03/04/05/06之外的字段、错误码、Trace事件名 |
| LifeMemory | 候选确认/忽略，用户可控，不偷偷画像 |

## 28. 2026-05-23追加：模型接口设置页

新增设置页：

| 页面 | 路由 | API | 可见对象 |
| --- | --- | --- | --- |
| 模型接口设置 | `/settings` | `GET /api/v1/settings/llm`、`PATCH /api/v1/settings/llm` | 受控LLM配置脱敏投影 |

展示规则：

1. 页面允许切换`deepseek`和`qwen`，并编辑`base_url`、`model`、超时、重试、输出上限、思考模式和访问凭证。
2. 访问凭证输入框只用于提交新值，读取接口只展示脱敏`credential_mask`。
3. 设置页属于开发/评委联调入口，普通规划页不展示底层凭证、Prompt或LLM推理链。
4. Provider切换只影响IntentParser和PlanGenerator的受控LLM辅助步骤；PlanContract、MockAPI、Verifier、Executor和Recovery契约不变。

## 29. 2026-05-23追加：首页模拟初始状态

首页新增“模拟初始状态”模块，用于Demo前置设定当前区域、当前位置、当前时间和可规划时长。

前端规则：

1. 该模块只写入`POST /api/v1/plans/create`既有可选字段：`user_location`、`preferred_start_time`、`preferred_end_time`。
2. 不新增业务API路径，不让前端直接读取fixture或自行判断天气、路线、余位。
3. 页面文案必须标注Mock/模拟环境，避免用户误解为真实定位或真实平台状态。
4. 计划结果页继续只渲染完整`PlanContract`或合法用户可见投影。
5. 路线卡应展示后端返回的转场起终点、模拟交通方式、距离和时长；若无转场，展示“无需明显转场或等待刷新”，不得让前端编造路线。

## 30. 2026-05-23追加：类脑推荐优先级展示

计划结果页可以展示`ConstraintSet.recommendation_profile.normalized_tags`的用户可见投影，但展示必须是产品解释，不是调试信息。

展示规则：

1. 展示标题使用“类脑推荐优先级”，用于解释本次为什么按这些方向选地点。
2. 只展示映射后的中文标签，例如“手作体验”“漂亮饭”“招待友好”“下沙代表性”“可小酌”。
3. 不展示底层权重、原始Prompt、LLM推理链、API Key、failure_injection、seed或未脱敏payload。
4. 英文受控标签没有中文映射时默认不展示，避免普通用户页出现机器枚举。
5. 前端不得基于这些标签重新排序或自行判断余位；排序结果仍以后端PlanContract为准。
## 31. 2026-05-24追加：首页时间锚点与投票动态预览

### 31.1首页模拟初始状态修订

首页“模拟初始状态”中的时间字段改为“当前时间锚点”。

前端提交规则：

1. `current_time`提交当前模拟时刻。
2. `preferred_duration_hours`提交可规划时长。
3. 不再把当前模拟时刻写入`preferred_start_time`。
4. 只有当后续增加“锁定出发窗口”的明确控件时，才允许提交`preferred_start_time/end_time`。

默认比赛态：

```text
当前时间锚点：2026-05-23 09:00
可规划时长：4小时
```

新增快捷样例：

```text
周末下午我想去一个人散散心，顺便喝杯酒。
```

### 31.2计划页类脑推荐优先级

计划页可展示“类脑推荐优先级”，只展示中文投影，不展示底层标签权重、Prompt、模型推理链、API Key或failure injection。

### 31.3投票页动态调整预览

投票页在提交前展示实时约束预览：

1. 喜欢的候选方案会显示为优先参考对象。
2. 人均预算上限会显示为最终共识预算约束。
3. 步行容忍和排队容忍会显示为路线与可预约优先级。
4. free text只做偏好补充预览，最终仍由后端`ConsensusService.finalize()`压缩为约束并重新生成PlanContract。

前端不得在投票页直接改写候选PlanContract，也不得自行判断余位、天气、路线或执行成功。

## 32. 2026-05-24追加：执行页Mock资源快照展示

执行页可在动作结果中展示Mock余桌、排队和余票摘要，例如：

```text
订座前Mock余桌2桌，预计等8分钟
预约前Mock余票18张
```

展示边界：

1. 只展示后端Executor返回的`action_results.result`摘要。
2. 凭证标题必须保留“Mock”或“模拟”。
3. 不暗示真实订座、真实票务、真实支付或真实消息发送。

## 33. 2026-05-24追加：多节点行程展示约定

计划结果页需要兼容4-5个POI节点的长窗口行程。

展示规则：

1. Timeline按`PlanContract.timeline`原顺序渲染所有步骤，不限制为“活动-吃饭-收尾”三段。
2. `transport`节点可以压缩展示为转场条，但不能被计入“4-5个活动”的数量提示。
3. 预算卡展示总预算、人均预算和预算约束；当Verifier为`pass`时无需展示内部预算调参过程。
4. 餐厅卡只展示后端返回的Mock余桌、排队和订座动作状态，不展示`itinerary_nodes`、内部评分、Prompt、API Key或模型推理链。
5. 如果后端返回`verifier_result.warning`，前端展示用户可执行PlanB提示；如果为`fail`，必须引导Recovery或刷新，不允许直接执行。

## 34. 2026-05-25追加：Stitch美团风格前端集成约定

本轮前端允许吸收Stitch生成的美团风格视觉样例，但集成方式必须是“真实应用组件化重构”，不能把静态HTML直接作为Demo页面。

集成目标：

1. 首页第一屏突出“生活时间导航Agent”，保留自然语言输入、当前时间锚点、可规划时长和快捷场景。
2. 计划页、投票页、记忆页和底部导航统一为轻量本地生活风格：黄色主行动、白色卡片、实时状态、小图场景卡和移动端底部导航。
3. 普通用户页展示LifePilot优势时，使用产品语言解释“结构化计划、Verifier闸门、失败可恢复、朋友局共识、生活记忆”，不得展示底层枚举、Prompt、模型推理链、API Key或failure injection。
4. 所有计划、投票、执行、记忆数据仍必须来自后端`/api/v1`接口和`PlanContract`用户可见投影。
5. 前端可以展示“模拟路线轨迹”“Mock余位/余票/订座凭证”等Demo能力，但必须保留“模拟”或“Mock”边界，不暗示真实支付、真实订座、真实锁票或真实消息发送。

页面映射：

| Stitch样例 | 当前真实页面 | 必须保持的真实能力 |
| --- | --- | --- |
| 生活导航首页 | `/` | `POST /api/v1/plans/create`生成真实PlanContract，快捷场景只填充输入和场景hint |
| 计划总览/时间轴 | `/plans/{plan_id}`、`/execution/{execution_id}` | 展示后端Timeline、Verifier状态、Executor结果和Recovery入口 |
| 好友投票与共识 | `/vote/{vote_page_id}`、`/consensus/{consensus_session_id}` | 投票提交、约束压缩和共识方案生成全部走后端 |
| 生活记忆与个人资料 | `/memory` | 候选记忆读取、确认和忽略全部走后端 |

导航规则：

1. 顶部保留品牌与设置入口。
2. 底部导航包含“首页、计划、同步、我的”。
3. “计划”和“同步”可以读取最近一次创建计划或投票的本地会话缓存作为快捷入口；缓存只用于导航，不作为业务真相。
4. 如果没有最近计划或投票，导航回到首页或默认入口，不构造假的`plan_id`、`vote_page_id`或`consensus_session_id`。

## 35. 2026-05-26追加：重构后前端实现约定

当前前端实现保持移动端应用壳，但所有业务数据仍来自`/api/v1`：

1. `frontend/lib/api.ts`统一构造`X-Trace-Id`、`X-Idempotency-Key`、Debug Header和标准错误处理；页面不得绕过该客户端直接拼业务请求。
2. 页面加载函数应使用稳定依赖，避免`useEffect`闭包依赖不清导致重复请求或lint warning。
3. `/settings`可提交LLM运行态配置，但读取时只展示`credential_configured`和`credential_mask`；未配置凭证时显示“未配置”。
4. 普通页允许显示`trace_id`作为调试入口线索，但不得展示Prompt、API Key、LLM推理链、未脱敏payload、`failure_injection`或内部候选结构。
5. Playwright E2E属于端到端巡检，不是并发压测；默认单worker执行，确保计划生成、投票、执行和记忆链路稳定可复现。
6. 本地会话缓存只用于“最近计划/最近投票”导航快捷入口，不可作为业务真相。
