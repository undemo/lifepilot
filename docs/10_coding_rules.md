# 10_coding_rules.md

## 1. 文档信息

| 项 | 内容 |
| --- | --- |
| 文档名称 | `10_coding_rules.md` |
| 项目名称 | LifePilot |
| 产品定位 | 生活时间导航Agent |
| 核心隐喻 | 高德导航的是一段路，LifePilot导航的是一段生活时间 |
| 文档类型 | 编码规范、工程实现规范、代码审查规则 |
| 文档版本 | v0.1 |
| 面向读者 | 前端、后端、Agent、Mock、测试、Demo负责人 |
| 当前范围 | 比赛Demo阶段，P0闭环优先 |
| Demo区域 | 杭州下沙/金沙湖/高教园区 |
| 默认时区 | Asia/Shanghai |
| 时间格式 | ISO 8601，例如`2026-05-20T13:00:00+08:00` |
| 技术假设 | React/Next.js Web Demo、Backend API Service、JSON/SQLite Demo存储 |
| 契约基准 | `00_project_vision.md`到`09_demo_script.md` |

本文件面向LifePilot工程实现阶段，规定代码目录、命名、类型、联调、CI扫描和Code Review红线。它不重新定义产品、Schema、API、Agent流程或Mock能力，只把00-09已经确定的契约转成开发时必须遵守的工程规则。

当前仓库实际文件名为`03_schema.md`时，正文统一使用项目最终文件名`03_data_schema.md`。

## 2. 文档目标与边界

### 2.1 本文回答什么

| 问题 | 10中的回答 |
| --- | --- |
| 代码目录怎么组织 | 给出推荐仓库结构、前后端分层、测试脚本位置 |
| TypeScript/Python/Node命名如何统一 | 规定文件命名、领域字段、ID前缀、内部对象命名 |
| 前端ViewModel如何和Schema隔离 | 明确`PlanContractView`等只用于展示，不进入03 Schema |
| API Client如何封装 | 统一`/api/v1`、标准响应解析、trace和幂等Header |
| 后端如何分层 | Controller、Service、Orchestrator、MockAPI、SchemaValidator、Store、Logging职责 |
| SchemaValidator放在哪里 | 所有领域对象落库、返回、执行前必须通过03校验 |
| `trace_id`和`idempotency_key`如何贯穿代码 | 写操作关联trace，执行类接口强制幂等 |
| Mock fixture如何投影为03对象 | fixture内部字段先投影，再做Schema校验和HTTP响应 |
| Recovery如何实现版本化 | 原计划不原地覆盖，新计划用`updated_plan_id`关联 |
| LifeMemory如何做隐私分级 | 低打扰、可审计、用户可控，高敏默认不保存 |
| 测试、CI、grep扫描如何阻止旧契约回流 | 给出静态扫描、Schema、Integration、E2E红线 |
| Code Review如何验收 | 提供可直接用于PR审查的阻塞项和建议项 |

### 2.2 本文不回答什么

| 不做 | 说明 |
| --- | --- |
| 不重新定义产品范围 | P0/P1/P2以01为准 |
| 不重新定义系统架构 | 分层和模块职责以02为准 |
| 不重新定义Schema字段 | 字段、枚举、ID前缀以03为准 |
| 不重新定义API路径 | 路径、响应、错误码、Header以04为准 |
| 不重新定义Mock能力 | Mock路径、fixture、failure_injection以06为准 |
| 不重新定义Agent流程 | 主链路、Verifier、Executor、Recovery以05为准 |
| 不新增Demo功能 | P0稳定闭环优先 |
| 不承诺真实平台能力 | 不承诺真实支付、真实短信/微信、真实订座、真实票务或真实第三方爬取 |

## 3. 来源文档与契约优先级

| 优先级 | 来源 | 10中的使用方式 |
| ---: | --- | --- |
| 1 | `03_data_schema.md` | 字段命名、ID前缀、JSONSchema、对象结构、状态枚举、TraceLog、PlanContract、VerifierResult、RecoveryResult、ExecutionResult、Consensus、LifeMemory、ToolAction最终权威 |
| 2 | `04_api_contract.md` | HTTP路径、标准响应、错误码、请求头、trace_id、幂等键、Mock接口路径、Debug边界最终权威 |
| 3 | `05_agent_workflow.md` | Agent主链路、DraftPlan边界、Verifier闸门、Executor、Recovery、Consensus、LifeMemory流程最终权威 |
| 4 | `06_mock_api_design.md` | MockAPI路径、Mock标识、failure_injection、fixture、Mock凭证、Mock边界最终权威 |
| 5 | `07_frontend_design.md` | 前端页面、路由、ViewModel、API Client、移动端、Debug Trace、错误展示最终权威 |
| 6 | `08_evaluation_design.md` | 测试体系、Benchmark、契约扫描、红线检查、验收标准最终权威 |
| 7 | `09_demo_script.md` | Demo点击链路、演示兜底、彩排检查、评委模式展示边界 |
| 8 | `02_system_architecture.md` | 系统分层、模块职责、目录结构、端到端链路 |
| 9 | `01_prd.md` | 产品范围、页面需求、P0/P1/P2、用户流程 |
| 10 | `00_project_vision.md` | 产品定位、核心隐喻、创新点、不做什么 |

