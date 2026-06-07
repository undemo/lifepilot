# 05_agent_workflow.md

## 1.文档信息

| 项目     | 内容                                                                                                        |
| ------ | --------------------------------------------------------------------------------------------------------- |
| 文档名称   | 05_agent_workflow.md                                                                                      |
| 项目名称   | LifePilot                                                                                                 |
| 产品定位   | 生活时间导航Agent                                                                                               |
| 文档类型   | Agent工作流与编排规范                                                                                             |
| 文档版本   | v0.1                                                                                                      |
| 面向读者   | Agent、后端、前端、Mock数据、测试、评委                                                                                  |
| 核心目标   | 规定LifePilot从自然语言目标到PlanContract、Verifier、Executor、Recovery、Consensus、LifeMemory、TraceLog的内部编排流程           |
| 当前范围   | 比赛Demo阶段，优先支持P0闭环：家庭亲子、朋友局共识、纪念日情绪导航                                                                      |
| 契约基准   | 03_data_schema.md、04_api_contract.md                                                                      |
| 默认技术假设 | React/Next.js Web Demo；Backend API Service可使用Node.js或Python FastAPI；Demo存储使用JSON文件或SQLite，后续可扩展PostgreSQL |
| 默认时区   | Asia/Shanghai                                                                                             |
| 时间格式   | ISO 8601，例如`2026-05-20T13:00:00+08:00`                                                                    |

LifePilot的统一表达为：

```text
高德导航的是一段路，LifePilot导航的是一段生活时间。
```

本文件只描述Agent内部如何编排，不重新定义03中的领域Schema，不重新定义04中的HTTP契约。

---

## 2.文档目标与边界

### 2.1文档目标

`05_agent_workflow.md`回答以下问题：

| 问题                           | 本文档回答方式                                                    |
| ---------------------------- | ---------------------------------------------------------- |
| 一句话输入后，Agent内部怎么运行           | 定义主编排链路和各子模块步骤                                             |
| 哪些步骤允许LLM参与                  | 单独定义LLM使用边界                                                |
| 哪些步骤必须由规则、MockAPI、Verifier决定 | 在模块职责和验收标准中强制约束                                            |
| PlanContract如何从草案变成可执行对象     | 定义DraftPlan、PlanBuildCandidate、Verifier、PlanContractBuilder、Full SchemaValidator链路 |
| Verifier如何作为执行前闸门            | 定义检查项、状态、Recovery触发规则                                      |
| Recovery如何局部修复               | 采用版本化Recovery，生成新的完整PlanContract                           |
| 朋友局Consensus如何形成共识约束         | 定义投票、实时统计、finalize、重新生成最终PlanContract流程                    |
| LifeMemory何时读取、何时写候选         | 区分P0候选闭环与P1完整闭环                                            |
| LoggingService如何记录Agent每一步   | 定义TraceLog事件类型、可见性和脱敏规则                                    |
| 测试如何验收Agent行为                | 给出模块验收标准、端到端样例和错误处理标准                                      |

### 2.2文档边界

本文档不做以下事情：

| 不做                   | 原因                                    |
| -------------------- | ------------------------------------- |
| 不重新写PRD              | 页面、用户场景、交互范围以01_prd.md为准              |
| 不重新写系统架构             | 模块边界、服务分层以02_system_architecture.md为准 |
| 不复制完整JSONSchema      | 字段、必填项、枚举以03_data_schema.md为准         |
| 不复制完整API契约           | API路径、请求响应、幂等规则以04_api_contract.md为准  |
| 不定义真实交易能力            | P0只做Mock执行                            |
| 不定义真实第三方爬取           | SocialSignal只能是Mock或扩展能力              |
| 不把内部草案当成PlanContract | DraftPlan仅为Agent内部中间态                 |
| 不暴露Prompt和LLM推理链     | Trace投影不得包含底层Prompt、推理链、API Key       |

---

## 3.来源文档与契约优先级

### 3.1来源文档

| 优先级 | 来源                        | 05中的使用方式                                                                                           |
| --: | ------------------------- | -------------------------------------------------------------------------------------------------- |
|   1 | 03_data_schema.md         | 字段命名、ID前缀、JSONSchema、状态枚举、TraceLog、PlanContract、RecoveryResult、Consensus、LifeMemory、ToolAction最终权威 |
|   2 | 04_api_contract.md        | API路径、HTTP响应、幂等键、用户可见Trace投影、接口边界最终权威                                                              |
|   3 | 02_system_architecture.md | Agent模块、服务边界、状态机、工程分层、运行链路基础                                                                       |
|   4 | 01_prd.md                 | P0/P1/P2功能范围、页面交互、产品验收标准                                                                           |
|   5 | 00_project_vision.md      | 产品定位、核心隐喻、创新点、Mock边界、不做什么                                                                          |

### 3.2冲突处理规则

| 冲突类型               | 处理规则                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------- |
| 01/02早期示意与03字段冲突   | 以03为准                                                                                 |
| 02早期API路径与04冲突     | 以04的`/api/v1`路径为准                                                                     |
| Recovery字段新旧冲突     | 使用`original`、`replacement`、`diff`、`updated_plan_id`                                   |
| Consensus字段新旧冲突    | 使用`consensus_session_id`、`vote_page_id`、`plan_group_id`、`vote_id`                     |
| Trace事件新旧冲突        | 只能使用03/04定义的最终`event_type`                                                            |
| BackupPlan语义冲突     | BackupPlan不是完整PlanContract，不使用`plan_id`表示                                             |
| PlanContract片段展示冲突 | 完整对象叫`PlanContract`；摘要必须叫`PlanContractView`、`PlanSummary`或`UserVisiblePlanProjection` |

### 3.3强制ID前缀

本表只收束05中会引用到的核心与API层ID前缀；最终约束以03/04为准。

| 字段                   | 前缀         |
| -------------------- | ---------- |
| user_id              | `user_`    |
| plan_id              | `plan_`    |
| trace_id             | `trace_`   |
| plan_group_id        | `plangrp_` |
| vote_page_id         | `vpage_`   |
| consensus_session_id | `cs_`      |
| vote_id              | `vote_`    |
| step_id              | `step_`    |
| poi_id               | `poi_`     |
| action_id            | `act_`     |
| execution_id         | `exec_`    |
| recovery_id          | `rec_`     |
| memory_id            | `mem_`     |
| candidate_id         | `memcand_` |
| route_id             | `route_`   |
| log_id               | `log_`     |
| risk_id              | `risk_`    |
| backup_plan_id       | `backup_`  |
| signal_id            | `sig_`     |
| feedback_id          | `fb_`      |
| question_id          | `q_`       |
| run_id               | `benchrun_` |

禁止使用：

```text
group_0001
vote_page_0001
泛化session_id
把BackupPlan写成plan_id
```

---

## 4.Agent总体设计原则

### 4.1PlanContract驱动原则

LifePilot内部所有关键模块围绕PlanContract运行：

```text
Frontend渲染
→ Verifier检查
→ Executor执行
→ Recovery修复
→ Logging追踪
→ Benchmark评测
```

规则：

1. 前端不直接消费LLM自然语言草案。
2. Verifier不验证自然语言，只验证结构化候选对象，并输出可进入PlanContract的VerifierResult。
3. Executor不执行自然语言，只执行ToolAction。
4. Recovery不直接改写原PlanContract，而是生成新的完整PlanContract。
5. TraceLog记录每一步，但用户页只展示投影。

### 4.2LLM受控参与原则

LLM可以参与理解、草案、解释和文案，不可以决定真实世界状态。

| LLM可以做         | LLM不能做                      |
| -------------- | --------------------------- |
| 目标理解摘要         | 确认餐厅有位                      |
| 场景初判           | 确认活动可预约                     |
| 约束候选抽取         | 确认路线通畅                      |
| 候选计划草案         | 确认天气安全                      |
| 自然语言解释         | 确认执行成功                      |
| 群聊消息草案         | 绕过Verifier                  |
| 纪念日话术          | 写入长期LifeMemory              |
| Recovery用户解释润色 | 输出不符合03 Schema的PlanContract |

### 4.3Mock显式标识原则

Mock对象必须按04的对象类型满足对应Mock标识，不强制所有对象同时包含同一组字段。

| 对象类型 | 必须标识 | 说明 |
| -------- | -------- | ---- |
| Mock POI | `mock_only:true` | 固定数字孪生区域的Demo地点 |
| Mock状态 | `source:"mock_api"`或`mock_only:true` | POIStatus、RestaurantStatus、WeatherStatus等 |
| Mock凭证 | `mock_only:true` | 预约号、订座号、订单号、消息号等 |
| Mock消息 | `mock_only:true` | 不得暗示真实微信或短信已发送 |
| SocialSignalMock | `is_mock:true`、`source_type:"mock_social_signal"` | 不得伪装真实爬取 |

Mock状态示例：

```json
{
  "source": "mock_api"
}
```

SocialSignal必须包含：

```json
{
  "is_mock": true,
  "source_type": "mock_social_signal"
}
```

`failure_injection`只用于Debug/测试，不展示给普通用户。

### 4.4Verifier闸门原则

Verifier是执行前的硬闸门：

```text
DraftPlan未通过内部预检，不得进入Verifier；
Verifier生成合法VerifierResult后，才可组装完整PlanContract；
完整PlanContract未通过Full SchemaValidator，不得返回前端或持久化；
PlanContract未通过Verifier，不得进入Executor；
Verifier.status=fail且不可恢复，不得执行；
Verifier.status=warning可以展示，但必须说明风险和PlanB。
```

### 4.5版本化Recovery原则

LifePilot P0采用版本化Recovery策略。

```text
原PlanContract不被原地覆盖；
原plan_id进入recovered状态；
RecoveryResult.updated_plan_id指向新的完整PlanContract；
新的plan_id如plan_20260520_0001_r1承载恢复后的完整计划；
Executor继续基于updated_plan_id执行替换后的ToolAction。
```

### 4.6低打扰记忆原则

LifeMemory不是不可见画像系统。

| 信息敏感度 | 处理                               |
| ----- | -------------------------------- |
| 低敏    | 可生成MemoryCandidate，规则允许时可启用或进入候选 |
| 中敏    | 必须用户确认                           |
| 高敏    | 默认不保存                            |
| 关闭个性化 | 不读取、不写入长期记忆                      |

用户当次明确输入优先于长期记忆。

---

## 5.Agent角色与模块职责

| 模块                  |   P0 | 核心职责                        | LLM参与       | 关键输出                                         |
| ------------------- | ---: | --------------------------- | ----------- | -------------------------------------------- |
| InputGateway        |    是 | 接收用户输入，创建或复用trace_id        | 不需要         | input_log                                    |
| Agent Orchestrator  |    是 | 编排全链路，控制模块顺序和兜底             | 可调用LLM子模块   | PlanContract或错误                              |
| IntentParser        |    是 | 识别场景、目标摘要、意图标签              | 允许辅助理解      | UserGoal                                     |
| ConstraintExtractor |    是 | 抽取约束，标记默认值来源                | 允许生成候选      | ConstraintSet                                |
| MemoryRetriever     | P0弱化 | 按开关读取可用长期记忆                 | 不建议         | MemoryUsage                                  |
| CandidateRetriever  |    是 | 搜索POI、餐厅、活动、路线候选            | 不决定状态       | CandidateSet                                 |
| MockAPIService      |    是 | 返回Mock状态、路线、天气、执行凭证         | 不允许         | POIStatus、RouteEstimate、WeatherStatus、Mock凭证 |
| PlanGenerator       |    是 | 生成候选时间线草案                   | 允许生成草案      | DraftPlan                                    |
| PlanContractBuilder |    是 | 将已验证内部候选补齐为完整PlanContract | 不建议         | PlanContract                                 |
| SchemaValidator     |    是 | 校验完整PlanContract的03 Schema | 不允许         | pass/fail                                    |
| VerifierService     |    是 | 检查可执行性                      | 不允许绕过       | VerifierResult                               |
| PlanRanker          |    是 | 对候选计划排序                     | P0规则版       | ranked PlanContract                          |
| ResponseAssembler   |    是 | 生成展示投影                      | 允许润色文案      | PlanContractView                             |
| ExecutorService     |    是 | 执行ToolAction                | 不允许         | ExecutionResult                              |
| RecoveryPlanner     |    是 | 局部替换并生成新PlanContract        | 仅允许解释润色     | RecoveryResult、updated_plan_id               |
| ConsensusService    |    是 | 投票、统计、finalize、共识约束         | 解释可用LLM润色   | ConsensusSummary、final_plan_id               |
| LifeMemoryService   | P0最小 | 生成候选、隐私分级、确认预留              | 候选内容可用LLM草拟 | MemoryCandidate                              |
| LoggingService      |    是 | 写TraceLog，生成用户可见投影          | 不允许         | TraceLog、UserVisibleTraceEvent               |

---

## 6.主编排链路：自然语言目标到PlanContract

### 6.1主链路

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

### 6.2步骤总表

| 顺序 | 步骤                  | 输入                                       | 输出                 | LLM参与     | 必须由规则/Mock/Verifier决定  | 失败策略                      | TraceLog event_type | 对应对象                                  |
| -: | ------------------- | ---------------------------------------- | ------------------ | --------- | ---------------------- | ------------------------- | ------------------- | ------------------------------------- |
|  1 | InputGateway        | HTTP请求、input_text                        | trace_id、raw input | 不需要       | trace_id生成             | 输入为空返回BAD_REQUEST         | input_log           | TraceLog                              |
|  2 | IntentParser        | raw_text、scenario_hint                   | UserGoal草案         | 允许        | 不能决定可执行状态              | 低置信度转fallback_unknown或模板  | intent_log          | UserGoal                              |
|  3 | ConstraintExtractor | raw_text、UserGoal                        | ConstraintSet草案    | 允许        | 默认值来源必须规则标记            | 缺失字段填默认并标记assumption      | constraint_log      | ConstraintSet                         |
|  4 | MemoryRetriever     | user_id、use_memory、ConstraintSet         | MemoryUsage[]      | 不建议       | 个性化关闭时不读取              | 不可用则空记忆继续                 | memory_log          | MemoryUsage                           |
|  5 | CandidateRetriever  | ConstraintSet、location、MemoryUsage       | CandidateSet       | 可辅助重写检索意图 | POI状态不能由LLM产生          | 候选不足扩大半径或换同类              | poi_log             | POI、CandidateSet                      |
|  6 | MockAPI状态查询         | candidate POI、arrival_time、party_size    | 状态快照               | 不允许       | 余位、路线、天气必须来自Mock/规则    | 状态缺失返回MOCK_STATUS_MISSING | tool_log            | POIStatus、RouteEstimate、WeatherStatus |
|  7 | PlanGenerator       | UserGoal、ConstraintSet、CandidateSet、状态快照 | DraftPlan[]        | 允许        | 不得写可执行结论               | 失败用场景模板                   | intent_log/poi_log  | DraftPlan内部对象                         |
|  8 | PlanBuildCandidate预检 | DraftPlan、状态快照                           | PlanBuildCandidate | 不建议       | 仅做引用、时间线、动作草案预检       | 缺字段则补规则默认或失败              | tool_log            | 内部对象，不进入03/04契约                     |
|  9 | Verifier            | PlanBuildCandidate、Mock状态、路线、天气            | VerifierResult、ExecutableWindow、Risk | 不允许绕过 | 可执行性最终由Verifier决定      | fail可恢复触发Recovery，否则阻断    | verifier_log        | VerifierResult                        |
| 10 | PlanContractBuilder | PlanBuildCandidate、VerifierResult            | 完整PlanContract    | 不建议       | 必填字段由Builder补齐         | 缺字段返回PLAN_SCHEMA_INVALID   | tool_log            | PlanContract                          |
| 11 | Full SchemaValidator | 完整PlanContract                            | Schema pass/fail   | 不允许       | 03 Schema最终决定          | 失败返回PLAN_SCHEMA_INVALID   | error_log           | PlanContract                          |
| 12 | PlanRanker          | 多个已验证且Schema合法PlanContract                 | 排序结果               | P0不需要     | 排序以规则和VerifierResult为准 | 排序失败按硬约束通过数               | verifier_log        | PlanContract                          |
| 13 | ResponseAssembler   | PlanContract、Trace投影                     | API响应              | 允许润色展示文案  | 不得删改PlanContract本体     | 投影失败返回完整计划可展示             | tool_log            | PlanContractView                      |
| 14 | Trace写入             | 全链路事件                                    | TraceLog[]         | 不允许       | 脱敏规则强制                 | 日志失败不阻断业务                 | 对应事件                | TraceLog                              |

