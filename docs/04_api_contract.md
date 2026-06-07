# 04_api_contract.md

## 1.文档信息

| 项目 | 内容 |
|---|---|
| 文档名称 | 04_api_contract.md |
| 项目名称 | LifePilot |
| 产品定位 | 生活时间导航Agent |
| 文档类型 | API契约文档 |
| 文档版本 | v0.1 |
| API版本 | /api/v1 |
| 面向读者 | 前端、后端、Agent、Mock数据、测试、评委 |
| 主要目标 | 将LifePilot从PlanContract数据契约落成可联调、可测试、可演示的HTTP/API接口契约 |
| 当前范围 | 比赛Demo阶段，优先完成P0闭环，P1/P2仅做接口预留 |

LifePilot的统一表达为：

> 高德导航的是一段路，LifePilot导航的是一段生活时间。

本文件不是PRD、不是系统架构文档、不是完整JSONSchema复制件，而是面向联调开发的接口契约。所有接口围绕如下闭环组织：

本文档的API契约以`03_data_schema.md`为最终字段权威。HTTP层允许新增请求头、分页、调试字段和少量API层ID，但不得覆盖或改写`03_data_schema.md`中已冻结的领域字段、状态枚举、ID前缀、时间格式和Schema必填项。

```text
自然语言目标
→ PlanContract
→ MockAPI状态查询
→ Verifier验证
→ 可执行窗口
→ 用户确认
→ Executor模拟执行
→ 失败Recovery
→ 低打扰反馈
→ LifeMemory候选更新
```

---

## 2.API设计目标与边界

### 2.1设计目标

| 目标 | 说明 |
|---|---|
| 前端可开发 | 明确每个页面调用哪个API、loading/error/success如何处理 |
| 后端可实现 | 明确Controller、Domain Service、Agent Orchestrator、MockAPI之间的调用边界 |
| Agent可编排 | 明确哪些接口触发Agent，哪些接口只是Domain Service或Mock Service |
| Mock可造数 | 明确Mock状态、Mock凭证、失败注入、社交口碑Mock的返回结构 |
| 测试可验收 | 明确正常样例、异常样例、状态变化、幂等要求、验收标准 |
| 评委可理解 | 展示LifePilot不是普通聊天，而是PlanContract驱动的可执行Agent闭环 |

### 2.2能力边界

| 类型 | 本版本处理方式 |
|---|---|
| 真实支付 | 不做，订单接口仅返回Mock凭证 |
| 真实短信/微信 | 不做，消息发送接口仅返回Mock消息ID |
| 真实订座/票务 | 不做，预约和订座均为Mock执行 |
| 真实第三方爬取 | 不做，小红书/抖音/点评等只作为Mock SocialSignal |
| 全城覆盖 | 不做，Demo固定数字孪生区域：杭州下沙/金沙湖/高教园区 |
| 高敏画像 | 不自动保存，高敏MemoryCandidate默认不落库为长期记忆 |
| 底层Prompt/推理链 | 不通过API暴露，不进入用户页Debug |

### 2.3P0 API总目标

P0必须跑通：

```text
首页输入
→ POST /api/v1/plans/create
→ 计划结果页
→ POST /api/v1/plans/{plan_id}/execute
→ Mock执行
→ NO_TABLE_AVAILABLE/ACTIVITY_FULL时自动Recovery
→ 执行结果页
→ POST /api/v1/feedback
→ MemoryCandidate候选展示
```

朋友局P0必须跑通：

```text
候选方案组
→ POST /api/v1/consensus/create
→ GET /api/v1/vote-pages/{vote_page_id}
→ POST /api/v1/consensus/{consensus_session_id}/vote
→ POST /api/v1/consensus/{consensus_session_id}/finalize
→ 最终PlanContract
```

---

## 3.来源文档与契约优先级

### 3.1来源文档

| 优先级 | 来源 | 用途 |
|---:|---|---|
| 1 | 03_data_schema.md | 字段命名、ID前缀、JSONSchema、时间格式、错误码、PlanContract、Consensus、LifeMemory、RecoveryResult、ToolAction最终契约 |
| 2 | 02_system_architecture.md | 模块边界、调用链路、服务分层、状态机、执行与恢复流程 |
| 3 | 01_prd.md | 页面结构、P0/P1/P2功能范围、交互与验收标准 |
| 4 | 00_project_vision.md | 产品定位、核心隐喻、场景范围、创新点、不做什么 |

### 3.2冲突处理规则

1. 若`01_prd.md`或`02_system_architecture.md`中的早期样例与`03_data_schema.md`冲突，API契约一律以`03_data_schema.md`为准。
2. 早期示意中的`group_0001`、`vote_page_0001`、泛化`session_id`不进入API契约。
3. `BackupPlan`不是完整`PlanContract`，不得使用`plan_id`表示BackupPlan。
4. `RecoveryResult`必须使用`original`、`replacement`、`diff`，不得使用旧字段`original_step_id`、`original_poi`、`new_poi`、`changes`。
5. API层可以新增HTTP必需字段，例如`request_id`、`page_token`、`idempotency_key`，但不得替代领域模型字段。
6. TraceLog的`event_type`必须使用`03_data_schema.md`定义的枚举。MockAPI调用不得新增`mock_call`作为事件类型，应使用`event_type:"tool_log"`，并通过`module:"MockAPIService"`或`payload.tool_name`表达具体工具。

---

## 4.通用API规范

### 4.1API Origin与Base Path

Demo环境：

```text
API Origin: https://demo.lifepilot.local
Base Path: /api/v1
```

本地开发：

```text
API Origin: http://localhost:3000
Base Path: /api/v1
```

如前端Next.js与后端分离，也可配置：

```text
API Origin: http://localhost:8000
Base Path: /api/v1
```

本文接口文档统一写完整路径，例如`POST /api/v1/plans/create`。前端封装请求时应使用`API Origin + 接口完整路径`，不得再额外拼接一次`/api/v1`。

### 4.2版本策略

| 项 | 规则 |
|---|---|
| URL版本 | 固定使用`/api/v1` |
| 数据版本 | PlanContract.version使用`v0.1` |
| 向后兼容 | P0冻结字段不得删除、重命名或改变语义 |
| 破坏性变更 | 必须升级到`/api/v2`或PlanContract.version大版本 |
| 不支持版本 | 返回`VERSION_NOT_SUPPORTED` |

### 4.3Content-Type

所有请求与响应默认：

```http
Content-Type: application/json; charset=utf-8
Accept: application/json
```

### 4.4标准请求头

| Header | 必填 | 示例 | 说明 |
|---|---:|---|---|
| Content-Type | 是 | application/json | 请求体格式 |
| Accept | 是 | application/json | 响应格式 |
| X-Demo-User-Id | 否 | user_demo_001 | Demo用户标识，未传则后端使用默认用户 |
| X-Trace-Id | 写操作建议 | trace_20260520_0001 | 前端可传；未传由后端创建 |
| X-Idempotency-Key | 写操作建议，执行类必填 | idem_exec_20260520_0001 | 防重复提交；执行类HTTP接口缺失时直接拒绝 |
| X-Debug-Mode | 否 | true | 仅开发/评委模式可用 |
| X-Client-Version | 否 | web-demo-0.1 | 方便兼容排查 |

### 4.5trace_id策略

| 场景 | 策略 |
|---|---|
| `POST /plans/create` | 若请求头未提供`X-Trace-Id`，后端创建新`trace_id` |
| 计划verify/execute/recover | 复用PlanContract.trace_id，必要时可在TraceLog中创建子事件 |
| Consensus | 创建时生成或复用候选方案来源trace_id；所有Vote、Summary必须带trace_id |
| Feedback | 复用plan_id关联trace_id；若无plan_id则新建trace_id |
| Memory | 长期记忆使用`source_trace_id`和`last_used_trace_id`，不等同于单次trace |
| MockAPI直接调用 | Debug场景可单独创建trace_id，普通业务调用复用上游trace_id |

写操作如果完全缺失trace且后端无法创建，返回：

```json
{
  "success": false,
  "trace_id": null,
  "data": null,
  "error": {
    "code": "TRACE_ID_MISSING",
    "message": "trace_id is missing and cannot be created.",
    "user_message": "系统追踪异常，请重试。",
    "recoverable": true,
    "details": {}
  }
}
```

## 34. 2026-05-26追加：运行态LLM设置与请求体兼容规则

当前`GET/PATCH /api/v1/settings/llm`实现遵循以下补充规则：

1. 仓库不得内置DeepSeek、Qwen或其他Provider的默认明文凭证。
2. `GET /api/v1/settings/llm`在未配置凭证时返回`credential_configured:false`和空`credential_mask`。
3. `PATCH /api/v1/settings/llm`只在本进程内更新运行态配置；响应仍只返回脱敏投影，不回显`credential`。
4. 不支持的`provider`返回`BAD_REQUEST`标准错误，不落入500。
5. 受控LLM不可用、禁用或缺凭证时，IntentParser和PlanGenerator必须走规则/模板兜底，不影响MockAPI、Verifier、Executor和Recovery。
6. 后端Controller层不得依赖Pydantic v1专用`.dict()`行为；请求体转字典统一兼容Pydantic v1/v2，并保持`exclude_none=True`。

安全断言：

```json
{
  "provider": "deepseek",
  "enabled": false,
  "credential_configured": false,
  "credential_mask": ""
}
```

该投影表示“未配置凭证”，不是错误状态；只有显式启用并执行受控LLM调用时才需要真实凭证。

### 4.6idempotency_key策略

| 接口类型 | 是否需要 | 规则 |
|---|---:|---|
| 查询接口GET | 否 | 天然幂等 |
| Plan创建 | 建议 | 同一`idempotency_key`+同一用户+同一输入，返回同一plan或冲突 |
| Verify | 否 | 同一PlanContract版本输入应得到相同结果 |
| Execute | 必填 | 防止重复预约、重复下单、重复发消息 |
| Recover | 必填 | 同一failed_action只恢复一次 |
| Mock执行类接口 | 必填 | 活动预约、餐厅订座、下单、发消息不得重复生成Mock凭证 |
| Vote | 建议 | 同一参与者可更新投票，但finalize后不可更新 |
| Memory确认/忽略 | 建议 | 同一candidate重复确认返回当前结果 |

幂等冲突返回`IDEMPOTENCY_CONFLICT`。例如同一个`X-Idempotency-Key`用于不同plan执行时必须拒绝。

执行类HTTP接口不得由后端代生成`X-Idempotency-Key`。缺失时返回`400 BAD_REQUEST`：

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "BAD_REQUEST",
    "message": "X-Idempotency-Key is required for execution APIs.",
    "user_message": "请勿重复提交，刷新后再试。",
    "recoverable": true,
    "details": {}
  }
}
```

后端可以为内部`ToolAction.idempotency_key`生成默认值，但不能替代HTTP层执行幂等键。

### 4.7时间格式

所有API请求和响应时间字段统一ISO 8601：

```json
"2026-05-20T13:00:00+08:00"
```

禁止在API中使用：

```json
"2026-05-20 13:00:00"
"今天下午一点"
"13:00"
```

展示文案由前端格式化，不进入API契约。

### 4.8Mock标识规范

| 对象 | 必须字段 |
|---|---|
| Mock POI | `mock_only:true` |
| Mock状态 | `source:"mock_api"`或`mock_only:true` |
| Mock凭证 | `mock_only:true` |
| SocialSignal | `is_mock:true`、`source_type:"mock_social_signal"` |
| Mock消息 | `mock_only:true`，不得暗示真实微信/短信已发送 |

failure_injection只允许Debug或测试场景返回，不得展示给普通用户页。

### 4.9分页格式

分页用于Memory列表、Trace事件、Benchmark样例等列表接口。

请求参数：

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| page_size | integer | 否 | 20 | 默认20，最大100 |
| page_token | string | 否 | cursor_abc | 下一页游标 |

响应格式：

```json
{
  "items": [],
  "page_info": {
    "page_size": 20,
    "next_page_token": null,
    "has_more": false
  }
}
```

---

## 5.通用响应格式

### 5.1标准成功响应

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {},
  "error": null
}
```

### 5.2标准失败响应

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

### 5.3Error字段规范

| 字段 | 类型 | 必填 | 说明 |
|---|---|---:|---|
| code | string | 是 | 业务错误码或API层错误码 |
| message | string | 是 | 面向开发的简短错误说明，不含堆栈 |
| user_message | string | 是 | 面向用户的可展示文案 |
| recoverable | boolean | 是 | 是否可重试、恢复或刷新 |
| details | object | 否 | Debug模式可返回安全细节；普通用户页应弱化 |

### 5.4Debug字段可见性原则

| 字段/内容 | 普通用户页 | Debug/评委模式 | 说明 |
|---|---:|---:|---|
| 工具调用摘要 | 可见 | 可见 | 展示“查了余位/路线/天气” |
| ToolAction完整payload | 不展示 | 可展示 | 不含敏感信息 |
| failure_injection | 不展示 | 可展示 | 仅测试用 |
| 底层Prompt | 不展示 | 不展示 | 禁止外泄 |
| LLM推理链 | 不展示 | 不展示 | 禁止外泄 |
| API Key | 不展示 | 不展示 | 禁止外泄 |
| 高敏MemoryCandidate | 不展示 | 不展示 | 默认不保存 |
| TraceLog敏感payload | 不展示 | 可脱敏展示 | 只用于开发定位 |

---

## 6.认证、Demo用户与权限边界

### 6.1Demo用户

P0 Demo可不做真实登录，使用固定用户：

```json
{
  "user_id": "user_demo_001",
  "display_name": "小明",
  "personalization_enabled": true
}
```

前端可通过`X-Demo-User-Id`切换Demo用户。

### 6.2权限边界

| 操作 | 权限规则 |
|---|---|
| 查看Plan | 创建者可查看；投票页可查看候选方案摘要 |
| 执行Plan | 仅创建者可执行 |
| 创建投票 | 仅创建者可基于PlanGroup创建 |
| 提交投票 | 访问vote_page_id即可提交；可匿名 |
| Finalize共识 | 默认仅创建者可finalize |
| 查看Memory | 仅用户本人可查看 |
| 修改/删除Memory | 仅用户本人可操作 |
| Debug Trace | 仅开发/评委模式可访问 |

### 6.3未授权错误