冲突处理规则：

1. 字段、枚举、ID前缀、状态、Schema必填项冲突，一律以`03_data_schema.md`为准。
2. API路径、错误码、响应格式、请求头、幂等规则冲突，一律以`04_api_contract.md`为准。
3. Agent执行顺序、Verifier闸门、Recovery版本化策略冲突，一律以`05_agent_workflow.md`为准。
4. Mock路径、Mock标识、failure_injection可见性冲突，一律以`06_mock_api_design.md`为准。
5. 前端路由、ViewModel、组件、移动端展示冲突，一律以`07_frontend_design.md`为准。
6. 测试、Benchmark、契约扫描、红线验收冲突，一律以`08_evaluation_design.md`为准。
7. Demo兜底和现场演示边界参考`09_demo_script.md`，但09不覆盖03/04/05/06/07/08契约。
8. 10不得新增领域Schema字段、API路径、错误码、Trace事件名、ToolAction.type、状态枚举、Mock能力。
9. 10可以定义代码目录约定、命名约定、PR检查清单、CI扫描规则和内部辅助类型，但这些不进入03 Schema或04 API契约。

## 4. 工程总原则

| 原则 | 必须这样做 | 禁止这样做 | 关联来源 |
| --- | --- | --- | --- |
| Schema First | 所有领域对象以03为准，类型、DTO、fixture投影、测试样例都从03同步 | 为了代码方便反向修改Schema字段或枚举 | 03 |
| API Contract First | 所有HTTP接口使用04的`/api/v1`路径、标准响应、错误码和Header | 使用旧路径、临时路径或新增未定义API | 04 |
| PlanContract驱动 | 前端、后端、Agent、Verifier、Executor、Recovery、Benchmark围绕完整`PlanContract`运行 | 把LLM自然语言回答、`DraftPlan`、`PlanBuildCandidate`当最终计划 | 03/05/07 |
| Verifier硬闸门 | 未通过Verifier和Full SchemaValidator不得返回、落库或执行 | 让前端、LLM或Mock直接宣布计划可执行 | 03/05 |
| LLM受控 | LLM只做理解、草案、解释、文案润色 | 让LLM确认余位、票务、路线、天气、执行成功、Verifier通过 | 03/05 |
| Mock透明 | 所有Mock状态、凭证、消息、SocialSignalMock显式标Mock | 把Mock包装成真实平台能力 | 04/06/07 |
| Recovery版本化 | 失败恢复生成新的完整`PlanContract`，通过`updated_plan_id`关联 | 原地覆盖旧PlanContract，只返回局部patch | 03/04/05/06 |
| Trace脱敏 | 写操作和核心对象关联`trace_id`，Debug只展示脱敏Trace | 暴露Prompt、LLM推理链、API Key、高敏payload、普通用户不可见failure_injection | 03/04/05/07 |
| LifeMemory用户可控 | 候选记忆有来源、敏感度、确认状态，高敏默认不保存 | 偷偷画像，关闭个性化后仍读写长期记忆 | 03/05 |
| P0稳定优先 | 规则服务6月7日前稳定Demo，P1/P2只预留或加分 | 让P1/P2成为P0主链路强依赖 | 00-09 |

## 5. 推荐仓库目录结构

以下是工程建议，不进入03 Schema或04 API契约。后端可使用FastAPI、Node.js或其他轻量API服务，但领域契约必须一致。

```text
lifepilot/
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── types/
│   └── tests/
├── backend/
│   ├── controllers/
│   ├── orchestrator/
│   ├── services/
│   ├── mock_api/
│   ├── schemas/
│   ├── data/
│   ├── tests/
│   └── main.py 或 server.ts
├── docs/
│   ├── 00_project_vision.md
│   ├── 01_prd.md
│   ├── 02_system_architecture.md
│   ├── 03_data_schema.md
│   ├── 04_api_contract.md
│   ├── 05_agent_workflow.md
│   ├── 06_mock_api_design.md
│   ├── 07_frontend_design.md
│   ├── 08_evaluation_design.md
│   ├── 09_demo_script.md
│   └── 10_coding_rules.md
└── scripts/
    ├── validate_schema.*
    ├── scan_contract_violations.*
    ├── seed_demo_data.*
    └── run_e2e_demo.*
```