### 6.3PlanContract与展示投影

凡写`PlanContract`，默认必须是满足03完整Schema的领域对象。

如果只给前端展示摘要，必须命名为：

```text
PlanContractView
PlanSummary
UserVisiblePlanProjection
```

规则：

1. `PlanContractView`不得冒充完整PlanContract。
2. `GET /api/v1/plans/{plan_id}`返回完整PlanContract。
3. 计划结果页可渲染投影，但内部执行必须读取完整PlanContract。
4. 测试必须校验完整PlanContract，而不是只校验展示字段。

### 6.4InputGateway工作流

| 项目 | 规则 |
| ---- | ---- |
| 输入 | HTTP请求、`input_text`、可选`scenario_hint`、可选`X-Trace-Id` |
| 输出 | `trace_id`、标准化raw input、`input_log` |
| 失败降级 | `input_text`为空或过长时返回`BAD_REQUEST`；无法创建trace时返回`TRACE_ID_MISSING` |
| 验收 | 每次主流程必须有`trace_id`；原始输入不得被改写后覆盖；必须写`input_log` |

### 6.5Agent Orchestrator工作流

| 项目 | 规则 |
| ---- | ---- |
| 输入 | InputGateway输出、用户上下文、P0能力开关 |
| 输出 | 完整PlanContract或标准错误响应 |
| 编排职责 | 控制IntentParser、ConstraintExtractor、CandidateRetriever、PlanGenerator、Verifier、PlanContractBuilder、Full SchemaValidator、ResponseAssembler顺序 |
| 失败降级 | LLM不可用时走规则模板；候选不足时回到CandidateRetriever扩大范围；Schema失败只允许重试一次 |
| 验收 | 不允许LLM越权写可执行状态；不允许跳过Verifier；不允许返回未通过Full SchemaValidator的PlanContract |

### 6.6PlanRanker工作流

| 项目 | 规则 |
| ---- | ---- |
| 输入 | 多个已Verifier通过且Schema合法的PlanContract、ConstraintSet |
| 输出 | 排序后的PlanContract列表和首选计划 |
| P0排序 | 硬约束满足度 > VerifierResult.status/score > 可执行窗口 > 距离 > 预算 > 排队风险 > 场景匹配 > 情绪价值 |
| 失败降级 | 排序失败时按硬约束通过数和VerifierResult.score排序 |
| 验收 | PlanRanker不能绕过Verifier，不能把`fail`计划排到可执行首选 |

### 6.7ResponseAssembler工作流

| 项目 | 规则 |
| ---- | ---- |
| 输入 | 完整PlanContract、UserVisibleTraceEvent投影、可展示文案 |
| 输出 | `PlanContractView`、`PlanSummary`或`UserVisiblePlanProjection` |
| 展示边界 | 只生成展示投影，不修改PlanContract本体 |
| 安全规则 | 不展示Prompt、LLM推理链、API Key、高敏MemoryCandidate、`failure_injection`、ToolAction敏感payload |
| 验收 | `GET /api/v1/plans/{plan_id}`仍返回完整PlanContract；展示投影不得冒充完整对象 |

---

## 7.IntentParser工作流

### IntentParser

#### 模块定位

IntentParser负责把用户自然语言输入转为03中的`UserGoal`，识别LifePilot P0场景，并给后续ConstraintExtractor和PlanGenerator提供场景上下文。

#### 是否P0

是。

#### 输入

| 输入对象          | 来源           | 是否必填 | 说明              |
| ------------- | ------------ | ---: | --------------- |
| raw_text      | InputGateway |    是 | 用户原始输入          |
| scenario_hint | 前端快捷卡片       |    否 | 只能作为参考，不能直接替代解析 |
| user_location | 请求体          |    否 | 辅助判断本地生活场景      |
| trace_id      | InputGateway |    是 | 写入TraceLog      |

#### 输出

| 输出对象                  | 去向                                | 是否进入03 Schema | 说明                                                                                                 |
| --------------------- | --------------------------------- | ------------: | -------------------------------------------------------------------------------------------------- |
| UserGoal.raw_text     | PlanContractBuilder               |             是 | 保留用户原文                                                                                             |
| UserGoal.scenario     | ConstraintExtractor、PlanGenerator |             是 | `friend_group`、`family_parent_child`、`anniversary_emotion`、`city_light_explore`、`fallback_unknown` |
| UserGoal.goal_summary | ResponseAssembler                 |             是 | 目标摘要                                                                                               |
| UserGoal.intent_tags  | ConstraintExtractor               |             是 | 意图标签数组                                                                                             |
| UserGoal.emotion_goal | PlanGenerator                     |             是 | 关系目标或情绪目标                                                                                          |
| UserGoal.source       | PlanContractBuilder               |             是 | `user_input`、`llm_generated`或`rule_generated`，不得缺失                                                        |
| confidence            | Orchestrator                      |             是 | 低置信度触发兜底                                                                                           |

#### 是否允许LLM参与

允许。LLM只能辅助理解、摘要和分类建议。最终`scenario`必须经过规则校正。

#### 不允许LLM决定的内容

| 禁止项     |
| ------- |
| 餐厅是否有位  |
| 活动是否可预约 |
| 路线是否通畅  |
| 天气是否安全  |
| 计划是否可执行 |
| 是否执行成功  |

#### 工作步骤

1. 清洗输入：去除空白、限制长度、保留原文。
2. 规则初判：

   * 出现“朋友、同学、几个人、大家、群、投票”等，候选`friend_group`。
   * 出现“老婆、孩子、儿子、女儿、亲子、5岁”等，候选`family_parent_child`。
   * 出现“纪念日、生日、约会、用心、仪式感、不尴尬”等，候选`anniversary_emotion`。
3. LLM辅助摘要：生成`goal_summary`、`intent_tags`、`emotion_goal`候选。
4. 规则校正：

   * 若出现纪念日、生日、仪式感、用心、约会等强关系经营信号，优先`anniversary_emotion`。
   * 否则若出现孩子、亲子、年龄、老婆孩子、家庭成员约束，优先`family_parent_child`。
   * 否则若出现朋友、同学、群、投票、多人朋友局，优先`friend_group`。
5. 低置信度处理：

   * 置信度低但仍像本地生活规划，P0统一使用`fallback_unknown`并走P0通用模板。
   * `city_light_explore`仅作为P1扩展场景，不进入P0默认降级路径。
   * 无法判断且缺少必要信息，使用`fallback_unknown`并请求前端补充或走通用模板。
6. 输出UserGoal并写入`intent_log`。

#### TraceLog

| event_type | module       | visible_to_user | payload摘要                                    |
| ---------- | ------------ | --------------: | -------------------------------------------- |
| intent_log | IntentParser |               是 | scenario、goal_summary、intent_tags、confidence |
| error_log  | IntentParser |               否 | parse_failed、fallback_reason                 |

#### 失败与降级

| 失败情况   | 降级策略                                          |
| ------ | --------------------------------------------- |
| LLM不可用 | 使用关键词规则模板                                     |
| 低置信度   | P0返回`fallback_unknown`并走通用模板；P1才可扩展`city_light_explore` |
| 输入过短   | 返回BAD_REQUEST或请求前端补充                          |
| 场景冲突   | 使用规则裁决：强关系经营信号→纪念日；否则家庭成员/孩子约束→家庭亲子；否则多人朋友局→朋友局；保留冲突标签给ConstraintExtractor |

#### 验收标准

1. 家庭亲子示例必须识别为`family_parent_child`。
2. 朋友局示例必须识别为`friend_group`。
3. 纪念日示例必须识别为`anniversary_emotion`。
4. `raw_text`必须原样进入UserGoal。
5. LLM失败时仍可通过规则得到场景。
6. IntentParser不得写任何Mock状态或Verifier结果。
7. UserGoal必须包含03要求的`source`和`confidence`。

---

## 8.ConstraintExtractor工作流

### ConstraintExtractor

#### 模块定位

ConstraintExtractor负责把UserGoal和原始输入转为03中的`ConstraintSet`，并为PlanGenerator、CandidateRetriever、Verifier提供结构化约束。

#### 是否P0

是。

#### 输入

| 输入对象                 | 来源           | 是否必填 | 说明        |
| -------------------- | ------------ | ---: | --------- |
| raw_text             | InputGateway |    是 | 用户原文      |
| UserGoal             | IntentParser |    是 | 场景和目标摘要   |
| user_location        | 请求体          |    否 | 距离约束计算    |
| preferred_start_time | 请求体          |    否 | 优先于自然语言时间 |
| preferred_end_time   | 请求体          |    否 | 优先于自然语言时间 |
| trace_id             | InputGateway |    是 | 写TraceLog |

#### 输出

| 输出对象                  | 去向                           | 是否进入03 Schema | 说明                  |
| --------------------- | ---------------------------- | ------------: | ------------------- |
| ConstraintSet         | PlanContractBuilder、Verifier |             是 | 03字段                |
| TimeWindow草案          | PlanContractBuilder          |             是 | 规则解析生成              |
| assumption_notes      | TraceLog                     |             否 | 内部来源标记，不进入03 Schema |
| extraction_confidence | Orchestrator                 |             否 | 降级判断                |

#### 是否允许LLM参与

允许。LLM只能给出约束候选，最终字段必须由规则归一化。

#### 不允许LLM决定的内容

| 禁止项       |
| --------- |
| 预算是否实际超限  |
| 路线是否满足距离  |
| 餐厅排队是否可接受 |
| 天气是否安全    |
| 活动票务是否可用  |

#### 必须抽取字段

| 字段                      | 抽取来源         | 缺失默认策略                | 来源标记                      |
| ----------------------- | ------------ | --------------------- | ------------------------- |
| party_size              | “4个人”“老婆孩子”等 | 单人默认为1；家庭亲子示例推断为3     | user_input/rule_generated |
| time_window             | 今天下午、今晚、周末等  | 当前日期下的场景默认窗口          | user_input/rule_generated |
| distance_preference     | 别太远、附近、近点    | `nearby`或`unknown`    | user_input/rule_generated |
| budget_max              | 总预算          | 缺失为null               | user_input                |
| budget_max_per_person   | 人均预算         | 缺失为null               | user_input                |
| walking_tolerance       | 不想走、轻松、不累    | 缺失按场景默认               | user_input/rule_generated |
| queue_tolerance         | 别排队、少排队      | 缺失按场景默认`medium`       | user_input/rule_generated |
| dietary_preference      | 减脂、低卡、清淡、忌口  | 缺失为空数组                | user_input                |
| activity_preference     | 亲子、互动、拍照、展览、桌游等 | 缺失为空数组                | user_input/rule_generated |
| child_friendly_required | 孩子、亲子、年龄     | 家庭亲子默认true            | rule_generated            |
| weather_sensitive       | 户外、散步、下雨     | 户外节点默认true            | rule_generated            |
| indoor_preferred        | 下雨、儿童、安静约会、室内偏好 | 缺失默认false；天气敏感可推断true | user_input/rule_generated |
| emotion_intensity       | 不夸张、仪式感、用心   | 纪念日默认`light`或`medium` | user_input/rule_generated |
| time_flexibility        | 随便、固定时间、别太晚   | 缺失默认`medium`或`unknown` | user_input/rule_generated |
| must_have               | 明确必须         | 缺失为空数组                | user_input                |
| must_not_have           | 明确不要         | 缺失为空数组                | user_input                |

#### 默认值原则

1. 默认值必须在TraceLog中标记为`assumption`或`rule_generated`。
2. 默认值不得伪装成用户明确表达。
3. 当次用户明确输入优先于长期LifeMemory。
4. 长期LifeMemory只能补充偏好，不能覆盖当次硬约束。

#### 工作步骤

1. 解析人数和参与人。
2. 解析时间窗口，并转换为ISO 8601。
3. 解析距离、预算、步行、排队、饮食、活动偏好、天气、室内偏好、儿童友好、情绪强度、时间弹性。
4. 根据场景补默认值：

   * `family_parent_child`默认降低步行强度和排队容忍。
   * `friend_group`默认保留预算和共识弹性。
   * `anniversary_emotion`默认控制流程自然度和仪式感强度。
5. 输出ConstraintSet。
6. 写`constraint_log`，记录显式字段和默认字段来源。

#### TraceLog

| event_type     | module              | visible_to_user | payload摘要                        |
| -------------- | ------------------- | --------------: | -------------------------------- |
| constraint_log | ConstraintExtractor |               是 | 显式约束、默认约束、party_size、time_window |
| error_log      | ConstraintExtractor |               否 | invalid_time、constraint_conflict |

#### 失败与降级

| 失败情况   | 降级策略                                    |
| ------ | --------------------------------------- |
| 时间解析失败 | 使用场景默认时间窗口并标记assumption                 |
| 预算冲突   | 保留更严格预算，写入warning                       |
| 人数不明   | 默认party_size=1或根据家庭成员规则推断               |
| 约束冲突   | 写入must_have/must_not_have，由Verifier最终判断 |

#### 验收标准

1. 家庭亲子示例必须抽取孩子5岁、低卡、距离近、少排队。
2. 缺失预算时不得伪造预算上限。
3. 时间字段必须转ISO 8601。
4. 默认值必须写入TraceLog来源说明。
5. ConstraintSet.party_size必填。
6. 不得把LLM输出的自然语言直接塞入不可校验字段。

---

## 9.MemoryRetriever与LifeMemory工作流

### LifeMemory总体边界

P0只要求最小候选闭环：

```text
生成MemoryCandidate
→ 展示候选
→ 确认/忽略接口或按钮预留
```

P1才实现完整闭环：

```text
LifeMemory管理页
→ 确认、编辑、删除
→ 关闭个性化
→ 下次规划读取长期记忆
→ 记忆使用可解释
```

### MemoryRetriever

#### 模块定位

MemoryRetriever在用户允许个性化时读取已启用的长期LifeMemory，为ConstraintExtractor和PlanGenerator提供辅助偏好。

#### 是否P0

P0可弱化；P1完整。

#### 输入

| 输入对象                    | 来源                  | 是否必填 | 说明                    |
| ----------------------- | ------------------- | ---: | --------------------- |
| user_id                 | API Gateway         |    是 | Demo可用`user_demo_001` |
| use_memory              | 请求体                 |    否 | false时不读取             |
| personalization_enabled | User/Profile        |    是 | 关闭个性化时不读不写            |
| ConstraintSet           | ConstraintExtractor |    是 | 用于筛选相关记忆              |
| trace_id                | InputGateway        |    是 | 写memory_log           |

#### 输出