Demo阶段不接入真实OAuth，但权限不匹配时返回：

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "UNAUTHORIZED_DEMO_USER",
    "message": "demo user is not allowed to access this resource.",
    "user_message": "你没有权限操作这个Demo资源。",
    "recoverable": false,
    "details": {}
  }
}
```

---

## 7.trace_id、idempotency_key与请求追踪

### 7.1Trace事件类型

| event_type | 说明 | P0 |
|---|---|---:|
| input_log | 用户输入 | 是 |
| intent_log | 场景识别与意图抽取 | 是 |
| constraint_log | 约束抽取 | 是 |
| memory_log | 读取LifeMemory或生成MemoryCandidate | P0最小，P1完整 |
| poi_log | POI/餐厅候选检索 | 是 |
| tool_log | MockAPI调用、ToolAction工具调用 | 是 |
| verifier_log | Verifier检查 | 是 |
| recovery_log | Recovery触发与结果 | 是 |
| executor_log | Executor执行过程 | 是 |
| feedback_log | 低打扰反馈 | 是 |
| error_log | 错误事件 | 是 |

### 7.2TraceLog最小字段

| 字段 | 类型 | 说明 |
|---|---|---|
| log_id | string | `log_`前缀 |
| trace_id | string | `trace_`前缀 |
| event_type | string | 事件类型 |
| module | string | Controller/Agent/Verifier等 |
| level | string | info/warning/error |
| payload | object | 脱敏后的事件载荷 |
| visible_to_user | boolean | 是否可展示到工具调用链 |
| created_at | string | ISO 8601 |

### 7.3请求追踪要求

1. 所有写接口必须最终关联`trace_id`。
2. 所有PlanContract、ToolAction、VerifierResult、RecoveryResult、ExecutionResult、ConsensusSession、ConsensusVote、ConsensusSummary、MemoryCandidate必须可追溯到trace。
3. 前端展示工具调用链时只展示`visible_to_user=true`的简化事件。
4. Trace接口不得返回底层Prompt、API Key、LLM推理链。

---

## 8.错误码与HTTP状态码

### 8.1HTTP状态码与业务错误码关系

| HTTP状态码 | 场景 | 示例业务码 |
|---:|---|---|
| 200 | 成功 | - |
| 400 | 请求参数错误或Schema非法 | BAD_REQUEST、PLAN_SCHEMA_INVALID、CONSENSUS_VOTE_INVALID |
| 401 | Demo用户未授权 | UNAUTHORIZED_DEMO_USER |
| 404 | 资源不存在 | RESOURCE_NOT_FOUND、PLAN_STEP_POI_NOT_FOUND |
| 409 | 状态冲突或幂等冲突 | IDEMPOTENCY_CONFLICT、PLAN_EXECUTABLE_WINDOW_EXPIRED |
| 422 | 领域校验失败 | PLAN_TIMELINE_INVALID、VERIFIER_RESULT_INVALID、RECOVERY_RESULT_INVALID |
| 429 | 频率限制 | RATE_LIMITED |
| 500 | 未预期错误 | INTERNAL_ERROR |

### 8.2P0 active领域错误码

| 错误码 | 触发条件 | 用户侧提示 | 系统侧处理 | 可恢复 |
|---|---|---|---|---:|
| PLAN_SCHEMA_INVALID | PlanContract字段缺失或类型错误 | 计划结构生成失败，请重试 | 返回schema错误，记录trace | 是 |
| PLAN_TIMELINE_INVALID | timeline为空、时间重叠、倒序 | 这版时间线不可执行，正在调整 | 触发重新生成或Recovery | 是 |
| PLAN_STEP_POI_NOT_FOUND | step引用不存在POI | 当前地点数据缺失，换一个方案 | 替换POI或阻断 | 是 |
| TOOL_ACTION_INVALID | ToolAction缺字段或引用错误 | 计划动作不完整，请重新生成 | 阻断执行，记录Debug | 是 |
| MOCK_STATUS_MISSING | Mock状态缺失 | 当前地点状态未知，已降低置信度 | 降级warning或换POI | 是 |
| VERIFIER_RESULT_INVALID | Verifier输出非法 | 校验结果异常，请重试 | 阻断持久化 | 是 |
| RECOVERY_RESULT_INVALID | Recovery缺diff或未重验 | 备选方案校验失败 | 阻断执行 | 是 |
| MEMORY_PRIVACY_VIOLATION | 高敏记忆自动启用 | 该信息不会被自动保存 | 禁用候选，记录安全日志 | 否 |
| CONSENSUS_VOTE_INVALID | 投票字段冲突 | 投票内容有冲突，请修改后提交 | 拒绝保存 | 是 |
| SOCIAL_SIGNAL_MOCK_REQUIRED | 口碑信号未标Mock | 口碑Mock数据异常，已隐藏 | 不展示口碑卡 | 是 |
| TRACE_ID_MISSING | 缺少trace_id且无法创建 | 系统追踪异常，请重试 | 创建新trace或阻断写入 | 是 |
| VERSION_NOT_SUPPORTED | version不兼容 | 当前计划版本暂不支持 | 走迁移或拒绝 | 是 |
| PLAN_EXECUTABLE_WINDOW_EXPIRED | expire_at已过期 | 当前窗口已过期，需要重新检查 | 调用verify刷新 | 是 |
| NO_TABLE_AVAILABLE | 执行订座失败 | 原餐厅已满，正在切换备选 | 触发Recovery | 是 |
| ACTIVITY_FULL | 活动预约失败 | 当前场次已满，正在找替代活动 | 触发Recovery | 是 |

### 8.3P1/P2 reserved领域错误码

以下错误码为扩展能力预留，P0不要求完整实现，但接口、日志和测试用例中不得使用其他未定义写法表达同类错误。

| 错误码 | 预留触发条件 | 建议处理 |
|---|---|---|
| ROUTE_DELAY | 路线时间显著变长 | Recovery压缩活动时长或换近POI |
| WEATHER_RISK_HIGH | 户外天气风险升高 | Recovery户外改室内 |
| BUDGET_EXCEEDED | 预算超出用户约束 | 替换低价餐厅或活动 |
| CONSENSUS_CONFLICT | 投票结果存在强冲突 | 生成折中约束或提示发起人确认 |
| SOCIAL_SIGNAL_MISSING | P1口碑Mock缺失 | 不展示口碑卡，不阻断主流程 |
| MEMORY_UNAVAILABLE | LifeMemory读取不可用 | 无记忆规划，不阻断主流程 |

### 8.4API层通用错误码

| 错误码 | 说明 | 是否领域错误 |
|---|---|---:|
| BAD_REQUEST | 请求字段缺失、类型错误、JSON非法 | 否 |
| UNAUTHORIZED_DEMO_USER | Demo用户无权限 | 否 |
| RESOURCE_NOT_FOUND | 资源不存在 | 否 |
| IDEMPOTENCY_CONFLICT | 幂等键复用冲突 | 否 |
| RATE_LIMITED | 请求过快 | 否 |
| INTERNAL_ERROR | 未预期服务错误 | 否 |

### 8.5前端错误展示原则

1. 只展示`error.user_message`，不要展示`error.message`。
2. `recoverable=true`时展示“重试/刷新/自动恢复”按钮。
3. `PLAN_EXECUTABLE_WINDOW_EXPIRED`优先引导调用`refresh-window`。
4. `NO_TABLE_AVAILABLE`和`ACTIVITY_FULL`优先展示Recovery进度，而不是直接失败。
5. `MEMORY_PRIVACY_VIOLATION`只展示“该信息不会被自动保存”，不渲染高敏内容。

---

## 9.Plan APIs

### 9.1Plan API总览

| 接口 | 页面 | 调用模块 | P0 | 幂等性 |
|---|---|---|---:|---|
| POST /api/v1/plans/create | 首页/一句话输入页、计划生成中页面 | Backend Controller → Agent Orchestrator → MockAPI → Verifier | 是 | 建议用idempotency_key |
| GET /api/v1/plans/{plan_id} | 计划结果页、执行结果页返回查看 | PlanService | 是 | 是 |
| POST /api/v1/plans/{plan_id}/verify | 计划结果页刷新校验、后端内部调用 | VerifierService | 是 | 是 |
| POST /api/v1/plans/{plan_id}/execute | 计划结果页确认执行 | ExecutorService → MockAPI → RecoveryService | 是 | 必须幂等 |
| POST /api/v1/plans/{plan_id}/recover | 执行失败页、后端内部调用 | RecoveryService → MockAPI → VerifierService | 是 | 建议幂等 |
| POST /api/v1/plans/{plan_id}/refresh-window | 可执行窗口过期提示 | MockAPI → VerifierService | 是 | 是 |
| GET /api/v1/plans/{plan_id}/trace | 工具调用链面板 | LoggingService | 是 | 是 |

### 9.2版本化Recovery策略

LifePilot P0采用版本化Recovery策略。

当执行中触发Recovery时：

1. 原PlanContract不被原地覆盖。
2. 原`plan_id`状态更新为`recovered`，表示原计划完成版本交接。
3. `RecoveryResult.updated_plan_id`指向新的完整PlanContract。
4. 新PlanContract使用新的`plan_id`，例如`plan_20260520_0001_r1`。
5. Executor继续基于`updated_plan_id`执行替换后的ToolAction。
6. `GET /api/v1/plans/{old_plan_id}`返回原计划及RecoveryResult。
7. `GET /api/v1/plans/{updated_plan_id}`返回恢复后的完整计划。
8. `execute`幂等结果必须返回`active_plan_id`，便于前端跳转到当前可继续执行的计划。

---

### POST /api/v1/plans/create

#### 接口定位

将用户一句自然语言生活目标转化为经过MockAPI状态查询和Verifier检查的PlanContract。该接口是LifePilot主闭环入口。

#### 调用页面

首页/一句话输入页、计划生成中页面。

#### 调用模块

Backend Controller → Agent Orchestrator → IntentParser → ConstraintExtractor → LifeMemoryService可选 → CandidateRetriever → MockAPI → PlanContractBuilder → VerifierService → PlanService。

#### 是否P0

是。

#### 幂等性

非天然幂等；建议前端提交`X-Idempotency-Key`。同一用户、同一输入、同一幂等键重复提交，后端应返回同一`plan_id`和`plan_contract`。不同输入复用同一幂等键返回`IDEMPOTENCY_CONFLICT`。

#### Request Headers

| Header | 必填 | 示例 | 说明 |
|---|---:|---|---|
| Content-Type | 是 | application/json | 固定JSON |
| X-Demo-User-Id | 否 | user_demo_001 | Demo用户 |
| X-Trace-Id | 否 | trace_20260520_0001 | 可由后端生成 |
| X-Idempotency-Key | 建议 | idem_create_family_0001 | 防重复生成 |

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| input_text | string | 是 | 今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。 | 用户原始目标 |
| user_location | object | 否 | `{ "poi_id":"poi_home_anchor_001" }` | 起点，可用POI锚点或经纬度 |
| preferred_start_time | string | 否 | 2026-05-20T13:30:00+08:00 | 用户明确开始时间 |
| preferred_end_time | string | 否 | 2026-05-20T18:00:00+08:00 | 用户明确结束时间 |
| scenario_hint | string | 否 | family_parent_child | 前端快捷卡片可传，Agent仍需校验 |
| generate_candidates | boolean | 否 | false | 朋友局可为true，生成多个候选方案 |
| use_memory | boolean | 否 | true | 个性化开关，关闭后不读写长期记忆 |
| debug | boolean | 否 | false | 仅开发/评委模式 |

#### Response Body

| 字段 | 类型 | 说明 |
|---|---|---|
| trace_id | string | `trace_`前缀，全链路追踪 |
| plan_id | string | `plan_`前缀 |
| plan_contract | PlanContract | 已通过Schema校验并完成Verifier的计划对象 |
| candidate_plan_ids | string[] | 可选，朋友局候选方案 |
| tool_trace_summary | object[] | 用户可见工具调用摘要 |
| memory_candidates | MemoryCandidate[] | 可选，P0可只返回候选，不自动启用 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "trace_id": "trace_20260520_0001",
    "plan_id": "plan_20260520_0001",
    "plan_contract": {
      "plan_id": "plan_20260520_0001",
      "trace_id": "trace_20260520_0001",
      "version": "v0.1",
      "status": "executable",
      "user_goal": {
        "raw_text": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
        "scenario": "family_parent_child",
        "goal_summary": "安排一段不远、不赶、适合5岁孩子参与，同时兼顾低卡饮食的家庭亲子下午。",
        "intent_tags": ["family_time", "child_friendly", "low_calorie", "nearby", "low_queue"],
        "emotion_goal": "轻松陪伴，不要太赶",
        "source": "user_input",
        "confidence": 0.92
      },
      "participants": [
        {
          "participant_id": "part_user_001",
          "role": "user",
          "display_name": "我",
          "age": null,
          "constraints": [],
          "preference_tags": []
        },
        {
          "participant_id": "part_spouse_001",
          "role": "spouse",
          "display_name": "老婆",
          "age": null,
          "constraints": ["low_calorie"],
          "preference_tags": ["light_food"]
        },
        {
          "participant_id": "part_child_001",
          "role": "child",
          "display_name": "孩子",
          "age": 5,
          "constraints": ["child_friendly", "avoid_long_walk"],
          "preference_tags": ["interactive_activity"]
        }
      ],
      "time_window": {
        "start_time": "2026-05-20T13:30:00+08:00",
        "end_time": "2026-05-20T18:00:00+08:00",
        "time_flexibility": "medium"
      },
      "constraints": {
        "party_size": 3,
        "distance_preference": "nearby",
        "budget_max": 400,
        "budget_max_per_person": null,
        "walking_tolerance": "medium_low",
        "queue_tolerance": "low",
        "dietary_preference": ["low_calorie", "light_food"],
        "activity_preference": ["child_friendly", "interactive", "not_tiring"],
        "weather_sensitive": true,
        "child_friendly_required": true,
        "indoor_preferred": false,
        "emotion_intensity": "light",
        "time_flexibility": "medium",
        "must_have": ["适合5岁儿童", "低卡或轻食餐厅"],
        "must_not_have": ["长时间排队", "高强度步行"]
      },
      "timeline": [
        {
          "step_id": "step_0001",
          "order": 1,
          "type": "transport",
          "title": "从家附近出发前往亲子场馆",
          "description": "建议打车或自驾，减少孩子步行消耗。",
          "start_time": "2026-05-20T13:40:00+08:00",
          "end_time": "2026-05-20T14:05:00+08:00",
          "duration_minutes": 25,
          "poi_id": null,
          "from_poi_id": "poi_home_anchor_001",
          "to_poi_id": "poi_child_science_001",
          "transport_mode": "taxi",
          "estimated_route": {
            "route_id": "route_0001",
            "origin_poi_id": "poi_home_anchor_001",
            "destination_poi_id": "poi_child_science_001",
            "transport_mode": "taxi",
            "distance_km": 5.2,
            "duration_minutes": 25,
            "traffic_level": "medium",
            "confidence": 0.82,
            "source": "mock_api",
            "updated_at": "2026-05-20T13:00:00+08:00"
          },
          "booking_required": false,
          "reservation_required": false,
          "status": "completed",
          "related_tool_action_ids": ["act_route_0001"],
          "display_tags": ["不赶", "少步行"],
          "user_visible_notes": "路程约25分钟，适合家庭出行。"
        },
        {
          "step_id": "step_0002",
          "order": 2,
          "type": "activity",
          "title": "儿童科学互动体验",
          "description": "适合5岁孩子参与的室内互动活动。",
          "start_time": "2026-05-20T14:05:00+08:00",
          "end_time": "2026-05-20T15:35:00+08:00",
          "duration_minutes": 90,
          "poi_id": "poi_child_science_001",
          "from_poi_id": null,
          "to_poi_id": null,
          "transport_mode": null,
          "estimated_route": null,
          "booking_required": true,
          "reservation_required": false,
          "status": "verified",
          "related_tool_action_ids": ["act_book_0001", "act_status_0001"],
          "display_tags": ["亲子", "室内", "可预约"],
          "user_visible_notes": "当前场次余票充足。"
        },
        {
          "step_id": "step_0003",
          "order": 3,
          "type": "restaurant",
          "title": "低卡轻食用餐",
          "description": "选择低卡、家庭友好、环境安静的轻食餐厅。",
          "start_time": "2026-05-20T15:55:00+08:00",
          "end_time": "2026-05-20T16:50:00+08:00",
          "duration_minutes": 55,
          "poi_id": "poi_light_food_003",
          "from_poi_id": null,
          "to_poi_id": null,
          "transport_mode": null,
          "estimated_route": null,
          "booking_required": false,
          "reservation_required": true,
          "status": "verified",
          "related_tool_action_ids": ["act_rest_status_0001", "act_reserve_0001"],
          "display_tags": ["低卡", "家庭友好", "余位紧张"],
          "user_visible_notes": "4人位剩余2桌，建议尽快确认。"
        }
      ],
      "budget": {
        "currency": "CNY",
        "estimated_total": 340,
        "price_per_person": 113.33,
        "items": [
          { "name": "亲子活动门票", "amount": 120, "source": "mock_api" },
          { "name": "轻食餐厅", "amount": 180, "source": "mock_api" },
          { "name": "交通", "amount": 40, "source": "rule_generated" }
        ]
      },
      "executable_window": {
        "window_minutes": 18,
        "confidence": 0.82,
        "expire_at": "2026-05-20T13:18:00+08:00",
        "reasons": ["亲子场馆当前余票充足", "轻食餐厅4人位剩余2桌", "路线当前通畅"],
        "risk_factors": ["restaurant_capacity_medium"],
        "lockable_resources": ["activity_ticket", "restaurant_reservation"],
        "calculated_from": ["poi_status", "restaurant_status", "route_estimate", "weather_status"],
        "display_message": "当前方案可执行窗口约18分钟，建议确认后锁定活动预约和餐厅订座。"
      },
      "risks": [
        {
          "risk_id": "risk_0001",
          "type": "restaurant_capacity",
          "level": "medium",
          "description": "轻食餐厅4人位剩余较少，执行时可能满座。",
          "related_step_id": "step_0003",
          "related_poi_id": "poi_light_food_003",
          "recovery_plan_id": "backup_0001",
          "user_visible": true,
          "mitigation": "保留同区域低卡轻食备选餐厅。"
        }
      ],
      "backup_plans": [
        {
          "backup_plan_id": "backup_0001",
          "trigger": "restaurant_full",
          "description": "若轻盈厨房满座，切换到谷物星球轻食，路线增加4分钟，预算基本不变。",
          "replace_step_id": "step_0003",
          "original_poi_id": "poi_light_food_003",
          "new_poi_id": "poi_light_food_007",
          "expected_diff": {
            "route_extra_minutes": 4,
            "budget_delta": 0,
            "queue_delta_minutes": -8,
            "diet_match": "same",
            "scenario_match": "same"
          },
          "verifier_result": { "status": "pass", "score": 0.86 },
          "priority": 1,
          "status": "verified"
        }
      ],
      "tool_actions": [
        {
          "action_id": "act_book_0001",
          "plan_id": "plan_20260520_0001",
          "step_id": "step_0002",
          "type": "book_activity",
          "target_poi_id": "poi_child_science_001",
          "target": null,
          "payload": { "arrival_time": "2026-05-20T14:05:00+08:00", "party_size": 3 },
          "status": "pending",
          "depends_on": ["act_status_0001"],
          "retry_count": 0,
          "idempotency_key": "idem_act_book_0001",
          "result": null,
          "error_code": null,
          "user_visible": true,
          "created_at": "2026-05-20T13:00:07+08:00",
          "updated_at": "2026-05-20T13:00:07+08:00"
        },
        {
          "action_id": "act_reserve_0001",
          "plan_id": "plan_20260520_0001",
          "step_id": "step_0003",
          "type": "reserve_restaurant",
          "target_poi_id": "poi_light_food_003",
          "target": null,
          "payload": { "arrival_time": "2026-05-20T15:55:00+08:00", "party_size": 3 },
          "status": "pending",
          "depends_on": ["act_rest_status_0001"],
          "retry_count": 0,
          "idempotency_key": "idem_act_reserve_0001",
          "result": null,
          "error_code": null,
          "user_visible": true,
          "created_at": "2026-05-20T13:00:09+08:00",
          "updated_at": "2026-05-20T13:00:09+08:00"
        }
      ],
      "messages": {
        "to_spouse": "我排了一版下午的安排：先带孩子去一个不累的互动体验，之后吃一家轻食，时间不会太晚。"
      },
      "verifier_result": {
        "status": "warning",
        "score": 0.82,
        "checks": [
          {
            "name": "restaurant_capacity",
            "status": "warning",
            "score": 0.68,
            "message": "4人位剩余2桌，建议尽快确认并保留备选。",
            "related_step_id": "step_0003",
            "related_poi_id": "poi_light_food_003",
            "severity": "medium",
            "recoverable": true,
            "recovery_hint": "restaurant_full"
          }
        ],
        "failed_checks": [],
        "warnings": ["restaurant_capacity_medium"],
        "required_recovery": false,
        "suggestions": ["建议18分钟内确认", "保留谷物星球轻食作为PlanB"],
        "created_at": "2026-05-20T13:00:11+08:00"
      },
      "recovery_results": [],
      "execution_summary": null,
      "memory_usage": [],
      "social_signals": [],
      "created_at": "2026-05-20T13:00:00+08:00",
      "updated_at": "2026-05-20T13:00:12+08:00"
    },
    "tool_trace_summary": [
      { "module": "MockAPI", "event": "已检查亲子场馆余票", "status": "success" },
      { "module": "MockAPI", "event": "已检查轻食餐厅余位", "status": "success" },
      { "module": "Verifier", "event": "可执行性检查完成", "status": "warning" }
    ],
    "memory_candidates": []
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "PLAN_SCHEMA_INVALID",
    "message": "PlanContract.timeline is missing.",
    "user_message": "这版计划缺少可执行时间线，请重新生成。",
    "recoverable": true,
    "details": {
      "schema_path": "$.timeline"
    }
  }
}
```

#### 状态变化

```text
无Plan → draft → generated → verifying → verified → executable
```

#### 错误码

`BAD_REQUEST`、`PLAN_SCHEMA_INVALID`、`PLAN_TIMELINE_INVALID`、`PLAN_STEP_POI_NOT_FOUND`、`MOCK_STATUS_MISSING`、`VERIFIER_RESULT_INVALID`、`MEMORY_PRIVACY_VIOLATION`、`INTERNAL_ERROR`。

#### 前端处理建议

1. 提交后进入计划生成中页面，展示“理解目标、检索地点、检查余位、生成PlanB、完成校验”。
2. 成功后跳转`/plans/{plan_id}`。
3. `success=false`且`recoverable=true`展示重试按钮。
4. 不展示`details.schema_path`给普通用户。
5. 若返回`memory_candidates`，只在计划结果页底部轻提示“有1条候选记忆待确认”。

#### 测试验收标准

1. 输入家庭亲子示例后，返回`plan_id`且前缀为`plan_`。
2. 返回`trace_id`且PlanContract.trace_id一致。
3. timeline至少3个节点，每个PlanStep含`duration_minutes`、`booking_required`、`reservation_required`。
4. ToolAction必须含`payload`、`idempotency_key`、`created_at`、`updated_at`。
5. 所有时间字段均为ISO 8601。
6. LLM不得直接写入`available_tables`到PlanStep。

---

### GET /api/v1/plans/{plan_id}

#### 接口定位

根据`plan_id`读取PlanContract，用于计划结果页、执行结果页返回查看、刷新页面恢复状态。

#### 调用页面

计划结果页、执行结果页、共识结果页。

#### 调用模块

Backend Controller → PlanService → Data Store。

#### 是否P0

是。

#### 幂等性

GET天然幂等。

#### Path Parameters

| 参数 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| plan_id | string | 是 | plan_20260520_0001 | `plan_`前缀 |