后端分层建议：

```text
Controller
→ Service
→ Agent Orchestrator / Domain Service
→ MockAPIService
→ SchemaValidator
→ Store
→ LoggingService
```

## 6. 命名规范

### 6.1 文件命名

| 类型 | 规则 | 示例 |
| --- | --- | --- |
| 前端组件 | `PascalCase.tsx` | `PlanTimeline.tsx` |
| 前端工具函数 | `camelCase.ts` | `formatTime.ts` |
| 前端类型文件 | 按职责拆分 | `schema.ts`、`api.ts`、`view-model.ts` |
| Python后端服务 | `snake_case.py` | `plan_service.py` |
| Node后端服务 | 统一使用`kebab-case.ts`或项目既有规范 | `plan-service.ts` |
| Schema文件 | 保持`*_schema.json` | `plan_contract_schema.json` |
| Mock fixture | 使用`mock_*.json` | `mock_pois.json` |
| 测试文件 | 遵循技术栈约定 | `*.test.ts`、`*.spec.ts`、`test_*.py` |

### 6.2 领域字段命名

1. 领域对象字段统一使用03中的小写蛇形字段，例如`plan_id`、`trace_id`、`updated_plan_id`。
2. 前端route param可使用`planId`，但映射回领域对象时必须使用`plan_id`。
3. 不得使用泛化`session_id`替代`consensus_session_id`。
4. 不得使用`group_0001`替代`plan_group_id`。
5. 不得使用`vote_page_0001`替代`vote_page_id`。
6. 内部展示对象必须显式命名为View或Projection，不能冒充03领域对象。

### 6.3 ID前缀

ID前缀以03最终定义为准，代码生成器、fixture、测试断言必须使用以下前缀：

| 字段 | 前缀 |
| --- | --- |
| `plan_id` | `plan_` |
| `trace_id` | `trace_` |
| `step_id` | `step_` |
| `poi_id` | `poi_` |
| `action_id` | `act_` |
| `execution_id` | `exec_` |
| `recovery_id` | `rec_` |
| `plan_group_id` | `plangrp_` |
| `vote_page_id` | `vpage_` |
| `consensus_session_id` | `cs_` |
| `vote_id` | `vote_` |
| `memory_id` | `mem_` |
| `candidate_id` | `memcand_` |
| `route_id` | `route_` |
| `log_id` | `log_` |
| `sample_id` | `bench_` |

## 7. 前端编码规则

### 7.1 前端只消费合法对象

1. 计划结果页只渲染完整`PlanContract`或合法`UserVisiblePlanProjection`。
2. 不渲染LLM `DraftPlan`。
3. 不消费Agent内部`PlanBuildCandidate`。
4. 不把ViewModel字段写回03 Schema。
5. 前端不得直接读Mock fixture、JSON文件或SQLite数据。
6. 普通业务流程不得由前端直接调用MockAPI完成，应调用Plan/Execution聚合接口。

### 7.2 API Client规则

1. 所有业务请求走`/api/v1`。
2. 统一解析`success / trace_id / data / error`。
3. 普通用户只展示`error.user_message`。
4. Debug模式才可展示脱敏`error.details`。
5. 写操作携带`X-Trace-Id`，计划后续操作复用`PlanContract.trace_id`。
6. 执行类接口必须携带`X-Idempotency-Key`。
7. API Client不得吞掉`trace_id`，失败态也要保留。
8. `IDEMPOTENCY_CONFLICT`只提示刷新或返回计划页，不自动重复执行。

### 7.3 ViewModel规则

允许的前端展示类型：

```text
PlanContractView
PlanSummary
UserVisiblePlanProjection
TimelineViewItem
ToolTraceViewItem
RecoveryDiffView
```

这些类型只存在于前端展示层，不进入03 Schema，不作为04 API契约。它们可以做格式化、排序、分组和用户可见字段裁剪，但不得改变领域字段语义。

### 7.4 页面状态规则