| 输出对象               | 去向                  | 是否进入03 Schema | 说明           |
| ------------------ | ------------------- | ------------: | ------------ |
| MemoryUsage[]      | PlanContractBuilder |             是 | 仅引用enabled记忆 |
| memory_explanation | ResponseAssembler   |           可投影 | 用户可见解释       |
| empty_memory       | Orchestrator        |             否 | 不阻断主流程       |

#### 是否允许LLM参与

不建议。检索应由规则和数据服务完成。LLM可在ResponseAssembler中润色“本次使用了哪些记忆”的说明。

#### 不允许LLM决定的内容

| 禁止项          |
| ------------ |
| 是否启用长期记忆     |
| 是否保存高敏记忆     |
| 是否绕过用户确认     |
| 是否覆盖用户当次明确输入 |

#### 工作步骤

1. 检查`personalization_enabled`和`use_memory`。
2. 若关闭个性化，直接返回空记忆，并写`memory_log`。
3. 读取`enabled`且未过期LifeMemory。
4. 根据当前场景、约束和用户目标筛选相关记忆。
5. 生成MemoryUsage，包含`memory_id`、`used_for`、`explanation`、`confidence`、`user_visible`。
6. 写入`last_used_trace_id`和`last_used_at`。
7. 当次明确输入与记忆冲突时，以当次输入为准，并写冲突说明。

#### TraceLog

| event_type | module            | visible_to_user | payload摘要                                                |
| ---------- | ----------------- | --------------: | -------------------------------------------------------- |
| memory_log | MemoryRetriever   |               是 | used_memory_count、skipped_reason、personalization_enabled |
| error_log  | LifeMemoryService |               否 | MEMORY_UNAVAILABLE、MEMORY_PRIVACY_VIOLATION              |

#### 失败与降级

| 失败情况        | 降级策略                           |
| ----------- | ------------------------------ |
| Memory服务不可用 | 返回空记忆，不阻断计划                    |
| 个性化关闭       | 不读不写长期记忆                       |
| 记忆冲突        | 当次输入优先                         |
| 疑似隐私违规      | 返回MEMORY_PRIVACY_VIOLATION，不保存 |

#### 验收标准

1. 个性化关闭后不读取长期记忆。
2. MemoryUsage必须写入`memory_log`。
3. 当次输入优先于长期记忆。
4. 中敏记忆未确认前不得强使用。
5. 高敏信息默认不保存。
6. 长期LifeMemory必须包含`source_trace_id`和`last_used_trace_id`。

### MemoryCandidateGenerator

#### 模块定位

从用户输入和反馈中生成可审计的记忆候选，不直接写入长期LifeMemory。

#### 工作步骤

1. 接收用户输入或反馈。
2. 抽取与规划相关的偏好、约束、长期目标。
3. PrivacyClassifier分为`low`、`medium`、`high`。
4. 低敏生成候选；中敏进入`pending_confirmation`；高敏默认丢弃。
5. 输出MemoryCandidate。
6. 写`memory_log`。

---

## 10.CandidateRetriever与MockAPI工作流

### CandidateRetriever

#### 模块定位

CandidateRetriever根据场景和约束检索可用于计划生成的POI、餐厅、活动、路线候选。它只负责候选召回，不负责最终可执行判断。

#### 是否P0

是。

#### 输入

| 输入对象          | 来源                  | 是否必填 | 说明                          |
| ------------- | ------------------- | ---: | --------------------------- |
| UserGoal      | IntentParser        |    是 | 场景                          |
| ConstraintSet | ConstraintExtractor |    是 | 检索约束                        |
| TimeWindow    | ConstraintExtractor |    是 | 查询状态需要到达时间                  |
| user_location | 请求体或默认锚点            |    是 | Demo可用`poi_home_anchor_001` |
| MemoryUsage[] | MemoryRetriever     |    否 | 辅助偏好                        |
| trace_id      | InputGateway        |    是 | 写poi_log和tool_log           |

#### 输出

| 输出对象                       | 去向                          | 是否进入03 Schema | 说明             |
| -------------------------- | --------------------------- | ------------: | -------------- |
| POI candidates             | PlanGenerator               |          是/引用 | 活动、散步点、服务点     |
| Restaurant candidates      | PlanGenerator               |          是/引用 | 餐厅             |
| RouteEstimate[]            | PlanStep.estimated_route    |             是 | 必须完整字段         |
| POIStatus/RestaurantStatus | Verifier                    |             是 | 必须带`expire_at` |
| WeatherStatus              | Verifier                    |             是 | 使用03结构         |
| SocialSignalMock[]         | PlanContract.social_signals |            P1 | 必须标Mock        |

#### 是否允许LLM参与

LLM可以把用户目标改写成检索意图，例如“轻松亲子活动”“低卡家庭餐厅”。但检索结果、状态、余位、路线和天气必须来自MockAPI或规则。

#### 不允许LLM决定的内容

| 禁止项      |
| -------- |
| POI是否营业  |
| 餐厅是否有桌   |
| 活动是否有票   |
| 路线耗时     |
| 天气风险     |
| 社交口碑是否真实 |

#### MockAPI调用范围

| 能力               |       P0 | 输入要求                                            | 输出要求                                              |
| ---------------- | -------: | ----------------------------------------------- | ------------------------------------------------- |
| POI搜索            |        是 | scenario、location、tags、radius                   | POI列表，Mock POI需`mock_only:true`                   |
| 餐厅搜索             |        是 | dietary_preference、budget、location              | 餐厅候选                                              |
| 路线估计             |        是 | origin_poi_id、destination_poi_id、transport_mode | RouteEstimate完整字段                                 |
| 餐厅状态查询           |        是 | poi_id、arrival_time、party_size                  | RestaurantStatus，必须带`expire_at`                   |
| 活动状态查询           |        是 | poi_id、arrival_time、party_size                  | POIStatus，必须带`expire_at`                          |
| 天气查询             |        是 | location、time_window                            | WeatherStatus                                     |
| SocialSignalMock | P1，P0可预留 | poi_id                                          | `is_mock:true`、`source_type:"mock_social_signal"` |

餐厅状态查询必须包含：

```json
{
  "arrival_time": "2026-05-20T15:55:00+08:00",
  "party_size": 3
}
```

#### 工作步骤

1. 根据场景选择召回模板：

   * 家庭亲子：亲子活动、低卡餐厅、短路线、低排队。
   * 朋友局：多类候选方案所需POI组合。
   * 纪念日：安静餐厅、散步/看展、轻仪式服务。
2. 调用Mock POI搜索和餐厅搜索。
3. 对候选POI查询状态。
4. 对候选组合估计路线。
5. 查询天气。
6. 可选读取SocialSignalMock。
7. 过滤明显不满足硬约束的候选。
8. 写`poi_log`和`tool_log`。

#### TraceLog

| event_type | module             | visible_to_user | payload摘要                                       |
| ---------- | ------------------ | --------------: | ----------------------------------------------- |
| poi_log    | CandidateRetriever |               是 | candidate_count、selected_categories、radius      |
| tool_log   | MockAPIService     |               是 | tool_name、poi_id、source:"mock_api"              |
| error_log  | MockAPIService     |               否 | MOCK_STATUS_MISSING、SOCIAL_SIGNAL_MOCK_REQUIRED |

MockAPI调用Trace示例：

```json
{
  "event_type": "tool_log",
  "module": "MockAPIService",
  "payload": {
    "tool_name": "get_restaurant_status",
    "poi_id": "poi_light_food_003",
    "source": "mock_api"
  }
}
```

#### 失败与降级

| 失败情况               | 降级策略                               |
| ------------------ | ---------------------------------- |
| POI候选不足            | 扩大半径或切换同类POI                       |
| 餐厅候选不足             | 降级为轻食/简餐同类                         |
| Mock状态缺失           | 返回`MOCK_STATUS_MISSING`，降低置信度或换POI |
| 路线估计失败             | 换近距离候选，或标记Verifier warning         |
| SocialSignalMock缺失 | 不展示口碑卡，不阻断主流程                      |
| 天气缺失               | 标记天气风险unknown，优先室内方案               |

#### 验收标准

1. 餐厅状态查询必须带`arrival_time`和`party_size`。
2. POIStatus/RestaurantStatus必须带`expire_at`。
3. RouteEstimate必须含完整字段。
4. Mock结果必须按对象类型满足04的Mock标识：POI/凭证用`mock_only:true`，状态用`source:"mock_api"`或`mock_only:true`，SocialSignal用`is_mock:true`和`source_type:"mock_social_signal"`。
5. LLM不得编造Mock状态。
6. `failure_injection`不得展示给普通用户。

---

## 11.PlanGenerator工作流

### PlanGenerator

#### 模块定位

PlanGenerator负责基于UserGoal、ConstraintSet、CandidateSet和Mock状态，生成内部`DraftPlan`。DraftPlan只是候选时间线草案，不是可执行结果。

#### 是否P0

是。

#### 输入

| 输入对象                  | 来源                  |           是否必填 | 说明          |
| --------------------- | ------------------- | -------------: | ----------- |
| UserGoal              | IntentParser        |              是 | 场景和目标       |
| ConstraintSet         | ConstraintExtractor |              是 | 硬约束与软偏好     |
| CandidateSet          | CandidateRetriever  |              是 | POI、餐厅、路线候选 |
| Mock状态快照              | MockAPIService      |              是 | 仅用于引用，不可改写  |
| MemoryUsage[]         | MemoryRetriever     |              否 | 个性化辅助       |
| consensus_constraints | ConsensusService    | 朋友局finalize后必填 | 共识约束        |
| trace_id              | InputGateway        |              是 | 写TraceLog   |

#### 输出

| 输出对象              | 去向                           | 是否进入03 Schema | 说明        |
| ----------------- | ---------------------------- | ------------: | --------- |
| DraftPlan[]       | PlanBuildCandidate预检        |             否 | 内部草案      |
| draft_explanation | ResponseAssembler            |             否 | 可用于展示文案   |
| message_drafts    | PlanContractBuilder.messages |          是/可选 | 群聊消息、邀请话术 |

#### 是否允许LLM参与

允许。LLM可以生成候选时间线、解释文案、群聊消息草案、纪念日邀请话术。

#### 不允许LLM决定的内容

| 禁止项                      |
| ------------------------ |
| DraftPlan不能声称“已预约成功”     |
| 不能生成Mock凭证               |
| 不能确认余位、票务、路线、天气          |
| 不能跳过SchemaValidator      |
| 不能输出完整PlanContract冒充最终对象 |

#### 工作步骤

1. 根据场景选择计划模板：

   * `family_parent_child`：亲子活动→轻食餐厅→轻松散步/室内备选→返程。
   * `friend_group`：生成3～4个意图差异候选，如拍照逛展、好吃不累、桌游聊天、低预算。
   * `anniversary_emotion`：自然过渡→安静餐厅→轻仪式细节→合照点/返程。
2. 将候选POI组合成时间线草案。
3. 插入缓冲时间，避免过赶。
4. 生成PlanB候选，但只作为BackupPlan草案。
5. 生成解释和消息草案。
6. 输出DraftPlan给PlanBuildCandidate预检。
7. 写入TraceLog摘要。

#### DraftPlan内部约束

DraftPlan可以包含内部字段，但不得进入03 Schema。建议内部命名：

```text
draft_id
draft_steps
draft_reasoning_summary
selected_candidate_refs
draft_messages
draft_backup_options
```

禁止将DraftPlan返回给前端作为最终计划。

#### TraceLog

| event_type | module        | visible_to_user | payload摘要                     |
| ---------- | ------------- | --------------: | ----------------------------- |
| intent_log | PlanGenerator |               是 | selected_template、draft_count |
| poi_log    | PlanGenerator |               是 | selected_poi_ids              |
| error_log  | PlanGenerator |               否 | draft_generation_failed       |

#### 失败与降级

| 失败情况    | 降级策略                                             |
| ------- | ------------------------------------------------ |
| LLM生成失败 | 使用固定Demo模板                                       |
| 时间线冲突   | 交由PlanBuildCandidate预检规范化或返回PLAN_TIMELINE_INVALID |
| 候选不足    | 回到CandidateRetriever扩大范围                         |
| 朋友局候选不足 | 至少生成3个候选方案，否则提示候选不足                              |

#### 验收标准

1. DraftPlan不得直接返回前端。
2. DraftPlan不得包含执行成功状态。
3. 家庭亲子场景至少生成3个时间线节点。
4. 朋友局至少生成3个候选方案。
5. 纪念日场景必须包含自然流程和话术草案。
6. 生成的草案必须能先形成PlanBuildCandidate，并在Verifier通过后由PlanContractBuilder补齐为完整PlanContract。

---

## 12.PlanContractBuilder与SchemaValidator工作流

### PlanContractBuilder

#### 模块定位

PlanContractBuilder把已经过Verifier的内部`PlanBuildCandidate`转换为03定义的完整PlanContract。它负责补齐ID、状态、时间、预算、ToolAction、BackupPlan、VerifierResult、created_at、updated_at等必填字段。

`PlanBuildCandidate`是Agent内部对象，只用于Verifier前的引用、时间线、动作草案预检，不进入03/04领域契约，不得返回前端。

#### 是否P0

是。

#### 输入

| 输入对象             | 来源                  | 是否必填 | 说明                         |
| ---------------- | ------------------- | ---: | -------------------------- |
| PlanBuildCandidate | PlanGenerator/预检   |    是 | 内部候选，不是PlanContract        |
| UserGoal         | IntentParser        |    是 | 进入PlanContract.user_goal   |
| ConstraintSet    | ConstraintExtractor |    是 | 进入PlanContract.constraints |
| TimeWindow       | ConstraintExtractor |    是 | 进入PlanContract.time_window |
| Candidate/Mock状态 | CandidateRetriever  |    是 | 填充POI、路线、预算、状态引用           |
| VerifierResult   | VerifierService     |    是 | 进入PlanContract.verifier_result |
| ExecutableWindow | VerifierService     |    是 | 进入PlanContract.executable_window |
| Risk[]           | VerifierService     |    是 | 进入PlanContract.risks |
| trace_id         | InputGateway        |    是 | PlanContract.trace_id      |
| plan_id          | PlanService         |    是 | `plan_`前缀                  |

#### 输出

| 输出对象               | 去向              | 是否进入03 Schema | 说明         |
| ------------------ | --------------- | ------------: | ---------- |
| PlanContract | Full SchemaValidator |             是 | 完整Schema对象 |
| BuildError         | Orchestrator    |             否 | 字段缺失或引用错误  |

#### 是否允许LLM参与

不建议。Builder应为规则模块。LLM生成的文案只能进入允许的展示字段或`messages`。

#### 必须补齐字段

| 对象            | 必须补齐                                                                                                                                                                                                                     |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| PlanContract  | `plan_id`、`trace_id`、`version`、`status`、`user_goal`、`participants`、`time_window`、`constraints`、`timeline`、`budget`、`executable_window`、`risks`、`backup_plans`、`tool_actions`、`verifier_result`、`created_at`、`updated_at` |
| PlanStep      | `duration_minutes`、`booking_required`、`reservation_required`、`status`                                                                                                                                                    |
| ToolAction    | `payload`、`idempotency_key`、`created_at`、`updated_at`                                                                                                                                                                    |
| BackupPlan    | `backup_plan_id`、`trigger`、`description`、`replace_step_id`、`original_poi_id`、`new_poi_id`、`expected_diff`、`verifier_result`、`priority`、`status`                                                                          |
| RouteEstimate | `route_id`、`origin_poi_id`、`destination_poi_id`、`transport_mode`、`distance_km`、`duration_minutes`、`traffic_level`、`confidence`、`source`、`updated_at`                                                                     |

#### 工作步骤