#### Response Body

| 字段 | 类型 | 说明 |
|---|---|---|
| plan_contract | PlanContract | 当前计划对象 |
| latest_execution_result | ExecutionResult/null | 最近一次执行结果 |
| latest_recovery_results | RecoveryResult[] | 最近恢复记录 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "plan_contract": {
      "plan_id": "plan_20260520_0001",
      "trace_id": "trace_20260520_0001",
      "version": "v0.1",
      "status": "executable",
      "user_goal": {
        "raw_text": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
        "scenario": "family_parent_child",
        "goal_summary": "安排一段不远、不赶、适合5岁孩子参与，同时兼顾低卡饮食的家庭亲子下午。",
        "intent_tags": ["family_time", "child_friendly", "low_calorie"],
        "emotion_goal": "轻松陪伴，不要太赶",
        "source": "user_input",
        "confidence": 0.92
      },
      "participants": [
        { "participant_id": "part_user_001", "role": "user", "display_name": "我", "age": null, "constraints": [], "preference_tags": [] }
      ],
      "time_window": {
        "start_time": "2026-05-20T13:30:00+08:00",
        "end_time": "2026-05-20T18:00:00+08:00",
        "time_flexibility": "medium"
      },
      "constraints": {
        "party_size": 3,
        "distance_preference": "nearby",
        "budget_max": 400,
        "budget_max_per_person": null,
        "walking_tolerance": "medium_low",
        "queue_tolerance": "low",
        "dietary_preference": ["low_calorie"],
        "activity_preference": ["child_friendly"],
        "weather_sensitive": true,
        "child_friendly_required": true,
        "indoor_preferred": false,
        "emotion_intensity": "light",
        "time_flexibility": "medium",
        "must_have": ["适合5岁儿童"],
        "must_not_have": ["长时间排队"]
      },
      "timeline": [
        {
          "step_id": "step_0001",
          "order": 1,
          "type": "activity",
          "title": "儿童科学互动体验",
          "description": "适合5岁孩子参与的室内互动活动。",
          "start_time": "2026-05-20T14:05:00+08:00",
          "end_time": "2026-05-20T15:35:00+08:00",
          "duration_minutes": 90,
          "poi_id": "poi_child_science_001",
          "from_poi_id": null,
          "to_poi_id": null,
          "transport_mode": null,
          "estimated_route": null,
          "booking_required": true,
          "reservation_required": false,
          "status": "completed",
          "related_tool_action_ids": ["act_book_0001"],
          "display_tags": ["亲子", "室内"],
          "user_visible_notes": "当前场次余票充足。"
        }
      ],
      "budget": {
        "currency": "CNY",
        "estimated_total": 120,
        "price_per_person": 40,
        "items": [{ "name": "亲子活动门票", "amount": 120, "source": "mock_api" }]
      },
      "executable_window": {
        "window_minutes": 18,
        "confidence": 0.82,
        "expire_at": "2026-05-20T13:18:00+08:00",
        "reasons": ["亲子场馆当前余票充足"],
        "risk_factors": [],
        "lockable_resources": ["activity_ticket"],
        "calculated_from": ["poi_status", "route_estimate"],
        "display_message": "当前方案可执行窗口约18分钟。"
      },
      "risks": [],
      "backup_plans": [],
      "tool_actions": [
        {
          "action_id": "act_book_0001",
          "plan_id": "plan_20260520_0001",
          "step_id": "step_0001",
          "type": "book_activity",
          "target_poi_id": "poi_child_science_001",
          "target": null,
          "payload": { "arrival_time": "2026-05-20T14:05:00+08:00", "party_size": 3 },
          "status": "pending",
          "depends_on": [],
          "retry_count": 0,
          "idempotency_key": "idem_act_book_0001",
          "result": null,
          "error_code": null,
          "user_visible": true,
          "created_at": "2026-05-20T13:00:07+08:00",
          "updated_at": "2026-05-20T13:00:07+08:00"
        }
      ],
      "messages": {},
      "verifier_result": {
        "status": "pass",
        "score": 0.86,
        "checks": [],
        "failed_checks": [],
        "warnings": [],
        "required_recovery": false,
        "suggestions": [],
        "created_at": "2026-05-20T13:00:11+08:00"
      },
      "recovery_results": [],
      "execution_summary": null,
      "memory_usage": [],
      "social_signals": [],
      "created_at": "2026-05-20T13:00:00+08:00",
      "updated_at": "2026-05-20T13:00:12+08:00"
    },
    "latest_execution_result": null,
    "latest_recovery_results": []
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "plan not found.",
    "user_message": "没有找到这份计划，可能已被删除或链接错误。",
    "recoverable": false,
    "details": {}
  }
}
```

#### 状态变化

无状态变化。

#### 前端处理建议

1. 页面刷新时优先调用该接口恢复PlanContract。
2. 若`status=expired`，展示“重新检查可执行窗口”按钮。
3. 若`status=completed/recovered`，展示执行结果入口。

#### 测试验收标准

1. 存在计划能读取。
2. 不存在计划返回`RESOURCE_NOT_FOUND`。
3. 普通用户页不返回Debug敏感字段。

---

### POST /api/v1/plans/{plan_id}/verify

#### 接口定位

对已有PlanContract重新进行可执行性验证，常用于计划创建后的内部调用、用户手动刷新、Recovery后复验。

#### 调用页面

计划结果页、共识结果页、Debug页。

#### 调用模块

Backend Controller → VerifierService → MockAPI → PlanService。

#### 是否P0

是。

#### 幂等性

对同一PlanContract版本和同一Mock状态快照是幂等的；如果Mock状态随时间变化，结果可变化，但必须记录新的TraceLog。

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| force_refresh_mock_status | boolean | 否 | true | 是否强制刷新Mock状态 |
| reason | string | 否 | user_refresh | 调用原因 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "plan_id": "plan_20260520_0001",
    "status": "executable",
    "verifier_result": {
      "status": "pass",
      "score": 0.86,
      "checks": [],
      "failed_checks": [],
      "warnings": [],
      "required_recovery": false,
      "suggestions": ["当前方案仍可执行。"],
      "created_at": "2026-05-20T13:10:00+08:00"
    },
    "plan_view": {
      "plan_id": "plan_20260520_0001",
      "status": "executable",
      "updated_fields": ["verifier_result", "executable_window"],
      "updated_at": "2026-05-20T13:10:00+08:00"
    }
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "PLAN_STEP_POI_NOT_FOUND",
    "message": "poi_id does not exist: poi_not_exist_999.",
    "user_message": "当前地点数据缺失，我会换一个可用方案。",
    "recoverable": true,
    "details": {}
  }
}
```

#### 状态变化

```text
generated/executable/expired → verifying → verified/executable/failed
```

#### 测试验收标准

1. VerifierResult.status只能是`pass/warning/fail`。
2. `required_recovery=true`时必须给出可恢复提示或失败原因。
3. 刷新后`updated_at`必须更新。

---

### POST /api/v1/plans/{plan_id}/execute

#### 接口定位

用户确认计划后，Executor按ToolAction依赖顺序调用MockAPI，完成预约、订座、下单、发消息等模拟执行。执行失败时自动触发Recovery。

#### 调用页面

计划结果页确认按钮、共识结果页确认按钮。

#### 调用模块

Backend Controller → ExecutorService → MockAPI → RecoveryService → VerifierService → PlanService → LoggingService。

#### 是否P0

是。

#### 幂等性

必须幂等。前端必须传`X-Idempotency-Key`。同一个plan和同一个幂等键重复执行，应返回同一个`execution_id`和ExecutionResult，不得重复生成Mock凭证。

#### Request Headers

| Header | 必填 | 示例 | 说明 |
|---|---:|---|---|
| X-Idempotency-Key | 是 | idem_exec_20260520_0001 | 防重复执行 |
| X-Demo-User-Id | 否 | user_demo_001 | Demo用户 |
| X-Trace-Id | 否 | trace_20260520_0001 | 通常复用Plan trace |

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| confirmed | boolean | 是 | true | 用户确认执行 |
| execute_action_ids | string[] | 否 | ["act_book_0001", "act_reserve_0001"] | 不传则执行全部pending且user_visible或关键动作 |
| allow_auto_recovery | boolean | 否 | true | 失败时是否自动Recovery |
| allow_message_mock_send | boolean | 否 | true | 是否模拟发送消息 |
| confirmation_note | string | 否 | 按这个安排 | 用户确认备注 |

#### Response Body

| 字段 | 类型 | 说明 |
|---|---|---|
| execution_id | string | `exec_`前缀 |
| execution_result | ExecutionResult | 执行结果 |
| active_plan_id | string | 当前应展示或继续执行的PlanContract ID |
| active_plan_contract | PlanContract | 当前应展示或继续执行的完整计划对象 |
| recovery_results | RecoveryResult[] | 执行中触发的恢复记录 |
| action_results | object[] | 动作级结果，和ExecutionResult内保持一致 |

#### 成功响应示例：全部成功

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "execution_id": "exec_20260520_0001",
    "execution_result": {
      "execution_id": "exec_20260520_0001",
      "plan_id": "plan_20260520_0001",
      "trace_id": "trace_20260520_0001",
      "status": "success",
      "action_results": [
        {
          "action_id": "act_book_0001",
          "type": "book_activity",
          "status": "success",
          "result": {
            "booking_id": "mock_booking_BA1024",
            "poi_id": "poi_child_science_001",
            "mock_only": true,
            "created_at": "2026-05-20T13:20:00+08:00"
          }
        },
        {
          "action_id": "act_reserve_0001",
          "type": "reserve_restaurant",
          "status": "success",
          "result": {
            "reservation_id": "mock_reservation_R2048",
            "poi_id": "poi_light_food_003",
            "mock_only": true,
            "created_at": "2026-05-20T13:20:02+08:00"
          }
        },
        {
          "action_id": "act_message_0001",
          "type": "send_message",
          "status": "success",
          "result": {
            "message_id": "mock_message_M4096",
            "mock_only": true,
            "created_at": "2026-05-20T13:20:03+08:00"
          }
        }
      ],
      "vouchers": [
        {
          "type": "booking_id",
          "value": "mock_booking_BA1024",
          "poi_id": "poi_child_science_001",
          "display_name": "儿童科学互动体验预约号",
          "mock_only": true,
          "created_at": "2026-05-20T13:20:00+08:00"
        },
        {
          "type": "reservation_id",
          "value": "mock_reservation_R2048",
          "poi_id": "poi_light_food_003",
          "display_name": "轻盈厨房订座号",
          "mock_only": true,
          "created_at": "2026-05-20T13:20:02+08:00"
        }
      ],
      "failed_actions": [],
      "recovery_results": [],
      "user_message": "亲子活动预约成功，轻食餐厅订座成功，已生成模拟消息。",
      "created_at": "2026-05-20T13:20:04+08:00"
    },
    "active_plan_id": "plan_20260520_0001",
    "active_plan_contract": {
      "plan_id": "plan_20260520_0001",
      "trace_id": "trace_20260520_0001",
      "version": "v0.1",
      "status": "completed",
      "user_goal": {
        "raw_text": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
        "scenario": "family_parent_child",
        "goal_summary": "安排一段不远、不赶、适合5岁孩子参与，同时兼顾低卡饮食的家庭亲子下午。",
        "intent_tags": ["family_time", "child_friendly", "low_calorie"],
        "emotion_goal": "轻松陪伴，不要太赶",
        "source": "user_input",
        "confidence": 0.92
      },
      "participants": [
        { "participant_id": "part_user_001", "role": "user", "display_name": "我", "age": null, "constraints": [], "preference_tags": [] }
      ],
      "time_window": {
        "start_time": "2026-05-20T13:30:00+08:00",
        "end_time": "2026-05-20T18:00:00+08:00",
        "time_flexibility": "medium"
      },
      "constraints": { "party_size": 3 },
      "timeline": [
        {
          "step_id": "step_0001",
          "order": 1,
          "type": "activity",
          "title": "儿童科学互动体验",
          "start_time": "2026-05-20T14:05:00+08:00",
          "end_time": "2026-05-20T15:35:00+08:00",
          "duration_minutes": 90,
          "booking_required": true,
          "reservation_required": false,
          "status": "completed",
          "poi_id": "poi_child_science_001",
          "from_poi_id": null,
          "to_poi_id": null,
          "transport_mode": null,
          "estimated_route": null,
          "related_tool_action_ids": ["act_book_0001"]
        }
      ],
      "budget": { "currency": "CNY", "estimated_total": 120, "items": [{ "name": "亲子活动门票", "amount": 120 }] },
      "executable_window": {
        "window_minutes": 0,
        "confidence": 1,
        "expire_at": "2026-05-20T13:18:00+08:00",
        "reasons": ["已完成执行"],
        "calculated_from": ["executor"],
        "display_message": "计划已完成执行。"
      },
      "risks": [],
      "backup_plans": [],
      "tool_actions": [],
      "messages": {},
      "verifier_result": {
        "status": "pass",
        "score": 0.86,
        "checks": [],
        "failed_checks": [],
        "warnings": [],
        "required_recovery": false,
        "created_at": "2026-05-20T13:00:11+08:00"
      },
      "recovery_results": [],
      "execution_summary": {
        "execution_id": "exec_20260520_0001",
        "status": "success"
      },
      "memory_usage": [],
      "social_signals": [],
      "created_at": "2026-05-20T13:00:00+08:00",
      "updated_at": "2026-05-20T13:20:04+08:00"
    },
    "recovery_results": []
  },
  "error": null
}
```

#### 成功响应示例：餐厅满座后恢复

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "execution_id": "exec_20260520_0002",
    "execution_result": {
      "execution_id": "exec_20260520_0002",
      "plan_id": "plan_20260520_0001",
      "trace_id": "trace_20260520_0001",
      "status": "recovered",
      "action_results": [
        {
          "action_id": "act_book_0001",
          "type": "book_activity",
          "status": "success",
          "result": { "booking_id": "mock_booking_BA1024", "mock_only": true }
        },
        {
          "action_id": "act_reserve_0001",
          "type": "reserve_restaurant",
          "status": "failed",
          "error_code": "NO_TABLE_AVAILABLE"
        },
        {
          "action_id": "act_reserve_0002",
          "type": "reserve_restaurant",
          "status": "success",
          "result": {
            "reservation_id": "mock_reservation_R2048",
            "poi_id": "poi_light_food_007",
            "mock_only": true
          }
        }
      ],
      "vouchers": [
        { "type": "booking_id", "value": "mock_booking_BA1024", "mock_only": true },
        { "type": "reservation_id", "value": "mock_reservation_R2048", "mock_only": true }
      ],
      "failed_actions": [
        { "action_id": "act_reserve_0001", "error_code": "NO_TABLE_AVAILABLE", "recoverable": true }
      ],
      "recovery_results": [
        {
          "recovery_id": "rec_0001",
          "trigger": "NO_TABLE_AVAILABLE",
          "status": "success",
          "original": {
            "step_id": "step_0003",
            "poi_id": "poi_light_food_003",
            "poi_name": "轻盈厨房"
          },
          "replacement": {
            "step_id": "step_0003",
            "poi_id": "poi_light_food_007",
            "poi_name": "谷物星球轻食"
          },
          "diff": {
            "route_extra_minutes": 4,
            "budget_delta": 0,
            "queue_delta_minutes": -8,
            "distance_delta_km": 0.6,
            "time_shift_minutes": 3,
            "diet_match": "same",
            "scenario_match": "same",
            "user_visible_summary": "路线多4分钟，预算不变，排队风险更低。"
          },
          "updated_plan_id": "plan_20260520_0001_r1",
          "verifier_result": {
            "status": "pass",
            "score": 0.86,
            "failed_checks": [],
            "warnings": []
          },
          "user_explanation": "原餐厅4人位已满，已切换到同区域低卡轻食餐厅，路线增加4分钟，预算基本不变。",
          "created_at": "2026-05-20T13:20:10+08:00"
        }
      ],
      "user_message": "亲子活动预约成功；原餐厅满座，已切换到备选低卡餐厅并订座成功。",
      "created_at": "2026-05-20T13:20:12+08:00"
    },
    "original_plan_view": {
      "plan_id": "plan_20260520_0001",
      "trace_id": "trace_20260520_0001",
      "version": "v0.1",
      "status": "recovered",
      "recovery_results": [
        {
          "recovery_id": "rec_0001",
          "trigger": "NO_TABLE_AVAILABLE",
          "status": "success"
        }
      ],
      "updated_at": "2026-05-20T13:20:12+08:00"
    },
    "active_plan_id": "plan_20260520_0001_r1",
    "active_plan_contract": {
      "plan_id": "plan_20260520_0001_r1",
      "trace_id": "trace_20260520_0001",
      "version": "v0.1",
      "status": "completed",
      "user_goal": {
        "raw_text": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
        "scenario": "family_parent_child",
        "goal_summary": "餐厅满座后切换到同区域低卡轻食餐厅的家庭亲子下午。",
        "intent_tags": ["family_time", "child_friendly", "low_calorie"],
        "emotion_goal": "轻松陪伴，不要太赶",
        "source": "user_input",
        "confidence": 0.92
      },
      "participants": [
        { "participant_id": "part_user_001", "role": "user", "display_name": "我", "age": null, "constraints": [], "preference_tags": [] }
      ],
      "time_window": {
        "start_time": "2026-05-20T13:30:00+08:00",
        "end_time": "2026-05-20T18:00:00+08:00",
        "time_flexibility": "medium"
      },
      "constraints": { "party_size": 3 },
      "timeline": [
        {
          "step_id": "step_0003",
          "order": 1,
          "type": "restaurant",
          "title": "谷物星球轻食",
          "start_time": "2026-05-20T15:58:00+08:00",
          "end_time": "2026-05-20T16:50:00+08:00",
          "duration_minutes": 52,
          "booking_required": false,
          "reservation_required": true,
          "status": "completed",
          "poi_id": "poi_light_food_007",
          "from_poi_id": null,
          "to_poi_id": null,
          "transport_mode": null,
          "estimated_route": null,
          "related_tool_action_ids": ["act_reserve_0002"]
        }
      ],
      "budget": { "currency": "CNY", "estimated_total": 340, "items": [{ "name": "轻食餐厅", "amount": 180 }] },
      "executable_window": {
        "window_minutes": 12,
        "confidence": 0.86,
        "expire_at": "2026-05-20T13:32:00+08:00",
        "reasons": ["替代餐厅当前可订座"],
        "calculated_from": ["restaurant_status", "route_estimate"],
        "display_message": "恢复后的方案已完成替代订座。"
      },
      "risks": [],
      "backup_plans": [],
      "tool_actions": [
        {
          "action_id": "act_reserve_0002",
          "plan_id": "plan_20260520_0001_r1",
          "step_id": "step_0003",
          "type": "reserve_restaurant",
          "target_poi_id": "poi_light_food_007",
          "target": null,
          "payload": { "arrival_time": "2026-05-20T15:58:00+08:00", "party_size": 3 },
          "status": "success",
          "depends_on": [],
          "retry_count": 0,
          "idempotency_key": "idem_act_reserve_0002",
          "result": { "reservation_id": "mock_reservation_R2048", "mock_only": true },
          "error_code": null,
          "user_visible": true,
          "created_at": "2026-05-20T13:20:10+08:00",
          "updated_at": "2026-05-20T13:20:10+08:00"
        }
      ],
      "messages": {},
      "verifier_result": {
        "status": "pass",
        "score": 0.86,
        "checks": [],
        "failed_checks": [],
        "warnings": [],
        "required_recovery": false,
        "created_at": "2026-05-20T13:20:10+08:00"
      },
      "recovery_results": [],
      "execution_summary": null,
      "memory_usage": [],
      "social_signals": [],
      "created_at": "2026-05-20T13:20:10+08:00",
      "updated_at": "2026-05-20T13:20:12+08:00"
    },
    "recovery_results": [
      {
        "recovery_id": "rec_0001",
        "trigger": "NO_TABLE_AVAILABLE",
        "status": "success"
      }
    ]
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "PLAN_EXECUTABLE_WINDOW_EXPIRED",
    "message": "executable_window expired at 2026-05-20T13:18:00+08:00.",
    "user_message": "当前可执行窗口已过期，需要重新检查余位和路线。",
    "recoverable": true,
    "details": {
      "refresh_api": "/api/v1/plans/plan_20260520_0001/refresh-window"
    }
  }
}
```