1. UI loading/error/empty状态不得替代领域状态。
2. `PlanContract.status`、`ToolAction.status`、`ExecutionResult.status`以03为准。
3. 按`ExecutableWindow.expire_at`禁用确认按钮或引导`refresh-window`。
4. 不由前端自行判断余位、票务、路线、天气、执行成功。
5. `VerifierResult.status=fail`且不可恢复时，前端不得显示“确认执行”入口。
6. `VerifierResult.status=warning`必须展示风险和PlanB。

### 7.5 Mock展示规则

1. 普通页面可以显示“Demo模拟数据”“Mock凭证”或“模拟消息已生成”。
2. 普通页面不得展示`failure_injection`或`failure_scenario_id`。
3. 不得写“已真实发送微信”“已真实订座”“已真实支付”“已真实锁票”。
4. SocialSignalMock只能写成口碑Mock或模拟信号，不得写实时抓取。
5. Debug页可展示脱敏Mock来源、API路径摘要和Trace摘要。

### 7.6 移动端规则

1. 375px宽度可完整演示。
2. 底部按钮不遮挡内容、错误提示、投票表单或时间线。
3. 时间线可滚动，节点时间和状态不重叠。
4. Debug面板可折叠，不影响普通Demo。
5. 投票页单手可完成喜欢、反选、预算、文字提交。
6. 普通用户页不得为了Debug塞入不可见但可被截图扫到的敏感字段。

## 8. 后端编码规则

### 8.1 Controller规则

Controller只负责：

1. 参数校验。
2. `trace_id`创建或复用。
3. Demo用户与权限检查。
4. `X-Idempotency-Key`必填校验。
5. 标准响应包装。
6. 将请求转发给Service或Orchestrator。

Controller禁止：

1. 写复杂业务逻辑。
2. 直接读写Mock fixture。
3. 绕过Service直接拼`PlanContract`。
4. 暴露底层异常堆栈给普通用户。
5. 返回非04标准响应。

### 8.2 Service规则

| Service | 职责 |
| --- | --- |
| `PlanService` | `PlanContract`持久化和读取，不负责LLM生成 |
| `VerifierService` | 硬约束校验，输出合法`VerifierResult` |
| `ExecutorService` | 只执行`ToolAction`，不执行自然语言 |
| `RecoveryService` | 版本化恢复，生成新完整`PlanContract` |
| `ConsensusService` | 投票、统计、finalize和共识约束 |
| `LifeMemoryService` | 记忆候选、隐私分级、确认/忽略 |
| `LoggingService` | `TraceLog`和用户可见Trace投影 |
| `MockAPIService` | Mock状态查询和Mock执行凭证 |

### 8.3 SchemaValidator规则

1. 完整`PlanContract`必须通过03 JSONSchema。
2. `VerifierResult`、`RecoveryResult`、`ExecutionResult`、`ConsensusVote`、`MemoryCandidate`等对象也要按03校验。
3. Schema校验失败不得持久化为合法计划。
4. Schema失败只允许有限重试，不能无限自修复。
5. Agent输出必须先进入内部对象，不能直接落库为`PlanContract`。
6. 字段缺失不得靠前端补，必须由后端Builder或SchemaValidator前置处理。

### 8.4 标准响应规则