1. 接收已通过Verifier的`PlanBuildCandidate`。
2. 创建`plan_id`和基础元信息。
3. 写入UserGoal、participants、time_window、constraints。
4. 将候选步骤转换为PlanStep，并生成`step_id`。
5. 计算每个PlanStep的`duration_minutes`。
6. 根据活动/餐厅/消息节点生成ToolAction：

   * `book_activity`
   * `reserve_restaurant`
   * `order_item`
   * `send_message`
   * `get_restaurant_status`
   * `get_poi_status`

   其中`order_item` ToolAction由Executor映射到`POST /api/v1/mock/orders/create`。
7. 为每个ToolAction生成`action_id`和内部`idempotency_key`。
8. 生成Budget。
9. 生成BackupPlan，而不是完整PlanContract。
10. 写入Verifier生成的`verifier_result`、`executable_window`和`risks`。
11. 根据VerifierResult设置`status=verified`或`status=executable`；不可执行失败不得返回为可执行计划。
12. 交给Full SchemaValidator。

### SchemaValidator

#### 模块定位

SchemaValidator基于03 JSONSchema校验完整PlanContract。任何不满足03 Schema的计划不得返回给前端。

#### 是否允许LLM参与

不允许。

#### 工作步骤

1. 校验PlanContract根字段必填。
2. 校验`additionalProperties:false`规则。
3. 校验ID前缀。
4. 校验时间格式。
5. 校验timeline非空、step顺序、时间不倒序。
6. 校验ToolAction字段完整、引用合法。
7. 校验BackupPlan字段完整。
8. 校验VerifierResult结构合法。
9. 失败返回`PLAN_SCHEMA_INVALID`或更具体错误。
10. 成功后才允许返回前端或持久化为完整PlanContract。

#### TraceLog

| event_type | module              | visible_to_user | payload摘要                       |
| ---------- | ------------------- | --------------: | ------------------------------- |
| tool_log   | PlanContractBuilder |               否 | plan_id、step_count、action_count |
| error_log  | SchemaValidator     |               否 | error_code、schema_path、安全摘要     |

#### 失败与降级

| 失败情况          | 降级策略                           |
| ------------- | ------------------------------ |
| 缺必填字段         | Builder尝试规则补齐一次                |
| step引用不存在POI  | 返回`PLAN_STEP_POI_NOT_FOUND`    |
| ToolAction缺字段 | 返回`TOOL_ACTION_INVALID`        |
| timeline非法    | 返回`PLAN_TIMELINE_INVALID`      |
| 二次校验仍失败       | 返回`PLAN_SCHEMA_INVALID`，不得返回前端 |

#### 验收标准

1. 不满足03 Schema的PlanContract不得返回给前端。
2. PlanStep必须包含`duration_minutes`、`booking_required`、`reservation_required`。
3. ToolAction必须包含`payload`、`idempotency_key`、`created_at`、`updated_at`。
4. BackupPlan不得使用`plan_id`。
5. PlanContract摘要必须命名为PlanContractView、PlanSummary或UserVisiblePlanProjection。
6. `additionalProperties:false`违规必须被阻断。

---

## 13.Verifier工作流

### VerifierService

#### 模块定位

Verifier是执行前闸门，负责判断内部PlanBuildCandidate是否可组装为当前可执行的PlanContract。Verifier不能被LLM绕过。

#### 是否P0

是。

#### 输入

| 输入对象                       | 来源              | 是否必填 | 说明            |
| -------------------------- | --------------- | ---: | ------------- |
| PlanBuildCandidate         | PlanGenerator/预检 |    是 | 内部候选，不是完整PlanContract |
| POIStatus/RestaurantStatus | MockAPIService  |    是 | 状态快照          |
| RouteEstimate              | MockAPIService  |    是 | 路线估计          |
| WeatherStatus              | MockAPIService  |    是 | 天气状态          |
| trace_id                   | InputGateway    |    是 | 写verifier_log |

#### 输出

| 输出对象             | 去向                             | 是否进入03 Schema | 说明                      |
| ---------------- | ------------------------------ | ------------: | ----------------------- |
| VerifierResult   | PlanContract.verifier_result   |             是 | `pass`、`warning`、`fail` |
| ExecutableWindow | PlanContract.executable_window |             是 | 可执行窗口                   |
| Risk[]           | PlanContract.risks             |             是 | 用户可见风险                  |
| RecoveryHint     | RecoveryPlanner                |             否 | 可恢复失败提示                 |

#### 是否允许LLM参与

不允许。LLM只能在ResponseAssembler阶段润色风险解释，不能改变VerifierResult。

#### 检查项

| check.name              | 检查内容                | 失败处理         |
| ----------------------- | ------------------- | ------------ |
| time_feasibility        | 时间线是否重叠、倒序、过赶       | 可恢复则调整或阻断    |
| opening_hours           | POI/餐厅是否营业          | 换POI或阻断      |
| distance_constraint     | 距离是否满足偏好            | 换近距离POI      |
| budget_constraint       | 预算是否超限              | 换低价方案        |
| restaurant_capacity     | 餐厅余位/排队是否可接受        | 可触发Recovery  |
| activity_ticket         | 活动票务/预约是否可用         | 可触发Recovery  |
| queue_time              | 排队是否超出容忍            | 换POI或warning |
| weather_risk            | 天气是否影响户外节点          | P1/P2可恢复     |
| participant_constraints | 儿童友好、饮食、同行人约束       | 换候选          |
| tool_action_integrity   | ToolAction是否完整、依赖合法 | 阻断执行         |
| executable_window       | 可执行窗口是否有效           | 刷新或阻断        |

VerifierCheck枚举支持以上11项。P0必须实现前8项：`time_feasibility`、`opening_hours`、`distance_constraint`、`budget_constraint`、`restaurant_capacity`、`activity_ticket`、`queue_time`、`weather_risk`。P0执行前建议强制实现`tool_action_integrity`，避免Executor执行坏Action；`participant_constraints`和`executable_window`可做轻量检查或作为P1增强。

#### VerifierResult.status规则

| status  | 含义       |          是否可展示 |                是否可执行 |
| ------- | -------- | -------------: | -------------------: |
| pass    | 关键检查通过   |              是 |                    是 |
| warning | 可执行但存在风险 | 是，必须说明风险和PlanB |                    是 |
| fail    | 关键检查失败   |       是，展示用户说明 | 否，除非Recovery成功后新计划通过 |

#### 工作步骤

1. 读取PlanBuildCandidate。
2. 校验timeline草案、ToolAction草案、POI引用。
3. 对需要状态的节点读取最新Mock状态。
4. 执行检查项。
5. 汇总`checks`、`failed_checks`、`warnings`。
6. 计算`score`。
7. 生成ExecutableWindow：

   * `window_minutes`
   * `confidence`
   * `expire_at`
   * `reasons`
   * `risk_factors`
   * `lockable_resources`
   * `calculated_from`
   * `display_message`
8. 若`fail`且可恢复，设置`required_recovery=true`。
9. 写`verifier_log`。
10. 输出VerifierResult、ExecutableWindow和Risk[]给PlanContractBuilder：

    * pass/warning：允许Builder组装完整PlanContract；
    * fail不可恢复：阻断组装可执行计划；
    * fail可恢复：进入RecoveryPlanner或重新生成候选。

#### TraceLog

| event_type   | module          | visible_to_user | payload摘要                           |
| ------------ | --------------- | --------------: | ----------------------------------- |
| verifier_log | VerifierService |               是 | status、score、failed_checks、warnings |
| tool_log     | MockAPIService  |               是 | Verifier触发的状态刷新                     |
| error_log    | VerifierService |               否 | VERIFIER_RESULT_INVALID             |

#### 失败与降级

| 失败情况               | 降级策略                                                |
| ------------------ | --------------------------------------------------- |
| VerifierResult结构非法 | 返回`VERIFIER_RESULT_INVALID`                         |
| Mock状态缺失           | 返回`MOCK_STATUS_MISSING`或warning                     |
| 可执行窗口过期            | 返回`PLAN_EXECUTABLE_WINDOW_EXPIRED`，引导refresh-window |
| fail且可恢复           | 触发RecoveryPlanner                                   |
| fail且不可恢复          | 阻断执行，展示原因                                           |

#### 验收标准

1. VerifierResult.status只能是`pass`、`warning`、`fail`。
2. P0执行前必须至少做`tool_action_integrity`轻量检查。
3. warning必须给风险说明和PlanB。
4. fail不可恢复时不得进入Executor。
5. fail可恢复时必须触发Recovery。
6. Verifier不能被LLM绕过。

---

## 14.Executor工作流

### ExecutorService

#### 模块定位

Executor在用户确认后执行PlanContract中的ToolAction。P0执行均为Mock，不产生真实交易、不真实发送消息、不真实订座。

#### 是否P0

是。

#### 输入

| 输入对象                | 来源           | 是否必填 | 说明                          |
| ------------------- | ------------ | ---: | --------------------------- |
| plan_id             | API路径        |    是 | `plan_`前缀                   |
| PlanContract        | PlanService  |    是 | status必须为`executable`或可确认状态 |
| confirmed           | 请求体          |    是 | 必须为true                     |
| X-Idempotency-Key   | HTTP Header  |    是 | 执行类接口必填                     |
| execute_action_ids  | 请求体          |    否 | 不传执行全部pending关键动作           |
| allow_auto_recovery | 请求体          |    否 | 默认true                      |
| trace_id            | PlanContract |    是 | 写executor_log               |

#### 输出

| 输出对象                 | 去向                                   | 是否进入03 Schema | 说明             |
| -------------------- | ------------------------------------ | ------------: | -------------- |
| ExecutionResult      | API响应/PlanContract.execution_summary |             是 | 执行结果           |
| action_results       | ExecutionResult                      |             是 | 动作结果           |
| vouchers             | ExecutionResult                      |             是 | Mock凭证         |
| RecoveryResult[]     | RecoveryPlanner                      |             是 | 触发恢复时返回        |
| active_plan_id       | API响应                                |             是 | 当前应展示计划ID      |
| active_plan_contract | API响应                                |             是 | 完整PlanContract |

#### 是否允许LLM参与

不允许。Executor只执行ToolAction。

#### 执行前条件

1. HTTP执行接口必须带`X-Idempotency-Key`。
2. 内部ToolAction必须有`idempotency_key`。
3. PlanContract必须通过SchemaValidator。
4. VerifierResult.status不得为`fail`。
5. 可执行窗口未过期；过期则返回`PLAN_EXECUTABLE_WINDOW_EXPIRED`或调用refresh-window。

#### ToolAction状态机

```text
pending
→ running
→ success / failed
→ recovered / skipped
```

#### 工作步骤

1. 校验`confirmed=true`。
2. 校验HTTP幂等键。
3. 读取PlanContract和ToolAction。
4. 按`depends_on`拓扑顺序执行。
5. 每个ToolAction执行前设为`running`。
6. 调用MockAPI执行：

   * `book_activity`
   * `reserve_restaurant`
   * `order_item`
   * `send_message`
7. MockAPI返回成功时写`success`和Mock凭证。
8. MockAPI返回失败时写`failed`和`error_code`。
9. 若错误可恢复且`allow_auto_recovery=true`，触发RecoveryPlanner。
10. Recovery成功后，原动作标记`recovered`，Executor基于`updated_plan_id`继续执行替换ToolAction。
11. 汇总ExecutionResult。
12. 写`executor_log`和必要的`recovery_log`。

#### Mock凭证要求

所有Mock凭证必须包含：

```json
{
  "mock_only": true
}
```

消息发送结果只能表示模拟发送，例如：

```json
{
  "message_id": "mock_message_M4096",
  "mock_only": true
}
```

不得暗示真实微信或短信已发送。

#### TraceLog

| event_type   | module          | visible_to_user | payload摘要                          |
| ------------ | --------------- | --------------: | ---------------------------------- |
| executor_log | ExecutorService |               是 | execution_id、action_id、status      |
| tool_log     | MockAPIService  |               是 | tool_name、mock_only、result_summary |
| recovery_log | RecoveryPlanner |               是 | trigger、updated_plan_id            |
| error_log    | ExecutorService |               否 | IDEMPOTENCY_CONFLICT、action_failed |

#### 失败与降级

| 失败情况                | 降级策略                                                |
| ------------------- | --------------------------------------------------- |
| 缺少X-Idempotency-Key | 返回BAD_REQUEST                                       |
| 幂等键冲突               | 返回`IDEMPOTENCY_CONFLICT`                            |
| 可执行窗口过期             | 返回`PLAN_EXECUTABLE_WINDOW_EXPIRED`，引导refresh-window |
| NO_TABLE_AVAILABLE  | 触发Recovery                                          |
| ACTIVITY_FULL       | 触发Recovery                                          |
| Recovery失败          | 展示PlanB或失败原因                                        |
| 非关键消息动作失败           | 可标记skipped，不阻断核心预约                                  |

#### 验收标准

1. Executor只执行ToolAction，不执行自然语言。
2. 必须按`depends_on`顺序执行。
3. 执行类HTTP接口必须要求`X-Idempotency-Key`。
4. 每个ToolAction必须有内部`idempotency_key`。
5. Mock预约、订座、下单、发消息都返回Mock凭证。
6. 不生成真实交易，不真实发送消息。

---

## 15.RecoveryPlanner工作流

### RecoveryPlanner

#### 模块定位

RecoveryPlanner在Verifier或Executor发现可恢复失败时，对当前计划做局部修复，生成新的完整PlanContract和RecoveryResult。

#### 是否P0

是。

#### P0必须覆盖触发器

| trigger/error_code             | 场景      | P0/P1   |
| ------------------------------ | ------- | ------- |
| NO_TABLE_AVAILABLE             | 餐厅满座    | P0      |
| ACTIVITY_FULL                  | 活动满员    | P0      |
| PLAN_EXECUTABLE_WINDOW_EXPIRED | 可执行窗口过期 | P0      |
| ROUTE_DELAY                    | 路线延迟    | P1/P2预留 |
| WEATHER_RISK_HIGH              | 天气风险升高  | P1/P2预留 |
| BUDGET_EXCEEDED                | 预算超限    | P1/P2预留 |

#### 输入

| 输入对象                  | 来源                        |    是否必填 | 说明                             |
| --------------------- | ------------------------- | ------: | ------------------------------ |
| original PlanContract | PlanService               |       是 | 原完整计划                          |
| failed_action         | Executor                  | 执行失败时必填 | 包含action_id、step_id、error_code |
| failed_check          | Verifier                  | 验证失败时必填 | 包含check.name、recoverable       |
| BackupPlan[]          | PlanContract.backup_plans |       否 | 优先读取已验证备选                      |
| CandidateRetriever    | 服务调用                      |       否 | BackupPlan不足时重新检索              |
| trace_id              | PlanContract              |       是 | 写recovery_log                  |

#### 输出

| 输出对象                 | 去向                            | 是否进入03 Schema | 说明               |
| -------------------- | ----------------------------- | ------------: | ---------------- |
| RecoveryResult       | PlanContract.recovery_results |             是 | 最终结构             |
| updated_plan_id      | Executor/API                  |             是 | 新PlanContract ID |
| updated PlanContract | PlanService                   |             是 | 完整新计划            |
| Recovery Diff        | 前端投影                          |             否 | 给用户展示替换差异        |

#### 是否允许LLM参与

只允许润色`user_explanation`。不得由LLM决定替换是否可执行。

#### RecoveryResult结构

必须使用03结构：

```json
{
  "recovery_id": "rec_0001",
  "trigger": "NO_TABLE_AVAILABLE",
  "status": "success",
  "original": {},
  "replacement": {},
  "diff": {},
  "updated_plan_id": "plan_0001_r1",
  "verifier_result": {},
  "user_explanation": "...",
  "created_at": "2026-05-20T13:20:10+08:00"
}
```