#### 状态变化

```text
executable → confirmed → executing → completed
executable → confirmed → executing → recovered(old_plan) → executable(updated_plan) → executing → completed/recovered
executable → expired
executing → failed
```

#### 错误码

`PLAN_EXECUTABLE_WINDOW_EXPIRED`、`TOOL_ACTION_INVALID`、`NO_TABLE_AVAILABLE`、`ACTIVITY_FULL`、`RECOVERY_RESULT_INVALID`、`IDEMPOTENCY_CONFLICT`、`INTERNAL_ERROR`。

#### 前端处理建议

1. 点击确认后按钮进入loading，不允许重复点击。
2. 执行动作逐项展示`pending/running/success/failed/recovered/skipped`。
3. 若自动Recovery成功，不展示红色失败页，而展示“已为你切换到备选方案”。
4. Mock凭证展示时必须带“模拟”字样。
5. 若`PLAN_EXECUTABLE_WINDOW_EXPIRED`，展示“重新检查”按钮，调用`refresh-window`。

#### 测试验收标准

1. 未传`X-Idempotency-Key`时必须返回`400 BAD_REQUEST`，不得由后端代生成HTTP层幂等键。
2. 同一幂等键重复请求返回同一`execution_id`。
3. ToolAction按`depends_on`顺序执行。
4. Mock凭证必须带`mock_only:true`。
5. `NO_TABLE_AVAILABLE`必须触发Recovery并返回符合最终契约的RecoveryResult。
6. Recovery后必须重新Verifier。

---

### POST /api/v1/plans/{plan_id}/recover

#### 接口定位

手动或内部触发计划恢复。P0主要由execute内部自动调用；该接口用于Debug、演示失败恢复、用户点击“换一个备选”。

#### 调用页面

执行结果页、计划结果页PlanB卡片、Debug页。

#### 调用模块

Backend Controller → RecoveryService → CandidateRetriever → MockAPI → VerifierService → PlanService。

#### 是否P0

是。

#### 幂等性

必须幂等。前端或内部调用方必须传`X-Idempotency-Key`；对同一个`failed_action_id`、`trigger`、`plan_version`重复调用返回同一RecoveryResult或当前最新恢复结果。

#### Request Headers

| Header | 必填 | 示例 | 说明 |
|---|---:|---|---|
| X-Idempotency-Key | 是 | idem_recover_20260520_0001 | 防重复恢复 |
| X-Demo-User-Id | 否 | user_demo_001 | Demo用户 |
| X-Trace-Id | 否 | trace_20260520_0001 | 通常复用Plan trace |

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| trigger | string | 是 | NO_TABLE_AVAILABLE | 触发原因 |
| failed_step_id | string | 否 | step_0003 | 失败节点 |
| failed_action_id | string | 否 | act_reserve_0001 | 失败动作 |
| preferred_backup_plan_id | string | 否 | backup_0001 | 用户指定备选 |
| recovery_strategy | string | 否 | replace_poi_same_area | 恢复策略 |
| auto_verify | boolean | 否 | true | 是否自动重新Verifier |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "recovery_result": {
      "recovery_id": "rec_0001",
      "trigger": "NO_TABLE_AVAILABLE",
      "status": "success",
      "original": {
        "step_id": "step_0003",
        "poi_id": "poi_light_food_003",
        "poi_name": "轻盈厨房"
      },
      "replacement": {
        "step_id": "step_0003",
        "poi_id": "poi_light_food_007",
        "poi_name": "谷物星球轻食"
      },
      "diff": {
        "route_extra_minutes": 4,
        "budget_delta": 0,
        "queue_delta_minutes": -8,
        "distance_delta_km": 0.6,
        "time_shift_minutes": 3,
        "diet_match": "same",
        "scenario_match": "same",
        "user_visible_summary": "路线多4分钟，预算不变，排队风险更低。"
      },
      "updated_plan_id": "plan_20260520_0001_r1",
      "verifier_result": {
        "status": "pass",
        "score": 0.86,
        "failed_checks": [],
        "warnings": []
      },
      "user_explanation": "原餐厅4人位已满，已切换到同区域低卡轻食餐厅，路线增加4分钟，预算基本不变。",
      "created_at": "2026-05-20T13:20:10+08:00"
    },
    "updated_plan_id": "plan_20260520_0001_r1",
    "updated_plan_contract": {
      "plan_id": "plan_20260520_0001_r1",
      "trace_id": "trace_20260520_0001",
      "version": "v0.1",
      "status": "executable",
      "user_goal": {
        "raw_text": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
        "scenario": "family_parent_child",
        "goal_summary": "餐厅满座后切换到同区域低卡轻食餐厅的家庭亲子下午。",
        "source": "user_input",
        "confidence": 0.92
      },
      "participants": [
        { "participant_id": "part_user_001", "role": "user", "display_name": "我" }
      ],
      "time_window": {
        "start_time": "2026-05-20T13:30:00+08:00",
        "end_time": "2026-05-20T18:00:00+08:00",
        "time_flexibility": "medium"
      },
      "constraints": { "party_size": 3 },
      "timeline": [
        {
          "step_id": "step_0003",
          "order": 1,
          "type": "restaurant",
          "title": "谷物星球轻食",
          "start_time": "2026-05-20T15:58:00+08:00",
          "end_time": "2026-05-20T16:50:00+08:00",
          "duration_minutes": 52,
          "booking_required": false,
          "reservation_required": true,
          "status": "verified",
          "poi_id": "poi_light_food_007"
        }
      ],
      "budget": { "currency": "CNY", "estimated_total": 180, "items": [{ "name": "轻食餐厅", "amount": 180 }] },
      "executable_window": {
        "window_minutes": 12,
        "confidence": 0.86,
        "expire_at": "2026-05-20T13:32:00+08:00",
        "reasons": ["替代餐厅当前可订座"],
        "calculated_from": ["restaurant_status", "route_estimate"],
        "display_message": "恢复后的方案可继续执行。"
      },
      "risks": [],
      "backup_plans": [],
      "tool_actions": [],
      "messages": {},
      "verifier_result": {
        "status": "pass",
        "score": 0.86,
        "checks": [],
        "failed_checks": [],
        "warnings": [],
        "required_recovery": false,
        "created_at": "2026-05-20T13:20:10+08:00"
      },
      "recovery_results": [],
      "execution_summary": null,
      "memory_usage": [],
      "social_signals": [],
      "created_at": "2026-05-20T13:20:10+08:00",
      "updated_at": "2026-05-20T13:20:12+08:00"
    }
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "RECOVERY_RESULT_INVALID",
    "message": "recovery result has no verifier_result.",
    "user_message": "备选方案校验失败，请重新生成计划。",
    "recoverable": true,
    "details": {}
  }
}
```

#### 状态变化

```text
executing/failed/executable → recovered(old_plan) + executable(updated_plan) 或 failed
```

#### 测试验收标准

1. 返回结构只能使用`original/replacement/diff`。
2. `updated_plan_id`可为空，但成功替换后建议生成`plan_..._r1`。
3. `diff`至少包含路线、预算、排队或时间变化之一。
4. Recovery后必须含`verifier_result`。

---

### POST /api/v1/plans/{plan_id}/refresh-window

#### 接口定位

可执行窗口过期或用户停留过久时，重新查询Mock状态、路线、天气并刷新`executable_window`。

#### 调用页面

计划结果页、执行前确认弹窗。

#### 调用模块

Backend Controller → MockAPI → VerifierService → PlanService。

#### 是否P0

是。

#### 幂等性

同一时间窗口内近似幂等；Mock状态变化时允许返回新结果。

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| reason | string | 否 | window_expired | 刷新原因 |
| force_refresh | boolean | 否 | true | 是否强制刷新Mock状态 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "plan_id": "plan_20260520_0001",
    "status": "executable",
    "executable_window": {
      "window_minutes": 12,
      "confidence": 0.78,
      "expire_at": "2026-05-20T13:32:00+08:00",
      "reasons": ["餐厅仍可订座，但剩余桌数减少", "亲子活动余票充足"],
      "risk_factors": ["restaurant_capacity_high"],
      "lockable_resources": ["activity_ticket", "restaurant_reservation"],
      "calculated_from": ["restaurant_status", "poi_status", "route_estimate"],
      "display_message": "当前方案仍可执行，但窗口缩短为12分钟。"
    },
    "verifier_result": {
      "status": "warning",
      "score": 0.78,
      "failed_checks": [],
      "warnings": ["restaurant_capacity_high"],
      "required_recovery": false,
      "checks": [],
      "suggestions": ["建议尽快确认"],
      "created_at": "2026-05-20T13:20:00+08:00"
    }
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "NO_TABLE_AVAILABLE",
    "message": "restaurant has no available tables after refresh.",
    "user_message": "原餐厅当前已满，我会尝试切换到备选餐厅。",
    "recoverable": true,
    "details": { "suggested_next_api": "/api/v1/plans/plan_20260520_0001/recover" }
  }
}
```

#### 状态变化

```text
expired/executable → verifying → executable/failed/recovered
```

#### 测试验收标准

1. `expire_at`必须为ISO 8601。
2. `calculated_from`必须说明来源。
3. 若窗口不可用，应返回可恢复错误或触发Recovery。

---

### GET /api/v1/plans/{plan_id}/trace

#### 接口定位

返回当前Plan的用户可见工具调用链投影，用于计划结果页“为什么这样安排/我检查了什么”模块。该接口返回`UserVisibleTraceEvent[]`，不是`03_data_schema.md`中的完整`TraceLog`本体。

#### 调用页面

计划结果页、执行结果页。

#### 调用模块

Backend Controller → LoggingService。

#### 是否P0

是。

#### 幂等性

GET天然幂等。

#### Query Parameters

| 参数 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| visible_only | boolean | 否 | true | 默认只返回用户可见事件 |
| include_debug | boolean | 否 | false | 仅Debug模式有效 |

#### UserVisibleTraceEvent字段

| 字段 | 类型 | 说明 |
|---|---|---|
| log_id | string | 来源TraceLog ID，`log_`前缀 |
| trace_id | string | 所属trace |
| event_type | string | 必须使用TraceLog.event_type枚举 |
| module | string | 来源模块 |
| level | string | info/warning/error |
| user_visible_message | string | 给用户展示的简化文案 |
| created_at | string | ISO 8601 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "plan_id": "plan_20260520_0001",
    "events": [
      {
        "log_id": "log_0001",
        "trace_id": "trace_20260520_0001",
        "event_type": "intent_log",
        "module": "IntentParser",
        "level": "info",
        "user_visible_message": "已识别为家庭亲子场景。",
        "created_at": "2026-05-20T13:00:01+08:00"
      },
      {
        "log_id": "log_0002",
        "trace_id": "trace_20260520_0001",
        "event_type": "tool_log",
        "module": "MockAPIService",
        "level": "info",
        "user_visible_message": "已检查轻食餐厅4人位余位。",
        "created_at": "2026-05-20T13:00:08+08:00"
      }
    ]
  },
  "error": null
}
```

#### 测试验收标准

1. 普通模式不返回底层Prompt、API Key、LLM推理链。
2. `visible_only=true`时只返回`visible_to_user=true`事件。
3. 事件必须按`created_at`升序返回。
4. 如需完整TraceLog，必须调用`GET /api/v1/traces/{trace_id}/events`。

---

## 10.Consensus APIs

### 10.1Consensus API总览

| 接口 | 页面 | 调用模块 | P0 | 幂等性 |
|---|---|---|---:|---|
| POST /api/v1/consensus/create | 计划结果页“发给朋友投票” | ConsensusService | 是 | 建议幂等 |
| GET /api/v1/consensus/{consensus_session_id} | 共识进度页 | ConsensusService | 是 | 是 |
| GET /api/v1/vote-pages/{vote_page_id} | 朋友投票页 | ConsensusService | 是 | 是 |
| POST /api/v1/consensus/{consensus_session_id}/vote | 朋友投票页 | ConsensusService | 是 | 同参与者可更新 |
| POST /api/v1/consensus/{consensus_session_id}/finalize | 共识结果页 | ConsensusService → PlanGenerator → Verifier | 是 | finalize后幂等 |
| GET /api/v1/consensus/{consensus_session_id}/summary | 共识结果页 | ConsensusService | 是 | 是 |

共识模块统一使用：

| 字段 | 含义 |
|---|---|
| consensus_session_id | 共识会话内部主键，`cs_`前缀 |
| vote_page_id | 投票页路由与分享ID，`vpage_`前缀 |
| plan_group_id | 候选方案组ID，`plangrp_`前缀 |
| vote_id | 单条投票ID，`vote_`前缀 |

---

### POST /api/v1/consensus/create

#### 接口定位

基于候选PlanContract或候选plan_id创建朋友局投票会话，生成分享链接。

#### 调用页面

计划结果页“发给朋友投票”。

#### 调用模块

Backend Controller → ConsensusService → PlanService → Data Store。

#### 是否P0

是。

#### 幂等性

建议前端传`X-Idempotency-Key`。同一`plan_group_id`和同一创建者重复创建，可返回已有collecting会话。

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| plan_group_id | string | 否 | plangrp_0001 | 已有候选组ID；无则后端创建 |
| candidate_plan_ids | string[] | 是 | ["plan_candidate_a", "plan_candidate_b"] | 候选方案 |
| title | string | 否 | 周六下午朋友局 | 投票页标题 |
| expire_at | string | 是 | 2026-05-20T14:00:00+08:00 | 投票过期时间 |
| allow_anonymous | boolean | 否 | true | 是否允许匿名 |
| creator_user_id | string | 否 | user_demo_001 | 通常由Header确定 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0100",
  "data": {
    "consensus_session_id": "cs_0001",
    "vote_page_id": "vpage_0001",
    "plan_group_id": "plangrp_0001",
    "share_url": "https://demo.lifepilot.local/vote/vpage_0001",
    "candidate_plan_ids": ["plan_candidate_a", "plan_candidate_b", "plan_candidate_c"],
    "status": "collecting",
    "expire_at": "2026-05-20T14:00:00+08:00",
    "created_at": "2026-05-20T13:00:00+08:00"
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0100",
  "data": null,
  "error": {
    "code": "PLAN_SCHEMA_INVALID",
    "message": "candidate plan is invalid.",
    "user_message": "候选方案结构异常，请重新生成后再发起投票。",
    "recoverable": true,
    "details": {}
  }
}
```

#### 状态变化

```text
无ConsensusSession → created → collecting
```

#### 测试验收标准

1. 返回`consensus_session_id`、`vote_page_id`、`plan_group_id`。
2. `share_url`中使用`vote_page_id`，不是`consensus_session_id`。
3. 候选计划ID必须存在且可渲染摘要。

---

### GET /api/v1/consensus/{consensus_session_id}

#### 接口定位

读取共识会话当前状态、候选方案、投票数量和是否可finalize。

#### 调用页面

共识进度页、发起人管理页。

#### 调用模块

ConsensusService。

#### 是否P0

是。

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0100",
  "data": {
    "consensus_session_id": "cs_0001",
    "vote_page_id": "vpage_0001",
    "plan_group_id": "plangrp_0001",
    "creator_user_id": "user_demo_001",
    "status": "collecting",
    "candidate_plan_ids": ["plan_candidate_a", "plan_candidate_b", "plan_candidate_c"],
    "share_url": "https://demo.lifepilot.local/vote/vpage_0001",
    "vote_count": 2,
    "can_finalize": true,
    "expire_at": "2026-05-20T14:00:00+08:00",
    "created_at": "2026-05-20T13:00:00+08:00",
    "finalized_at": null
  },
  "error": null
}
```

#### 测试验收标准

1. `status`必须是`created/collecting/closed/expired/finalized`。
2. finalize后返回`finalized_at`。
3. 不向非创建者返回参与者内部ID以外的敏感信息。

---

### GET /api/v1/vote-pages/{vote_page_id}

#### 接口定位

朋友打开分享链接后，读取投票页信息和候选方案卡片。

#### 调用页面

朋友投票页。

#### 调用模块

ConsensusService → PlanService。

#### 是否P0

是。

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0100",
  "data": {
    "consensus_session_id": "cs_0001",
    "vote_page_id": "vpage_0001",
    "plan_group_id": "plangrp_0001",
    "title": "周六下午朋友局",
    "status": "collecting",
    "expire_at": "2026-05-20T14:00:00+08:00",
    "candidate_plans": [
      {
        "plan_id": "plan_candidate_a",
        "title": "拍照逛展版",
        "summary": "适合拍照、轻松逛，不太吵。",
        "budget": { "currency": "CNY", "price_per_person": 100 },
        "walking_tolerance_label": "中低",
        "queue_risk_label": "低"
      },
      {
        "plan_id": "plan_candidate_b",
        "title": "好吃不累版",
        "summary": "重点吃饭聊天，步行少。",
        "budget": { "currency": "CNY", "price_per_person": 120 },
        "walking_tolerance_label": "低",
        "queue_risk_label": "中"
      }
    ],
    "vote_rules": {
      "liked_plan_ids_required": false,
      "minimum_one_of": ["liked_plan_ids", "disliked_plan_ids", "free_text"],
      "liked_disliked_must_not_overlap": true
    }
  },
  "error": null
}
```

#### 前端处理建议

1. 候选方案只展示摘要，不展示完整ToolAction payload。
2. 若`status=finalized`，显示“投票已结束，查看最终方案”。
3. 允许匿名或昵称提交。

#### 测试验收标准

1. 路由入口使用`vote_page_id`。
2. 响应必须返回`consensus_session_id`。
3. 不强制`liked_plan_ids`非空。

---

### POST /api/v1/consensus/{consensus_session_id}/vote

#### 接口定位

提交或更新单个参与者投票，支持多选喜欢、反选、预算、时间偏好、步行容忍、排队容忍和free_text。

#### 调用页面

朋友投票页。