成功响应：

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {},
  "error": null
}
```

失败响应：

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

规则：

1. `error.code`只能使用04定义的错误码。
2. 不新增`MOCK_API_FAILED`、`UNKNOWN_MOCK_ERROR`等未定义错误码。
3. 普通用户页只展示`error.user_message`。
4. `details`只允许Debug/评委模式展示，且必须脱敏。

## 9. Agent编码规则

### 9.1 主链路顺序

Agent主链路必须按05执行：

```text
InputGateway
→ Trace初始化
→ IntentParser
→ ConstraintExtractor
→ MemoryRetriever/P0可弱化
→ CandidateRetriever
→ MockAPI状态查询
→ PlanGenerator
→ PlanBuildCandidate预检
→ Verifier
→ PlanContractBuilder
→ Full SchemaValidator
→ PlanRanker
→ ResponseAssembler
→ Trace写入
```

不得把`PlanContractBuilder`放在Verifier硬校验之后却跳过Full SchemaValidator；不得让`ResponseAssembler`修改PlanContract本体。

### 9.2 LLM使用边界

LLM可以：

1. 目标理解摘要。
2. 场景初判。
3. 约束候选抽取。
4. 候选计划草案。
5. 解释说明。
6. 群聊消息草案。
7. 纪念日话术。
8. Recovery用户解释润色。

LLM不能：

1. 确认餐厅有位。
2. 确认活动可预约。
3. 确认路线通畅。
4. 确认天气安全。
5. 确认执行成功。
6. 绕过Verifier。
7. 写入长期LifeMemory。
8. 输出不符合03 Schema的`PlanContract`。

### 9.3 内部对象规则

可以存在内部对象：

```text
DraftPlan
PlanBuildCandidate
CandidateSet
InternalFixturePOI
UserVisibleTraceEvent
```

规则：

1. 它们不进入03 Schema。
2. 不作为04 API响应对象。
3. 不直接返回给前端当作`PlanContract`。
4. 进入用户页面前必须投影或构建成合法对象。
5. 类型文件应和领域Schema类型分开存放。

## 10. MockAPI编码规则

### 10.1 MockAPI不是伪装真实平台

禁止代码、日志、文案中出现暗示真实执行的表达：

```text
已真实支付
已真实发送微信/短信
已真实订座
已真实锁票
已实时抓取小红书/抖音/点评
已调用真实商家系统
真实平台确认可用
```

正确表达：

```text
Mock预约号已生成
Mock订座号已生成
Mock订单号已生成
模拟消息已生成
Demo模拟数据
口碑Mock信号
```

### 10.2 Mock路径必须使用04/06最终路径

P0路径以04/06为准，不新增路径：

| 能力 | 路径 |
| --- | --- |
| POI搜索 | `GET /api/v1/mock/poi/search` |
| 餐厅搜索 | `GET /api/v1/mock/restaurants/search` |
| POI状态 | `GET /api/v1/mock/poi/{poi_id}/status` |
| 餐厅状态 | `GET /api/v1/mock/restaurants/{poi_id}/status` |
| 路线估计 | `GET /api/v1/mock/routes/estimate` |
| 天气查询 | `GET /api/v1/mock/weather` |
| 活动预约 | `POST /api/v1/mock/activities/{poi_id}/book` |
| 餐厅订座/排号 | `POST /api/v1/mock/restaurants/{poi_id}/reserve` |
| 创建Mock订单 | `POST /api/v1/mock/orders/create` |
| 模拟消息发送 | `POST /api/v1/mock/messages/send` |
| Mock口碑信号 | `GET /api/v1/mock/social-signals/{poi_id}` |

禁止旧路径：

```text
/api/mock/...
```

### 10.3 fixture投影规则

Mock内部fixture可以有内部字段，但HTTP响应和PlanContract引用必须投影回03/04对象。

```text
InternalFixturePOI
→ POIProjection
→ 03 POI Schema校验
→ HTTP Response
```

fixture中的`failure_injection`只用于Demo、Debug和测试，不进入普通用户可见响应。

### 10.4 查询快照不等于执行成功

1. 状态查询用于Verifier和`ExecutableWindow`。
2. 执行动作用于用户确认后的模拟锁定。
3. 查询时可用不保证执行时成功。
4. 执行失败触发Recovery。
5. 窗口过期必须阻断或调用`refresh-window`。
6. Mock执行类接口必须幂等，重复请求返回同一Mock凭证或幂等冲突。

## 11. Verifier、Executor、Recovery编码规则

### 11.1 Verifier规则

1. Verifier只验证结构化对象。
2. `VerifierResult.status`只能是`pass / warning / fail`。
3. `fail`且不可恢复时不得进入Executor。
4. `warning`必须展示风险和PlanB。
5. Verifier不得调用LLM补状态。
6. Verifier结果必须写入TraceLog。
7. Verifier输入中的余位、路线、天气必须来自MockAPI或规则计算。

### 11.2 Executor规则

1. Executor只执行`ToolAction`。
2. 不执行自然语言文案。
3. 执行类接口必须有`X-Idempotency-Key`。
4. Mock凭证必须含Mock标识。
5. 执行失败要返回04定义错误码。
6. 窗口过期不得继续假装执行成功。
7. 执行动作按`depends_on`拓扑顺序执行。

### 11.3 ToolAction规则

1. 订单动作统一使用`order_item`。
2. 禁止使用`create_order`作为`ToolAction.type`。
3. `ToolAction.target_poi_id`必须能引用到存在的POI或合法target。
4. `ToolAction.step_id`必须引用存在的`PlanStep`。
5. ToolAction缺字段必须阻断执行。
6. `ToolAction.idempotency_key`可用于内部动作追踪，但不能替代HTTP Header。

### 11.4 Recovery规则

1. Recovery采用版本化策略。
2. 原`PlanContract`不原地覆盖。
3. 原`plan_id`状态更新为`recovered`。
4. `RecoveryResult.updated_plan_id`指向新的完整`PlanContract`。
5. 新`PlanContract`必须重新Verifier和SchemaValidator。
6. `RecoveryResult`必须使用`original / replacement / diff / updated_plan_id`。
7. 禁止使用旧字段`new_poi / changes / original_step_id`。
8. 新ToolAction使用新的`action_id`和新的内部幂等键，不复用旧失败动作。

## 12. Consensus编码规则

1. 共识字段使用`consensus_session_id`、`vote_page_id`、`plan_group_id`、`vote_id`。
2. 禁止使用泛化`session_id`。
3. 朋友投票页可以匿名提交，但finalize默认发起人操作。
4. `liked_plan_ids`和`disliked_plan_ids`不能重叠。
5. 投票至少应有喜欢、反选、预算或文字反馈中的一种有效信息。
6. finalize后必须重新生成最终`PlanContract`并重新Verifier。
7. `ConsensusSummary`不得绕过Schema和Trace。
8. 投票文字反馈可以由LLM辅助摘要，但最终约束必须规则化。
9. 群聊消息只能是草案或Mock消息，不得写真实微信已发送。

## 13. LifeMemory编码规则

1. LifeMemory不是偷偷画像。
2. 用户当次输入优先于长期记忆。
3. `use_memory=false`时不读取、不写入长期记忆。
4. 低敏可生成候选。
5. 中敏必须用户确认。
6. 高敏默认不保存。
7. `MemoryCandidate`必须含来源、置信度、敏感度、有效期、用户可见性、确认状态。
8. 不得保存精确住址、健康诊断、收入等高敏内容到长期记忆。
9. 普通页面不得展示高敏详情。
10. 关闭个性化后不读写长期记忆；当前会话可保留必要上下文，但不得生成长期候选。

## 14. Trace与日志编码规则

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

禁止：

```text
mock_call
mock_log
api_log
未定义Trace事件名
```

Trace规则：

1. 所有写操作必须关联`trace_id`。
2. 所有核心对象必须可追踪，包括PlanContract、ToolAction、VerifierResult、RecoveryResult、ExecutionResult、Consensus、MemoryCandidate。
3. 普通用户只看简化工具调用链。
4. Debug/评委模式可看脱敏Trace。
5. 不得返回Prompt、LLM推理链、API Key、高敏payload、failure_injection给普通用户。
6. MockAPI调用统一写`tool_log`，候选召回摘要才写`poi_log`。

## 15. 错误处理规则

1. HTTP状态码表达传输和请求层状态，业务错误码表达领域失败原因。
2. 领域错误码不得新增，只能使用04定义的错误码。
3. 普通用户只展示`error.user_message`。
4. `recoverable=true`展示重试、刷新或自动恢复入口。
5. `NO_TABLE_AVAILABLE`和`ACTIVITY_FULL`优先触发Recovery。
6. `PLAN_EXECUTABLE_WINDOW_EXPIRED`优先引导`refresh-window`。
7. `MEMORY_PRIVACY_VIOLATION`不展示高敏内容。
8. `IDEMPOTENCY_CONFLICT`不得自动重放执行动作。
9. `PLAN_SCHEMA_INVALID`、`VERIFIER_RESULT_INVALID`不得降级为“正常计划已生成”。

常见HTTP状态关系以04为准：

| HTTP状态 | 用途 |
| --- | --- |
| 400 | 请求参数、Header、Schema输入错误 |
| 401/403 | Demo用户或权限错误 |
| 404 | 资源不存在 |
| 409 | 状态冲突、幂等冲突、窗口过期 |
| 422 | 领域对象校验失败 |
| 500 | 未预期服务端错误，普通用户只看友好文案 |

## 16. 幂等与状态管理规则

1. GET天然幂等。
2. `POST /api/v1/plans/create`建议幂等。
3. `POST /api/v1/plans/{plan_id}/execute`必须幂等。
4. `POST /api/v1/plans/{plan_id}/recover`必须或强烈建议幂等，前端按必须处理。
5. Mock执行类接口必须幂等。
6. 同一个`X-Idempotency-Key`用于不同plan必须返回`IDEMPOTENCY_CONFLICT`。
7. 后端可以生成内部`ToolAction.idempotency_key`，但不能替代HTTP Header。
8. 前端重复点击同一执行按钮不得生成新的幂等键。
9. Recovery后的新ToolAction不得复用旧失败动作的HTTP幂等键。

## 17. 类型与Schema同步规则

1. 前端`types/schema.ts`应从03 Schema手动同步或生成。
2. 后端Pydantic、TypeScript、Zod类型不得反向修改03。
3. ViewModel类型与Schema类型分文件。
4. Mock内部类型与HTTP响应类型分文件。
5. API DTO与领域对象分层，但不得改变字段语义。
6. 字段缺失不得靠前端补，必须由后端Builder或SchemaValidator处理。
7. 测试fixture应先通过03/06投影校验，再进入E2E。
8. 新增内部辅助类型时必须在代码注释或类型名中表明不进入03/04契约。

## 18. 测试与CI规则

### 18.1 静态扫描

CI必须扫描并阻断：

| 扫描项 | 阻断内容 |
| --- | --- |
| ToolAction旧类型 | `create_order`作为`ToolAction.type` |
| 旧Mock路径 | `/api/mock/...` |
| 未定义错误码 | 04未定义的领域错误码 |
| 未定义Trace事件名 | `mock_call`、`mock_log`、`api_log`等 |
| 非ISO时间格式 | `2026-05-20 13:00:00`、`今天下午一点`进入API/Schema |
| failure_injection泄露 | 普通页面出现`failure_injection` |
| 真实平台文案 | 真实支付、短信、微信、订座、票务、实时抓取等表述 |
| 敏感信息泄露 | Prompt、chain-of-thought、API Key |
| Recovery旧字段 | `new_poi / changes / original_step_id` |
| Consensus旧字段 | 泛化`session_id`误用为共识会话 |
| DraftPlan泄露 | 前端Props或API响应出现`DraftPlan`、`PlanBuildCandidate` |

### 18.2 Schema测试

必须测试：

1. `PlanContract`必填字段。
2. ID前缀。
3. ISO时间。
4. timeline非空连续。
5. ToolAction引用完整。
6. `VerifierResult`合法。
7. `RecoveryResult`包含`original/replacement/diff/updated_plan_id`。
8. `ExecutionResult`含Mock凭证标识。
9. `ConsensusVote`喜欢和反选不重叠。
10. `MemoryCandidate`敏感度和确认状态合法。

### 18.3 Integration测试

至少覆盖：

1. 家庭亲子生成`PlanContract`。
2. 餐厅满座触发Recovery。
3. 活动满员触发Recovery。
4. 可执行窗口过期阻断执行。
5. 朋友局投票finalize后重新Verifier。
6. Feedback生成`MemoryCandidate`。
7. 执行类接口缺少`X-Idempotency-Key`时拒绝。
8. 同一幂等键重复执行返回同一结果。

### 18.4 E2E测试

至少覆盖：

1. 首页提交家庭亲子输入→计划页→执行→Mock凭证。
2. 朋友局创建投票→提交喜欢/反选/free_text→finalize→最终计划。
3. 执行返回`NO_TABLE_AVAILABLE`→展示Recovery Diff和`updated_plan_id`。
4. 普通用户页不展示Prompt、推理链、API Key、failure_injection。
5. 375px移动端主链路可操作。
6. 窗口过期时执行按钮禁用或引导刷新。

## 19. 环境变量与配置规则

1. API Origin与Base Path必须显式配置，Base Path固定`/api/v1`。
2. Demo用户使用配置项，例如`X-Demo-User-Id`或后端默认Demo用户。
3. Debug/评委模式必须有开关，不得默认向普通用户开放。
4. Mock failure scenario必须有开关，默认不污染普通路径。
5. 不把API Key写入前端。
6. 不把真实用户隐私写入Mock fixture。
7. 本地、Demo、测试环境配置隔离。
8. 配置缺失时应返回明确错误，而不是静默伪造状态。
9. `failure_injection`只允许测试、Debug或评委模式读取。

## 20. 安全与隐私红线

1. 不暴露Prompt。
2. 不暴露LLM推理链。
3. 不暴露API Key。
4. 不保存高敏LifeMemory。
5. 不向普通用户展示`failure_injection`。
6. 不让Mock伪装真实平台。
7. 不让LLM决定真实状态。
8. 不把Trace做成未脱敏日志流。
9. 不把用户输入写入不受控日志。
10. 不把真实个人隐私写入fixture。

## 21. P0实现顺序建议

以下是工程建议，不是新增功能：

1. 先落03 Schema类型和校验器。
2. 再落04 API标准响应和API Client。
3. 再落Mock fixture和MockAPI投影。
4. 再落Plan create主链路。
5. 再落Verifier和`ExecutableWindow`。
6. 再落Executor。
7. 再落Recovery版本化。
8. 再落朋友局Consensus。
9. 再落Feedback和`MemoryCandidate`最小闭环。
10. 最后落Trace Debug页、CI扫描、Demo兜底脚本。

## 22. PR Code Review清单

| 检查项 | 是否阻塞 | 通过标准 |
| --- | --- | --- |
| 是否新增了03没有的字段 | 是 | 领域对象字段完全来自03；内部字段明确不进入03/04 |
| 是否新增了04没有的API路径 | 是 | 所有业务路径来自04，Mock路径来自04/06 |
| 是否新增了错误码 | 是 | `error.code`只使用04定义 |
| 是否新增了Trace事件名 | 是 | 只使用最终11类Trace事件 |
| 是否使用旧路径 | 是 | 不出现`/api/mock/...`或未带`/api/v1`的业务路径 |
| 是否使用`create_order` | 是 | ToolAction订单动作使用`order_item` |
| 是否跳过Verifier | 是 | 计划返回、落库、执行前均有Verifier和SchemaValidator |
| 是否执行自然语言文案 | 是 | Executor只执行`ToolAction` |
| 是否原地覆盖Recovery | 是 | 新计划通过`updated_plan_id`关联，原计划保留 |
| 是否普通页面展示`failure_injection` | 是 | 普通用户投影过滤，Debug受开关控制 |
| 是否Mock伪装真实能力 | 是 | 文案和凭证均标Mock/模拟 |
| 是否泄露Prompt/API Key/推理链 | 是 | Trace、日志、Debug、前端快照均不含敏感信息 |
| 是否执行类接口缺少幂等键 | 是 | 缺`X-Idempotency-Key`时拒绝执行 |
| 是否没有Schema测试 | 是 | 涉及领域对象变更必须有Schema测试 |
| 是否没有E2E覆盖主链路 | 是 | P0链路变更必须覆盖家庭亲子、执行/Recovery或Consensus相关E2E |
| 是否前端读fixture | 是 | 前端只通过`/api/v1`接口读取业务数据 |
| 是否LLM决定可执行状态 | 是 | 可执行状态来自MockAPI/规则/Verifier |
| 是否LifeMemory偷偷画像 | 是 | 中敏确认，高敏不保存，来源可见 |
| 是否P1/P2破坏P0 | 是 | P1/P2仅预留或加分，不阻塞P0闭环 |

## 23. 禁止项总表

| 禁止项 | 正确做法 |
| --- | --- |
| 禁止新增领域Schema字段 | 按03同步类型；内部字段标注不进入03 |
| 禁止新增API路径 | 使用04已有路径 |
| 禁止新增错误码 | 使用04定义错误码 |
| 禁止新增Trace事件名 | 使用最终11类Trace事件 |
| 禁止使用旧Recovery字段 | 使用`original/replacement/diff/updated_plan_id` |
| 禁止使用`create_order` | 使用`order_item` |
| 禁止使用`/api/mock/...` | 使用`/api/v1/mock/...` |
| 禁止前端读fixture | 前端只走`/api/v1` |
| 禁止前端自行判断余位/天气/路线/执行成功 | 由MockAPI、Verifier、Executor返回结构化结果 |
| 禁止LLM决定可执行状态 | LLM只做理解、草案、解释、文案 |
| 禁止Mock伪装真实平台 | 所有状态、凭证、消息、口碑显式标Mock |
| 禁止真实支付/真实短信/真实微信/真实订座/真实票务/真实爬取表述 | 使用Mock、模拟、可复制草案等透明表达 |
| 禁止普通用户页展示`failure_injection` | 仅Debug/测试/评委模式脱敏展示 |
| 禁止暴露Prompt、LLM推理链、API Key | Trace和Debug只展示脱敏投影 |
| 禁止LifeMemory偷偷画像 | 候选化、敏感度分级、用户确认或忽略 |

## 24. 2026-05-26追加：重构维护规则

1. 不允许在仓库中提交真实或疑似真实的模型、地图、支付、短信、微信等服务凭证；示例凭证必须使用`EMPTY`、`your_key_here`或中文占位。
2. LLM Provider默认不得因为缺凭证导致主链路失败；规则兜底必须覆盖P0样例。
3. API Controller请求体转字典必须兼容Pydantic v1/v2，不直接散落调用`.dict(exclude_none=True)`。
4. 前端新增业务请求必须经过统一API客户端，继承Trace、幂等键和标准错误处理。
5. E2E smoke默认单worker；如需并发测试，单独新增性能/压力脚本，不改P0巡检默认稳定性。
6. 生成物、依赖目录、缓存和系统文件必须进入`.gitignore`；若历史已追踪，不在功能重构中混入大规模删除，单独开清理提交处理。
7. 实验日志处理完必须改名为`*_finished.md`，并保证对应代码、文档和验证记录已经对齐。