禁止使用旧字段：

```text
original_step_id
original_poi
new_poi
changes
```

#### BackupPlan规则

BackupPlan不是完整PlanContract。必须使用：

```text
backup_plan_id
trigger
description
replace_step_id
original_poi_id
new_poi_id
expected_diff
verifier_result
priority
status
```

#### 工作步骤

1. 接收失败触发器。
2. 判断是否可恢复。
3. 优先读取PlanContract.backup_plans中`status=verified`且`trigger`匹配的BackupPlan。
4. 若无可用BackupPlan，调用CandidateRetriever检索同类替代。
5. 局部替换失败节点：

   * 餐厅满座：替换餐厅Step和相关ToolAction。
   * 活动满员：替换活动Step和相关ToolAction。
   * 窗口过期：刷新状态或重排时间。
6. 保留原目标、核心约束、参与人和大部分时间线。
7. 重新查询路线、余位、票务、天气。
8. 生成新的内部PlanBuildCandidate。
9. 对新候选执行Verifier。
10. Verifier通过或warning可执行后，组装新的完整PlanContract，使用新`plan_id`，如`plan_20260520_0001_r1`。
11. 对新PlanContract执行Full SchemaValidator。
12. 若Verifier通过或warning可执行，且Full SchemaValidator通过：

    * 原PlanContract.status=`recovered`。
    * RecoveryResult.status=`success`。
    * RecoveryResult.updated_plan_id指向新计划。
13. 若Verifier或Full SchemaValidator失败：

    * RecoveryResult.status=`failed`或`partial`。
    * 不继续执行。
14. 前端展示Recovery Diff，而不是展示底层复杂日志。
15. 写`recovery_log`。

#### TraceLog

| event_type   | module          | visible_to_user | payload摘要                                      |
| ------------ | --------------- | --------------: | ---------------------------------------------- |
| recovery_log | RecoveryPlanner |               是 | trigger、status、updated_plan_id、diff_summary    |
| verifier_log | VerifierService |               是 | recovered_plan_verifier_status                 |
| tool_log     | MockAPIService  |               是 | replacement status checks                      |
| error_log    | RecoveryPlanner |               否 | RECOVERY_RESULT_INVALID、recovery_failed_reason |

#### 失败与降级

| 失败情况               | 降级策略                        |
| ------------------ | --------------------------- |
| 无BackupPlan        | 重新检索同类候选                    |
| 替换后Verifier fail   | 展示失败原因和人工可选PlanB            |
| RecoveryResult结构非法 | 返回`RECOVERY_RESULT_INVALID` |
| 多次Recovery冲突       | 保留最新active_plan_id，旧计划不覆盖   |
| 用户不允许自动恢复          | 展示Recovery Diff，等待用户确认      |

#### 验收标准

1. Recovery必须局部替换，不改变核心目标。
2. 原PlanContract不被原地覆盖。
3. 原`plan_id`进入`recovered`状态。
4. 新计划使用`updated_plan_id`。
5. 替换后必须重新Verifier。
6. RecoveryResult必须包含`original`、`replacement`、`diff`。

---

## 16.Consensus Agent工作流

### ConsensusService

#### 模块定位

ConsensusService负责朋友局共识导航：生成候选方案组、创建投票页、收集投票、实时统计、finalize后生成ConsensusSummary，再将共识约束交给PlanGenerator生成最终PlanContract。

#### 是否P0

是，基础版。

#### 输入

| 输入对象                 | 来源               | 是否必填 | 说明           |
| -------------------- | ---------------- | ---: | ------------ |
| candidate_plan_ids   | PlanGenerator    |    是 | 候选方案组        |
| plan_group_id        | PlanService      |    是 | `plangrp_`前缀 |
| creator_user_id      | API              |    是 | 发起人          |
| vote_page_id         | ConsensusService |    是 | `vpage_`前缀   |
| consensus_session_id | ConsensusService |    是 | `cs_`前缀      |
| ConsensusVote        | 投票页              |    是 | 单个朋友投票       |
| trace_id             | 上游trace          |    是 | 写TraceLog    |

#### 输出

| 输出对象                   | 去向            |     是否进入03 Schema | 说明             |
| ---------------------- | ------------- | ----------------: | -------------- |
| ConsensusSession       | Data Store    |                 是 | 共识会话           |
| RealtimeConsensusStats | 前端投票页         |              否/投影 | 未finalize前展示   |
| ConsensusSummary       | PlanGenerator |                 是 | finalize后生成    |
| consensus_constraints  | PlanGenerator | 是/进入ConstraintSet | 共识约束           |
| final_plan_id          | API响应         |                 是 | finalize后生成    |
| final_plan_contract    | PlanService   |                 是 | 完整PlanContract |

#### 投票校验规则

1. `liked_plan_ids`、`disliked_plan_ids`、`free_text`三者至少一个有效。
2. `liked_plan_ids`和`disliked_plan_ids`不能重叠。
3. finalize后默认不允许继续修改投票。
4. 投票非法返回`CONSENSUS_VOTE_INVALID`。
5. `liked_plan_ids`不是必填。

#### 不允许新增字段

ConsensusSummary不要新增`quality_flags`。投票不足时使用`detected_conflicts`表达`low_vote_count`。

#### 工作流

```text
候选方案组生成
→ 创建consensus_session_id/vote_page_id/plan_group_id
→ 收集投票
→ 校验投票
→ 实时统计RealtimeConsensusStats
→ finalize
→ ConsensusSummary
→ 共识约束
→ 重新生成最终候选
→ Verifier
→ PlanContractBuilder
→ Full SchemaValidator
→ 返回最终方案
```

#### 工作步骤

1. 基于朋友局输入生成3～4个候选PlanContract。
2. 创建`plan_group_id`、`consensus_session_id`、`vote_page_id`。
3. ConsensusSession状态从`created`进入`collecting`。
4. 投票页收集：

   * liked_plan_ids
   * disliked_plan_ids
   * budget_max
   * time_preference
   * walking_tolerance
   * queue_tolerance
   * free_text
5. 每次投票先校验，再保存ConsensusVote。
6. 更新RealtimeConsensusStats。
7. 未finalize时不能伪造ConsensusSummary。
8. 发起人调用finalize。
9. ConsensusSession状态进入`closed`或`expired`，随后进入`finalized`。
10. 生成ConsensusSummary。
11. 投票不足时，在`detected_conflicts`中加入`type:"low_vote_count"`。
12. 将ConsensusSummary转为`consensus_constraints`。
13. 调用PlanGenerator重新生成最终方案候选。
14. Verifier检查最终候选。
15. PlanContractBuilder生成完整final PlanContract。
16. Full SchemaValidator校验。
17. finalize后生成`final_plan_id`。
18. 返回最终方案和群聊消息草案。

#### TraceLog

| event_type     | module           | visible_to_user | payload摘要                                 |
| -------------- | ---------------- | --------------: | ----------------------------------------- |
| intent_log     | ConsensusService |               是 | plan_group_id、candidate_count             |
| tool_log       | ConsensusService |               是 | vote_page_created、vote_saved              |
| constraint_log | ConsensusService |               是 | consensus_constraints_summary             |
| verifier_log   | VerifierService  |               是 | final_plan_verifier_status                |
| error_log      | ConsensusService |               否 | CONSENSUS_VOTE_INVALID、CONSENSUS_CONFLICT |

#### 失败与降级

| 失败情况                         | 降级策略                                              |
| ---------------------------- | ------------------------------------------------- |
| 投票非法                         | 返回`CONSENSUS_VOTE_INVALID`                        |
| 投票人数少                        | 用`detected_conflicts`表达`low_vote_count`，可基于已有反馈生成 |
| 强冲突                          | P1可返回`CONSENSUS_CONFLICT`，P0给发起人确认                |
| finalize后再投票                 | 拒绝或返回当前finalized结果                                |
| 最终PlanContract Verifier fail | 触发Recovery或阻断final_plan_id生成                      |

#### 验收标准

1. 统一使用`consensus_session_id`、`vote_page_id`、`plan_group_id`、`vote_id`。
2. 未finalize时只能返回RealtimeConsensusStats，不能伪造ConsensusSummary。
3. finalize后才生成`final_plan_id`。
4. 投票不足用`detected_conflicts`表达`low_vote_count`。
5. 最终PlanContract仍必须经过Verifier。
6. 群聊消息只作为文案，不代表真实微信发送。

---

## 17.Feedback与MemoryCandidate工作流

### FeedbackService

#### 模块定位

FeedbackService在计划执行后收集低打扰反馈，用于生成MemoryCandidate。反馈不阻断主流程。

#### 是否P0

是，最小闭环。

#### 输入

| 输入对象             | 来源              | 是否必填 | 说明             |
| ---------------- | --------------- | ---: | -------------- |
| plan_id          | 执行结果页/API请求    |    是 | P0严格遵循`POST /api/v1/feedback`契约 |
| execution_id     | 执行结果页           |    否 | 关联执行           |
| rating           | 用户              |    否 | 轻量评分，如`just_right` |
| selected_options | 用户              |    否 | 选项反馈，如`queue_too_long` |
| free_text        | 用户              |    否 | 文本反馈           |
| skipped          | 用户              |    否 | 用户可跳过          |
| trace_id         | PlanContract     |    是 | 复用Plan trace，写feedback_log  |

#### 输出

| 输出对象                      | 去向                | 是否进入03 Schema | 说明        |
| ------------------------- | ----------------- | ------------: | --------- |
| FeedbackRecord            | Data Store        |            可选 | 反馈记录      |
| MemoryCandidate[]         | LifeMemoryService |             是 | 候选记忆      |
| UserVisibleFeedbackResult | 前端                |             否 | 反馈感谢、候选提示 |

#### 规则

1. 反馈最多2个问题。
2. 用户可以跳过。
3. 跳过不阻断主流程。
4. 反馈可生成MemoryCandidate。
5. 不得自动写入高敏记忆。
6. 中敏记忆必须待确认。
7. 关闭个性化时不写长期记忆，但可保留当次匿名反馈用于Demo展示，不能进入长期LifeMemory。
8. P0反馈入参严格遵循04的`POST /api/v1/feedback`契约；若未来支持非计划级反馈，应另行扩展API。

#### 工作步骤

1. 执行完成后展示反馈入口。
2. 第一问：整体感受。
3. 第二问：只追问一个关键原因。
4. 用户跳过则写`feedback_log`，流程结束。
5. 用户提交后生成反馈记录。
6. MemoryCandidateGenerator抽取候选。
7. PrivacyClassifier分类。
8. CandidateReviewer决定状态：

   * low：candidate或pending_confirmation。
   * medium：pending_confirmation。
   * high：ignored/deleted，不保存长期记忆。
9. 返回候选展示或确认入口。
10. 写`memory_log`。

#### TraceLog

| event_type   | module            | visible_to_user | payload摘要                           |
| ------------ | ----------------- | --------------: | ----------------------------------- |
| feedback_log | FeedbackService   |               是 | submitted/skipped、question_count    |
| memory_log   | LifeMemoryService |               是 | candidate_count、sensitivity_summary |
| error_log    | LifeMemoryService |               否 | MEMORY_PRIVACY_VIOLATION            |

#### 验收标准

1. 反馈问题不超过2个。
2. 用户跳过不阻断流程。
3. 反馈可生成MemoryCandidate。
4. 中敏候选必须待确认。
5. 高敏默认丢弃。
6. 关闭个性化时不写长期记忆。

---

## 18.Trace、Logging与可观测性工作流

### LoggingService

#### 模块定位

LoggingService负责记录每个Agent步骤的TraceLog，并生成用户可见的UserVisibleTraceEvent投影。

#### 是否P0

是。

#### TraceLog事件类型

只能使用：

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

禁止使用：

```text
input
intent
mock_call
verifier
recovery
executor
```

#### 输入

| 输入对象            | 来源             | 是否必填 | 说明                 |
| --------------- | -------------- | ---: | ------------------ |
| trace_id        | InputGateway   |    是 | `trace_`前缀         |
| event_type      | 各模块            |    是 | 只能用最终枚举            |
| module          | 各模块            |    是 | 模块名                |
| payload         | 各模块            |    是 | 脱敏摘要               |
| visible_to_user | 各模块            |    是 | 用户页是否展示            |
| level           | 各模块            |    是 | info/warning/error |
| created_at      | system_runtime |    是 | ISO 8601           |

#### 输出

| 输出对象                  | 去向                                  | 是否进入03 Schema | 说明                   |
| --------------------- | ----------------------------------- | ------------: | -------------------- |
| TraceLog              | Data Store                          |             是 | 完整日志                 |
| UserVisibleTraceEvent | `GET /api/v1/plans/{plan_id}/trace` |          否/投影 | 用户可见投影               |
| DebugTrace            | Debug/评委模式                          |          否/脱敏 | 不含Prompt、推理链、API Key |

#### 用户可见投影规则

`GET /api/v1/plans/{plan_id}/trace`返回的是UserVisibleTraceEvent投影，不是TraceLog本体。

普通用户页可展示：

| 可展示             | 不可展示                |
| --------------- | ------------------- |
| 已理解目标           | 底层Prompt            |
| 已检查余位           | LLM推理链              |
| 已估算路线           | API Key             |
| Verifier结果摘要    | 高敏MemoryCandidate   |
| Recovery Diff摘要 | ToolAction敏感payload |
| Mock标识          | failure_injection   |

#### 工作步骤

1. InputGateway创建trace_id。
2. 每个Agent模块写TraceLog。
3. 对payload做脱敏。
4. 设置`visible_to_user`。
5. 写入Data Store。
6. ResponseAssembler读取可见日志生成工具调用链。
7. Debug/评委模式可展示更多脱敏字段。
8. 普通用户页只展示投影。

#### TraceLog事件映射

| Agent步骤    | event_type     | visible_to_user建议 |
| ---------- | -------------- | ----------------: |
| 用户输入       | input_log      |                 是 |
| 场景识别       | intent_log     |                 是 |
| 约束抽取       | constraint_log |                 是 |
| 记忆读取/候选生成  | memory_log     |          是，隐藏敏感内容 |
| POI召回      | poi_log        |                 是 |
| MockAPI调用  | tool_log       |                 是 |
| Schema校验失败 | error_log      |                 否 |
| Verifier检查 | verifier_log   |                 是 |
| Recovery触发 | recovery_log   |                 是 |
| Executor执行 | executor_log   |                 是 |
| 反馈提交       | feedback_log   |                 是 |
| 系统异常       | error_log      |                 否 |

#### 验收标准

1. 每个主流程必须有`trace_id`。
2. 计划生成、验证、执行、恢复、反馈必须贯穿同一trace。
3. MockAPI调用必须写`tool_log`。
4. 用户页Trace只展示UserVisibleTraceEvent投影。
5. 不展示Prompt、LLM推理链、API Key、高敏MemoryCandidate。
6. 完整TraceLog只用于Debug/评委模式。

---

## 19.状态机与Agent触发关系

### 19.1PlanContract状态流转

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