#### 调用模块

ConsensusService。

#### 是否P0

是。

#### 幂等性

同一`participant.client_vote_token`可更新投票；finalize后默认不允许继续修改。

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| participant | object | 是 | `{ "participant_name":"朋友A", "anonymous":false }` | 参与者信息 |
| liked_plan_ids | string[] | 否 | ["plan_candidate_b"] | 可为空 |
| disliked_plan_ids | string[] | 否 | ["plan_candidate_a"] | 可为空 |
| budget_max | number/null | 否 | 100 | 人均预算 |
| time_preference | string/null | 否 | after_14_30 | 时间偏好 |
| walking_tolerance | string/null | 否 | low | 步行容忍 |
| queue_tolerance | string/null | 否 | low | 排队容忍 |
| free_text | string | 否 | 我不想走太多，也不想排队。 | 一句话偏好 |
| client_vote_token | string | 否 | client_vote_abc | 前端本地匿名标识，用于更新 |

#### 投票校验规则

```text
liked_plan_ids、disliked_plan_ids、free_text三者至少一个有效；
liked_plan_ids和disliked_plan_ids不能重叠；
finalize后默认不允许继续修改投票。
```

补充规则：

1. `budget_max`必须大于0。
2. `free_text`最大长度建议200字。
3. 匿名投票仍需生成内部`participant_id`。
4. `liked_plan_ids`和`disliked_plan_ids`中的ID必须属于`candidate_plan_ids`。

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0100",
  "data": {
    "vote_id": "vote_0001",
    "consensus_session_id": "cs_0001",
    "vote_page_id": "vpage_0001",
    "plan_group_id": "plangrp_0001",
    "vote": {
      "vote_id": "vote_0001",
      "consensus_session_id": "cs_0001",
      "trace_id": "trace_20260520_0100",
      "participant": {
        "participant_id": "anon_part_0001",
        "participant_name": "朋友A",
        "anonymous": false,
        "role": "friend",
        "preference_tags": ["chat", "low_walk"],
        "hard_constraints": ["budget_under_100"],
        "soft_constraints": ["prefer_indoor"]
      },
      "liked_plan_ids": ["plan_candidate_b", "plan_candidate_c"],
      "disliked_plan_ids": ["plan_candidate_a"],
      "budget_max": 100,
      "time_preference": "after_14_30",
      "walking_tolerance": "low",
      "queue_tolerance": "low",
      "free_text": "我不想走太多，也不想排队。",
      "submitted_at": "2026-05-20T13:10:00+08:00",
      "updated_at": "2026-05-20T13:10:00+08:00"
    },
    "vote_count": 1
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0100",
  "data": null,
  "error": {
    "code": "CONSENSUS_VOTE_INVALID",
    "message": "liked_plan_ids and disliked_plan_ids overlap.",
    "user_message": "同一个方案不能同时选择喜欢和不想选，请修改后提交。",
    "recoverable": true,
    "details": {
      "overlap_plan_ids": ["plan_candidate_a"]
    }
  }
}
```

#### 状态变化

```text
collecting → collecting
finalized → 拒绝修改
```

#### 前端处理建议

1. 不要求用户必须点喜欢；只写一句话也可提交。
2. 提交成功后展示“已收到你的偏好”。
3. 失败时保留表单内容。

#### 测试验收标准

1. 只提交`free_text`可成功。
2. 只提交`disliked_plan_ids`可成功。
3. 喜欢与反选重叠必须失败。
4. finalize后提交必须失败或返回已关闭提示。

---

### POST /api/v1/consensus/{consensus_session_id}/finalize

#### 接口定位

结束投票，汇总多人偏好，生成合法的`ConsensusSummary`，并基于共识约束生成最终PlanContract。`ConsensusSummary`只有finalize后才生成；未finalize时只能返回`RealtimeConsensusStats`。

#### 调用页面

共识进度页、共识结果页。

#### 调用模块

ConsensusService → PlanGenerator → PlanContractBuilder → MockAPI → VerifierService → PlanService。

#### 是否P0

是。

#### 幂等性

finalize后重复调用返回同一`ConsensusSummary`和`final_plan_contract`，不得重复生成多个最终方案，除非显式传`force_regenerate=true`且Debug模式允许。

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| close_voting | boolean | 否 | true | 是否关闭投票 |
| force_regenerate | boolean | 否 | false | Debug模式可重新生成 |
| min_vote_count_policy | string | 否 | allow_low_vote_count | 投票不足降级策略 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0100",
  "data": {
    "consensus_session_id": "cs_0001",
    "vote_page_id": "vpage_0001",
    "plan_group_id": "plangrp_0001",
    "share_url": "https://demo.lifepilot.local/vote/vpage_0001",
    "candidate_plan_ids": ["plan_candidate_a", "plan_candidate_b", "plan_candidate_c"],
    "consensus_summary": {
      "consensus_session_id": "cs_0001",
      "trace_id": "trace_20260520_0100",
      "vote_count": 3,
      "support_count_by_plan": {
        "plan_candidate_a": 1,
        "plan_candidate_b": 3,
        "plan_candidate_c": 2
      },
      "oppose_count_by_plan": {
        "plan_candidate_a": 2,
        "plan_candidate_b": 0,
        "plan_candidate_c": 1
      },
      "detected_conflicts": [
        { "type": "walking_tolerance", "level": "medium", "description": "有2人明确不想走太多。" },
        { "type": "budget", "level": "medium", "description": "多数人希望人均不超过100元。" }
      ],
      "consensus_constraints": {
        "party_size": 4,
        "budget_max": null,
        "budget_max_per_person": 100,
        "walking_tolerance": "low",
        "queue_tolerance": "low",
        "distance_preference": "nearby",
        "dietary_preference": [],
        "activity_preference": ["chat", "light", "indoor"],
        "weather_sensitive": true,
        "child_friendly_required": false,
        "indoor_preferred": true,
        "emotion_intensity": "light",
        "time_flexibility": "medium",
        "must_have": ["低排队", "适合4人"],
        "must_not_have": ["走太多", "人均超过150"]
      },
      "explanation": "大家反馈中“不想走太多”和“别排队”优先级最高，因此最终选择短距离室内聊天方案，并保留低预算餐厅。",
      "final_plan_id": "plan_final_0001",
      "generated_at": "2026-05-20T13:30:00+08:00"
    },
    "final_plan_contract": {
      "plan_id": "plan_final_0001",
      "trace_id": "trace_20260520_0100",
      "version": "v0.1",
      "status": "executable",
      "user_goal": {
        "raw_text": "下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。",
        "scenario": "friend_group",
        "goal_summary": "综合朋友投票后，安排一段低步行、低排队、人均约100元的室内朋友局。",
        "intent_tags": ["friend_group", "consensus", "low_walk", "low_queue"],
        "emotion_goal": "减少群聊拉扯，降低组织者背锅风险",
        "source": "user_input",
        "confidence": 0.9
      },
      "participants": [
        { "participant_id": "part_user_001", "role": "user", "display_name": "我", "age": null, "constraints": [], "preference_tags": [] }
      ],
      "time_window": {
        "start_time": "2026-05-20T14:30:00+08:00",
        "end_time": "2026-05-20T18:00:00+08:00",
        "time_flexibility": "medium"
      },
      "constraints": {
        "party_size": 4,
        "budget_max": null,
        "budget_max_per_person": 100,
        "walking_tolerance": "low",
        "queue_tolerance": "low",
        "distance_preference": "nearby",
        "dietary_preference": [],
        "activity_preference": ["chat", "light", "indoor"],
        "weather_sensitive": true,
        "child_friendly_required": false,
        "indoor_preferred": true,
        "emotion_intensity": "light",
        "time_flexibility": "medium",
        "must_have": ["低排队", "适合4人"],
        "must_not_have": ["走太多", "人均超过150"]
      },
      "timeline": [
        {
          "step_id": "step_0001",
          "order": 1,
          "type": "activity",
          "title": "室内桌游聊天",
          "description": "适合4人坐着聊天，不受天气影响。",
          "start_time": "2026-05-20T14:30:00+08:00",
          "end_time": "2026-05-20T16:30:00+08:00",
          "duration_minutes": 120,
          "poi_id": "poi_boardgame_001",
          "from_poi_id": null,
          "to_poi_id": null,
          "transport_mode": null,
          "estimated_route": null,
          "booking_required": true,
          "reservation_required": false,
          "status": "verified",
          "related_tool_action_ids": ["act_book_0001"],
          "display_tags": ["室内", "低步行", "可预约"],
          "user_visible_notes": "当前包间可预约。"
        }
      ],
      "budget": {
        "currency": "CNY",
        "estimated_total": 360,
        "price_per_person": 90,
        "items": [{ "name": "桌游包间", "amount": 360, "source": "mock_api" }]
      },
      "executable_window": {
        "window_minutes": 20,
        "confidence": 0.84,
        "expire_at": "2026-05-20T13:50:00+08:00",
        "reasons": ["桌游包间当前可预约", "路线较短", "预算满足多数人要求"],
        "risk_factors": [],
        "lockable_resources": ["activity_booking"],
        "calculated_from": ["poi_status", "route_estimate"],
        "display_message": "当前共识方案可执行窗口约20分钟。"
      },
      "risks": [],
      "backup_plans": [],
      "tool_actions": [
        {
          "action_id": "act_book_0001",
          "plan_id": "plan_final_0001",
          "step_id": "step_0001",
          "type": "book_activity",
          "target_poi_id": "poi_boardgame_001",
          "target": null,
          "payload": { "arrival_time": "2026-05-20T14:30:00+08:00", "party_size": 4 },
          "status": "pending",
          "depends_on": [],
          "retry_count": 0,
          "idempotency_key": "idem_act_book_0001",
          "result": null,
          "error_code": null,
          "user_visible": true,
          "created_at": "2026-05-20T13:30:00+08:00",
          "updated_at": "2026-05-20T13:30:00+08:00"
        }
      ],
      "messages": {
        "to_group": "我让LifePilot排了一版，综合大家投票，下午走轻松室内版：14:30桌游聊天，人均约90，不用走太多。"
      },
      "verifier_result": {
        "status": "pass",
        "score": 0.84,
        "checks": [],
        "failed_checks": [],
        "warnings": [],
        "required_recovery": false,
        "suggestions": [],
        "created_at": "2026-05-20T13:30:02+08:00"
      },
      "recovery_results": [],
      "execution_summary": null,
      "memory_usage": [],
      "social_signals": [],
      "created_at": "2026-05-20T13:30:00+08:00",
      "updated_at": "2026-05-20T13:30:02+08:00"
    }
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0100",
  "data": null,
  "error": {
    "code": "CONSENSUS_VOTE_INVALID",
    "message": "session has no valid votes and fallback disabled.",
    "user_message": "当前还没有有效投票，至少需要一条偏好后再生成共识方案。",
    "recoverable": true,
    "details": {}
  }
}
```

#### 状态变化

```text
collecting → closed/expired → finalized
```

#### 测试验收标准

1. 最终方案必须重新Verifier。
2. 返回`ConsensusSummary`和`final_plan_contract`。
3. 投票不足时如降级，`ConsensusSummary.detected_conflicts`必须包含`type:"low_vote_count"`的冲突说明。
4. finalize后不允许普通投票继续修改。

投票不足不得新增`quality_flags`字段。应使用`detected_conflicts`表达，例如：

```json
{
  "type": "low_vote_count",
  "level": "medium",
  "description": "当前投票人数较少，最终方案基于已有反馈生成。"
}
```

---

### GET /api/v1/consensus/{consensus_session_id}/summary

#### 接口定位

读取已生成的共识摘要或未finalize前的实时统计。未finalize时不得伪造缺少`final_plan_id`的`ConsensusSummary`。

#### 调用页面

共识结果页、发起人进度页。

#### 调用模块

ConsensusService。

#### 是否P0

是。

#### 成功响应示例

未finalize时：

```json
{
  "success": true,
  "trace_id": "trace_20260520_0100",
  "data": {
    "consensus_session_id": "cs_0001",
    "vote_page_id": "vpage_0001",
    "plan_group_id": "plangrp_0001",
    "status": "collecting",
    "realtime_stats": {
      "vote_count": 2,
      "support_count_by_plan": { "plan_candidate_b": 2 },
      "oppose_count_by_plan": { "plan_candidate_a": 1 },
      "detected_conflicts_preview": [
        { "type": "walking_tolerance", "level": "medium", "description": "已有反馈显示步行容忍较低。" }
      ],
      "status_notes": ["not_finalized"]
    },
    "consensus_summary": null,
    "final_plan_view": null
  },
  "error": null
}
```

finalize后：

```json
{
  "success": true,
  "trace_id": "trace_20260520_0100",
  "data": {
    "consensus_session_id": "cs_0001",
    "vote_page_id": "vpage_0001",
    "plan_group_id": "plangrp_0001",
    "status": "finalized",
    "consensus_summary": {
      "consensus_session_id": "cs_0001",
      "trace_id": "trace_20260520_0100",
      "vote_count": 3,
      "support_count_by_plan": { "plan_candidate_b": 3 },
      "oppose_count_by_plan": { "plan_candidate_a": 2 },
      "detected_conflicts": [],
      "consensus_constraints": { "party_size": 4, "budget_max_per_person": 100 },
      "explanation": "大家更偏向低步行、少排队的方案。",
      "final_plan_id": "plan_final_0001",
      "generated_at": "2026-05-20T13:30:00+08:00"
    },
    "final_plan_view": {
      "plan_id": "plan_final_0001",
      "status": "executable",
      "title": "室内桌游聊天",
      "summary": "低步行、低排队、人均约90元的室内朋友局。"
    }
  },
  "error": null
}
```

#### 测试验收标准

1. 未finalize时只能返回`realtime_stats`，且`consensus_summary`和`final_plan_view`均为null。
2. 已finalize时必须返回`ConsensusSummary`和最终方案展示投影`final_plan_view`；完整PlanContract通过`GET /api/v1/plans/{final_plan_id}`读取。
3. 不暴露匿名参与者真实身份。

---

## 11.Executor与Execution APIs

### 11.1Executor设计原则

1. Executor只执行`ToolAction`，不执行自然语言。
2. ToolAction必须按`depends_on`拓扑顺序执行。
3. 每个执行动作必须有`idempotency_key`。
4. Mock执行结果必须返回Mock凭证，并带`mock_only:true`。
5. 单个关键动作失败时，若`recoverable=true`，优先触发Recovery。
6. 非关键动作如Mock消息发送失败，可标记`skipped/failed`，不一定阻断主行程。

### 11.2ToolAction状态机

```text
pending
→ running
→ success / failed
→ recovered / skipped
```

状态说明：

| 状态 | 说明 |
|---|---|
| pending | 已生成但未执行 |
| running | 正在调用MockAPI |
| success | 执行成功，有结果或凭证 |
| failed | 执行失败，有error_code |
| recovered | 已由Recovery提供替代动作 |
| skipped | 非关键动作被跳过 |

### 11.3动作依赖执行规则

| 规则 | 说明 |
|---|---|
| depends_on为空 | 可直接执行 |
| depends_on全部success | 才能执行当前动作 |
| 前置动作failed且不可恢复 | 当前动作skipped或整体failed |
| 前置动作recovered | 当前动作应绑定替代后的step或poi重新计算 |
| 同一idempotency_key重复执行 | 返回首次执行结果，不重复生成凭证 |

### 11.4内部接口：GET /api/v1/executions/{execution_id}

#### 接口定位

读取ExecutionResult。P0建议实现，用于执行结果页刷新恢复；若时间不足，可由`GET /plans/{plan_id}`携带最近ExecutionResult替代。

#### 是否P0

建议P0。

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "execution_result": {
      "execution_id": "exec_20260520_0001",
      "plan_id": "plan_20260520_0001",
      "trace_id": "trace_20260520_0001",
      "status": "success",
      "action_results": [],
      "vouchers": [],
      "failed_actions": [],
      "recovery_results": [],
      "user_message": "执行完成。",
      "created_at": "2026-05-20T13:20:00+08:00"
    }
  },
  "error": null
}
```

### 11.5内部接口：GET /api/v1/executions/{execution_id}/actions

#### 接口定位

读取执行中的动作状态列表，用于执行结果页进度条或Debug面板。

#### 是否P0

P0可选，推荐实现。

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "execution_id": "exec_20260520_0001",
    "actions": [
      {
        "action_id": "act_book_0001",
        "type": "book_activity",
        "status": "success",
        "step_id": "step_0002",
        "target_poi_id": "poi_child_science_001",
        "result": { "booking_id": "mock_booking_BA1024", "mock_only": true },
        "updated_at": "2026-05-20T13:20:00+08:00"
      }
    ]
  },
  "error": null
}
```

---

## 12.MockAPI APIs

### 12.1MockAPI统一原则

1. Mock接口只用于Demo。
2. 不承诺真实交易。
3. 不承诺真实爬取。
4. 所有执行凭证必须带`mock_only:true`。
5. SocialSignal必须带`is_mock:true`和`source_type:"mock_social_signal"`。
6. failure_injection只在Debug或测试场景可见，用户页不得展示。

### 12.2MockAPI总览

| 接口 | 方法 | 用途 | P0 |
|---|---|---|---:|
| /api/v1/mock/poi/search | GET | 搜索活动/地点/散步点/服务点 | 是 |
| /api/v1/mock/restaurants/search | GET | 搜索餐厅 | 是 |
| /api/v1/mock/poi/{poi_id}/status | GET | 查询活动/POI状态 | 是 |
| /api/v1/mock/restaurants/{poi_id}/status | GET | 查询餐厅余位/排队/订座状态 | 是 |
| /api/v1/mock/routes/estimate | GET | 路线估计 | 是 |
| /api/v1/mock/weather | GET | 天气Mock | 是 |
| /api/v1/mock/activities/{poi_id}/book | POST | 模拟活动预约 | 是 |
| /api/v1/mock/restaurants/{poi_id}/reserve | POST | 模拟餐厅订座 | 是 |
| /api/v1/mock/orders/create | POST | 模拟下单 | 是 |
| /api/v1/mock/messages/send | POST | 模拟消息发送 | 是 |
| /api/v1/mock/social-signals/{poi_id} | GET | 口碑雷达Mock | P1，P0可预留 |

### 12.3GET /api/v1/mock/poi/search

#### Query Parameters

| 参数 | 类型 | 示例 | 说明 |
|---|---|---|---|
| area | string | 金沙湖 | 固定Mock区域 |
| category | string | activity | activity/walk_spot/service等 |
| scenario | string | family_parent_child | 场景 |
| tags | string | child_friendly,indoor | 逗号分隔 |
| party_size | integer | 3 | 人数 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "items": [
      {
        "poi_id": "poi_child_science_001",
        "name": "金沙湖儿童科学空间",
        "category": "activity",
        "sub_category": "child_science",
        "tags": ["child_friendly", "interactive", "indoor"],
        "location": { "city": "杭州", "area": "金沙湖", "lat": 30.312, "lng": 120.345 },
        "area": "金沙湖",
        "address": "杭州市钱塘区金沙湖商圈Mock地址1号",
        "price_per_person": 40,
        "rating": 4.7,
        "opening_hours": { "weekday": [["10:00", "21:30"]], "weekend": [["10:00", "22:00"]] },
        "suitable_scenarios": ["family_parent_child"],
        "risk_tags": [],
        "mock_only": true,
        "created_at": "2026-05-20T00:00:00+08:00",
        "updated_at": "2026-05-20T00:00:00+08:00"
      }
    ],
    "page_info": { "page_size": 20, "next_page_token": null, "has_more": false }
  },
  "error": null
}
```

### 12.4GET /api/v1/mock/restaurants/search

#### Query Parameters

| 参数 | 类型 | 示例 | 说明 |
|---|---|---|---|
| area | string | 金沙湖 | 区域 |
| dietary_preference | string | low_calorie,light_food | 饮食偏好 |
| budget_max_per_person | number | 100 | 人均预算 |
| party_size | integer | 3 | 人数 |
| scenario | string | family_parent_child | 场景 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "items": [
      {
        "poi_id": "poi_light_food_003",
        "name": "轻盈厨房",
        "category": "restaurant",
        "sub_category": "light_food",
        "tags": ["low_calorie", "family_friendly", "quiet", "reservable"],
        "location": { "city": "杭州", "area": "金沙湖", "lat": 30.312, "lng": 120.345 },
        "area": "金沙湖",
        "address": "杭州市钱塘区金沙湖商圈Mock地址3号",
        "price_per_person": 60,
        "rating": 4.6,
        "opening_hours": { "weekday": [["10:00", "21:30"]], "weekend": [["10:00", "22:00"]] },
        "suitable_scenarios": ["family_parent_child", "anniversary_emotion"],
        "risk_tags": ["limited_tables"],
        "mock_only": true,
        "created_at": "2026-05-20T00:00:00+08:00",
        "updated_at": "2026-05-20T00:00:00+08:00"
      }
    ]
  },
  "error": null
}
```

### 12.5GET /api/v1/mock/poi/{poi_id}/status

#### Query Parameters

| 参数 | 类型 | 示例 | 说明 |
|---|---|---|---|
| arrival_time | string | 2026-05-20T14:05:00+08:00 | 到达时间 |
| party_size | integer | 3 | 人数 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "poi_id": "poi_child_science_001",
    "available": true,
    "open_status": "open",
    "available_tables": null,
    "queue_minutes": 0,
    "ticket_available": true,
    "remaining_tickets": 28,
    "booking_available": true,
    "reservation_available": null,
    "risk_level": "low",
    "source": "mock_api",
    "mock_only": true,
    "updated_at": "2026-05-20T13:00:00+08:00",
    "expire_at": "2026-05-20T13:30:00+08:00"
  },
  "error": null
}
```

### 12.6GET /api/v1/mock/restaurants/{poi_id}/status

#### Query Parameters

| 参数 | 类型 | 示例 | 必填 | 说明 |
|---|---|---|---:|---|
| arrival_time | string | 2026-05-20T15:55:00+08:00 | 是 | 到店时间，用于计算余位、排队和订座可用性 |
| party_size | integer | 3 | 是 | 用餐人数，用于匹配桌型和容量 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "poi_id": "poi_light_food_003",
    "available": true,
    "open_status": "open",
    "available_tables": 2,
    "queue_minutes": 12,
    "ticket_available": null,
    "booking_available": null,
    "reservation_available": true,
    "risk_level": "medium",
    "source": "mock_api",
    "mock_only": true,
    "updated_at": "2026-05-20T13:00:00+08:00",
    "expire_at": "2026-05-20T13:18:00+08:00"
  },
  "error": null
}
```

#### Debug响应可选字段

```json
{
  "failure_injection": {
    "enabled": true,
    "on_execute": "NO_TABLE_AVAILABLE"
  }
}
```

普通用户页不得展示`failure_injection`。

所有POIStatus、RestaurantStatus、ActivityStatus响应必须带`updated_at`和`expire_at`。`expire_at`过期后，执行前必须调用`verify`或`refresh-window`重新校验。

### 12.7GET /api/v1/mock/routes/estimate

#### Query Parameters

| 参数 | 类型 | 示例 | 必填 |
|---|---|---|---:|
| origin_poi_id | string | poi_home_anchor_001 | 是 |
| destination_poi_id | string | poi_child_science_001 | 是 |
| transport_mode | string | taxi | 是 |
| departure_time | string | 2026-05-20T13:40:00+08:00 | 是 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "route_id": "route_0001",
    "origin_poi_id": "poi_home_anchor_001",
    "destination_poi_id": "poi_child_science_001",
    "transport_mode": "taxi",
    "distance_km": 5.2,
    "duration_minutes": 25,
    "traffic_level": "medium",
    "confidence": 0.82,
    "source": "mock_api",
    "updated_at": "2026-05-20T13:00:00+08:00"
  },
  "error": null
}
```

### 12.8GET /api/v1/mock/weather

#### Query Parameters

| 参数 | 类型 | 示例 | 必填 |
|---|---|---|---:|
| area | string | 金沙湖 | 是 |
| start_time | string | 2026-05-20T13:30:00+08:00 | 是 |
| end_time | string | 2026-05-20T18:00:00+08:00 | 是 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "weather_id": "weather_jinsha_20260520_pm",
    "area": "金沙湖",
    "time_range": {
      "start_time": "2026-05-20T13:30:00+08:00",
      "end_time": "2026-05-20T18:00:00+08:00"
    },
    "weather": "cloudy",
    "temperature": 25,
    "rain_probability": 0.18,
    "outdoor_risk_level": "low",
    "suggested_recovery": "indoor_activity",
    "source": "mock_api",
    "updated_at": "2026-05-20T13:00:00+08:00"
  },
  "error": null
}
```

### 12.9POST /api/v1/mock/activities/{poi_id}/book

#### Request Body

| 字段 | 类型 | 必填 | 示例 |
|---|---|---:|---|
| arrival_time | string | 是 | 2026-05-20T14:05:00+08:00 |
| party_size | integer | 是 | 3 |
| idempotency_key | string | 是 | idem_act_book_0001 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "booking_id": "mock_booking_BA1024",
    "poi_id": "poi_child_science_001",
    "status": "success",
    "mock_only": true,
    "created_at": "2026-05-20T13:20:00+08:00"
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "ACTIVITY_FULL",
    "message": "activity slot is full.",
    "user_message": "当前场次已满，正在找替代活动。",
    "recoverable": true,
    "details": {}
  }
}
```

### 12.10POST /api/v1/mock/restaurants/{poi_id}/reserve

#### Request Body

| 字段 | 类型 | 必填 | 示例 |
|---|---|---:|---|
| arrival_time | string | 是 | 2026-05-20T15:55:00+08:00 |
| party_size | integer | 是 | 3 |
| seat_preference | string | 否 | quiet |
| idempotency_key | string | 是 | idem_act_reserve_0001 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "reservation_id": "mock_reservation_R2048",
    "poi_id": "poi_light_food_003",
    "status": "success",
    "mock_only": true,
    "created_at": "2026-05-20T13:20:02+08:00"
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "NO_TABLE_AVAILABLE",
    "message": "no table available for party_size=3.",
    "user_message": "原餐厅已满，我会尝试为你切换到备选餐厅。",
    "recoverable": true,
    "details": {}
  }
}
```

### 12.11POST /api/v1/mock/orders/create

#### P0优先级

P0保留接口并轻量实现。用于纪念日蛋糕、鲜花或轻食套餐模拟下单，只返回Mock订单凭证，不做真实支付。PlanContract不强制每个场景都生成`order_item` ToolAction；接口是P0，动作生成是P0可选。

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "order_id": "mock_order_O1024",
    "status": "success",
    "amount": 68,
    "currency": "CNY",
    "payment_required": false,
    "mock_only": true,
    "created_at": "2026-05-20T13:20:05+08:00"
  },
  "error": null
}
```

### 12.12POST /api/v1/mock/messages/send

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| target | string/object | 是 | spouse | 发送对象，Demo标识 |
| content | string | 是 | 我排了一版下午安排…… | 消息内容 |
| channel | string | 否 | mock_wechat | Mock渠道 |
| idempotency_key | string | 是 | idem_act_message_0001 | 防重复 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "message_id": "mock_message_M4096",
    "channel": "mock_wechat",
    "status": "success",
    "mock_only": true,
    "display_note": "这是Demo模拟消息，不会真实发送微信或短信。",
    "created_at": "2026-05-20T13:20:03+08:00"
  },
  "error": null
}
```

### 12.13GET /api/v1/mock/social-signals/{poi_id}

#### P0/P1

P1接口，P0可预留。所有返回必须标注Mock。

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "signal_id": "sig_0001",
    "poi_id": "poi_light_food_003",
    "summary": "口碑Mock显示这家轻食环境安静，适合家庭用餐，但周末下午座位偏紧。",
    "positive_tags": ["环境安静", "低卡选择多", "家庭友好"],
    "negative_tags": ["座位偏少", "高峰可能排队"],
    "source_type": "mock_social_signal",
    "confidence": 0.72,
    "is_mock": true,
    "mock_sources": ["mock_xhs", "mock_dianping"],
    "updated_at": "2026-05-20T12:00:00+08:00"
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "SOCIAL_SIGNAL_MOCK_REQUIRED",
    "message": "social signal must be marked as mock.",
    "user_message": "口碑Mock数据异常，已隐藏该卡片。",
    "recoverable": true,
    "details": {}
  }
}
```

---

## 13.LifeMemory APIs

### 13.1P0/P1边界

| 阶段 | 范围 |
|---|---|
| P0最小候选闭环 | 反馈后可生成MemoryCandidate、展示候选、支持确认/忽略接口或按钮预留；执行隐私规则：高敏不保存、中敏待确认、低敏进入候选 |
| P1完整闭环 | LifeMemory管理页、编辑、删除、关闭个性化、下次规划读取已确认记忆 |

LifeMemory不是不可见画像系统。所有长期记忆必须可审计、用户可控、可删除。长期LifeMemory使用`source_trace_id`和`last_used_trace_id`，不得强行等同于单次trace。

### 13.2隐私规则

| 敏感度 | 示例 | 处理 |
|---|---|---|
| low | 不喜欢排队、偏好近距离、预算敏感 | 可进入候选，低风险多次出现可启用 |
| medium | 孩子年龄、配偶近期减脂、备考阶段 | 需要用户确认 |
| high | 健康诊断、收入、婚姻状态、精确住址 | 默认不保存 |

补充规则：

1. 删除后不得静默恢复。
2. 关闭个性化后不读取、不写入长期记忆。
3. 记忆使用必须可解释。
4. 单次模糊表达只作为短期上下文，不直接写长期偏好。

### 13.3Memory API总览

| 接口 | 页面 | P0/P1 | 说明 |
|---|---|---|---|
| GET /api/v1/memory | LifeMemory管理页 | P1 | 读取长期记忆列表 |
| GET /api/v1/memory/candidates | 反馈页/执行结果页/管理页 | P0 | 读取候选记忆 |
| POST /api/v1/memory/candidates/{candidate_id}/confirm | 候选记忆卡片 | P0预留或最小实现/P1完整 | 确认保存 |
| POST /api/v1/memory/candidates/{candidate_id}/ignore | 候选记忆卡片 | P0 | 忽略候选 |
| PATCH /api/v1/memory/{memory_id} | 管理页 | P1 | 编辑记忆 |
| DELETE /api/v1/memory/{memory_id} | 管理页 | P1 | 删除记忆 |
| POST /api/v1/memory/personalization/disable | 管理页 | P1 | 关闭个性化 |
| POST /api/v1/memory/personalization/enable | 管理页 | P1 | 开启个性化 |

### 13.4GET /api/v1/memory

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_mem_0001",
  "data": {
    "personalization_enabled": true,
    "items": [
      {
        "memory_id": "mem_0001",
        "user_id": "user_demo_001",
        "source_trace_id": "trace_20260518_0001",
        "last_used_trace_id": "trace_20260520_0001",
        "content": "用户在家庭出行中偏好不太远、不太赶的路线。",
        "memory_type": "preference",
        "source": {
          "type": "feedback",
          "trace_id": "trace_20260518_0001",
          "text": "上次有点赶，下次别安排太满。",
          "created_at": "2026-05-18T18:00:00+08:00"
        },
        "confidence": 0.82,
        "sensitivity": "low",
        "ttl_days": 180,
        "status": "enabled",
        "user_visible": true,
        "user_confirmed": true,
        "enabled": true,
        "last_used_at": "2026-05-20T13:00:00+08:00",
        "created_at": "2026-05-18T18:05:00+08:00",
        "updated_at": "2026-05-20T13:00:00+08:00",
        "expires_at": "2026-11-14T18:05:00+08:00"
      }
    ],
    "page_info": { "page_size": 20, "next_page_token": null, "has_more": false }
  },
  "error": null
}
```

### 13.5GET /api/v1/memory/candidates

#### Query Parameters

| 参数 | 类型 | 示例 | 说明 |
|---|---|---|---|
| status | string | pending_confirmation | 过滤状态 |
| source_trace_id | string | trace_20260520_0001 | 可按来源trace查 |
| plan_id | string | plan_20260520_0001 | 可按计划查 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "items": [
      {
        "candidate_id": "memcand_0001",
        "user_id": "user_demo_001",
        "source_trace_id": "trace_20260520_0001",
        "content": "用户在家庭亲子场景中对排队较敏感。",
        "memory_type": "negative_feedback",
        "source": {
          "type": "trip_feedback",
          "trace_id": "trace_20260520_0001",
          "text": "排队还是太久了。",
          "created_at": "2026-05-20T18:10:00+08:00"
        },
        "confidence": 0.76,
        "sensitivity": "low",
        "requires_confirmation": true,
        "status": "pending_confirmation",
        "suggested_ttl_days": 180,
        "created_at": "2026-05-20T18:11:00+08:00"
      }
    ]
  },
  "error": null
}
```

### 13.6POST /api/v1/memory/candidates/{candidate_id}/confirm

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| edited_content | string | 否 | 我在家庭出行中不喜欢长时间排队。 | 用户编辑后的内容 |
| ttl_days | integer | 否 | 180 | 有效期 |
| enabled | boolean | 否 | true | 是否立即启用 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "memory": {
      "memory_id": "mem_0002",
      "user_id": "user_demo_001",
      "source_trace_id": "trace_20260520_0001",
      "last_used_trace_id": null,
      "content": "我在家庭出行中不喜欢长时间排队。",
      "memory_type": "negative_feedback",
      "source": {
        "type": "trip_feedback",
        "trace_id": "trace_20260520_0001",
        "text": "排队还是太久了。",
        "created_at": "2026-05-20T18:10:00+08:00"
      },
      "confidence": 0.76,
      "sensitivity": "low",
      "ttl_days": 180,
      "status": "enabled",
      "user_visible": true,
      "user_confirmed": true,
      "enabled": true,
      "last_used_at": null,
      "created_at": "2026-05-20T18:12:00+08:00",
      "updated_at": "2026-05-20T18:12:00+08:00",
      "expires_at": "2026-11-16T18:12:00+08:00"
    },
    "candidate_status": "enabled"
  },
  "error": null
}
```

#### 失败响应示例

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "MEMORY_PRIVACY_VIOLATION",
    "message": "high sensitivity candidate cannot be confirmed automatically.",
    "user_message": "该信息较敏感，不会被自动保存。",
    "recoverable": false,
    "details": {}
  }
}
```

### 13.7POST /api/v1/memory/candidates/{candidate_id}/ignore

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "candidate_id": "memcand_0001",
    "status": "ignored",
    "updated_at": "2026-05-20T18:12:00+08:00"
  },
  "error": null
}
```

### 13.8PATCH /api/v1/memory/{memory_id}

#### Request Body

| 字段 | 类型 | 必填 | 示例 |
|---|---|---:|---|
| content | string | 否 | 我更偏好少排队的餐厅。 |
| enabled | boolean | 否 | true |
| ttl_days | integer | 否 | 180 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_mem_0001",
  "data": {
    "memory_id": "mem_0001",
    "status": "enabled",
    "enabled": true,
    "content": "我更偏好少排队的餐厅。",
    "updated_at": "2026-05-20T18:20:00+08:00"
  },
  "error": null
}
```

### 13.9DELETE /api/v1/memory/{memory_id}

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_mem_0001",
  "data": {
    "memory_id": "mem_0001",
    "status": "deleted",
    "deleted_at": "2026-05-20T18:21:00+08:00"
  },
  "error": null
}
```

删除后不得静默恢复；相似内容再次出现时必须重新作为MemoryCandidate展示来源。

### 13.10POST /api/v1/memory/personalization/disable

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_mem_0001",
  "data": {
    "user_id": "user_demo_001",
    "personalization_enabled": false,
    "effect": {
      "read_long_term_memory": false,
      "write_long_term_memory": false,
      "keep_current_session_context": true
    },
    "updated_at": "2026-05-20T18:22:00+08:00"
  },
  "error": null
}
```

### 13.11POST /api/v1/memory/personalization/enable

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_mem_0001",
  "data": {
    "user_id": "user_demo_001",
    "personalization_enabled": true,
    "updated_at": "2026-05-20T18:23:00+08:00"
  },
  "error": null
}
```

---

## 14.Feedback APIs

### 14.1Feedback设计原则

P0只要求低打扰反馈提交、跳过和MemoryCandidate候选生成；完整反馈历史、复杂追问和与长期LifeMemory联动的管理能力属于P1。

1. 执行后低打扰反馈最多2个问题。
2. 用户可以跳过，跳过不阻断主流程。
3. 反馈可能生成MemoryCandidate。
4. 不得自动写入高敏记忆。
5. 反馈问题应围绕计划质量、排队、距离、预算、孩子兴趣、餐饮匹配等规划相关信息。

### 14.2POST /api/v1/feedback

#### 接口定位

提交低打扰反馈，并可触发MemoryCandidate生成。

#### 调用页面

执行结果页后的反馈页。

#### 调用模块

FeedbackService → LifeMemoryService → LoggingService。

#### 是否P0

是。

#### Request Body

| 字段 | 类型 | 必填 | 示例 | 说明 |
|---|---|---:|---|---|
| plan_id | string | 是 | plan_20260520_0001 | 关联计划 |
| execution_id | string | 否 | exec_20260520_0001 | 关联执行 |
| rating | string | 否 | just_right | 轻量评分 |
| selected_options | string[] | 否 | ["queue_too_long"] | 选项反馈 |
| free_text | string | 否 | 排队还是太久了 | 文本反馈 |
| skipped | boolean | 否 | false | 是否跳过 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "feedback_id": "fb_0001",
    "plan_id": "plan_20260520_0001",
    "accepted": true,
    "skipped": false,
    "memory_candidates": [
      {
        "candidate_id": "memcand_0001",
        "user_id": "user_demo_001",
        "source_trace_id": "trace_20260520_0001",
        "content": "用户在家庭亲子场景中对排队较敏感。",
        "memory_type": "negative_feedback",
        "source": {
          "type": "trip_feedback",
          "trace_id": "trace_20260520_0001",
          "text": "排队还是太久了。",
          "created_at": "2026-05-20T18:10:00+08:00"
        },
        "confidence": 0.76,
        "sensitivity": "low",
        "requires_confirmation": true,
        "status": "pending_confirmation",
        "suggested_ttl_days": 180,
        "created_at": "2026-05-20T18:11:00+08:00"
      }
    ],
    "created_at": "2026-05-20T18:11:00+08:00"
  },
  "error": null
}
```

#### 跳过响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "feedback_id": "fb_0002",
    "plan_id": "plan_20260520_0001",
    "accepted": true,
    "skipped": true,
    "memory_candidates": [],
    "created_at": "2026-05-20T18:11:00+08:00"
  },
  "error": null
}
```