| 状态         | 触发Agent/服务                 | 进入条件                            |    前端展示 | 说明                  |
| ---------- | -------------------------- | ------------------------------- | ------: | ------------------- |
| draft      | PlanService                | 创建plan_id，尚未完整生成                | Debug可见 | 内部状态                |
| generated  | PlanGenerator/预检          | DraftPlan已形成PlanBuildCandidate | Debug可见 | 未验证                 |
| verifying  | VerifierService            | 进入Verifier                      |   可展示进度 | 校验中                 |
| verified   | VerifierService/Builder     | Verifier pass/warning并组装完整PlanContract |     可展示 | 已验证                 |
| executable | Builder/Full SchemaValidator | 可执行窗口、ToolAction和完整Schema均合法       |       是 | 用户可确认               |
| confirmed  | API/用户                     | 用户点击确认执行                        |       是 | 待执行                 |
| executing  | ExecutorService            | 开始执行ToolAction                  |       是 | 执行中                 |
| completed  | ExecutorService            | 关键动作成功                          |       是 | 进入反馈                |
| recovered  | RecoveryPlanner            | 原计划版本交接完成                       |       是 | active_plan_id指向新计划 |
| failed     | Verifier/Executor/Recovery | 不可恢复失败                          |       是 | 展示失败原因              |
| expired    | Verifier/refresh-window    | 可执行窗口过期                         |       是 | 可刷新                 |
| cancelled  | 用户/API                     | 用户取消                            |       是 | 结束                  |

### 19.2ToolAction状态流转

```text
pending
→ running
→ success / failed
→ recovered / skipped
```

| 状态        | 触发模块                |       前端展示 | 说明             |
| --------- | ------------------- | ---------: | -------------- |
| pending   | PlanContractBuilder | Debug/部分展示 | 已生成未执行         |
| running   | ExecutorService     |          是 | 调用MockAPI中     |
| success   | MockAPIService      |          是 | 成功，返回Mock凭证    |
| failed    | MockAPIService      |          是 | 失败，含error_code |
| recovered | RecoveryPlanner     |          是 | 已由替代动作接管       |
| skipped   | ExecutorService/用户  |          是 | 非关键动作跳过        |

### 19.3ConsensusSession状态流转

```text
created
→ collecting
→ closed / expired
→ finalized
```

| 状态         | 触发模块                 | 前端展示 | 说明                                |
| ---------- | -------------------- | ---: | --------------------------------- |
| created    | ConsensusService     |    是 | 投票页创建                             |
| collecting | 投票页/ConsensusService |    是 | 收集中                               |
| closed     | 发起人                  |    是 | 停止投票                              |
| expired    | 系统时间                 |    是 | 超时                                |
| finalized  | ConsensusService     |    是 | 已生成ConsensusSummary和final_plan_id |

### 19.4LifeMemory状态流转

```text
candidate
→ pending_confirmation
→ enabled / ignored / deleted
→ disabled / expired
```

| 状态                   | 触发模块/用户                  | 前端展示 | 说明         |
| -------------------- | ------------------------ | ---: | ---------- |
| candidate            | MemoryCandidateGenerator |    是 | 候选记忆       |
| pending_confirmation | PrivacyClassifier        |    是 | 中敏或低置信度待确认 |
| enabled              | 用户确认/规则允许                |    是 | 可用于后续规划    |
| ignored              | 用户忽略                     |    是 | 不启用        |
| deleted              | 用户删除                     |    是 | 不再使用       |
| disabled             | 用户关闭个性化                  |    是 | 暂停使用       |
| expired              | TTL到期                    |  可展示 | 过期不可用      |

---

## 20.错误处理与降级策略

| 错误/场景                 | 触发模块               | 错误码                               | 降级策略                      |   是否返回前端 |
| --------------------- | ------------------ | --------------------------------- | ------------------------- | -------: |
| LLM解析失败               | IntentParser       | 无需直接报错；未预期异常用INTERNAL_ERROR | 降级到规则模板                   | 是，用户友好文案 |
| 候选POI不足               | CandidateRetriever | PLAN_STEP_POI_NOT_FOUND           | 扩大半径或切换同类POI              |      可展示 |
| Mock状态缺失              | MockAPIService     | MOCK_STATUS_MISSING               | 降低置信度或换POI                |        是 |
| PlanContract Schema失败 | SchemaValidator    | PLAN_SCHEMA_INVALID               | 不返回前端，重试生成一次              |   是，失败文案 |
| 时间线非法                 | SchemaValidator    | PLAN_TIMELINE_INVALID             | 重排或Recovery               |        是 |
| ToolAction非法          | SchemaValidator    | TOOL_ACTION_INVALID               | 阻断执行                      |        是 |
| Verifier失败可恢复         | VerifierService    | 领域错误码                             | 触发Recovery                |  是，展示恢复中 |
| Verifier失败不可恢复        | VerifierService    | VERIFIER_RESULT_INVALID或具体错误      | 阻断执行                      |        是 |
| Recovery失败            | RecoveryPlanner    | RECOVERY_RESULT_INVALID或具体错误      | 展示人工可选PlanB或失败原因          |        是 |
| 执行幂等冲突                | ExecutorService    | IDEMPOTENCY_CONFLICT              | 返回已有结果或拒绝                 |        是 |
| 可执行窗口过期               | Verifier/Executor  | PLAN_EXECUTABLE_WINDOW_EXPIRED    | 调用refresh-window或重新verify |        是 |
| LifeMemory隐私违规        | LifeMemoryService  | MEMORY_PRIVACY_VIOLATION          | 不保存高敏内容                   |    是，弱提示 |
| Consensus投票非法         | ConsensusService   | CONSENSUS_VOTE_INVALID            | 拒绝保存，提示修改                 |        是 |

错误展示原则：

1. 前端展示`user_message`，不展示底层堆栈。
2. Debug细节仅限Debug/评委模式。
3. 可恢复错误优先展示“正在为你切换/刷新”。
4. 不可恢复错误给出原因和重新生成入口。
5. 所有错误必须写`error_log`。

---

## 21.Prompt与LLM使用边界

### 21.1LLM可以做

| 能力                  | 输出去向                            | 是否需要校验 |
| ------------------- | ------------------------------- | -----: |
| 目标理解摘要              | UserGoal.goal_summary           |      是 |
| 场景初判                | IntentParser候选                  |      是 |
| 约束候选抽取              | ConstraintExtractor候选           |      是 |
| 候选计划草案              | DraftPlan                       |      是 |
| 自然语言解释              | ResponseAssembler               |      是 |
| 群聊消息草案              | PlanContract.messages           |      是 |
| 纪念日话术               | PlanContract.messages           |      是 |
| Recovery用户解释润色      | RecoveryResult.user_explanation |      是 |
| MemoryCandidate内容草案 | MemoryCandidate                 | 必须隐私审核 |

### 21.2LLM不能做

| 禁止项                         |
| --------------------------- |
| 直接确认餐厅有位                    |
| 直接确认活动可预约                   |
| 直接确认路线通畅                    |
| 直接确认天气安全                    |
| 直接确认执行成功                    |
| 绕过Verifier                  |
| 写入长期LifeMemory              |
| 自动保存高敏记忆                    |
| 输出不符合03 Schema的PlanContract |
| 暴露Prompt、推理链或内部工具密钥         |

### 21.3Prompt安全规则

1. Prompt不得写入TraceLog。
2. LLM推理链不得进入API响应。
3. API Key不得进入TraceLog、Debug投影或前端。
4. LLM输出必须经过结构化解析和SchemaValidator。
5. LLM输出中的“已订座、已发送、已付款”等真实执行表达必须被过滤。
6. LLM生成消息时必须标记为草案，真实发送只允许MockAPI返回Mock凭证。

---

## 22.P0端到端工作流样例

### 22.1样例1：家庭亲子主链路

输入：

```text
今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。
```

| 步骤 | 模块                  | 输入                             | 输出                                           | TraceLog       | 关键校验                    |
| -: | ------------------- | ------------------------------ | -------------------------------------------- | -------------- | ----------------------- |
|  1 | InputGateway        | raw_text                       | trace_id=`trace_...`                         | input_log      | 输入非空                    |
|  2 | IntentParser        | raw_text                       | scenario=`family_parent_child`               | intent_log     | 不能决定可执行状态               |
|  3 | ConstraintExtractor | raw_text、scenario              | party_size=3、孩子5岁、低卡、距离近、少排队                 | constraint_log | 默认值标assumption          |
|  4 | MemoryRetriever     | user_id、use_memory             | P0可返回空或MemoryUsage[]                         | memory_log     | 个性化关闭则不读                |
|  5 | CandidateRetriever  | ConstraintSet                  | 亲子活动、低卡餐厅、轻松散步候选                             | poi_log        | 候选POI有`poi_`前缀          |
|  6 | MockAPIService      | poi_id、arrival_time、party_size | 余票、余位、路线、天气                                  | tool_log       | 状态必须source=`mock_api`   |
|  7 | PlanGenerator       | 候选和约束                          | DraftPlan：亲子活动→低卡餐厅→散步                       | intent_log     | DraftPlan不是PlanContract |
|  8 | PlanBuildCandidate预检 | DraftPlan                      | 内部候选对象                                      | tool_log       | 不进入03/04契约              |
|  9 | VerifierService     | PlanBuildCandidate、Mock状态      | VerifierResult warning/pass、ExecutableWindow | verifier_log   | 检查余位、预算、路线、天气           |
| 10 | PlanContractBuilder | VerifierResult、内部候选             | 完整PlanContract                                | tool_log       | PlanStep必填字段齐全          |
| 11 | Full SchemaValidator | 完整PlanContract                | pass                                         | error_log仅失败   | 不合法不得返回                 |
| 12 | PlanRanker          | 候选计划                           | 选择最稳方案                                       | verifier_log   | 规则排序                    |
| 13 | ResponseAssembler   | PlanContract                   | PlanContractView、PlanB、可执行窗口                 | tool_log       | 展示投影不冒充本体               |

期望输出：

```text
IntentParser识别family_parent_child；
ConstraintExtractor抽取孩子5岁、低卡、距离近、少排队；
CandidateRetriever检索亲子活动和低卡餐厅；
MockAPI查询余票、余位、路线、天气；
PlanGenerator生成时间线草案；
Verifier检查可执行性；
PlanContractBuilder生成完整PlanContract；
Full SchemaValidator校验完整PlanContract；
返回可执行窗口和PlanB。
```

### 22.2样例2：餐厅满座触发Recovery

触发场景：

```text
用户已确认执行，Executor执行reserve_restaurant时，MockAPI返回NO_TABLE_AVAILABLE。
```

| 步骤 | 模块                         | 输入                            | 输出                              | 状态变化                    | TraceLog     |
| -: | -------------------------- | ----------------------------- | ------------------------------- | ----------------------- | ------------ |
|  1 | ExecutorService            | act_reserve_0001              | running                         | pending→running         | executor_log |
|  2 | MockAPIService             | reserve_restaurant payload    | error_code=`NO_TABLE_AVAILABLE` | running→failed          | tool_log     |
|  3 | ExecutorService            | failed_action                 | 触发RecoveryPlanner               | ToolAction=failed       | executor_log |
|  4 | RecoveryPlanner            | 原PlanContract、BackupPlan      | 读取匹配BackupPlan                  | Plan仍executing          | recovery_log |
|  5 | CandidateRetriever/MockAPI | new_poi_id                    | 重新查询路线和余位                       | -                       | tool_log     |
|  6 | PlanBuildCandidate预检      | 替换后草案                         | 新内部候选对象                         | -                       | tool_log     |
|  7 | VerifierService            | 新内部候选对象                       | VerifierResult pass/warning     | -                       | verifier_log |
|  8 | PlanContractBuilder        | VerifierResult、替换后候选             | 新PlanContract：`plan_..._r1`     | 新plan executable        | tool_log     |
|  9 | Full SchemaValidator       | 新PlanContract                 | pass                            | -                       | error_log仅失败 |
| 10 | RecoveryPlanner            | original/replacement/diff     | RecoveryResult，updated_plan_id  | 原plan→recovered         | recovery_log |
| 11 | ExecutorService            | updated_plan_id中的替代ToolAction | 继续reserve_restaurant            | 新action running/success | executor_log |
| 12 | API                        | ExecutionResult               | active_plan_id=updated_plan_id  | completed/recovered     | executor_log |

必须满足：

```text
Executor执行reserve_restaurant；
MockAPI返回NO_TABLE_AVAILABLE；
RecoveryPlanner读取BackupPlan；
生成updated_plan_id；
替换餐厅；
重新查询路线和余位；
重新Verifier；
返回RecoveryResult和新的PlanContract。
```

### 22.3样例3：朋友局共识

输入：

```text
下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。
```

| 步骤 | 模块                  | 输入                       | 输出                                | 状态/对象                       | TraceLog       |
| -: | ------------------- | ------------------------ | --------------------------------- | --------------------------- | -------------- |
|  1 | IntentParser        | raw_text                 | scenario=`friend_group`           | UserGoal                    | intent_log     |
|  2 | ConstraintExtractor | raw_text                 | party_size=4、nearby、budget敏感、轻松   | ConstraintSet               | constraint_log |
|  3 | PlanGenerator       | 朋友局约束                    | 3～4个候选PlanContract                | plan_group_id=`plangrp_...` | intent_log     |
|  4 | ConsensusService    | candidate_plan_ids       | consensus_session_id、vote_page_id | created→collecting          | tool_log       |
|  5 | 朋友投票页               | liked/disliked/free_text | ConsensusVote                     | vote_id=`vote_...`          | tool_log       |
|  6 | ConsensusService    | votes                    | RealtimeConsensusStats            | collecting                  | tool_log       |
|  7 | ConsensusService    | finalize请求               | ConsensusSummary                  | closed/expired→finalized    | constraint_log |
|  8 | ConsensusService    | Summary                  | consensus_constraints             | -                           | constraint_log |
|  9 | PlanGenerator       | consensus_constraints    | final DraftPlan                   | -                           | intent_log     |
| 10 | VerifierService     | final内部候选对象             | VerifierResult                    | -                           | verifier_log   |
| 11 | PlanContractBuilder | VerifierResult、final候选   | final PlanContract                | final_plan_id               | tool_log       |
| 12 | Full SchemaValidator | final PlanContract       | pass                             | executable                  | error_log仅失败 |
| 13 | ResponseAssembler   | final PlanContract       | 最终方案和群聊消息                         | UserVisiblePlanProjection   | tool_log       |

必须满足：

```text
生成候选方案组；
创建vote_page_id；
朋友提交liked/disliked/free_text；
ConsensusService生成实时统计；
finalize后生成ConsensusSummary；
形成consensus_constraints；
Verifier检查；
重新生成final_plan_contract；
Full SchemaValidator校验；
返回最终方案和群聊消息。
```

### 22.4样例4：纪念日情绪导航

输入：

```text
想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。
```

| 步骤 | 模块                  | 输入                      | 输出                                 | 关键约束            |
| -: | ------------------- | ----------------------- | ---------------------------------- | --------------- |
|  1 | IntentParser        | raw_text                | scenario=`anniversary_emotion`     | 识别关系经营，不是普通吃饭   |
|  2 | ConstraintExtractor | raw_text                | emotion_intensity=`light`或`medium` | 控制仪式感强度         |
|  3 | CandidateRetriever  | 约束                      | 安静餐厅、散步/看展、合照点                     | 不选择过度夸张方案       |
|  4 | MockAPIService      | arrival_time、party_size | 餐厅余位、路线、天气                         | Mock状态显式标识      |
|  5 | PlanGenerator       | 候选                      | 自然流程草案                             | 散步/看展→餐厅→轻仪式→返程 |
|  6 | VerifierService     | 内部候选对象                  | VerifierResult                     | 检查余位、路线、预算、窗口   |
|  7 | PlanContractBuilder | VerifierResult、草案          | 完整PlanContract                     | 消息进入messages    |
|  8 | Full SchemaValidator | 完整PlanContract            | pass                              | 不合法不得返回         |
|  9 | ExecutorService     | send_message ToolAction | Mock message凭证                     | 不真实发送微信/短信      |