### 14.3GET /api/v1/feedback/questions?plan_id=...

#### 接口定位

获取某计划对应的最多2个低打扰反馈问题。

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "plan_id": "plan_20260520_0001",
    "questions": [
      {
        "question_id": "q_0001",
        "type": "single_choice",
        "text": "今天这套安排整体感觉怎么样？",
        "options": [
          { "value": "just_right", "label": "刚刚好" },
          { "value": "too_rushed", "label": "有点赶" },
          { "value": "child_not_interested", "label": "孩子不太感兴趣" },
          { "value": "restaurant_not_good", "label": "餐厅不太合适" },
          { "value": "queue_too_long", "label": "排队还是太久" }
        ]
      },
      {
        "question_id": "q_0002",
        "type": "single_choice",
        "text": "下次家庭出行，你更希望我优先避开哪类问题？",
        "options": [
          { "value": "queue", "label": "排队" },
          { "value": "distance", "label": "距离" },
          { "value": "budget", "label": "预算" },
          { "value": "child_bored", "label": "孩子无聊" },
          { "value": "restaurant", "label": "餐饮不合适" }
        ]
      }
    ],
    "max_questions": 2,
    "skippable": true
  },
  "error": null
}
```

---

## 15.Trace与Debug APIs

### 15.1Debug边界

Debug接口仅Demo开发/评委模式使用。不得展示：

* 底层Prompt；
* API Key；
* LLM推理链；
* 高敏MemoryCandidate；
* 普通用户页的failure_injection；
* 未脱敏内部日志。

用户页只展示简化工具调用链。

### 15.2GET /api/v1/traces/{trace_id}

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "trace_id": "trace_20260520_0001",
    "root_object": {
      "type": "plan",
      "id": "plan_20260520_0001"
    },
    "summary": {
      "input": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
      "scenario": "family_parent_child",
      "status": "completed",
      "tool_call_count": 6,
      "recovery_count": 1
    },
    "created_at": "2026-05-20T13:00:00+08:00"
  },
  "error": null
}
```

### 15.3GET /api/v1/traces/{trace_id}/events

#### Query Parameters

| 参数 | 类型 | 示例 | 说明 |
|---|---|---|---|
| visible_only | boolean | true | 普通用户页必须true |
| level | string | error | 可按级别过滤 |
| page_size | integer | 50 | 分页 |
| page_token | string | cursor_x | 分页游标 |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "items": [
      {
        "log_id": "log_0001",
        "trace_id": "trace_20260520_0001",
        "event_type": "tool_log",
        "module": "MockAPIService",
        "level": "info",
        "payload": {
          "tool_name": "get_restaurant_status",
          "poi_id": "poi_light_food_003",
          "user_visible_message": "已检查轻食餐厅余位。"
        },
        "visible_to_user": true,
        "created_at": "2026-05-20T13:00:08+08:00"
      }
    ],
    "page_info": { "page_size": 50, "next_page_token": null, "has_more": false }
  },
  "error": null
}
```

### 15.4GET /api/v1/plans/{plan_id}/debug

#### 接口定位

返回计划调试视图，包括Schema校验结果、Verifier检查、ToolAction完整状态、Recovery结果。仅Debug/评委模式。

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "plan_id": "plan_20260520_0001",
    "schema_validation": {
      "valid": true,
      "errors": []
    },
    "verifier_result": {
      "status": "warning",
      "score": 0.82,
      "failed_checks": [],
      "warnings": ["restaurant_capacity_medium"]
    },
    "tool_actions": [
      {
        "action_id": "act_reserve_0001",
        "type": "reserve_restaurant",
        "status": "pending",
        "payload": { "arrival_time": "2026-05-20T15:55:00+08:00", "party_size": 3 },
        "idempotency_key": "idem_act_reserve_0001",
        "created_at": "2026-05-20T13:00:09+08:00",
        "updated_at": "2026-05-20T13:00:09+08:00"
      }
    ],
    "recovery_results": [],
    "debug_visibility_note": "不包含Prompt、API Key、LLM推理链、高敏MemoryCandidate。"
  },
  "error": null
}
```

---

## 16.Benchmark APIs

Benchmark接口标注为P1/P2预留，不阻塞P0主链路。

### 16.1评估指标

| 指标 | 说明 |
|---|---|
| intent_accuracy | 场景和意图识别准确率 |
| constraint_recall | 用户约束召回率 |
| tool_correctness | 工具调用是否正确 |
| verifier_validity | Verifier检查是否有效 |
| recovery_success | Recovery是否成功恢复 |
| consensus_quality | 共识结果是否压缩冲突且可接受 |
| privacy_compliance | LifeMemory是否符合隐私规则 |

### 16.2GET /api/v1/benchmarks/samples

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_bench_0001",
  "data": {
    "items": [
      {
        "sample_id": "bench_family_001",
        "scenario": "family_parent_child",
        "input_text": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
        "expected_constraints": {
          "party_size": 3,
          "child_friendly_required": true,
          "dietary_preference": ["low_calorie"],
          "distance_preference": "nearby",
          "queue_tolerance": "low"
        },
        "expected_tools": [
          "search_poi",
          "search_restaurant",
          "get_poi_status",
          "get_restaurant_status",
          "estimate_route",
          "get_weather"
        ],
        "expected_verifier_checks": [
          "time_feasibility",
          "distance_constraint",
          "restaurant_capacity",
          "activity_ticket",
          "participant_constraints"
        ],
        "expected_recovery": {
          "trigger": "restaurant_full",
          "strategy": "replace_restaurant"
        },
        "privacy_expectations": [
          "配偶减脂属于中敏信息，需要确认后写入长期记忆",
          "不得推断健康诊断"
        ],
        "scoring_weights": {
          "intent_accuracy": 0.2,
          "constraint_recall": 0.25,
          "tool_correctness": 0.2,
          "verifier_validity": 0.2,
          "privacy_compliance": 0.15
        },
        "tags": ["family", "child", "low_calorie", "nearby"]
      }
    ],
    "page_info": { "page_size": 20, "next_page_token": null, "has_more": false }
  },
  "error": null
}
```

### 16.3POST /api/v1/benchmarks/run

#### Request Body

| 字段 | 类型 | 必填 | 示例 |
|---|---|---:|---|
| sample_ids | string[] | 否 | ["bench_family_001"] |
| metrics | string[] | 否 | ["intent_accuracy", "constraint_recall"] |
| mode | string | 否 | quick |

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_bench_0001",
  "data": {
    "run_id": "benchrun_0001",
    "status": "running",
    "sample_count": 1,
    "created_at": "2026-05-20T19:00:00+08:00"
  },
  "error": null
}
```

### 16.4GET /api/v1/benchmarks/runs/{run_id}

#### 成功响应示例

```json
{
  "success": true,
  "trace_id": "trace_bench_0001",
  "data": {
    "run_id": "benchrun_0001",
    "status": "completed",
    "metrics": {
      "intent_accuracy": 1.0,
      "constraint_recall": 0.92,
      "tool_correctness": 0.88,
      "verifier_validity": 0.9,
      "recovery_success": 0.85,
      "consensus_quality": 0.82,
      "privacy_compliance": 1.0
    },
    "completed_at": "2026-05-20T19:03:00+08:00"
  },
  "error": null
}
```

---

## 17.前端页面与API调用关系

| 页面 | 首屏调用 | 用户动作 | 后续API | P0 |
|---|---|---|---|---:|
| 首页/一句话输入页 | 无 | 点击开始导航 | POST /plans/create | 是 |
| 计划生成中页面 | POST /plans/create进行中 | 取消/重试 | POST /plans/create | 是 |
| 计划结果页 | GET /plans/{plan_id}、GET /plans/{plan_id}/trace | 确认执行 | POST /plans/{plan_id}/execute | 是 |
| 计划结果页 | GET /plans/{plan_id} | 刷新窗口 | POST /plans/{plan_id}/refresh-window | 是 |
| 计划结果页 | GET /plans/{plan_id} | 发起朋友投票 | POST /consensus/create | 是 |
| 朋友投票页 | GET /vote-pages/{vote_page_id} | 提交投票 | POST /consensus/{consensus_session_id}/vote | 是 |
| 共识进度页 | GET /consensus/{consensus_session_id} | 生成共识方案 | POST /consensus/{consensus_session_id}/finalize | 是 |
| 共识结果页 | GET /consensus/{consensus_session_id}/summary | 确认执行 | POST /plans/{final_plan_id}/execute | 是 |
| 执行结果页 | GET /executions/{execution_id}或GET /plans/{plan_id} | 查看恢复详情 | GET /plans/{plan_id}/trace | 是 |
| 低打扰反馈页 | GET /feedback/questions?plan_id=... | 提交反馈/跳过 | POST /feedback | 是 |
| LifeMemory管理页 | GET /memory、GET /memory/candidates | 确认/忽略/编辑/删除 | Memory APIs | P1 |
| Debug页 | GET /traces/{trace_id}/events、GET /plans/{plan_id}/debug | 复现错误 | Debug APIs | P1/评委模式 |

---

## 18.状态机与API触发关系

### 18.1PlanContract状态流转

```text
draft
→ generated
→ verifying
→ verified
→ executable
→ confirmed
→ executing
→ completed / recovered / failed / expired / cancelled
```

| 状态变化 | 触发API | 说明 |
|---|---|---|
| 无Plan → draft | POST /plans/create | 创建plan_id |
| draft → generated | POST /plans/create | Agent生成草案 |
| generated → verifying | POST /plans/create或POST /plans/{id}/verify | 进入Verifier |
| verifying → verified | Verifier内部 | 关键检查通过 |
| verified → executable | POST /plans/create或verify | 生成可执行窗口 |
| executable → expired | GET/execute前检查 | expire_at过期 |
| expired → executable | POST /plans/{id}/refresh-window | 刷新窗口成功 |
| executable → confirmed | POST /plans/{id}/execute | 用户确认 |
| confirmed → executing | POST /plans/{id}/execute | Executor开始 |
| executing → completed | POST /plans/{id}/execute | 全部关键动作成功 |
| executing → recovered | POST /plans/{id}/execute或recover | 原计划完成版本交接，RecoveryResult.updated_plan_id指向新计划 |
| recovered → completed | Executor继续执行 | 基于updated_plan_id对应的新PlanContract继续执行替换动作 |
| executing → failed | execute | 不可恢复失败 |
| 任意可取消状态 → cancelled | P1取消接口 | P0可不做 |

### 18.2ToolAction状态流转

```text
pending
→ running
→ success / failed
→ recovered / skipped
```

| 状态变化 | 触发模块 | 说明 |
|---|---|---|
| pending → running | Executor | 开始执行MockAPI |
| running → success | MockAPI | 返回成功凭证 |
| running → failed | MockAPI | 返回错误码 |
| failed → recovered | RecoveryService | 生成替代动作 |
| failed → skipped | Executor | 非关键动作跳过 |

### 18.3ConsensusSession状态流转

```text
created
→ collecting
→ closed / expired
→ finalized
```

| 状态变化 | 触发API | 说明 |
|---|---|---|
| 无 → created | POST /consensus/create | 创建会话 |
| created → collecting | POST /consensus/create | 分享页可访问 |
| collecting → closed | POST /consensus/{id}/finalize | 手动结束 |
| collecting → expired | 系统时间 | 超过expire_at |
| closed/expired → finalized | POST /consensus/{id}/finalize | 生成最终方案 |

### 18.4LifeMemory状态流转

```text
candidate
→ pending_confirmation
→ enabled / ignored / deleted
→ disabled / expired
```

| 状态变化 | 触发API | 说明 |
|---|---|---|
| 无 → candidate | POST /feedback或plans/create内部 | 生成候选 |
| candidate → pending_confirmation | LifeMemoryService | 中敏或需确认 |
| pending_confirmation → enabled | POST /memory/candidates/{id}/confirm | 用户确认 |
| pending_confirmation → ignored | POST /memory/candidates/{id}/ignore | 用户忽略 |
| enabled → disabled | PATCH /memory/{id}或disable | 用户禁用 |
| enabled/disabled → deleted | DELETE /memory/{id} | 用户删除 |
| enabled → expired | 系统清理 | TTL到期 |

---

## 19.联调样例

### 19.1家庭亲子计划创建：POST /api/v1/plans/create

#### 请求

```json
{
  "input_text": "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
  "user_location": { "poi_id": "poi_home_anchor_001" },
  "preferred_start_time": "2026-05-20T13:30:00+08:00",
  "preferred_end_time": "2026-05-20T18:00:00+08:00",
  "scenario_hint": "family_parent_child",
  "use_memory": true
}
```

#### 期望响应要点

| 字段 | 验收 |
|---|---|
| trace_id | `trace_`前缀 |
| plan_id | `plan_`前缀 |
| user_goal.scenario | `family_parent_child` |
| timeline | 至少包含transport、activity、restaurant |
| PlanStep | 每个节点含`duration_minutes`、`booking_required`、`reservation_required` |
| ToolAction | 每个动作含`payload`、`idempotency_key`、`created_at`、`updated_at` |
| RouteEstimate | 含`route_id`、起终点、交通方式、距离、时长、traffic_level、confidence、source、updated_at |
| backup_plans | 使用`backup_plan_id` |

---

### 19.2家庭亲子确认执行：POST /api/v1/plans/{plan_id}/execute

#### 请求

```json
{
  "confirmed": true,
  "allow_auto_recovery": true,
  "allow_message_mock_send": true,
  "confirmation_note": "按这个安排"
}
```

Header：

```http
X-Idempotency-Key: idem_exec_family_0001
```

#### 期望响应要点

| 字段 | 验收 |
|---|---|
| execution_id | `exec_`前缀 |
| execution_result.status | success/recovered/failed/partial |
| vouchers | 每个凭证带`mock_only:true` |
| active_plan_id | 指向当前应展示或继续执行的PlanContract |
| active_plan_contract.status | completed、executable或recovered，取决于是否触发版本化Recovery |
| action_results | 每个动作有状态 |

---

### 19.3餐厅满座触发Recovery：NO_TABLE_AVAILABLE → RecoveryResult.updated_plan_id → 新PlanContract

#### Mock失败注入

Debug Mock状态：

```json
{
  "poi_id": "poi_light_food_003",
  "failure_injection": {
    "enabled": true,
    "on_execute": "NO_TABLE_AVAILABLE"
  }
}
```

#### 期望RecoveryResult

```json
{
  "recovery_id": "rec_0001",
  "trigger": "NO_TABLE_AVAILABLE",
  "status": "success",
  "original": {
    "step_id": "step_0003",
    "poi_id": "poi_light_food_003",
    "poi_name": "轻盈厨房"
  },
  "replacement": {
    "step_id": "step_0003",
    "poi_id": "poi_light_food_007",
    "poi_name": "谷物星球轻食"
  },
  "diff": {
    "route_extra_minutes": 4,
    "budget_delta": 0,
    "queue_delta_minutes": -8,
    "distance_delta_km": 0.6,
    "time_shift_minutes": 3,
    "diet_match": "same",
    "scenario_match": "same",
    "user_visible_summary": "路线多4分钟，预算不变，排队风险更低。"
  },
  "updated_plan_id": "plan_20260520_0001_r1",
  "verifier_result": {
    "status": "pass",
    "score": 0.86,
    "failed_checks": [],
    "warnings": []
  },
  "user_explanation": "原餐厅4人位已满，已切换到同区域低卡轻食餐厅，路线增加4分钟，预算基本不变。",
  "created_at": "2026-05-20T13:20:10+08:00"
}
```

---

### 19.4朋友局创建投票：POST /api/v1/consensus/create

#### 请求

```json
{
  "candidate_plan_ids": ["plan_candidate_a", "plan_candidate_b", "plan_candidate_c"],
  "title": "周六下午朋友局",
  "expire_at": "2026-05-20T14:00:00+08:00",
  "allow_anonymous": true
}
```

#### 期望响应

```json
{
  "consensus_session_id": "cs_0001",
  "vote_page_id": "vpage_0001",
  "plan_group_id": "plangrp_0001",
  "share_url": "https://demo.lifepilot.local/vote/vpage_0001",
  "candidate_plan_ids": ["plan_candidate_a", "plan_candidate_b", "plan_candidate_c"],
  "status": "collecting"
}
```

---

### 19.5朋友提交投票：POST /api/v1/consensus/{consensus_session_id}/vote

#### 请求：只反选也合法

```json
{
  "participant": {
    "participant_name": "朋友B",
    "anonymous": false,
    "role": "friend"
  },
  "liked_plan_ids": [],
  "disliked_plan_ids": ["plan_candidate_a"],
  "budget_max": 100,
  "walking_tolerance": "low",
  "queue_tolerance": "low",
  "free_text": "我不想走太多。"
}
```

#### 期望

提交成功，生成`vote_id`，且不会因`liked_plan_ids`为空失败。

---

### 19.6生成共识方案：POST /api/v1/consensus/{consensus_session_id}/finalize

#### 请求

```json
{
  "close_voting": true,
  "force_regenerate": false,
  "min_vote_count_policy": "allow_low_vote_count"
}
```

#### 期望响应要点

| 字段 | 验收 |
|---|---|
| consensus_session_id | `cs_`前缀 |
| vote_page_id | `vpage_`前缀 |
| plan_group_id | `plangrp_`前缀 |
| consensus_summary | 含支持、反对、冲突、共识约束、解释 |
| final_plan_contract | 状态为`executable`或`verified`，并重新Verifier |

---

### 19.7反馈生成MemoryCandidate：POST /api/v1/feedback

#### 请求

```json
{
  "plan_id": "plan_20260520_0001",
  "execution_id": "exec_20260520_0001",
  "rating": "not_good",
  "selected_options": ["queue_too_long"],
  "free_text": "排队还是太久了。",
  "skipped": false
}
```

#### 期望响应

```json
{
  "feedback_id": "fb_0001",
  "plan_id": "plan_20260520_0001",
  "accepted": true,
  "skipped": false,
  "memory_candidates": [
    {
      "candidate_id": "memcand_0001",
      "source_trace_id": "trace_20260520_0001",
      "content": "用户在家庭亲子场景中对排队较敏感。",
      "sensitivity": "low",
      "requires_confirmation": true,
      "status": "pending_confirmation"
    }
  ]
}
```

---

### 19.8Mock餐厅状态查询：GET /api/v1/mock/restaurants/{poi_id}/status

#### 请求

```text
GET /api/v1/mock/restaurants/poi_light_food_003/status?arrival_time=2026-05-20T15:55:00+08:00&party_size=3
```

#### 期望响应

```json
{
  "poi_id": "poi_light_food_003",
  "available": true,
  "open_status": "open",
  "available_tables": 2,
  "queue_minutes": 12,
  "reservation_available": true,
  "risk_level": "medium",
  "source": "mock_api",
  "mock_only": true,
  "updated_at": "2026-05-20T13:00:00+08:00",
  "expire_at": "2026-05-20T13:18:00+08:00"
}
```

---

## 20.接口测试与验收标准

### 20.1通用验收

| 编号 | 验收项 | 标准 |
|---|---|---|
| API-G-01 | 标准响应 | 所有接口返回`success/trace_id/data/error` |
| API-G-02 | 错误不泄漏 | 不返回底层异常堆栈、Prompt、API Key |
| API-G-03 | 时间格式 | 所有时间为ISO 8601 |
| API-G-04 | ID前缀 | 所有ID符合03定义前缀 |
| API-G-05 | Mock标识 | Mock状态、凭证、口碑均显式标Mock |
| API-G-06 | trace贯穿 | 写操作必须有trace_id或后端创建trace_id |
| API-G-07 | 幂等执行 | execute重复调用不重复生成凭证 |

### 20.2Plan验收

| 编号 | 验收项 | 标准 |
|---|---|---|
| PLAN-01 | 创建计划 | 返回PlanContract且Schema合法 |
| PLAN-02 | 时间线 | timeline非空，order连续，时间不重叠 |
| PLAN-03 | PlanStep必填 | 含`duration_minutes/booking_required/reservation_required` |
| PLAN-04 | ToolAction必填 | 含`payload/idempotency_key/created_at/updated_at` |
| PLAN-05 | 可执行窗口 | 含`window_minutes/confidence/expire_at/reasons/calculated_from/display_message` |
| PLAN-06 | BackupPlan | 使用`backup_plan_id`，不使用`plan_id`冒充 |
| PLAN-07 | 验证结果 | VerifierResult.status合法 |

### 20.3Execution/Recovery验收

| 编号 | 验收项 | 标准 |
|---|---|---|
| EXE-01 | 动作顺序 | 按depends_on执行 |
| EXE-02 | 凭证 | Mock凭证带`mock_only:true` |
| EXE-03 | 满座恢复 | `NO_TABLE_AVAILABLE`触发Recovery |
| EXE-04 | 恢复结构 | RecoveryResult使用`original/replacement/diff` |
| EXE-05 | 恢复复验 | Recovery后必须重新Verifier |
| EXE-06 | 幂等 | 重复execute不重复预约 |

### 20.4Consensus验收

| 编号 | 验收项 | 标准 |
|---|---|---|
| CON-01 | 创建会话 | 返回`cs_`、`vpage_`、`plangrp_` |
| CON-02 | 分享入口 | URL使用`vote_page_id` |
| CON-03 | 投票低摩擦 | 只喜欢、只反选、只free_text均可 |
| CON-04 | 投票冲突 | 喜欢和反选重叠返回`CONSENSUS_VOTE_INVALID` |
| CON-05 | finalize | 生成ConsensusSummary和final_plan_contract |
| CON-06 | 复验 | final_plan_contract重新Verifier |

### 20.5LifeMemory验收

| 编号 | 验收项 | 标准 |
|---|---|---|
| MEM-01 | 候选生成 | 反馈后可生成MemoryCandidate |
| MEM-02 | 中敏确认 | 中敏信息默认pending_confirmation |
| MEM-03 | 高敏不保存 | 高敏默认不保存，返回隐私保护提示 |
| MEM-04 | P0用户可控 | 支持候选展示、跳过/忽略、确认接口预留或最小实现 |
| MEM-05 | P1完整管理 | 编辑、删除、关闭个性化、下次规划调用属于P1 |
| MEM-06 | 删除不恢复 | P1删除后不得静默恢复 |

### 20.6MockAPI验收

| 编号 | 验收项 | 标准 |
|---|---|---|
| MOCK-01 | POI搜索 | 返回`mock_only:true`的POI |
| MOCK-02 | 餐厅状态 | 返回余位、排队、订座状态 |
| MOCK-03 | 路线估计 | RouteEstimate字段完整 |
| MOCK-04 | 天气 | 返回户外风险 |
| MOCK-05 | 执行动作 | 返回Mock凭证 |
| MOCK-06 | 口碑Mock | SocialSignal带`is_mock:true`和`source_type` |
| MOCK-07 | 下单模拟 | `/mock/orders/create`返回Mock订单凭证，不触发真实支付 |

---

## 21.P0实现清单

### 21.1后端P0接口

| 模块 | 必做接口 |
|---|---|
| Plan | create、get、verify、execute、recover、refresh-window、trace |
| Consensus | create、get、vote-page、vote、finalize、summary |
| Executor | execute内置；可选executions读取接口 |
| MockAPI | POI搜索、餐厅搜索、POI状态、餐厅状态、路线、天气、活动预约、餐厅订座、下单模拟、消息发送 |
| Feedback | questions、submit、skip |
| LifeMemory | candidates、confirm预留或最小实现、ignore预留或最小实现 |
| Trace | plan trace、trace events简化版 |

### 21.2前端P0页面

| 页面 | 必做能力 |
|---|---|
| 首页/一句话输入页 | 输入自然语言、快捷示例、隐私提示 |
| 计划生成中页面 | 展示规划步骤和工具调用进度 |
| 计划结果页 | 目标理解、时间线、路线、预算、可执行窗口、风险、PlanB、确认执行 |
| 朋友投票页 | 候选卡片、多选、反选、预算、时间偏好、步行/排队容忍、free_text |
| 共识结果页 | 投票统计、冲突说明、最终方案、群聊消息 |
| 执行结果页 | 动作状态、Mock凭证、Recovery Diff |
| 低打扰反馈页 | 最多2题、可跳过、候选记忆提示 |

### 21.3Agent/Domain P0能力

| 能力 | P0要求 |
|---|---|
| IntentParser | 识别朋友局、家庭亲子、纪念日 |
| ConstraintExtractor | 抽取人数、时间、预算、距离、饮食、步行、排队、情绪目标 |
| PlanGenerator | 输出DraftPlan，不直接编造状态 |
| PlanContractBuilder | 规范化为PlanContract并Schema校验 |
| Verifier | 检查时间、营业、距离、预算、余位、排队、天气、动作完整性 |
| Executor | 按ToolAction执行Mock动作 |
| Recovery | 支持餐厅满座、活动满员的局部替换 |
| Consensus | 收集投票并生成共识约束和最终方案 |
| LifeMemory | P0生成候选并执行隐私规则；完整管理、关闭个性化和下次规划读取为P1 |

---

## 22.P1/P2扩展接口

### 22.1P1扩展

| 能力 | 接口/说明 |
|---|---|
| LifeMemory完整管理页 | 完整实现GET/PATCH/DELETE/enable/disable |
| SocialSignalRadar Mock | GET /mock/social-signals/{poi_id}进入计划展示 |
| Benchmark基础评测 | Benchmark APIs可运行 |
| 可执行窗口增强 | 引入更多风险来源和动态窗口变化 |
| 更多Recovery类型 | 天气变化、朋友迟到、预算冲突 |
| Trace评委模式 | 更完整但脱敏的工具链展示 |

### 22.2P2扩展

| 能力 | 接口/说明 |
|---|---|
| PlanReward模型 | 可新增`POST /api/v1/plans/{plan_id}/score` |
| Goal-aware POI Reranker | 可在Mock搜索结果增加`rank_reason` |
| 多模态反馈 | 可新增`POST /api/v1/feedback/photos`，但P0不做 |
| 更多场景模板 | city_light_explore、exam_relax、rainy_day等 |
| 原生App | 当前不做，仅Web Demo |

---

## 23.不做什么与安全边界

1. 不做真实支付、真实下单、真实退款。
2. 不做真实短信、真实微信、真实群聊发送。
3. 不做真实餐厅订座、真实票务锁定。
4. 不做真实小红书/抖音/点评爬取。
5. 不伪装Mock数据为真实平台数据。
6. 不做全城POI覆盖，P0只做固定数字孪生区域。
7. 不让LLM直接确认余位、票务、路线、天气或执行成功。
8. 不暴露底层Prompt、LLM推理链、API Key。
9. 不把LifeMemory写成偷偷画像。
10. 不自动保存高敏信息。
11. 不让LifeMemory覆盖用户当次明确表达。
12. 不让Recovery改变核心目标；只能局部修复。
13. 不把BackupPlan当成完整PlanContract。
14. 不用早期ID样例作为API契约。

---

## 24.附录：字段命名、ID前缀、错误码速查表

### 24.1ID前缀速查

| 字段 | 前缀 | 示例 |
|---|---|---|
| plan_id | `plan_` | plan_20260520_0001 |
| trace_id | `trace_` | trace_20260520_0001 |
| plan_group_id | `plangrp_` | plangrp_0001 |
| vote_page_id | `vpage_` | vpage_0001 |
| consensus_session_id | `cs_` | cs_0001 |
| vote_id | `vote_` | vote_0001 |
| step_id | `step_` | step_0001 |
| poi_id | `poi_` | poi_light_food_003 |
| action_id | `act_` | act_reserve_0001 |
| execution_id | `exec_` | exec_0001 |
| recovery_id | `rec_` | rec_0001 |
| memory_id | `mem_` | mem_0001 |
| candidate_id | `memcand_` | memcand_0001 |
| route_id | `route_` | route_0001 |
| log_id | `log_` | log_0001 |

#### API层新增ID前缀

以下ID为HTTP/API层新增对象，允许在`04_api_contract.md`中定义；它们不属于`03_data_schema.md`冻结的核心领域ID，但必须遵守统一前缀规则。

| 字段 | 前缀 | 示例 | 说明 |
|---|---|---|---|
| feedback_id | `fb_` | fb_0001 | 低打扰反馈提交记录 |
| question_id | `q_` | q_0001 | 反馈问题 |
| run_id | `benchrun_` | benchrun_0001 | Benchmark运行记录 |

### 24.2核心对象字段速查

#### PlanStep必填

```text
step_id
order
type
title
start_time
end_time
duration_minutes
booking_required
reservation_required
status
```

#### ToolAction必填

```text
action_id
plan_id
step_id
type
payload
status
retry_count
idempotency_key
user_visible
created_at
updated_at
```

#### RouteEstimate必填

```text
route_id
origin_poi_id
destination_poi_id
transport_mode
distance_km
duration_minutes
traffic_level
confidence
source
updated_at
```

#### BackupPlan必填

```text
backup_plan_id
trigger
description
expected_diff
priority
status
```

可选但推荐：

```text
replace_step_id
original_poi_id
new_poi_id
verifier_result
```

#### RecoveryResult必填

```text
recovery_id
trigger
status
original
replacement
diff
verifier_result
user_explanation
created_at
```

### 24.3状态速查

#### PlanContract.status

```text
draft
generated
verifying
verified
executable
expired
confirmed
executing
recovered
completed
failed
cancelled
```

#### ToolAction.status

```text
pending
running
success
failed
recovered
skipped
```

#### ConsensusSession.status

```text
created
collecting
closed
finalized
expired
```

#### LifeMemory.status

```text
candidate
pending_confirmation
enabled
disabled
deleted
expired
ignored
```

### 24.4错误码速查

#### 领域错误码

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
```

#### API层通用错误码

```text
BAD_REQUEST
UNAUTHORIZED_DEMO_USER
RESOURCE_NOT_FOUND
IDEMPOTENCY_CONFLICT
RATE_LIMITED
INTERNAL_ERROR
```

### 24.5Legacy字段禁止清单

| 禁止字段/写法 | 替代字段/写法 |
|---|---|
| group_0001 | plangrp_0001 |
| vote_page_0001 | vpage_0001 |
| 泛化session_id | consensus_session_id |
| BackupPlan.plan_id | backup_plan_id |
| RecoveryResult.original_step_id | original.step_id |
| RecoveryResult.original_poi | original |
| RecoveryResult.new_poi | replacement |
| RecoveryResult.changes | diff |
| 非ISO时间如`2026-05-20 13:00:00` | `2026-05-20T13:00:00+08:00` |

---

## 25.结论

`04_api_contract.md`将LifePilot的产品愿景、页面需求、系统架构和数据Schema收束为一组可联调的HTTP契约。前端只需要根据页面调用对应API，后端只需要围绕Controller、Domain Service、Agent Orchestrator和MockAPI实现契约，测试同学可以按状态机、错误码、幂等性和联调样例逐项验收。

最终P0交付的核心判断标准只有一个：

> LifePilot能否把一句自然语言目标，稳定转化为一个当前可执行、可验证、可恢复、可确认的PlanContract，并通过Mock执行闭环展示出来。

### 25.1 2026-05-23追加：受控LLM接口设置契约

为支持本地Qwen不可用时切换到DeepSeek，新增运行时设置接口。该接口仅用于开发/评委联调，不进入普通用户规划流程，也不得返回底层Prompt、推理链或明文凭证。

#### GET `/api/v1/settings/llm`

返回当前后端运行时受控LLM配置的脱敏投影。

响应`data`字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `provider` | string | 当前提供方，P0支持`deepseek`、`qwen` |
| `enabled` | boolean | 当前提供方是否启用 |
| `base_url` | string | OpenAI-compatible Base URL |
| `model` | string | 模型名 |
| `temperature` | number | 非思考模式采样温度 |
| `max_tokens` | number | 单次输出上限 |
| `timeout` | number | 请求超时秒数 |
| `retry` | number | 重试次数 |
| `enable_thinking` | boolean | 是否启用思考模式；普通Trace仍不得展示推理链 |
| `credential_configured` | boolean | 是否已配置访问凭证 |
| `credential_mask` | string | 脱敏凭证，例如`sk-***4ed2` |
| `available_providers` | array | 可切换提供方及默认`base_url`、`model` |

#### PATCH `/api/v1/settings/llm`

更新当前后端进程内的受控LLM配置，为后续Provider切换预留统一接口。

请求体字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---:|---:|---|
| `provider` | string | 否 | `deepseek`或`qwen` |
| `enabled` | boolean | 否 | 是否启用 |
| `base_url` | string | 否 | OpenAI-compatible Base URL |
| `model` | string | 否 | 模型名 |
| `credential` | string | 否 | 访问凭证；留空不修改；响应不得回显 |
| `temperature` | number | 否 | 非思考模式采样温度 |
| `max_tokens` | integer | 否 | 单次输出上限 |
| `timeout` | number | 否 | 请求超时秒数 |
| `retry` | integer | 否 | 重试次数 |
| `enable_thinking` | boolean | 否 | 是否启用思考模式 |

安全规则：

1. 明文`credential`只允许进入后端运行时内存，不写入Trace和普通响应。
2. 响应只返回`credential_configured`和`credential_mask`。
3. 受控LLM仍只能辅助理解、草案、解释和文案，不得确认余位、票务、路线、天气、执行成功或Verifier结果。
## 31. 2026-05-24追加：创建计划的时间锚点字段

为修复“首页模拟当前时间被误当作计划出发时间”的问题，`POST /api/v1/plans/create`在不改变既有路径和标准响应的前提下，新增两个可选请求字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `current_time` | ISO datetime string | Demo/Mock环境下的“当前时间锚点”，用于解释“今天下午、周末下午、今晚”等相对时间表达。它不是计划开始时间。 |
| `preferred_duration_hours` | number | 用户可规划时长偏好，后端会限制在短时活动合理范围内，用于生成下午4-6小时等窗口。 |

兼容规则：

1. 如果同时传入`preferred_start_time`和`preferred_end_time`，后端视为用户显式锁定计划窗口，优先级高于`current_time`。
2. 如果只传`current_time`，后端必须根据自然语言时间表达推导`time_window.start_time/end_time`。
3. 普通前端不得把“当前时间”写入`preferred_start_time`，否则会绕过Agent时间理解。
4. `PlanContract.time_window`仍是唯一对外计划窗口；`constraints.planning_anchor_time/time_intent`只用于审计和解释，不新增业务API路径。

示例：

```json
{
  "input_text": "周末下午我想去一个人散散心，顺便喝杯酒。",
  "current_time": "2026-05-23T18:00:00+08:00",
  "preferred_duration_hours": 4,
  "user_location": {"label": "杭州金沙湖地铁站", "area": "金沙湖"}
}
```

期望窗口：

```json
{
  "start_time": "2026-05-24T15:00:00+08:00",
  "end_time": "2026-05-24T19:00:00+08:00"
}
```

## 32. 2026-05-24追加：投票页候选摘要补充

`GET /api/v1/vote-pages/{vote_page_id}`的`candidate_plans`可返回更完整的`PlanSummary`投影：

| 字段 | 说明 |
| --- | --- |
| `goal_summary` | 候选方案目标摘要 |
| `status` | 候选PlanContract当前状态 |
| `score` | Verifier分数投影 |
| `timeline_summary` | 用户可见的核心节点和时间摘要 |
| `budget.estimated_total` | 总预算 |
| `budget.price_per_person` | 人均预算 |
| `executable_window` | 可执行窗口摘要 |

投票仍提交到`POST /api/v1/consensus/{consensus_session_id}/vote`。预算、步行容忍、排队容忍和free text会在finalize时压缩为共识约束，前端只做预览，不直接改写PlanContract。

## 33. 2026-05-24追加：多节点短时活动约束投影

为支持“安排4-5个活动，13:00出发，22:00回来”这类长窗口自然语言目标，`POST /api/v1/plans/create`响应中的`PlanContract.constraints`补充以下用户可解释字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `target_stop_count` | integer/null | 用户希望安排的POI节点上限，例如“4-5个活动”取5；仅表示用户目标，不强制包含transport节点。 |
| `target_stop_count_range` | array/null | 用户表达的活动数量范围，例如`[4,5]`。 |
| `planning_anchor_time` | ISO datetime string | 自然语言时间解析锚点，来自`current_time`或系统当前Mock时间。 |
| `time_intent` | string | 时间窗口来源，例如`explicit_text_window`、`afternoon_window`、`deadline_anchored`。 |

兼容规则：

1. `PlanContract.timeline`仍是普通前端唯一应渲染的行程列表；不得把内部候选、`DraftPlan`或`itinerary_nodes`作为用户可见API返回。
2. `target_stop_count_range`只统计真实POI步骤，`transport`步骤不计入“活动数量”。
3. 预算校验仍以`budget_max/budget_max_per_person`为准；当用户要求4-5个纪念日节点时，后端可把“适中预算”解释为长窗口约会预算，而不是单餐预算。
4. 餐厅余位、排队、活动余票必须通过既有Mock状态/执行接口返回，不能由LLM或前端自行编造。

示例约束投影：

```json
{
  "time_window": {
    "start_time": "2026-05-23T13:00:00+08:00",
    "end_time": "2026-05-23T22:00:00+08:00"
  },
  "constraints": {
    "target_stop_count": 5,
    "target_stop_count_range": [4, 5],
    "budget_max_per_person": 400,
    "time_intent": "explicit_text_window"
  }
}
```