必须体现：

1. 识别`anniversary_emotion`。
2. 控制仪式感强度。
3. 安排自然流程。
4. 生成邀请话术。
5. 不真实发送微信/短信。
6. 仅通过Mock message返回凭证。

### 22.5样例5：反馈生成MemoryCandidate

输入：

```text
今天整体有点赶，餐厅还可以，但孩子好像更喜欢互动类活动。
```

| 步骤 | 模块                       | 输入                            | 输出                                        | 隐私规则      | TraceLog     |
| -: | ------------------------ | ----------------------------- | ----------------------------------------- | --------- | ------------ |
|  1 | FeedbackService          | 用户反馈                          | FeedbackRecord                            | 最多2问      | feedback_log |
|  2 | MemoryCandidateGenerator | 反馈文本                          | 候选：家庭亲子更偏互动活动                             | 低敏候选      | memory_log   |
|  3 | PrivacyClassifier        | 候选内容                          | sensitivity=`low`                         | 可进入候选     | memory_log   |
|  4 | CandidateReviewer        | low候选                         | status=`candidate`或`pending_confirmation` | 用户可确认/忽略  | memory_log   |
|  5 | PrivacyClassifier        | 涉及孩子年龄等                       | sensitivity=`medium`                      | 待确认       | memory_log   |
|  6 | PrivacyClassifier        | 高敏内容                          | ignored/deleted                           | 默认丢弃      | memory_log   |
|  7 | LifeMemoryService        | personalization_enabled=false | 不写长期记忆                                    | 关闭个性化不读不写 | memory_log   |

必须满足：

```text
反馈问题不超过2个；
生成MemoryCandidate；
敏感度分类；
中敏待确认；
高敏默认丢弃；
关闭个性化时不写长期记忆。
```

---

## 23.P1/P2扩展工作流预留

### 23.1P1增强

| 能力                 | 工作流预留                                         | 不影响P0 |
| ------------------ | --------------------------------------------- | ----: |
| LifeMemory完整管理页    | enabled/disabled/deleted/expired完整状态流         |     是 |
| 下次规划真实读取长期记忆       | MemoryRetriever读取enabled记忆并生成MemoryUsage      |     是 |
| 关闭个性化完整链路          | personalization_enabled=false后不读不写            |     是 |
| SocialSignalMock增强 | CandidateRetriever可选读取口碑Mock                  |     是 |
| Benchmark基础评测      | 对Trace、Verifier、Recovery做样例评估                 |     是 |
| 更多异常恢复类型           | ROUTE_DELAY、WEATHER_RISK_HIGH、BUDGET_EXCEEDED |     是 |

### 23.2P2预留

| 能力                  | 预留位置                          | 约束                            |
| ------------------- | ----------------------------- | ----------------------------- |
| PlanReward          | PlanRanker                    | 不能绕过Verifier                  |
| Goal-aware Reranker | CandidateRetriever/PlanRanker | 不能伪造Mock状态                    |
| 多模态反馈               | FeedbackService               | 不自动保存高敏内容                     |
| 更复杂共识策略             | ConsensusService              | 仍需finalize后生成ConsensusSummary |
| 更丰富数字孪生区域           | MockAPIService                | 仍需Mock标识                      |

---

## 24.测试验收标准

### 24.1主链路验收

| 编号    | 验收项             | 通过标准                                                                                               |
| ----- | --------------- | -------------------------------------------------------------------------------------------------- |
| WF-01 | trace_id贯穿      | PlanContract、ToolAction、VerifierResult、RecoveryResult、ExecutionResult、Consensus、MemoryCandidate可追溯 |
| WF-02 | PlanContract完整性 | 返回前通过03 Schema                                                                                     |
| WF-03 | LLM边界           | 不由LLM确认余位、路线、天气、执行成功                                                                               |
| WF-04 | Mock标识          | Mock状态、凭证、口碑按04对象类型显式标识                                                                            |
| WF-05 | Verifier闸门      | 未通过Verifier不得执行                                                                                    |
| WF-06 | Trace事件名        | 只使用最终event_type枚举                                                                                  |
| WF-07 | API路径           | 只引用`/api/v1`路径                                                                                     |

### 24.2模块验收

| 模块                  | 关键验收                                            |
| ------------------- | ----------------------------------------------- |
| IntentParser        | 三个P0场景识别正确，低置信度可降级                              |
| ConstraintExtractor | party_size、time_window、预算、距离、排队、饮食、儿童友好、情绪强度可抽取 |
| CandidateRetriever  | 候选不足可降级；Mock状态不由LLM生成                           |
| PlanGenerator       | DraftPlan不返回前端                                  |
| PlanContractBuilder | PlanStep、ToolAction必填字段齐全                       |
| SchemaValidator     | Schema失败返回`PLAN_SCHEMA_INVALID`                 |
| Verifier            | P0至少实现前8项检查，执行前建议强制`tool_action_integrity`，status合法 |
| Executor            | 幂等键必填，按depends_on执行                             |
| RecoveryPlanner     | 版本化Recovery，original/replacement/diff齐全         |
| ConsensusService    | 投票校验、finalize后生成Summary和final_plan_id           |
| LifeMemoryService   | 高敏不保存，中敏待确认，关闭个性化不读不写                           |
| LoggingService      | 用户Trace为投影，不含Prompt和推理链                         |

### 24.3端到端验收

| 场景           | 必须通过                                     |
| ------------ | ---------------------------------------- |
| 家庭亲子         | 生成可执行PlanContract、可执行窗口、PlanB            |
| 餐厅满座Recovery | NO_TABLE_AVAILABLE触发updated_plan_id      |
| 朋友局共识        | 投票→finalize→final_plan_contract→Verifier |
| 纪念日          | 轻仪式流程、邀请话术、Mock message凭证                |
| 反馈记忆         | 最多2问、生成MemoryCandidate、隐私分级              |

---

## 25.不做什么与安全边界

### 25.1P0明确不做

| 不做        | 正确表达                          |
| --------- | ----------------------------- |
| 真实支付      | 仅返回Mock订单凭证                   |
| 真实短信/微信发送 | 仅返回Mock message凭证             |
| 真实订座      | 仅模拟订座                         |
| 真实票务      | 仅模拟预约/订票                      |
| 真实第三方爬取   | SocialSignalMock只做Mock        |
| 全城覆盖      | 固定数字孪生区域                      |
| 不透明画像     | LifeMemory低打扰、可审计、用户可控        |
| 大模型训练     | 使用LLM Orchestrator+规则+MockAPI |
| 无边界闲聊     | 围绕PlanContract驱动闭环            |

### 25.2安全边界

1. 不展示Prompt。
2. 不展示LLM推理链。
3. 不展示API Key。
4. 不保存高敏记忆。
5. 中敏记忆必须用户确认。
6. Mock能力必须标识，不伪装真实平台能力。
7. Executor不得执行PlanContract之外的动作。
8. Recovery不得生成无关新计划。
9. Consensus不得在未finalize时伪造ConsensusSummary。
10. Trace投影不得泄露敏感payload。

---

## 26.附录：Agent步骤、Trace事件、Schema对象速查表

### 26.1Agent步骤速查

| 步骤 | 模块                  | 主要对象                                            | event_type              |
| -: | ------------------- | ----------------------------------------------- | ----------------------- |
|  1 | InputGateway        | raw_text、trace_id                               | input_log               |
|  2 | IntentParser        | UserGoal                                        | intent_log              |
|  3 | ConstraintExtractor | ConstraintSet、TimeWindow                        | constraint_log          |
|  4 | MemoryRetriever     | MemoryUsage                                     | memory_log              |
|  5 | CandidateRetriever  | POI、CandidateSet                                | poi_log                 |
|  6 | MockAPIService      | POIStatus、RouteEstimate、WeatherStatus           | tool_log                |
|  7 | PlanGenerator       | DraftPlan                                       | intent_log              |
|  8 | PlanBuildCandidate预检 | PlanBuildCandidate                              | tool_log                |
|  9 | VerifierService     | VerifierResult、ExecutableWindow、Risk            | verifier_log            |
| 10 | PlanContractBuilder | 完整PlanContract                                | tool_log                |
| 11 | Full SchemaValidator | Schema result                                   | error_log仅失败            |
| 12 | PlanRanker          | ranked PlanContract                             | verifier_log            |
| 13 | ResponseAssembler   | PlanContractView                                | tool_log                |
| 14 | ExecutorService     | ExecutionResult                                 | executor_log            |
| 15 | RecoveryPlanner     | RecoveryResult、updated_plan_id                  | recovery_log            |
| 16 | ConsensusService    | ConsensusSession、ConsensusVote、ConsensusSummary | tool_log/constraint_log |
| 17 | FeedbackService     | FeedbackRecord                                  | feedback_log            |
| 18 | LifeMemoryService   | MemoryCandidate、LifeMemory                      | memory_log              |

### 26.2Trace事件速查

| event_type     | 用途                     |
| -------------- | ---------------------- |
| input_log      | 用户输入                   |
| intent_log     | 场景识别、目标摘要、计划草案摘要       |
| constraint_log | 约束抽取、共识约束              |
| memory_log     | 记忆读取、候选生成、隐私分级         |
| poi_log        | POI/餐厅/活动候选检索          |
| tool_log       | MockAPI调用、工具动作摘要       |
| verifier_log   | Verifier检查             |
| recovery_log   | Recovery触发、版本交接、Diff摘要 |
| executor_log   | Executor执行动作           |
| feedback_log   | 用户反馈                   |
| error_log      | 错误、异常、Schema失败         |

### 26.3Schema对象速查

| 对象               | 归属                  | 说明                    |
| ---------------- | ------------------- | --------------------- |
| UserGoal         | IntentParser        | 用户目标结构化结果             |
| ConstraintSet    | ConstraintExtractor | 可验证约束集合               |
| PlanBuildCandidate | Agent内部预检       | Verifier前内部候选，不进入03/04契约 |
| PlanContract     | PlanService         | 完整计划本体                |
| PlanStep         | PlanContract        | 时间线节点                 |
| ToolAction       | Executor            | 可执行动作                 |
| BackupPlan       | Recovery            | 备选分支，不是完整PlanContract |
| VerifierResult   | Verifier            | 可执行性检查结果              |
| RecoveryResult   | Recovery            | 恢复结果，含updated_plan_id |
| ExecutionResult  | Executor            | 执行结果                  |
| ConsensusSession | Consensus           | 共识会话                  |
| ConsensusVote    | Consensus           | 单个投票                  |
| ConsensusSummary | Consensus           | finalize后共识摘要         |
| MemoryCandidate  | LifeMemory          | 待确认记忆候选               |
| LifeMemory       | LifeMemory          | 已确认或启用长期记忆            |
| TraceLog         | Logging             | 全链路日志                 |

### 26.4最终API入口速查

| 入口                                                       | 用途                |
| -------------------------------------------------------- | ----------------- |
| `POST /api/v1/plans/create`                              | 一句话生成PlanContract |
| `GET /api/v1/plans/{plan_id}`                            | 读取完整PlanContract  |
| `POST /api/v1/plans/{plan_id}/verify`                    | 重新验证计划            |
| `POST /api/v1/plans/{plan_id}/execute`                   | 用户确认后执行           |
| `POST /api/v1/plans/{plan_id}/recover`                   | 手动或内部触发恢复         |
| `POST /api/v1/plans/{plan_id}/refresh-window`            | 刷新可执行窗口           |
| `GET /api/v1/plans/{plan_id}/trace`                      | 读取用户可见Trace投影     |
| `POST /api/v1/consensus/create`                          | 创建共识投票            |
| `POST /api/v1/consensus/{consensus_session_id}/vote`     | 提交投票              |
| `POST /api/v1/consensus/{consensus_session_id}/finalize` | 生成共识结果            |
| `POST /api/v1/feedback`                                  | 提交低打扰反馈           |

### 26.5P0/P1/P2边界速查

| 阶段     | 必须/预留                                                                                                                                  |
| ------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| P0必须实现 | 家庭亲子主链路、PlanContract生成、MockAPI状态查询、Verifier、Executor、餐厅满座或活动满员Recovery、朋友局投票基础版、TraceLog基础记录、Feedback最小闭环、MemoryCandidate生成与展示/确认/忽略预留 |
| P1增强   | LifeMemory完整管理页、下次规划真实读取长期记忆、关闭个性化完整链路、SocialSignalMock增强、Benchmark基础评测、更多异常恢复类型                                                       |
| P2预留   | PlanReward、Goal-aware Reranker、多模态反馈、更复杂共识策略、更丰富数字孪生区域                                                                                 |

---

本文档收束后的核心原则：

```text
LifePilot不是LLM自由生成攻略；
LifePilot是PlanContract驱动的生活时间导航Agent。

LLM负责理解和表达；
MockAPI负责状态和执行模拟；
Verifier负责可执行性闸门；
Executor负责按ToolAction执行；
Recovery负责版本化局部修复；
Consensus负责多人共识约束；
LifeMemory负责低打扰、可审计、用户可控的候选记忆；
TraceLog负责全链路可观测。
```

## 23. 2026-05-23追加：受控标签归一化与Goal-aware推荐编排

本追加不新增公开领域对象，不改变`PlanContract`主结构；实现上仅在`ConstraintSet`中保留可解释的推荐画像，并由`CandidateRetriever`作为内部排序依据。

标签策略：

```text
用户原始输入/LLM候选标签
→ 受控标签归一化
→ tag_axes分桶
→ 推荐权重
→ POI组合打分
```

要求：

1. 原始输入允许开放表达，例如“别折腾”“自然一点”“想散心”“轻松约会”。
2. 进入推荐引擎前必须映射到受控标签，如`route_simple`、`low_key`、`date_friendly`、`low_queue`、`quiet_dining`。
3. 未命中受控表的开放词只可作为内部`raw_terms`解释，不直接扩散成新的用户可见枚举。
4. 推荐排序必须综合意图匹配、Mock状态、路线、预算、区域、评分和POI质量惩罚。
5. LLM不得确认余位、路线、天气或执行成功；相关状态仍由MockAPI与Verifier产生。
6. 推荐引擎输出仍必须进入`DraftPlan → PlanBuildCandidate → Verifier → PlanContractBuilder → SchemaValidator`链路，不得直接返回前端。

## 24. 2026-05-23追加：类脑推荐画像与POI语义建模

本追加不改变`PlanContract`主结构，不新增API路径。类脑推荐只作为`IntentParser → ConstraintExtractor → CandidateRetriever`之间的内部决策层，并以`ConstraintSet.recommendation_profile`的可解释投影保留。

核心机制：

```text
用户意图
→ need_state：情绪/关系/招待/约会/陪伴
→ scene_frame：小酌、手作约会、家人来访、轻探索等场景框架
→ preference_axes：人数、关系、预算、品质、动线、排队、区域
→ poi_semantics：从POI名称和标签补全酒馆、手作、漂亮饭、到访友好、低端连锁等语义
→ chain_scoring：活动/餐饮/收尾节点组合评分
→ Mock状态与Verifier硬闸门
```

边界要求：

1. LLM可以辅助抽取`need_state`和可读摘要，但不能决定POI状态、余位、路线、营业或执行成功。
2. `CandidateRetriever`必须先把开放表达映射到受控标签，再做POI语义补全；不能只按原始高德类别或距离排序。
3. 关系型意图必须影响排序：一个人小酌优先低压力酒馆和按时收住；女朋友手作约会优先参与感和品质正餐；家人来访优先招待友好、好聊天和代表性。
4. 品质意图必须进入惩罚项：`漂亮饭`、`约会`、`招待家人`不得退化为萨莉亚、麦当劳、米村拌饭、奶茶、纯咖啡、棋牌、KTV、电竞等低匹配节点。
5. 组合排序必须缓存单POI评分与状态快照，避免在500 POI候选池上重复调用Mock状态造成延迟。
6. 推荐结果仍必须经过`VerifierService`，`fail`不得执行，`warning`必须展示风险和PlanB。

## 25. 2026-05-23追加：显式餐饮锚点与亲子安全闸门

本追加不改变`PlanContract`主结构，不新增公开API。它补充类脑POI推荐中的硬约束优先级，避免显式餐饮诉求和关系安全被路线近邻或高评分节点覆盖。

新增内部编排规则：

```text
用户明说“晚饭/晚餐/晚上吃”
→ ConstraintSet.must_have追加dinner
→ CandidateRetriever使用dinner_last规划顺序
→ PlanGenerator按“下午活动/休息节点/晚饭餐厅”生成时间线
```

餐饮硬约束：

1. 用户明说“火锅”时，`hotpot`是餐厅硬约束；候选餐厅必须具备火锅语义，不能用茶空间、咖啡、甜品或普通正餐替代。
2. 用户明说“清淡/轻食/晚饭清淡”时，推荐画像必须包含`light_meal/light_food`，餐厅优先粥、面、汤、蒸菜、日式/料理、鱼、椰子鸡等低负担语义。
3. 清淡诉求未同时包含火锅时，火锅、烧烤、烤肉、麻辣、干锅、美蛙、酸辣等`spicy_heavy`语义不得作为晚饭节点。
4. 餐饮硬约束只影响内部候选排序和可执行计划，不新增对外Schema字段。

亲子安全闸门：

1. 家庭亲子活动必须具备`child_friendly/kid_safe/family_time/hands_on/craft/amusement`等语义之一。
2. 电竞、网咖、棋牌、KTV、台球、健身、游泳、PS5/VR、剧本杀、桌游、酒吧/酒馆等成人或高刺激节点不得作为亲子核心活动或收尾活动。
3. 商场、购物、美食街等泛地点不能仅凭近距离和高评分成为亲子活动；必须有明确亲子、手作或儿童可参与语义。
4. “不排长队/少排队”进入`low_queue`画像，并由Mock状态和Verifier继续校验。

## 28. 2026-05-23追加：类脑策略层解耦与烤肉餐饮锚点

本追加不改变`PlanContract`主结构，不新增公开API。它把类脑推荐从散落的样例规则收束为可维护策略层，并补充“烤肉/烧烤”显式餐饮锚点。

### 28.1内部对象边界

新增内部服务：

```text
BrainRecommendationEngine
```

新增可维护策略文件：

```text
backend/data/brain_policy.json
```

两者均为Agent内部实现，不进入03 Schema，不作为04 HTTP响应对象。普通用户页只展示合法中文投影，例如“类脑推荐优先级”，不得展示底层分数、权重、Prompt、推理链或API Key。

### 28.2编排规则

```text
UserGoal.intent_tags
ConstraintSet.recommendation_profile
Candidate POI文本/标签/价格/评分/区域
→ BrainRecommendationEngine.semantic_tags()
→ BrainRecommendationEngine.score_item()
→ CandidateRetriever组合评分
→ Verifier
```

类脑评分至少包含：

1. 感知语义：从POI名称和标签推断手作、酒馆、火锅、烤肉、亲子、低匹配活动等语义。
2. 关系调制：约会、亲子、家人来访、一个人散心使用不同槽位偏好。
3. 硬约束门控：明说火锅/烤肉/清淡餐时，餐厅槽位必须满足对应语义。
4. 奖励重排：意图匹配、角色槽位、评分先验、路线顺序共同决定候选链路排序。
5. Verifier兜底：状态、余位、路线、天气、可执行窗口仍由MockAPI和Verifier决定。

### 28.3烤肉锚点

新增内部受控标签：

```text
bbq
grill
```

触发词包括：

```text
烤肉、烧烤、烧肉、炭烤、烤串、烤吧、自助烤肉、日式烧肉、韩式烤肉
```

当用户明说“晚上想吃烤肉/烧烤”时：

1. `IntentParser`保留`bbq/grill/dinner/date_friendly`等画像。
2. `ConstraintExtractor.must_have`追加`bbq/grill/dinner`。
3. `CandidateRetriever`餐厅槽位必须命中`bbq`或`grill`语义。
4. `PlanGenerator`按`dinner_last`生成“下午活动 → 轻收尾 → 烤肉晚饭”时间线。
5. 如果烤肉候选状态不可用，后续由Verifier/Recovery处理，不得静默替换为咖啡、茶空间、普通餐厅或火锅。

### 28.4训练接入边界

本地训练模型可作为P1/P2重排器接入，但必须满足：

1. 输入是用户画像、POI文本语义、价格、评分、区域、路线、Mock状态等泛化特征，不以固定POI ID为主。
2. 输出是排序分或偏好分，不输出PlanContract字段，不确认真实状态。
3. 模型结果受`brain_policy.json`硬门控约束；策略可单独维护、回滚和热更新。
4. 模型不可用时，规则版BrainRecommendationEngine仍可完成P0 Demo。

## 29. 2026-05-23追加：POI语义对齐与日料餐饮锚点

本追加补充一句话输入与POI候选之间的对齐流程，解决“用户明说日料却推荐茶空间/咖啡/普通氛围餐厅”的问题。本流程不改变`PlanContract`，只增强内部意图画像、约束抽取、POI语义增强和候选重排。

### 29.1新增受控语义

新增内部标签：

```text
cuisine_japanese
sushi
izakaya
```

触发词包括：

```text
日料、日式、日本料理、寿司、刺身、居酒屋、烧鸟、鮨、和风、会席、日式咖喱、回转寿司
```

标签蕴含：

```text
cuisine_japanese -> proper_dining, slow_dining, dinner, date_friendly
sushi -> cuisine_japanese, proper_dining, slow_dining, dinner
izakaya -> cuisine_japanese, proper_dining, slow_dining, dinner
```

### 29.2编排要求

当用户明说“想吃日料/日本料理/寿司/居酒屋”时：

1. `IntentParser`必须保留`cuisine_japanese/dinner`，寿司和居酒屋表达还要保留`sushi/izakaya`。
2. `ConstraintExtractor.must_have`必须追加对应餐饮锚点和`dinner`。
3. 未写“下午”但明说吃正餐时，默认规划窗口进入晚餐时间段，避免把晚餐提前压到下午四五点。
4. `CandidateRetriever`餐厅槽位必须命中`cuisine_japanese/sushi/izakaya`之一，不能被普通`quality_dining/ambience_dining`替代。
5. 约会场景中，日料候选优先日本料理、鮨、会席、烧鸟等更像正餐/约会的POI；日式咖喱、蛋包饭、回转寿司等快餐式POI只作为低优先级备选。
6. `PlanGenerator`用户可见说明应明确“晚饭按你们明说的日料来选”，但不展示内部权重或推理链。

### 29.3与模型训练的边界

POI语义对齐层可以接入本地训练模型，但模型不能替代硬门控：

```text
规则词典/硬锚点
→ 候选召回
→ 本地reranker/reward model可选加分
→ Verifier状态与路线校验
```

训练样本可以来自：

1. 用户输入与TopK POI候选的人工pairwise偏好。
2. “错误推荐”修复样例，例如日料请求被茶空间吸走。
3. 新POI的文本、类别、标签、价格、评分和区域特征。

模型不得把固定POI ID作为主特征；新增POI只要携带可识别语义，就应通过文本和标签泛化进入候选池。

## 30. 2026-05-23追加：开放餐饮偏好画像与泛化门控流程

本追加定义“吃烤羊排/吃西餐/想减脂/吃清淡”等开放表达的Agent流程。目标是避免继续按单个食品打补丁，让餐厅推荐从开放短语、受控标签和POI语义对齐中泛化。

### 30.1新增内部画像

`ConstraintExtractor`从`recommendation_profile.dining_preference`中读取或生成开放餐饮画像：

```json
{
  "explicit": true,
  "mode": "dish | cuisine | diet | dining",
  "raw_terms": ["烤羊排"],
  "positive_terms": ["烤羊排", "羊排", "羊肉", "烤肉", "烧烤"],
  "normalized_tags": ["dinner", "lamb", "bbq", "grill"],
  "specific_tags": ["lamb", "bbq", "grill"],
  "budget_max_per_person_hint": 180,
  "match_available": true
}
```

说明：

1. `raw_terms`保留用户明说的短语，用于解释和精确匹配。
2. `positive_terms`用于POI文本召回，不要求每个词都是受控标签。
3. `normalized_tags/specific_tags`只使用受控标签，用于`must_have`、排序和前端中文投影。
4. `match_available`由`CandidateRetriever`基于当前候选池回填；存在命中时开启硬门控。

### 30.2编排流程

```text
IntentParser
→ normalize_intent_profile()
→ extract_dining_preference()
→ ConstraintExtractor.must_have/dietary_preference/budget_hint/time_window
→ CandidateRetriever._open_dining_restaurant_candidates()
→ CandidateRetriever._item_score()硬门控
→ PlanGenerator生成“晚饭按你们明说的X来选”的可见说明
→ Verifier校验状态、路线和窗口
```

### 30.3门控规则

当`dining_preference.explicit=true`时：

1. 未声明“下午”且存在吃正餐意图时，默认规划晚餐窗口。
2. 餐厅候选池中如果存在开放画像命中项，最终餐厅必须命中该画像。
3. `quality_dining/ambience_dining/date_friendly`只能做加分，不能替代显式食物目标。
4. 约会用餐为主时，未明说手作/DIY，不应再把手作当默认第一节点；可使用低干扰活动或服务节点过渡。
5. 清淡/减脂类画像必须避开火锅、烧烤、麻辣、酸菜鱼等重口味或伪轻食节点。

### 30.4当前P0覆盖

当前P0已覆盖以下泛化族：

| 泛化族 | 例子 | 受控标签 |
| --- | --- | --- |
| 烤制/肉类 | 烤羊排、烤肉、烧烤、炭烤、羊肉炉 | `bbq/grill/lamb/dinner` |
| 西餐 | 西餐、牛排、意面、披萨 | `western_cuisine/steak/dinner` |
| 低负担 | 减脂、低卡、清淡、轻食、沙拉 | `healthy_light/light_meal/light_food/dinner` |
| 既有锚点 | 火锅、日料、寿司、居酒屋 | `hotpot/cuisine_japanese/sushi/izakaya/dinner` |

后续扩展新菜系时，优先更新开放词典、扩展词和受控标签映射；只有当新表达无法归入现有泛化族时，才新增受控标签。
## 31. 2026-05-24追加：TimeAnchorResolver与短时活动窗口

在`ConstraintExtractor`中补充时间锚点解析层，用于把自然语言中的相对时间转为可执行窗口。

流程：

```text
input_text + current_time + preferred_duration_hours
→ TimeAnchorResolver
→ ConstraintSet.planning_anchor_time / time_intent
→ PlanContract.time_window
→ CandidateRetriever按窗口查询状态、路线、天气
→ PlanGenerator按窗口生成时间线
→ Verifier校验窗口内可执行性
```

关键规则：

1. `current_time`表示Demo当前时刻，不等于出发时间。
2. `preferred_start_time/end_time`只在用户或测试显式锁定窗口时使用。
3. “今天下午”锚定当天；“周末/这周末”在工作日锚定最近周六，在周六下午已过时滚到周日，在周日已过时滚到下个周六。
4. “下午+晚饭”默认生成下午活动到晚饭的长窗口；“下午+小酌/喝酒”默认生成15:00-19:00左右的低压力窗口。
5. `PlanContract.time_window`仍是下游唯一权威计划窗口，LLM不得直接决定开始/结束时间。

回归样例：

```text
current_time = 2026-05-23T18:00:00+08:00
input_text = 周末下午我想去一个人散散心，顺便喝杯酒。
→ time_window = 2026-05-24T15:00:00+08:00 / 2026-05-24T19:00:00+08:00
```

## 32. 2026-05-24追加：赛事故事化编排补充

当前Demo的故事主线调整为“本地生活短时活动导航闭环”：

1. 类脑POI推荐引擎：受控标签、开放餐饮画像、POI语义、路线距离、Mock状态和天气共同打分；LLM只辅助理解和文案，不绕过硬约束。
2. 朋友局投票：候选PlanContract先生成，投票页收集预算、步行、排队和free text，finalize时压缩为共识约束并重新生成、重新Verifier。
3. MockAPI数字孪生：餐厅余桌、活动余票、排队、天气和路线均来自Mock工具层；确认执行后生成Mock预约/订座凭证。
4. 风险分支：Verifier发现余位、天气、路线或预算风险时展示PlanB；Executor遇到`NO_TABLE_AVAILABLE/ACTIVITY_FULL`时进入版本化Recovery，保留`original/replacement/diff/updated_plan_id`。

## 33. 2026-05-24追加：MultiStopItineraryPlanner编排

当用户明确要求“4-5个活动”“几个地方”“下午一点出发，晚上十点回来”时，Agent进入多节点短时活动编排。

```text
IntentParser
→ ConstraintExtractor解析显式起止时间与target_stop_count_range
→ CandidateRetriever选主活动/餐厅/收尾节点
→ CandidateRetriever补充extra_pois并组装itinerary_nodes
→ MockAPIService按相邻节点估算路线
→ PlanGenerator生成多POI timeline
→ PlanContractBuilder汇总预算
→ Verifier检查预算、路线、余位、排队、开闭店和窗口
```

编排约束：

1. `ConstraintExtractor`必须先识别文本中的出发/返回关键词，再把时间提及转为`explicit_text_window`，避免把“13:00出发”误当截止时间。
2. `target_stop_count_range`只影响真实POI节点数量；转场节点由路线工具生成，不挤占活动数量。
3. 纪念日长窗口默认按照“低压力活动 → 轻仪式节点 → 晚餐”组织，餐厅到店时间优先锚定18:00前后。
4. `CandidateRetriever`可以在主链之外补充`extra_pois`，但该结构仍是内部候选；普通API/UI只看最终`PlanContract.timeline`。
5. 多节点路线必须按相邻POI逐段估算，不能只估算“第一个活动到餐厅”两段。
6. 如果多节点候选不足，`PlanGenerator`必须回退到原有短链计划，而不是返回空timeline。

## 34. 2026-05-26追加：重构后服务编排约定

当前工作流实现必须保持以下顺序和边界：

```text
PlanService.create_plan
→ IdempotencyService
→ AgentOrchestrator
→ IntentParser
→ ConstraintExtractor
→ CandidateRetriever
→ PlanGenerator
→ PlanContractBuilder
→ VerifierService
→ SchemaValidator
→ ResponseAssembler
```

约定：

1. `IntentParser`和`PlanGenerator`可以调用受控LLM，但必须能在`DEEPSEEK_ENABLED=false`、`QWEN_ENABLED=false`或缺凭证时稳定降级。
2. `ConstraintExtractor`是自然语言时间、人数、预算、餐饮偏好和区域偏好的唯一结构化入口；前端不得自行推导计划窗口。
3. `CandidateRetriever`可以使用内部`itinerary_nodes`、`extra_pois`、策略分和缓存，但这些结构不得作为普通用户API/UI数据暴露。
4. `PlanContractBuilder`输出后必须经过`VerifierService`和`SchemaValidator`，再由`ResponseAssembler`生成标准响应。
5. `ExecutorService`只消费已落库`PlanContract.tool_actions`，不得执行自然语言文案。
6. `RecoveryService`不得原地覆盖旧计划，必须生成新`updated_plan_id`并保留差异。
