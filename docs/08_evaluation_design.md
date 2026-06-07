# 08_evaluation_design.md

## 1. 文档信息

| 项 | 内容 |
| --- | --- |
| 文档名称 | LifePilot评测设计、测试设计、Benchmark设计、验收标准和Demo评分规范 |
| 产品名称 | LifePilot |
| 产品定位 | 生活时间导航Agent |
| 核心隐喻 | 高德导航的是一段路，LifePilot导航的是一段生活时间 |
| 当前阶段 | 比赛Demo阶段，P0闭环优先 |
| Demo区域 | 杭州下沙/金沙湖/高教园区 |
| 默认时区 | Asia/Shanghai |
| 时间格式 | ISO 8601，例如`2026-05-20T13:00:00+08:00` |
| 技术假设 | React/Next.js Web Demo、Backend API Service、Demo存储JSON或SQLite |
| 权威范围 | 评测设计、自动化测试设计、契约扫描、Demo验收和评委评分 |

## 2. 文档目标与边界

本文档回答LifePilot如何被可复现地评测、测试和验收，重点证明系统不是普通推荐器或聊天壳，而是围绕`PlanContract`完成“目标理解、约束抽取、Mock状态查询、Verifier闸门、Executor执行、Recovery修复、Consensus共识、LifeMemory候选、Trace可解释”的生活时间导航闭环。

本文档覆盖：

| 目标 | 说明 |
| --- | --- |
| P0闭环验收 | 验证家庭亲子、朋友局、纪念日三类P0场景可以完成生成、验证、执行、异常恢复和展示 |
| 契约一致性 | 验证Schema、API、Agent、Mock、Frontend均符合00-07来源文档 |
| LifePilot-Bench | 设计小规模、可复现、可回归的Benchmark样例和指标 |
| 自动化测试 | 设计静态扫描、Schema测试、Unit、Integration、E2E、UI回归和Demo彩排 |
| 红线防护 | 防止LLM编造状态、Mock伪装真实平台、隐私越界、Trace泄露、旧字段回流 |
| 评委Demo | 用3分钟展示生活时间导航、共识导航、可执行窗口、Verifier-Recovery和可解释Trace |

本文档不做：

| 不做 | 原因 |
| --- | --- |
| 不重写PRD | 产品范围以`01_prd.md`为准 |
| 不重写系统架构 | 分层和模块职责以`02_system_architecture.md`为准 |
| 不重写Schema | 字段、枚举、ID、JSONSchema以`03_data_schema.md`为准 |
| 不新增HTTP契约 | 路径、响应格式、错误码、幂等以`04_api_contract.md`为准 |
| 不重写Agent流程 | 主链路、Verifier、Executor、Recovery、Consensus、LifeMemory以`05_agent_workflow.md`为准 |
| 不新增Mock能力边界 | Mock路径、fixture、failure_injection以`06_mock_api_design.md`为准 |
| 不重写前端设计 | 页面、路由、ViewModel、移动端和文案边界以`07_frontend_design.md`为准 |

## 3. 来源文档与契约优先级

评测实现必须先读取00-07文档。若来源中文件名存在轻微差异，例如当前仓库实际为`03_schema.md`，正文统一使用项目最终文件名`03_data_schema.md`。

| 优先级 | 来源文档 | 在08中的权威范围 |
| ---: | --- | --- |
| 1 | `03_data_schema.md` | 字段命名、ID前缀、JSONSchema、对象、状态枚举、TraceLog、BenchmarkSample、PlanContract、VerifierResult、RecoveryResult、ExecutionResult、Consensus、LifeMemory最终权威 |
| 2 | `04_api_contract.md` | HTTP路径、标准响应、错误码、请求头、trace_id、幂等键、Mock接口路径、Debug边界最终权威 |
| 3 | `05_agent_workflow.md` | Agent主链路、DraftPlan边界、Verifier闸门、Executor、Recovery、Consensus、LifeMemory流程最终权威 |
| 4 | `06_mock_api_design.md` | MockAPI路径、Mock标识、failure_injection、fixture、Mock凭证、Mock边界最终权威 |
| 5 | `07_frontend_design.md` | 前端页面、组件、ViewModel、移动端、前端E2E、错误展示、Debug Trace、文案扫描最终权威 |
| 6 | `02_system_architecture.md` | 系统分层、服务职责、模块边界、BenchmarkEvaluator定位 |
| 7 | `01_prd.md` | 产品范围、P0/P1/P2、页面验收、用户流程 |
| 8 | `00_project_vision.md` | 产品定位、核心隐喻、场景范围、创新点、不做什么 |

冲突处理规则：

1. 任何字段、枚举、ID前缀、时间格式、Schema必填项冲突，一律以`03_data_schema.md`为准。
2. 任何HTTP路径、错误码、响应格式、幂等规则冲突，一律以`04_api_contract.md`为准。
3. 任何Agent执行顺序、Verifier闸门、Recovery版本化策略冲突，一律以`05_agent_workflow.md`为准。
4. 任何Mock路径、Mock标识、failure_injection可见性冲突，一律以`06_mock_api_design.md`为准。
5. 任何前端路由、ViewModel、组件、移动端验收冲突，一律以`07_frontend_design.md`为准。
6. 08不得新增领域Schema字段，不得新增API路径，不得新增错误码，不得新增Trace事件名。
7. 如果为了评测需要定义内部评测对象，必须标注为“Evaluation内部对象”，不得进入03 Schema或04 HTTP契约。

## 4. 评测设计总原则

| 原则 | 评测要求 |
| --- | --- |
| PlanContract驱动 | 前端渲染、Verifier检查、Executor执行、Recovery修复、Logging追踪、Benchmark评测都围绕完整`PlanContract`进行 |
| Verifier硬闸门 | `VerifierResult.status=fail`且不可恢复时不得进入Executor；`warning`必须展示风险和PlanB |
| Mock透明 | 不做真实支付、真实短信/微信、真实订座、真实票务、真实第三方爬取，所有Mock能力必须标注Mock |
| LLM受控 | LLM可以生成摘要、草案、解释和消息文案，不得直接确认余位、票务、路线、天气、执行成功或Verifier结果 |
| Recovery版本化 | Recovery必须生成新的完整`PlanContract`，通过`updated_plan_id`关联，不得原地覆盖原计划 |
| 前端只消费合法对象 | 前端只消费完整`PlanContract`或合法`UserVisiblePlanProjection`，不得消费`DraftPlan`或`PlanBuildCandidate` |
| Trace贯穿 | 所有关键流程必须可通过`trace_id`追踪，Trace不得暴露Prompt、LLM推理链、API Key、高敏payload |
| LifeMemory低打扰 | 低打扰、可审计、用户可控；高敏默认不保存，中敏需用户确认，关闭个性化后不读写长期记忆 |
| P0优先 | P0指标是阻塞项；P1/P2只能作为加分和预留，不得影响P0闭环 |

## 5. 评测对象总览

| 评测对象 | 评测目标 | 输入 | 输出 | 核心指标 | P0验收标准 | 常见失败 |
| --- | --- | --- | --- | --- | --- | --- |
| IntentParser | 三类P0场景识别、`fallback_unknown`合理降级 | `raw_text`、`scenario_hint`、`trace_id` | `UserGoal`、`intent_log` | Intent Accuracy、Fallback Precision | `family_parent_child`、`friend_group`、`anniversary_emotion`识别正确；不得把可执行状态写入`UserGoal` | 把“纪念日”识别为普通吃饭；在`UserGoal`写“餐厅有位” |
| ConstraintExtractor | 抽取人数、时间、预算、距离、饮食、排队、步行、天气敏感、孩子友好、情绪强度等约束 | `raw_text`、`UserGoal`、位置、时间偏好 | `ConstraintSet`、`TimeWindow`、`constraint_log` | Constraint Recall、Assumption Trace Rate | 显式约束优先于长期记忆；缺失字段按规则默认并记录assumption | 缺失预算时伪造预算；长期记忆覆盖当次硬约束 |
| CandidateRetriever与MockAPI | 只从MockAPI或fixture投影读取POI、餐厅、路线、天气、状态 | `UserGoal`、`ConstraintSet`、`TimeWindow` | POI、状态、路线、天气、`tool_log` | Tool Correctness、Mock Compliance | 状态查询与执行动作区分，Mock标识完整，不伪装真实平台能力 | LLM编造余位；状态查询生成Mock凭证 |
| PlanContract | 验证03 JSONSchema、引用完整性和时间线可执行性 | Agent输出、Mock状态、Verifier结果 | 完整`PlanContract` | Schema Pass Rate、Timeline Validity | 必填字段齐全，ID前缀和ISO时间合法，`timeline`非空连续不倒序 | 缺`verifier_result`；`ToolAction.target_poi_id`不存在 |
| Verifier | 检查可执行性和硬约束 | PlanBuildCandidate、Mock状态、路线、天气 | `VerifierResult`、`ExecutableWindow`、`Risk[]` | Verifier Gate Correctness | 检查项覆盖P0要求；status只能为`pass/warning/fail`；fail阻断执行 | status写`pending`；warning不展示风险和PlanB |
| ExecutableWindow | 验证窗口计算和过期处理 | POIStatus、RestaurantStatus、VerifierScore、now | `ExecutableWindow` | Window Correctness | `window_minutes`、`confidence`、`expire_at`、`reasons`、`calculated_from`完整；过期触发阻断或refresh-window | 前端自行判断余位；缺`expire_at` |
| Executor | 只执行ToolAction并处理Mock失败 | `PlanContract`、`ToolAction[]`、幂等键 | `ExecutionResult`、Mock凭证、`executor_log` | ToolAction Integrity、Idempotency Pass | 执行类接口携带`X-Idempotency-Key`；Mock凭证含`mock_only`；处理窗口过期、餐厅满座、活动满员 | 执行自然语言文案；缺幂等键仍成功 |
| Recovery | 版本化修复并重新Verifier | 原计划、失败动作、错误码、Mock备选 | `RecoveryResult`、新`PlanContract` | Recovery Success Rate | 含`original/replacement/diff/updated_plan_id/verifier_result`；生成新计划，不原地覆盖 | 用旧字段`new_poi/changes`；未重验 |
| Consensus | 投票约束融合和finalize后重验 | `ConsensusSession`、`ConsensusVote[]` | `ConsensusSummary`、最终`PlanContract` | Consensus Fusion Score | 使用`consensus_session_id`、`vote_page_id`、`plan_group_id`、`vote_id`；finalize后重Verifier | 用`session_id`；喜欢和反选重叠仍保存 |
| LifeMemory | 候选记忆隐私合规和可解释 | feedback、执行结果、用户设置 | `MemoryCandidate`、`LifeMemory`、memory_usage | Privacy Compliance | 中敏待确认，高敏默认不保存，关闭个性化后不读写长期记忆 | 高敏自动保存；隐藏来源 |
| Frontend | 页面、组件、移动端和错误展示符合07 | API标准响应、`PlanContract`、Trace投影 | 页面UI、ViewModel | Critical Path Pass、Mobile UX | 首页、生成、计划、投票、共识、执行、反馈、Memory、Debug Trace符合07；375px可操作 | 普通页展示`failure_injection`、Prompt或API Key |
| Trace与Observability | 全链路可追踪且脱敏 | 模块事件、`trace_id` | `TraceLog`、用户可见Trace投影 | Trace Coverage Rate | 覆盖最终Trace枚举；`visible_to_user=true`支撑工具调用链 | 新增`mock_call`；Trace返回推理链 |
| API契约 | `/api/v1`、标准响应、错误码、幂等合规 | HTTP请求响应 | 标准响应 | API Contract Pass | 统一`success/trace_id/data/error`；执行类接口强制幂等键 | 旧路径、旧字段、未定义错误码 |
| Mock边界与文案 | 防止Mock伪装真实平台 | UI文案、Trace、Mock响应 | 文案扫描结果 | Forbidden Copywriting Hit Rate | 禁止真实支付、真实微信、真实订座、真实锁票、实时抓取等表述 | “已发送到微信群”“已真实订座” |

## 6. LifePilot-Bench设计

### 6.1 Benchmark目标

LifePilot-Bench用于评估：

| 评估目标 | 说明 |
| --- | --- |
| 意图识别准确性 | P0场景与`fallback_unknown`是否正确 |
| 约束抽取完整性 | 关键显式约束和默认assumption是否完整 |
| PlanContract Schema合规率 | 生成计划是否通过03 JSONSchema |
| Verifier通过率 | Verifier是否正确执行闸门和风险判断 |
| 可执行窗口正确性 | 窗口字段、计算来源、过期处理是否合规 |
| 工具调用正确性 | ToolAction和MockAPI路径、参数、幂等是否匹配 |
| Recovery成功率 | 餐厅满座、活动满员、窗口过期等是否生成版本化恢复 |
| Consensus偏好融合质量 | 投票喜欢、反选、预算、文字反馈是否压缩成共识约束 |
| LifeMemory隐私合规率 | 中敏确认、高敏不保存、关闭个性化不读写 |
| 前端E2E闭环成功率 | 关键页面和用户路径是否可操作 |
| Mock边界与文案合规率 | Mock标识、禁止文案和failure_injection可见性 |
| Trace可追踪率 | `trace_id`和最终Trace事件枚举覆盖情况 |

### 6.2 Benchmark样例分类

| sample_id | 类别 | 关键输入 | 重点断言 |
| --- | --- | --- | --- |
| `bench_family_001` | 家庭亲子正常样例 | “今天下午想和老婆孩子出去玩，老婆最近减脂，孩子5岁，别太远。” | scenario=`family_parent_child`；低卡、孩子友好、近距离、低排队；生成活动+餐厅+路线+窗口 |
| `bench_family_recovery_restaurant_001` | 家庭亲子餐厅满座Recovery样例 | “带孩子出去玩，吃点清淡的，别排队。” | `NO_TABLE_AVAILABLE`触发版本化Recovery，替换餐厅并重新Verifier |
| `bench_family_recovery_activity_001` | 家庭亲子活动满员Recovery样例 | “下午带孩子玩室内活动，最好能预约。” | `ACTIVITY_FULL`触发替换活动或调整场次，生成`updated_plan_id` |
| `bench_friend_001` | 朋友局共识正常样例 | “下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。” | 创建投票页，提交多类投票，finalize后最终计划重Verifier |
| `bench_friend_conflict_001` | 朋友局投票冲突样例 | 一人反对走路、一人预算低、一人想拍照 | `ConsensusSummary.detected_conflicts`非空，共识约束优先低步行和预算 |
| `bench_anniversary_001` | 纪念日轻仪式感正常样例 | “结婚纪念日，不想太夸张，但希望她觉得我用心。” | scenario=`anniversary_emotion`；`emotion_intensity`轻/中；消息仅为Mock或草案 |
| `bench_window_expired_001` | 可执行窗口过期样例 | 固定`expire_at`早于now | 执行阻断或调用refresh-window；返回`PLAN_EXECUTABLE_WINDOW_EXPIRED` |
| `bench_budget_exceeded_001` | 预算超限样例 | “人均别超过80”但候选超预算 | Verifier `budget_constraint` warning/fail；P1可用`BUDGET_EXCEEDED`恢复 |
| `bench_weather_risk_001` | 天气风险样例 | 户外散步且Mock天气高风险 | Verifier `weather_risk` warning/fail，PlanB改室内 |
| `bench_memory_high_001` | 高敏MemoryCandidate隐私样例 | 反馈中出现健康诊断、收入、精确住址等 | `MEMORY_PRIVACY_VIOLATION`或候选隐藏/忽略；不得保存长期记忆 |
| `bench_social_missing_001` | Mock口碑缺失样例 | SocialSignalMock fixture缺失 | 不阻断主流程，隐藏口碑卡，必要时使用`SOCIAL_SIGNAL_MISSING` |
| `bench_idempotency_conflict_001` | API幂等冲突样例 | 同一`X-Idempotency-Key`执行不同plan | 返回`IDEMPOTENCY_CONFLICT`，不得生成新凭证 |
| `bench_schema_invalid_001` | Schema非法样例 | 缺`timeline`或`verifier_result` | 返回`PLAN_SCHEMA_INVALID`或`VERIFIER_RESULT_INVALID`，不得持久化为合法计划 |
| `bench_frontend_failure_visible_001` | 前端普通页误展示failure_injection反例 | 普通用户模式执行失败 | 快照扫描命中即失败；`failure_injection`只允许Debug/测试/评委模式 |
| `bench_copy_real_payment_001` | 文案误写真实支付/真实微信发送反例 | UI或消息文案出现真实执行表述 | Forbidden Copywriting Hit Rate必须为0 |

### 6.3 BenchmarkSample与Evaluation内部对象

若03中已有`BenchmarkSample`字段，评测fixture优先使用03定义：

```text
sample_id
scenario
input_text
expected_constraints
expected_tools
expected_verifier_checks
expected_recovery
privacy_expectations
scoring_weights
tags
```

如评测实现需要更细的断言对象，可使用以下Evaluation内部对象：

```text
EvaluationSample
EvaluationRun
EvaluationResult
MetricResult
```

这些对象只用于08评测实现建议，不进入`03_data_schema.md`，不作为`04_api_contract.md`响应对象。

`EvaluationSample`建议字段：

| 字段 | 规则 |
| --- | --- |
| `sample_id` | 必须使用`bench_`前缀 |
| `category` | 对应样例类别 |
| `input_text` | 用户输入原文 |
| `scenario_expected` | 期望场景枚举，来自03 |
| `constraints_expected` | 期望关键约束断言 |
| `mock_setup` | fixture准备说明，不进入业务响应 |
| `failure_injection` | 仅测试/Debug内部使用，不进入PlanContract |
| `expected_api_calls` | 期望调用04/06已有路径，不新增路径 |
| `expected_verifier_checks` | 期望检查项，必须来自03枚举 |
| `expected_plan_assertions` | PlanContract字段、引用、时间线断言 |
| `expected_recovery_assertions` | RecoveryResult版本化、diff、重验断言 |
| `expected_frontend_assertions` | 页面、文案、移动端断言 |
| `privacy_assertions` | LifeMemory敏感度和确认规则 |
| `mock_boundary_assertions` | Mock标识和禁止真实平台文案 |
| `trace_assertions` | Trace事件枚举和可见性断言 |

### 6.4 Benchmark运行口径

| 阶段 | 输入 | 断言 |
| --- | --- | --- |
| Agent离线评测 | `input_text`、fixture、固定now | Intent、Constraint、PlanContract、Verifier、ToolAction |
| API契约评测 | 标准HTTP请求、幂等键、trace | `/api/v1`路径、标准响应、错误码、幂等 |
| Mock失败评测 | `failure_injection`、fixture状态 | `NO_TABLE_AVAILABLE`、`ACTIVITY_FULL`、窗口过期处理 |
| 前端E2E评测 | 浏览器路径和用户操作 | 页面流转、按钮状态、文案、移动端、Debug可见性 |
| 隐私评测 | feedback和记忆候选 | 中敏确认、高敏不保存、个性化关闭 |

### 6.5 可复现Mock状态引擎评测补充（2026-05-23追加）

Mock状态评测必须固定`LIFEPILOT_DEMO_NOW`和`LIFEPILOT_DEMO_SEED`。对天气、餐厅状态、活动状态、库存和口碑Mock执行以下断言：

| 断言 | 说明 |
| --- | --- |
| 同输入稳定 | 同一POI、日期、时段、人数、场景重复查询，响应中的天气、余位、排队、余票、风险等级保持一致 |
| 换日期变化 | 目标日期或时段变化后，至少天气ID、降雨概率、库存或排队压力之一允许变化 |
| 覆盖优先 | 当fixture存在同POI或同区域同时间覆盖时，使用fixture；缺失时不得404阻断主流程 |
| 口碑不阻断 | `mock_social_signals.json`缺失时生成`is_mock=true`的结构化摘要，不影响P0计划生成 |
| 普通页脱敏 | 普通用户页不展示`failure_injection`、底层seed、Prompt、API Key或模型推理链 |

## 7. 指标体系

### 7.1 P0硬指标

| 指标名称 | 评测对象 | 计算方式 | 数据来源 | 通过阈值 | 优先级 | 失败定位模块 | 对应来源文档 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PlanContract Schema Pass Rate | PlanContract | 通过03 JSONSchema校验的PlanContract数量 / 生成的PlanContract总数 | SchemaValidator、plans fixture、API响应 | 100% | P0 | PlanContractBuilder、SchemaValidator、Agent Orchestrator | 03、05 |
| P0 E2E Success Rate | 三大P0路径 | 成功完成家庭亲子、朋友局、纪念日E2E用例数 / P0 E2E总数 | Playwright/Cypress、API logs | >=95%，Demo主路径必须100% | P0 | Frontend、Backend Controller、Agent Orchestrator | 01、04、07 |
| Verifier Gate Correctness | Verifier | 正确阻断fail、允许pass/warning并展示风险的次数 / Verifier场景总数 | VerifierResult、TraceLog、E2E | 100% | P0 | VerifierService、ExecutorService | 03、05 |
| ToolAction Integrity Rate | ToolAction | 引用合法、类型合法、payload完整、幂等键存在的ToolAction数 / ToolAction总数 | PlanContract.tool_actions、ExecutionResult | 100% | P0 | PlanContractBuilder、ExecutorService | 03、04、06 |
| Recovery Success Rate | Recovery | 可恢复失败中生成合法RecoveryResult和新PlanContract的次数 / 可恢复失败总数 | ExecutionResult、RecoveryResult、TraceLog | 餐厅满座和活动满员100% | P0 | RecoveryPlanner、MockAPIService、VerifierService | 03、05、06 |
| ExecutableWindow Correctness | ExecutableWindow | 字段完整且过期处理正确的窗口数 / 窗口总数 | PlanContract、Mock状态、E2E | 100% | P0 | VerifierService、Frontend | 03、06、07 |
| API Contract Pass Rate | API | 标准响应、路径、错误码、Header、幂等均通过的请求数 / 契约测试请求数 | API contract tests | 100% | P0 | Backend Controller、API Client | 04 |
| Trace Coverage Rate | TraceLog | 关键流程中有合法Trace事件覆盖的步骤数 / 应覆盖步骤数 | TraceLog、`GET /api/v1/traces/{trace_id}/events` | >=95%，主链路关键事件100% | P0 | LoggingService、各Agent模块 | 03、05 |
| Mock Boundary Compliance Rate | MockAPI/UI | Mock标识合规对象数 / Mock对象总数 | Mock响应、UI快照、Trace | 100% | P0 | MockAPIService、Frontend | 04、06、07 |
| Frontend Critical Path Pass Rate | Frontend | 关键页面断言通过数 / 关键页面断言总数 | E2E、组件测试、快照 | >=95%，Demo路径100% | P0 | Frontend pages、API Client、ViewModel Mapper | 07 |
| Privacy Compliance Rate | LifeMemory | 隐私断言通过数 / 隐私测试总数 | MemoryCandidate、LifeMemory、Trace | 100% | P0 | LifeMemoryService、FeedbackService、Frontend | 03、04、05 |
| Forbidden Copywriting Hit Rate | Mock文案 | 禁止真实平台文案命中次数 | 静态扫描、UI快照、Trace payload | 0 | P0 | Frontend、ResponseAssembler、MockAPIService | 06、07 |

### 7.2 P1加分指标

| 指标名称 | 评测对象 | 计算方式 | 数据来源 | 通过阈值 | 优先级 | 失败定位模块 | 对应来源文档 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Consensus Preference Fusion Score | Consensus | 喜欢/反选/预算/文字反馈被正确转成共识约束的加权得分 | ConsensusVote、ConsensusSummary、最终PlanContract | >=0.8 | P1 | ConsensusService、ConstraintExtractor | 03、05 |
| LifeMemory Useful Candidate Rate | LifeMemory | 有明确来源、低打扰、用户可理解的候选数 / 候选总数 | MemoryCandidate、feedback logs | >=0.7且隐私100% | P1 | LifeMemoryService | 03、05 |
| SocialSignalMock Display Compliance | SocialSignalMock | 标注Mock且缺失不阻断的口碑卡数 / 口碑测试数 | SocialSignalMock、UI快照 | 100% | P1 | CandidateRetriever、Frontend | 03、06、07 |
| Debug Trace Explainability Score | Debug Trace | 评委可解释步骤数 / 关键步骤数 | Debug页、Trace事件 | >=0.85 | P1 | LoggingService、DebugTracePanel | 05、07 |
| Mobile UX Pass Rate | Frontend | 375px移动端断言通过数 / 移动端断言总数 | 浏览器E2E、截图 | >=95% | P1 | Frontend layout、components | 07 |
| Regression Test Coverage | 测试体系 | 已自动化断言覆盖的P0验收项 / P0验收项总数 | CI报告 | >=80% | P1 | Test Harness、CI | 08 |

### 7.3 P2扩展指标

| 指标名称 | 评测对象 | 计算方式 | 数据来源 | 通过阈值 | 优先级 | 失败定位模块 | 对应来源文档 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PlanReward/Reranker Quality Lift | PlanReward/Reranker | 使用重排后人工/规则评分提升量 | Benchmark离线评测 | 有正向提升即可 | P2 | PlanReward、PlanRanker | 00、02 |
| POI/Restaurant Reranker Quality | Reranker | 场景匹配TopK命中率 | Mock POI fixture、人工标签 | Top3 >=0.8 | P2 | CandidateRetriever、Reranker | 00、02 |
| 多模态反馈可用性 | Feedback | 多模态反馈能生成合规候选的比例 | Feedback samples | >=0.7且隐私100% | P2 | FeedbackService、LifeMemoryService | 00、02 |
| Demo Storytelling Score | Demo展示 | 评委是否在3分钟内理解核心创新的主观评分 | 彩排评分表 | >=8/10 | P2 | Demo负责人、Frontend | 00、01 |

## 8. 测试分层设计

| 测试层 | 目标 | 主要对象 | 必须覆盖 |
| --- | --- | --- | --- |
| 静态契约扫描 | 防止旧路径、旧字段、未定义枚举、禁止文案进入代码 | 源码、fixture、文案、测试数据 | 旧路径、旧字段、错误码、Trace事件、`create_order`、真实执行文案 |
| Schema测试 | 保证核心对象符合03 | PlanContract、ToolAction、VerifierResult、RecoveryResult、ExecutionResult、Consensus、Memory、Trace、Mock投影 | 合法样例通过、非法样例失败、错误码正确 |
| Unit测试 | 验证模块内规则 | IntentParser、ConstraintExtractor、VerifierService、RecoveryPlanner、ExecutorService、ConsensusService、LifeMemoryService、MockAPIService、API Client、ViewModel Mapper | 正常、边界、异常、隐私 |
| Integration测试 | 验证跨模块链路 | Plan创建、Verify刷新、Execute、Recovery、Consensus finalize、Feedback→MemoryCandidate、Trace聚合 | trace贯穿、Mock状态、幂等、版本化Recovery |
| E2E测试 | 验证用户闭环 | 首页、计划页、投票页、共识页、执行页、反馈页、Memory、Debug Trace | 三大P0路径、异常路径、移动端 |
| UI回归测试 | 验证页面可演示 | 375px布局、底部按钮、时间线、投票页、Debug面板、错误态 | 截图快照、可点击性、文案扫描 |
| Demo彩排测试 | 验证评委展示节奏 | 3分钟脚本、Debug Trace、Mock边界说明 | 正常路径、Recovery路径、Consensus路径、Trace解释 |

## 9. 契约扫描设计

静态契约扫描必须在本地和CI中执行，命中P0红线时直接失败。

| 扫描项 | 禁止内容 | 正确内容 | 失败处理 |
| --- | --- | --- | --- |
| 旧API路径 | `/api/mock/...`、`/api/plans/create`、未带`/api/v1`的业务路径 | `04_api_contract.md`中的`/api/v1/...`路径 | P0 Blocker |
| 旧字段 | `session_id`替代`consensus_session_id`、`group_0001`、`vote_page_0001` | `consensus_session_id`、`plangrp_`、`vpage_` | P0 Blocker |
| Recovery旧字段 | `original_step_id`、`original_poi`、`new_poi`、`changes` | `original`、`replacement`、`diff` | P0 Blocker |
| 未定义错误码 | `MOCK_API_FAILED`、`PLAN_CREATE_FAILED`、`RESTAURANT_FULL`、`TICKET_SOLD_OUT`、`UNKNOWN_STATUS` | 04定义错误码 | P0 Blocker |
| 未定义Trace事件名 | `mock_call`、`mock_log`、`api_log`、`verifier`、`executor` | 03/05最终Trace枚举 | P0 Blocker |
| ToolAction误用 | `create_order` | `order_item` | P0 Blocker |
| 幂等误用 | 执行类接口未传`X-Idempotency-Key`仍成功 | 返回`BAD_REQUEST` | P0 Blocker |
| DraftPlan泄露 | 前端组件Props或API响应出现`DraftPlan`、`PlanBuildCandidate` | 完整`PlanContract`或合法展示投影 | P0 Blocker |
| Mock误导文案 | “已真实支付”“已发送到微信群”“已真实订座”“已锁票”“已实时抓取小红书/抖音/点评” | “Mock”“模拟”“可复制消息草案” | P0 Blocker |
| Debug泄露 | Prompt、LLM推理链、API Key、高敏payload | 脱敏Trace投影 | P0 Blocker |
| failure_injection可见性 | 普通用户页出现`failure_injection` | 仅Debug/测试/评委模式 | P0 Blocker |

建议扫描文件范围：

```text
frontend/**
backend/**
app/**
src/**
docs/**
fixtures/**
tests/**
```

扫描允许例外：08、06、07等文档中在“禁止项”“反例”“扫描规则”上下文出现禁止词时，可通过白名单注释或扫描配置排除，但业务代码、fixture、UI文案和API响应样例不得命中。

## 10. Schema与数据一致性测试

| 对象 | 必测断言 | 非法样例 | 期望错误码 |
| --- | --- | --- | --- |
| PlanContract | required字段齐全，`additionalProperties=false`，ID前缀正确，ISO时间，`timeline`非空 | 缺`timeline`、缺`verifier_result`、非ISO时间 | `PLAN_SCHEMA_INVALID`、`VERIFIER_RESULT_INVALID` |
| ToolAction | `action_id`、`plan_id`、`step_id`、`type`、`payload`、`status`、`idempotency_key`完整 | `type=create_order`、target POI不存在、缺幂等键 | `TOOL_ACTION_INVALID` |
| VerifierResult | `status`只能为`pass/warning/fail`，checks.name来自03 | `status=pending`、未定义check | `VERIFIER_RESULT_INVALID` |
| RecoveryResult | 含`original/replacement/diff/verifier_result`，`updated_plan_id`指向新计划 | 使用旧字段、缺diff、未重验 | `RECOVERY_RESULT_INVALID` |
| ExecutionResult | `execution_id`、`plan_id`、`trace_id`、status、action_results完整，Mock凭证含`mock_only` | 凭证无Mock标识、失败动作无错误码 | `TOOL_ACTION_INVALID`或对应领域错误 |
| ConsensusVote | 喜欢和反选不重叠，至少一种反馈有效，`budget_max>0` | liked和disliked重叠 | `CONSENSUS_VOTE_INVALID` |
| ConsensusSummary | 含投票统计、冲突、共识约束、最终计划ID，finalize后最终计划重Verifier | final_plan_id不存在 | `PLAN_STEP_POI_NOT_FOUND`或`PLAN_SCHEMA_INVALID` |
| MemoryCandidate | 敏感度、确认状态、来源trace完整；高敏不保存 | 高敏`status=enabled` | `MEMORY_PRIVACY_VIOLATION` |
| TraceLog | `event_type`来自最终枚举，payload脱敏，`visible_to_user`正确 | `event_type=mock_call`、payload含Prompt | `PLAN_SCHEMA_INVALID`或安全扫描失败 |
| Mock响应投影对象 | Mock POI、状态、凭证、SocialSignalMock标识完整 | SocialSignalMock缺`is_mock:true` | `SOCIAL_SIGNAL_MOCK_REQUIRED` |

数据一致性附加断言：

1. `PlanStep.poi_id`必须存在于Mock POI集合。
2. `PlanStep.related_tool_action_ids`必须存在于`tool_actions`。
3. `ToolAction.step_id`必须存在于`timeline`。
4. `RouteEstimate.origin_poi_id`和`destination_poi_id`必须存在。
5. `executable_window.expire_at`不得缺省。
6. Recovery后原计划和新计划复用同一`trace_id`，但使用不同`plan_id`。
7. Consensus finalize后`final_plan_id`指向可读取的完整`PlanContract`。

## 11. Agent工作流评测

| Agent模块 | 评测目标 | 输入 | 输出 | 测试方法 | P0验收 |
| --- | --- | --- | --- | --- | --- |
| IntentParser | 场景识别正确，低置信度合理降级 | 三类P0输入、冲突输入、短输入 | `UserGoal`、`intent_log` | 参数化Unit测试、Benchmark离线跑分 | 三类P0识别100%；`fallback_unknown`不乱归类；不得写可执行状态 |
| ConstraintExtractor | 关键约束抽取完整，默认值有来源 | `raw_text`、`UserGoal`、位置、时间 | `ConstraintSet`、`TimeWindow`、assumption Trace | 规则样例、冲突样例、记忆覆盖测试 | 显式约束优先；缺失字段不伪造；assumption进入Trace |
| CandidateRetriever | Mock检索和状态查询合规 | 约束、时间窗、位置 | POI、Restaurant、Route、Weather、状态 | Mock fixture测试、API spy | 只使用MockAPI或fixture投影，状态和执行分离 |
| PlanGenerator | 草案不泄露到前端 | 候选和约束 | 内部DraftPlan/PlanBuildCandidate | Unit测试、API响应扫描 | DraftPlan只在内部流转 |
| PlanContractBuilder | 补齐03 required字段 | 内部候选、Verifier结果 | 完整PlanContract | Schema测试、引用完整性测试 | 100%通过03 Schema |
| VerifierService | 执行前硬闸门 | PlanBuildCandidate和Mock状态 | VerifierResult、ExecutableWindow、Risk | Unit+Integration | fail阻断执行；warning展示风险和PlanB |
| ExecutorService | 执行ToolAction并处理失败 | PlanContract、幂等键 | ExecutionResult | Integration、幂等测试 | 只执行ToolAction；失败触发Recovery |
| RecoveryPlanner | 版本化修复 | failed_action、错误码、原计划 | RecoveryResult、新PlanContract | 故障注入E2E | 不原地覆盖，重Verifier |
| ConsensusService | 投票融合 | ConsensusVote[] | ConsensusSummary、最终PlanContract | Unit+E2E | 字段ID正确，finalize后重Verifier |
| LifeMemoryService | 候选生成和隐私审核 | feedback、执行结果、用户设置 | MemoryCandidate、LifeMemory | 隐私样例测试 | 高敏不保存，中敏待确认，关闭个性化不读写 |
| LoggingService | Trace覆盖和脱敏 | 模块事件 | TraceLog、用户投影 | Trace快照、敏感词扫描 | 只用最终event_type，不泄露Prompt/推理链/API Key |

## 12. Verifier与ExecutableWindow评测

Verifier必须覆盖以下检查项：

```text
time_feasibility
opening_hours
distance_constraint
budget_constraint
restaurant_capacity
activity_ticket
queue_time
weather_risk
participant_constraints
tool_action_integrity
executable_window
```

| 检查项 | 输入来源 | pass断言 | warning/fail断言 | P0要求 |
| --- | --- | --- | --- | --- |
| `time_feasibility` | timeline、RouteEstimate | 时间顺序连续、不倒序、不重叠 | 倒序或明显赶场fail | 必测 |
| `opening_hours` | POIStatus/RestaurantStatus | 到达时营业 | closed时fail | 必测 |
| `distance_constraint` | RouteEstimate、用户距离约束 | 距离满足约束 | 超距warning/fail | 必测 |
| `budget_constraint` | Budget、ConstraintSet | 不超过预算 | 超预算warning/fail | 必测 |
| `restaurant_capacity` | RestaurantStatus | 有可用桌位或可预约 | 0桌fail，紧张warning | 必测 |
| `activity_ticket` | POIStatus/ActivityStatus | 余票满足人数 | 不足fail | 必测 |
| `queue_time` | POIStatus/RestaurantStatus | 排队时长不超过容忍 | 超过容忍warning/fail | 必测 |
| `weather_risk` | WeatherStatus | 户外风险可接受 | 高风险warning/fail | 必测 |
| `participant_constraints` | participants、ConstraintSet | 孩子友好、饮食、同行人约束满足 | 违反硬约束fail | P0建议 |
| `tool_action_integrity` | ToolAction、PlanStep引用 | 关键节点动作完整 | 缺动作或引用错误fail | P0建议强制 |
| `executable_window` | 状态`expire_at`、now | 未过期且字段完整 | 过期fail | 必测 |

`VerifierResult.status`只能是：

```text
pass
warning
fail
```

ExecutableWindow测试断言：

| 字段 | 断言 |
| --- | --- |
| `window_minutes` | 非负数，等于或近似等于`expire_at-now`，不得由前端自行计算可执行性 |
| `confidence` | 0-1，受Verifier score、状态置信度、路线置信度影响 |
| `expire_at` | ISO 8601，来自Mock状态有效期的最小约束或规则计算 |
| `reasons` | 非空，说明为什么当前可执行 |
| `calculated_from` | 非空，包含状态、路线、天气等来源标识 |
| `risk_factors` | 有风险时展示，不影响字段合法性 |

过期处理验收：

1. `expire_at`早于当前时间时，Executor不得执行。
2. API应返回或记录`PLAN_EXECUTABLE_WINDOW_EXPIRED`。
3. 前端计划页应禁用执行按钮或触发`POST /api/v1/plans/{plan_id}/refresh-window`。
4. 刷新窗口必须由后端Mock状态查询和Verifier完成，前端不得自行判断“仍有位”。

## 13. Executor与Recovery评测

### 13.1 Executor评测

| 评测项 | 断言 | 失败错误码 |
| --- | --- | --- |
| 执行动作来源 | Executor只执行`ToolAction`，不执行自然语言文案或页面按钮文案 | `TOOL_ACTION_INVALID` |
| 幂等Header | 执行类HTTP接口必须携带`X-Idempotency-Key` | `BAD_REQUEST` |
| ToolAction幂等字段 | `ToolAction.idempotency_key`存在，但不能替代HTTP Header | `TOOL_ACTION_INVALID` |
| Mock凭证 | 成功结果中凭证必须含`mock_only:true` | 契约扫描失败 |
| 窗口过期 | 执行前发现窗口过期必须阻断或刷新 | `PLAN_EXECUTABLE_WINDOW_EXPIRED` |
| 餐厅满座 | `reserve_restaurant`失败触发Recovery | `NO_TABLE_AVAILABLE` |
| 活动满员 | `book_activity`失败触发Recovery | `ACTIVITY_FULL` |
| 重复执行 | 同一plan同一幂等键返回同一`execution_id`和凭证 | `IDEMPOTENCY_CONFLICT`用于冲突key |

### 13.2 Recovery评测

Recovery触发源：

| 触发源 | 错误码 | P0行为 |
| --- | --- | --- |
| 餐厅订座失败 | `NO_TABLE_AVAILABLE` | 搜索同区域、同预算、同饮食偏好备选餐厅，重查状态和路线，重Verifier |
| 活动预约失败 | `ACTIVITY_FULL` | 搜索同区域、同场景活动或调整场次，重Verifier |
| 窗口过期 | `PLAN_EXECUTABLE_WINDOW_EXPIRED` | refresh-window或重新Verifier |
| 天气风险 | `WEATHER_RISK_HIGH` | P1/P2：户外改室内 |
| 预算超限 | `BUDGET_EXCEEDED` | P1/P2：替换低价节点 |

Recovery P0断言：

1. `RecoveryResult.recovery_id`使用`rec_`前缀。
2. `RecoveryResult`必须包含`original`、`replacement`、`diff`、`verifier_result`、`user_explanation`、`created_at`。
3. 成功恢复时`updated_plan_id`指向新的完整`PlanContract`。
4. 新计划使用新的`plan_id`，如`plan_20260520_0001_r1`。
5. 原计划不得被原地覆盖，原计划可记录`recovery_results`和状态交接。
6. Recovery后必须重新Verifier，新`VerifierResult.status`为`pass`或可接受的`warning`后才能继续执行。
7. 新ToolAction生成新的`action_id`和新的幂等键，不复用旧失败动作的HTTP幂等键。
8. 普通用户页展示替换说明和Diff，不展示`failure_injection`。

## 14. Consensus评测

| 评测项 | 断言 |
| --- | --- |
| ID字段 | 必须使用`consensus_session_id`、`vote_page_id`、`plan_group_id`、`vote_id`，不得使用泛化`session_id` |
| 投票合法性 | `liked_plan_ids`、`disliked_plan_ids`、`free_text`三者至少一个有效；喜欢和反选不得重叠 |
| 预算约束 | `budget_max`必须大于0，finalize后进入共识约束 |
| 文字反馈 | “不想走太多”“别排队”“人均100以内”等文字必须能转成约束候选 |
| 冲突压缩 | 投票冲突写入`detected_conflicts`，并在`explanation`中说明折中依据 |
| finalize | 生成`ConsensusSummary`和`final_plan_id`，最终`PlanContract`必须重新Verifier |
| 群聊消息 | 只做可复制消息或Mock发送，不能写真实微信已发送 |
| Trace | 投票、约束融合、finalize写合法Trace事件，复用或关联`trace_id` |

P0 E2E路径：

```text
首页输入朋友局
→ 生成候选PlanContract/PlanSummary
→ POST /api/v1/consensus/create
→ GET /api/v1/vote-pages/{vote_page_id}
→ 朋友提交喜欢/反选/预算/free_text
→ POST /api/v1/consensus/{consensus_session_id}/finalize
→ GET /api/v1/plans/{final_plan_id}
→ 最终计划重新Verifier
```

## 15. LifeMemory与隐私合规评测

| 敏感度 | 示例 | 评测断言 |
| --- | --- | --- |
| low | 不喜欢排队、偏好近距离、预算敏感 | 可进入候选；需有来源、置信度、用户可见解释 |
| medium | 孩子年龄、配偶近期减脂、备考阶段 | 必须`requires_confirmation=true`或待确认状态，不得静默启用 |
| high | 健康诊断、收入、婚姻状态、精确住址 | 默认不保存，不展示细节，不进入长期LifeMemory |

LifeMemory P0测试：

1. `MemoryCandidate`必须有`candidate_id`、`user_id`、`source_trace_id`、`content`、`memory_type`、`source`、`confidence`、`sensitivity`、`requires_confirmation`、`status`、`suggested_ttl_days`、`created_at`。
2. 中敏候选必须等待用户确认。
3. 高敏输入必须被忽略、隐藏或记录为隐私违规处理，不得保存为`enabled`。
4. 用户关闭个性化后，不读取、不写入长期记忆。
5. 删除后的记忆不得静默恢复；再次出现必须重新作为候选并说明来源。
6. 本次使用了哪些记忆必须可解释，`memory_usage`只展示用户可理解摘要，不展示内部权重和高敏内容。
7. Feedback问题不超过2个，用户可以跳过，跳过不阻断主流程。

## 16. MockAPI与数字孪生评测

MockAPI必须覆盖固定区域：杭州下沙/金沙湖/高教园区。评测重点不是“真实平台能力”，而是稳定、透明、可复现的数字孪生状态层。

| Mock能力 | 路径 | 查询/执行 | P0断言 |
| --- | --- | --- | --- |
| POI搜索 | `GET /api/v1/mock/poi/search` | 查询 | 返回Mock POI，`mock_only:true` |
| 餐厅搜索 | `GET /api/v1/mock/restaurants/search` | 查询 | 按饮食、预算、位置返回餐厅候选 |
| POI状态 | `GET /api/v1/mock/poi/{poi_id}/status` | 查询 | 返回状态和`expire_at`，不生成凭证 |
| 餐厅状态 | `GET /api/v1/mock/restaurants/{poi_id}/status` | 查询 | 必须带`arrival_time`和`party_size`，返回余位/排队/有效期 |
| 路线估计 | `GET /api/v1/mock/routes/estimate` | 查询 | `RouteEstimate.source="mock_api"` |
| 天气查询 | `GET /api/v1/mock/weather` | 查询 | WeatherStatus参与Verifier |
| 活动预约 | `POST /api/v1/mock/activities/{poi_id}/book` | 执行 | 必须幂等，成功返回Mock预约凭证 |
| 餐厅订座 | `POST /api/v1/mock/restaurants/{poi_id}/reserve` | 执行 | 必须幂等，失败可返回`NO_TABLE_AVAILABLE` |
| 创建Mock订单 | `POST /api/v1/mock/orders/create` | 执行 | 若使用`order_item`必须可执行且Mock标识 |
| 模拟消息发送 | `POST /api/v1/mock/messages/send` | 执行 | 返回Mock message凭证，不写真实发送 |
| Mock口碑信号 | `GET /api/v1/mock/social-signals/{poi_id}` | 查询 | P1；`is_mock:true`、`source_type:"mock_social_signal"` |

failure_injection测试：

| 注入场景 | 触发错误码 | 预期 |
| --- | --- | --- |
| 餐厅满座 | `NO_TABLE_AVAILABLE` | Executor触发Recovery，替换备选餐厅 |
| 活动满员 | `ACTIVITY_FULL` | Executor触发Recovery，替换活动或调整时间 |
| 可执行窗口过期 | `PLAN_EXECUTABLE_WINDOW_EXPIRED` | 阻断执行或refresh-window |

可见性断言：

1. 普通用户页不得展示`failure_injection`、`failure_scenario_id`。
2. Debug/评委模式可展示脱敏failure摘要。
3. Trace可记录工具名和错误码，但普通用户只看用户友好文案。
4. SocialSignalMock缺失不阻断主流程。
5. 文案必须使用“Mock”“模拟”“Demo模拟数据”等透明表达。

## 17. 前端E2E与移动端验收

### 17.1 页面覆盖

| 页面 | 路由 | P0断言 |
| --- | --- | --- |
| 首页 | `/` | 三个P0快捷输入可提交，调用`POST /api/v1/plans/create`，成功保存`plan_id`和`trace_id` |
| 生成页 | `/plans/creating` | 展示至少4个生成步骤，不展示Prompt或模型链路 |
| 计划页 | `/plans/[planId]` | 展示目标理解、时间线、路线、窗口、预算、风险、PlanB、工具链；过期禁用执行 |
| 投票页 | `/vote/[votePageId]` | 可提交喜欢、反选、预算、文字反馈；重叠选择阻断 |
| 共识页 | `/consensus/[consensusSessionId]` | 展示统计、冲突压缩、共识解释、最终计划；不写真实微信群发送 |
| 执行页 | `/execution/[executionId]` | 展示ToolAction进度、Mock凭证、失败动作、Recovery Diff、`updated_plan_id` |
| 反馈页 | `/feedback/[planId]` | 最多2问，可跳过，展示MemoryCandidate候选 |
| Memory页 | `/memory` | P1完整；P0可预留入口，候选确认/忽略可用时必须合规 |
| Debug Trace页 | `/debug/traces/[traceId]` | 仅Debug/评委模式，展示脱敏Trace、Verifier、Recovery、Mock标识 |

### 17.2 E2E用例

| 用例 | 操作 | 预期 |
| --- | --- | --- |
| 家庭亲子正常闭环 | 首页提交家庭亲子输入→计划页→确认执行→执行结果页 | 生成完整PlanContract，展示窗口和PlanB，执行返回Mock凭证 |
| 餐厅满座Recovery | 设置餐厅满座→执行订座→Recovery Diff | 展示`NO_TABLE_AVAILABLE`用户文案、`updated_plan_id`，继续执行新计划 |
| 活动满员Recovery | 设置活动满员→执行预约→替换活动 | 展示`ACTIVITY_FULL`用户文案，新计划重Verifier |
| 朋友局共识 | 创建投票→朋友提交反选和文字反馈→finalize | 生成ConsensusSummary和最终PlanContract |
| 纪念日 | 输入轻仪式需求→计划页→订座和消息Mock | 轻仪式感、自然消息、Mock凭证 |
| 窗口过期 | 固定过期窗口→打开计划页 | 执行按钮禁用或显示refresh-window |
| 高敏MemoryCandidate | 反馈输入高敏信息 | 不展示细节、不保存长期记忆 |
| failure_injection隐藏 | 普通用户模式触发失败 | 页面和用户可见Trace不出现`failure_injection` |

### 17.3 移动端和UI回归

| 验收项 | 标准 |
| --- | --- |
| 375px移动端 | 全流程可操作，无横向溢出 |
| 底部按钮 | 不遮挡时间线、投票表单、错误提示 |
| 时间线 | 可滚动，节点时间和状态不重叠 |
| 投票页 | 单手可完成喜欢、反选、预算、文字提交 |
| Debug面板 | 可折叠，不影响普通Demo |
| 错误态 | 普通用户只展示`error.user_message` |
| 空态/loading态 | 不出现空白页或未处理异常 |
| Mock文案 | Mock凭证和Mock口碑均有明确标识 |

## 18. Trace与可观测性验收

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

| 事件 | 必须覆盖的流程 | 用户可见规则 |
| --- | --- | --- |
| `input_log` | 首页输入、feedback提交 | 可见摘要 |
| `intent_log` | 场景识别、目标摘要 | 可见 |
| `constraint_log` | 约束抽取、共识约束融合 | 可见摘要 |
| `memory_log` | 记忆读取、候选生成、隐私分级 | 隐藏高敏，仅展示可解释摘要 |
| `poi_log` | 候选召回摘要 | 可见 |
| `tool_log` | MockAPI调用、工具动作摘要 | 可见脱敏摘要 |
| `verifier_log` | Verifier检查结果 | 可见摘要，Debug可见详情 |
| `recovery_log` | Recovery触发、Diff、版本交接 | 可见替换说明 |
| `executor_log` | ToolAction执行 | 可见进度和Mock结果 |
| `feedback_log` | 反馈提交或跳过 | 可见 |
| `error_log` | Schema失败、Mock失败、系统异常 | 普通用户只展示用户友好文案 |

验收断言：

1. PlanContract、ExecutionResult、RecoveryResult、Consensus、MemoryCandidate均可通过`trace_id`串联。
2. `visible_to_user=true`的Trace足以支撑前端工具调用链展示。
3. Debug/评委模式可展示脱敏payload、API路径摘要、错误码、Recovery链路。
4. Trace不得暴露底层Prompt、LLM推理链、API Key、高敏MemoryCandidate、未脱敏个人信息。
5. 普通用户页调用Trace时必须使用用户可见投影或`visible_only=true`。

## 19. 反例与红线测试

| 反例 | 错误表现 | 违反契约原因 | 应触发的测试 | 应返回或记录的错误码 | 修复建议 |
| --- | --- | --- | --- | --- | --- |
| LLM直接写“餐厅有位”但没有MockAPI来源 | `goal_summary`或PlanStep文案声称有位，Trace无Mock状态查询 | LLM不得确认余位，餐厅状态必须来自MockAPI | LLM边界扫描、Trace工具调用断言、Verifier输入断言 | `MOCK_STATUS_MISSING`或`VERIFIER_RESULT_INVALID` | 删除可执行状态文案，强制调用`get_restaurant_status`并进入Verifier |
| 前端直接消费DraftPlan | API响应或组件Props出现`DraftPlan` | 前端只能消费完整`PlanContract`或合法投影 | API响应扫描、组件Props扫描 | `PLAN_SCHEMA_INVALID` | 用PlanContractBuilder和SchemaValidator后再返回 |
| PlanContract缺少`verifier_result` | 计划页可渲染但无校验结果 | 03 required字段缺失，Verifier闸门被绕过 | Schema测试 | `PLAN_SCHEMA_INVALID`或`VERIFIER_RESULT_INVALID` | PlanContract持久化前强制Verifier |
| `VerifierResult.status=pending` | Verifier结果出现未定义状态 | status只能是`pass/warning/fail` | Schema测试、枚举扫描 | `VERIFIER_RESULT_INVALID` | 映射为合法状态，pending只能作为内部任务状态，不进入03 |
| `ToolAction.type=create_order` | 工具动作类型写旧值 | 03枚举使用`order_item`，07禁止`create_order` | 静态扫描、Schema测试 | `TOOL_ACTION_INVALID` | 替换为`order_item`并映射到`POST /api/v1/mock/orders/create` |
| RecoveryResult使用旧字段 | 出现`original_step_id/new_poi/changes` | 03规定使用`original/replacement/diff` | 静态扫描、Schema测试 | `RECOVERY_RESULT_INVALID` | 按03结构重构RecoveryResult |
| Recovery原地覆盖原PlanContract | 原`plan_id`内容被替换，无`updated_plan_id` | 05/06要求版本化Recovery | Integration、数据一致性测试 | `RECOVERY_RESULT_INVALID` | 创建新`plan_id`，原计划记录RecoveryResult |
| 使用`/api/mock/...`旧路径 | 前端或后端调用旧Mock路径 | 04/06统一`/api/v1/mock/...` | 静态路径扫描、API契约测试 | `BAD_REQUEST`或契约扫描失败 | 改为04/06最终路径 |
| 使用`/api/plans/create` | 创建计划未带`/api/v1` | 04要求统一Base Path | 静态路径扫描、API契约测试 | `BAD_REQUEST`或404 | 改为`POST /api/v1/plans/create` |
| 使用`session_id`替代`consensus_session_id` | 投票或共识响应字段泛化 | 03/04共识字段冻结 | 静态字段扫描、Consensus Schema测试 | `CONSENSUS_VOTE_INVALID`或`PLAN_SCHEMA_INVALID` | 使用`consensus_session_id` |
| SocialSignalMock写成真实抓取 | UI写“已抓取小红书实时数据” | Demo阶段必须是Mock，不承诺真实爬取 | 文案扫描、Mock边界测试 | `SOCIAL_SIGNAL_MOCK_REQUIRED` | 改为“口碑雷达Mock/模拟信号” |
| Mock消息写“已发送到微信群” | 执行页展示真实发送成功 | 不做真实微信/短信发送 | 文案扫描、E2E快照 | 契约扫描失败 | 改为“模拟消息已生成，可复制”或Mock message凭证 |
| 高敏MemoryCandidate自动保存 | 健康诊断/收入/精确住址进入`enabled`记忆 | LifeMemory高敏默认不保存 | 隐私测试、Memory Schema测试 | `MEMORY_PRIVACY_VIOLATION` | 高敏候选隐藏或忽略，不进入长期记忆 |
| 普通用户页展示`failure_injection` | 计划页/执行页出现注入字段 | failure_injection只允许Debug/测试/评委模式 | 前端快照、E2E | 契约扫描失败 | 普通投影过滤字段，Debug入口受控 |
| Trace返回Prompt或LLM推理链 | Debug页或Trace API包含Prompt/chain | 03/05/07明确禁止泄露 | Trace敏感词扫描 | 契约扫描失败或`MEMORY_PRIVACY_VIOLATION` | Trace写脱敏摘要，Prompt不入库不返回 |
| API执行类接口缺少`X-Idempotency-Key`仍成功执行 | 重复点击生成多个Mock凭证 | 04/06要求执行类HTTP接口幂等键必填 | API契约测试、重复执行测试 | `BAD_REQUEST` | Controller层先校验Header，缺失直接拒绝 |

## 20. P0/P1/P2验收清单

### 20.1 P0验收清单

| 验收项 | 所属模块 | 输入 | 预期结果 | 检查方式 | 通过标准 | 阻塞等级 | 来源 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 首页输入可以创建PlanContract | Frontend/API/Agent | 家庭亲子输入 | 返回`plan_id`、`trace_id`和完整PlanContract | E2E+API测试 | 使用`POST /api/v1/plans/create`，标准响应 | P0 Blocker | 04、07 |
| 家庭亲子场景可生成完整时间线 | Agent/Plan | “老婆减脂，孩子5岁，别太远” | 活动+餐厅+路线+窗口 | Benchmark+E2E | `scenario=family_parent_child`，timeline>=3 | P0 Blocker | 01、03、05 |
| 朋友局可创建投票页并finalize | Consensus/Frontend | 4人朋友局输入和投票 | `ConsensusSummary`和最终PlanContract | E2E | 使用正确ID字段，最终计划重Verifier | P0 Blocker | 03、04、05、07 |
| 纪念日可生成轻仪式感计划 | Agent/Frontend | 纪念日输入 | 轻仪式时间线、消息草案或Mock消息 | Benchmark+E2E | 不夸张，消息不写真实发送 | P0 Blocker | 00、01、05 |
| PlanContract通过03 Schema | SchemaValidator | 所有生成计划 | Schema valid | Schema测试 | 100%通过 | P0 Blocker | 03 |
| API使用`/api/v1`标准响应 | API | 所有HTTP请求 | `success/trace_id/data/error` | API契约测试 | 100%通过 | P0 Blocker | 04 |
| Verifier输出合法 | Verifier | 正常/异常计划 | `pass/warning/fail`和checks | Unit+Integration | status和check枚举合法 | P0 Blocker | 03、05 |
| 可执行窗口展示且过期可处理 | Verifier/Frontend | 窗口正常和过期样例 | 展示窗口；过期禁用或刷新 | E2E | 不由前端自行判断可执行性 | P0 Blocker | 03、06、07 |
| Executor执行ToolAction并返回Mock凭证 | Executor/MockAPI | 执行合法计划 | `ExecutionResult`和Mock凭证 | Integration+E2E | 凭证含`mock_only:true`，文案标Mock | P0 Blocker | 03、04、06 |
| 餐厅满座可触发Recovery | Executor/Recovery | `NO_TABLE_AVAILABLE` | 替换餐厅，生成新计划 | failure_injection E2E | 有`updated_plan_id`并重Verifier | P0 Blocker | 05、06 |
| Activity Full可触发Recovery | Executor/Recovery | `ACTIVITY_FULL` | 替换活动或调整场次 | failure_injection E2E | 有合法RecoveryResult | P0 Blocker | 05、06 |
| Recovery生成新PlanContract，不原地覆盖 | Recovery/Data | 执行失败 | 原计划保留，新计划可读取 | Integration | 新旧`plan_id`不同，同trace | P0 Blocker | 03、05、06 |
| Trace能串联输入、工具、Verifier、Executor、Recovery | Logging | 任一主流程 | Trace事件完整 | Trace测试 | 关键事件覆盖 | P0 Blocker | 03、05 |
| LifeMemory只生成候选，不偷偷保存高敏 | LifeMemory | 高敏/中敏/低敏反馈 | 中敏待确认，高敏不保存 | 隐私测试 | 100%合规 | P0 Blocker | 03、05 |
| 前端普通页不展示`failure_injection` | Frontend | 失败注入场景 | 普通页只展示用户文案 | 快照+E2E | 命中次数0 | P0 Blocker | 06、07 |
| Mock文案不伪装真实平台 | Frontend/MockAPI | 执行结果、消息、口碑 | 显示Mock/模拟 | 文案扫描 | 禁止文案命中0 | P0 Blocker | 06、07 |
| 375px移动端可完整演示 | Frontend | P0三路径 | 页面可操作无遮挡 | 移动端E2E | 主按钮、时间线、投票可用 | P0 Blocker | 07 |
| Debug Trace页不泄露Prompt、推理链、API Key | Debug/Logging | Trace页 | 只显示脱敏Trace | 敏感词扫描 | 命中0 | P0 Blocker | 03、05、07 |

### 20.2 P1/P2验收清单

| 优先级 | 验收项 | 通过标准 |
| --- | --- | --- |
| P1 | LifeMemory管理页完整闭环 | 查看、确认、忽略、编辑、删除、关闭个性化合规 |
| P1 | SocialSignalMock展示 | 口碑卡标Mock，缺失不阻断 |
| P1 | Benchmark自动化报告 | 输出P0/P1指标和失败定位 |
| P1 | Debug Trace可解释性 | 评委能看到输入→工具→Verifier→Recovery→Executor |
| P1 | 更多异常恢复 | 天气风险、路线延迟、预算超限可恢复或降级 |
| P2 | PlanReward/Reranker | 能展示质量提升，不影响P0闭环 |
| P2 | 多模态反馈 | 可生成合规候选记忆，高敏仍不保存 |

## 21. 自动化测试建议目录结构

```text
tests/
  contract/
    api_contract.test.ts
    static_contract_scan.test.ts
    forbidden_copywriting_scan.test.ts
    trace_event_scan.test.ts
  schema/
    plan_contract.schema.test.ts
    tool_action.schema.test.ts
    verifier_result.schema.test.ts
    recovery_result.schema.test.ts
    execution_result.schema.test.ts
    consensus.schema.test.ts
    memory.schema.test.ts
    trace_log.schema.test.ts
    mock_projection.schema.test.ts
  unit/
    intent_parser.test.ts
    constraint_extractor.test.ts
    verifier_service.test.ts
    recovery_planner.test.ts
    executor_service.test.ts
    consensus_service.test.ts
    life_memory_service.test.ts
    mock_api_service.test.ts
    api_client.test.ts
    view_model_mapper.test.ts
  integration/
    plan_create_flow.test.ts
    verify_refresh_flow.test.ts
    execute_flow.test.ts
    recovery_flow.test.ts
    consensus_finalize_flow.test.ts
    feedback_memory_flow.test.ts
    trace_aggregation_flow.test.ts
  e2e/
    family_parent_child.spec.ts
    restaurant_recovery.spec.ts
    activity_recovery.spec.ts
    friend_consensus.spec.ts
    anniversary.spec.ts
    executable_window_expired.spec.ts
    memory_privacy.spec.ts
    debug_trace.spec.ts
  bench/
    samples/
      lifepilot_bench.samples.json
    run_bench.test.ts
    metric_report.test.ts
  fixtures/
    mock_pois.json
    mock_status.json
    mock_inventory.json
    mock_routes.json
    mock_weather.json
    mock_failure_scenarios.json
    mock_social_signals.json
```

说明：

1. `bench/`中的Evaluation内部对象不得作为业务API响应。
2. `fixtures/`必须符合03/06约定，不得加入未定义领域字段。
3. `contract/static_contract_scan.test.ts`优先扫描业务代码和fixture，文档反例可配置白名单。

## 22. CI/本地测试运行建议

本地提交前建议顺序：

```text
1. 静态契约扫描
2. Schema测试
3. Unit测试
4. Integration测试
5. E2E测试
6. Benchmark评测
7. 文案和隐私扫描
8. Demo彩排检查
```

CI分层门禁：

| 阶段 | 命中失败时处理 |
| --- | --- |
| Contract Scan | P0 Blocker，禁止合入 |
| Schema Test | P0 Blocker，禁止合入 |
| Unit Test | P0模块失败禁止合入 |
| Integration Test | P0链路失败禁止合入 |
| E2E Smoke | Demo主路径失败禁止合入 |
| Full E2E | 可夜间跑，失败标记P1 Major，Demo前必须清零 |
| Benchmark Report | P1加分报告，P0指标不达标时升级Blocker |
| Copywriting/Privacy Scan | 禁止文案或隐私泄露命中即Blocker |

推荐输出报告字段：

| 字段 | 说明 |
| --- | --- |
| `run_id` | 评测运行ID，Evaluation内部对象 |
| `trace_id` | 若由真实链路产生，使用03前缀 |
| `sample_count` | 样例数 |
| `metric_results` | 指标结果，Evaluation内部对象 |
| `p0_blockers` | P0失败列表 |
| `failed_modules` | 失败定位模块 |
| `artifact_paths` | 截图、Trace、JSON报告路径 |

## 23. Demo彩排与评委评分表

### 23.1 3分钟Demo建议脚本

| 时间 | 展示 | 评委应该看懂 |
| --- | --- | --- |
| 0:00-0:20 | 开场：朋友群“随便、别太远、别太贵、我都行” | LifePilot解决的不是地点推荐，而是一段生活时间的决策和执行 |
| 0:20-0:55 | 朋友局：输入需求→候选方案→投票页→反选和文字反馈 | SocialConsensusPlanning把多人偏好压缩成可执行约束 |
| 0:55-1:25 | 共识finalize→最终PlanContract→Verifier摘要 | 最终方案不是聊天结果，而是重验后的结构化计划 |
| 1:25-2:05 | 家庭亲子：孩子5岁、配偶减脂、近距离→可执行窗口→确认执行 | ExecutableWindow+LifeOption表达“现在还能成立多久”和PlanB |
| 2:05-2:30 | 餐厅满座→Recovery Diff→`updated_plan_id`→继续执行 | Verifier/Executor/Recovery不是静态推荐器，能处理动态失败 |
| 2:30-2:45 | 纪念日轻仪式感计划和Mock消息 | Emotion-awarePlanning识别关系经营，不只是餐厅推荐 |
| 2:45-3:00 | Debug Trace页和Mock边界说明 | 工具、Mock、Verifier、Recovery可追踪；没有伪装真实支付/微信/订座 |

### 23.2 评委评分表

总分100分。

| 评分项 | 满分 | 评委看到什么 | 对应页面或Trace | 常见扣分点 | 3分钟展示建议 |
| --- | ---: | --- | --- | --- | --- |
| 产品理解分 | 10 | “导航一段生活时间”的清晰表达 | 开场、计划页时间线 | 讲成普通本地生活推荐或聊天助手 | 用一句话对比“高德导航一段路，LifePilot导航一段生活时间” |
| 闭环完整分 | 12 | 输入→计划→验证→执行→反馈/记忆 | 首页、计划页、执行页、反馈页 | 只展示生成，不展示执行和结果 | 家庭亲子路径完整跑一次 |
| 技术可信分 | 10 | API、Schema、Mock、Trace有契约 | Debug Trace页、PlanContract JSON | 口头讲技术但无可验证证据 | 展示`trace_id`和工具调用链 |
| Agent编排分 | 10 | Intent、Constraint、Retriever、Builder、Verifier清晰分工 | Debug Trace事件 | LLM像黑盒直接给答案 | 展示从意图到约束到工具的Trace |
| Verifier/Recovery分 | 12 | 餐厅满座或活动满员自动恢复 | Recovery Diff、执行页 | 失败后只报错，不能修复 | 现场触发`NO_TABLE_AVAILABLE` |
| 共识导航分 | 10 | 投票、反选、预算、文字反馈融合 | 投票页、共识页 | 只有投票UI，没有转成约束和最终计划 | 演示反选和“不想走太多”进入共识 |
| 前端体验分 | 8 | 移动端可操作，时间线清晰，状态完整 | 375px视口、计划页 | 按钮遮挡、页面跳转混乱、错误态粗糙 | 用移动端宽度演示主路径 |
| Mock边界透明度 | 8 | Mock凭证和口碑明确标注 | 执行页、MockBadge、Debug | “已真实订座/已发送微信/实时抓取” | 执行结果页主动说明“这是Mock凭证” |
| 隐私与LifeMemory合规 | 8 | 候选记忆可确认，高敏不保存 | 反馈页、Memory页 | 偷偷画像、保存高敏信息 | 展示中敏候选待确认和高敏不展示 |
| 可解释性与Trace展示 | 7 | `trace_id`串联输入、工具、Verifier、Recovery、Executor | Debug Trace页 | Trace缺失或泄露Prompt | 展示用户可见Trace和Debug脱敏Trace |
| 创新表达分 | 5 | SocialConsensusPlanning、ExecutableWindow+LifeOption、Emotion-awarePlanning、PlanContract+Verifier-Recovery、LifeMemory | 全流程 | 创新点散，和Demo脱节 | 结尾快速点名五个创新如何落在页面上 |

### 23.3 Demo彩排检查

| 检查项 | 通过标准 |
| --- | --- |
| 3分钟内完成 | 不超过3:10，核心路径不断 |
| 网络/服务稳定 | 本地或Demo环境可重复运行 |
| 固定fixture | Benchmark样例和failure_injection可复现 |
| Debug入口 | 评委模式可打开，普通用户模式默认隐藏 |
| Mock边界说明 | 不超过15秒，但必须说清楚不做真实平台能力 |
| 失败预案 | 如果现场E2E失败，可切到已录屏和Trace样例，但评分以可运行版本为准 |

## 24. 不做什么

| 不做 | 验收含义 |
| --- | --- |
| 不做真实支付 | 任何支付或订单只返回Mock订单凭证 |
| 不做真实短信/微信 | 消息只生成草案或Mock message凭证，不写真实发送 |
| 不做真实订座 | 餐厅订座只模拟，不承诺真实平台成功 |
| 不做真实票务锁定 | 活动预约只模拟，不伪装真实票务 |
| 不做真实第三方爬取 | SocialSignalMock必须标Mock，不写实时抓取 |
| 不做全城覆盖 | 只评测杭州下沙/金沙湖/高教园区数字孪生区域 |
| 不让LLM决定状态 | 余位、票务、路线、天气、执行成功、Verifier结果必须来自MockAPI/规则/服务 |
| 不把DraftPlan给前端 | 前端只消费完整PlanContract或合法展示投影 |
| 不原地覆盖Recovery | Recovery必须版本化生成新PlanContract |
| 不做不透明画像 | LifeMemory低打扰、可审计、用户可控 |
| 不泄露内部信息 | Prompt、推理链、API Key、高敏payload不得进入Trace或前端 |

## 25. 交付前最终Checklist

| 类别 | Checklist | 结果要求 |
| --- | --- | --- |
| Schema | 所有PlanContract通过03 JSONSchema | 100% |
| API | 所有路径使用`/api/v1`，响应为`success/trace_id/data/error` | 100% |
| 错误码 | 只使用04定义错误码 | 100% |
| Trace | 只使用最终Trace事件枚举 | 100% |
| Intent | 三类P0场景识别正确 | 100%主样例 |
| Constraint | 显式约束优先，默认值写assumption | 100%主样例 |
| Mock | 状态、凭证、口碑均标Mock | 100% |
| Verifier | fail阻断，warning展示风险和PlanB | 100% |
| Window | 窗口字段完整，过期可处理 | 100% |
| Executor | 执行类接口缺幂等键不得成功 | 100% |
| Recovery | 餐厅满座、活动满员生成`updated_plan_id` | 100% |
| Consensus | 投票字段、finalize、最终计划重Verifier | 100% |
| LifeMemory | 中敏待确认，高敏不保存，关闭个性化不读写 | 100% |
| Frontend | 首页、生成、计划、投票、共识、执行、反馈、Debug路径可演示 | P0主路径100% |
| Mobile | 375px无阻塞问题 | 100%主路径 |
| 文案 | 禁止真实支付、真实微信、真实订座、真实锁票、实时抓取 | 命中0 |
| Debug | Debug Trace不泄露Prompt、LLM推理链、API Key | 命中0 |
| Bench | 15类Benchmark样例可运行并生成指标报告 | P0指标达标 |
| Demo | 3分钟脚本完成正常路径、Recovery路径、共识路径和Trace解释 | 彩排通过 |

## 26. 2026-05-23追加：类脑POI推荐体验回归

为避免推荐退化为机械地点列表，新增三条体验回归样例。它们只作为评测样例和测试断言，不新增领域Schema或API契约。

| sample_id | 输入 | 核心断言 |
| --- | --- | --- |
| `bench_brain_solo_drink_001` | “我今天有点不开心，想找个地方喝点酒，晚上十点之前到家” | 首个非转场节点必须是可小酌/酒馆语义；不得用棋牌、纯咖啡或随机低价节点替代；最终时间不得超过回家截止时间 |
| `bench_brain_date_craft_meal_001` | “我周末想和女朋友去做手工，顺便安排一顿漂亮饭” | 场景识别为约会/情绪类；必须包含手作/DIY/陶艺等参与型活动；餐饮不得退化为萨莉亚、米村、麦当劳、奶茶等低匹配节点 |
| `bench_brain_family_visit_xiasha_001` | “这周末我姐要来下沙找我玩，帮我安排一下行程” | 场景识别为城市轻探索/家人来访；party_size=2；优先下沙/金沙湖区域、招待友好、好聊天、路线简单；不得推荐棋牌、KTV、电竞、健身或低端快餐饮品作为核心节点 |

通过标准：

1. 三条样例均返回完整`PlanContract`，且`VerifierResult.status`只能是`pass`或可展示PlanB的`warning`。
2. 普通计划页展示“类脑推荐优先级”中文投影，不展示英文枚举、Prompt、推理链或底层权重。
3. 单条计划生成应在本地500 POI候选池下保持秒级返回；重复状态打分必须使用缓存或等价优化。

## 27. 2026-05-23追加：显式餐饮与亲子安全体验回归

新增两条体验回归样例，验证类脑推荐引擎不会把显式诉求稀释成机械邻近POI。

| sample_id | 输入 | 核心断言 |
| --- | --- | --- |
| `bench_brain_family_light_dinner_001` | “今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭要清淡一点。” | 场景识别为亲子；包含`light_meal/low_queue/child_friendly`画像；晚饭餐厅排在最后且不早于傍晚；不得推荐电竞、网咖、棋牌、KTV、台球、健身、酒吧、火锅、烧烤、麻辣等节点；活动必须体现亲子/手作/儿童可参与语义 |
| `bench_brain_date_hotpot_001` | “周末想和女朋友出去放松一下，下午活动你来安排，但晚上我们想去吃火锅” | 场景识别为约会/情绪类；必须保留`hotpot/dinner/date_friendly`画像；最后一个餐饮节点必须是火锅语义餐厅；不得用咖啡、茶空间、甜品或普通餐厅替代火锅 |

通过标准：

1. 两条样例均返回完整`PlanContract`，且`VerifierResult.status`只能是`pass`或可展示PlanB的`warning`。
2. 显式餐饮偏好优先级高于距离近邻、默认品质餐厅和通用约会氛围标签。
3. 亲子安全闸门是硬约束，不得仅依赖排序低分。
4. 计划链路仍需保留Mock边界：排队、余位、路线和可执行窗口来自MockAPI/Verifier，不由LLM直接承诺。

## 28. 2026-05-23追加：类脑策略层与烤肉锚点回归

新增评测目标：证明推荐不是对少数样例写死，而是通过可维护策略、类脑评分和硬约束门控泛化到新POI和新表达。

### 28.1新增体验回归

| sample_id | 输入 | 核心断言 |
| --- | --- | --- |
| `bench_brain_date_bbq_001` | “周末想和女朋友出去放松一下，下午活动你来安排，但晚上我们想去吃烤肉” | 场景识别为约会/情绪类；必须保留`bbq/grill/dinner/date_friendly`画像；最后一个餐饮节点必须是烤肉/烧烤/烧肉/炭烤语义餐厅；不得用咖啡、茶空间、甜品、普通餐厅或火锅替代烤肉 |

### 28.2类脑策略层断言

| 断言 | 说明 |
| --- | --- |
| 策略可维护 | `backend/data/brain_policy.json`存在，允许维护语义词典、显式餐饮锚点和场景画像 |
| 规则与模型解耦 | 规则硬门控不依赖训练模型；模型不可用时P0样例仍可通过 |
| 泛化输入 | 新增POI通过名称、类别、标签、价格、评分、区域、路线和状态参与评分，不要求训练集中出现同一POI ID |
| 状态边界 | 类脑引擎不得直接判断餐厅有位、活动可预约、路线通畅、天气安全或执行成功 |
| 普通页脱敏 | 前端不得展示底层权重、Prompt、模型推理链、API Key或训练样本细节 |

### 28.3训练评测建议

如果接入本地双卡5090训练的重排模型，新增离线指标：

| 指标 | 通过标准 |
| --- | --- |
| Pairwise Preference Accuracy | 人工标注候选链路pair上准确率高于规则baseline |
| TopK Dining Anchor Hit Rate | 明确餐饮锚点样例中Top1餐厅命中硬偏好，阈值100% |
| New POI Generalization | 新增未训练POI进入候选池后，基于文本/类别/状态可被正确召回和重排 |
| Rule Override Safety | 模型高分但违反亲子安全、显式餐饮或Mock边界时必须被规则/Verifier拦截 |

## 29. 2026-05-23追加：POI语义对齐与日料泛化回归

新增评测目标：验证推荐系统能从用户一句话中抽取餐饮语义，并与开放POI池对齐，而不是只靠几个固定样例或通用氛围标签。

### 29.1新增体验回归

| sample_id | 输入 | 核心断言 |
| --- | --- | --- |
| `bench_brain_date_japanese_001` | “周末想和女朋友出去放松一下，晚上想吃日料” | 场景识别为约会/情绪类；必须保留`cuisine_japanese/dinner/date_friendly`画像；餐厅节点必须命中日料/日本料理/寿司/刺身/居酒屋/烧鸟/鮨/和风/会席等语义；不得用茶空间、咖啡、M Stand、瑞幸、库迪或普通氛围餐厅替代 |
| `bench_brain_date_japanese_short_001` | “周末想和女朋友吃日料” | 未写“下午”时默认进入晚餐窗口；餐厅槽位仍必须命中日料语义；时间线不得把晚餐压到下午早段 |

### 29.2通过标准

1. `IntentParser`输出中必须包含`cuisine_japanese`和`dinner`，寿司/居酒屋细分表达应额外包含`sushi/izakaya`。
2. `ConstraintSet.must_have`必须包含对应餐饮硬锚点，避免被通用`quality_dining/ambience_dining`覆盖。
3. `CandidateRetriever`的餐厅Top1必须命中日料语义；如果状态不可用，应通过PlanB/Recovery寻找同语义备选，而不是静默降级到非日料。
4. 日料泛化不依赖固定POI ID；新增POI只要文本或标签中出现可识别语义，就应进入召回和重排。
5. 普通用户页只展示“日料、寿司、居酒屋、正式用餐”等中文投影，不展示内部评分、Prompt、训练样本或模型推理链。

### 29.3离线评测建议

| 指标 | 通过标准 |
| --- | --- |
| Utterance-POI Alignment Hit Rate | 明确餐饮表达样例中，Top1餐厅命中对应语义，P0目标100% |
| Semantic Generalization | 未训练POI仅凭名称/类别/标签可被正确召回，人工抽样通过率高于规则变更前baseline |
| Wrong-Cluster Suppression | 日料请求不得落到茶空间、咖啡、甜品或普通氛围餐厅；烤肉/火锅请求同理不得互相替代 |
| Reranker Safety | 本地模型高分但违反显式餐饮锚点时，必须被规则硬门控拦截 |

## 30. 2026-05-23追加：开放餐饮偏好画像回归

新增评测目标：验证系统能处理开放餐饮短语，而不是只对火锅、烤肉、日料等少数硬编码样例有效。

### 30.1新增体验回归

| sample_id | 输入 | 核心断言 |
| --- | --- | --- |
| `bench_brain_date_lamb_chop_001` | “这周末想和女朋友吃烤羊排” | 必须保留`lamb/bbq/grill/dinner/date_friendly`画像；餐厅节点命中羊肉、烧烤、烤肉或烤羊排相关语义；不得推荐茶空间、咖啡、M Stand、瑞幸、库迪作为餐厅；未明说手作时不得默认落到“蕉个朋友DIY手工” |
| `bench_brain_date_western_001` | “这周末想和女朋友吃西餐” | 必须保留`western_cuisine/dinner/date_friendly`画像；餐厅节点命中西餐、牛排、意面、披萨或LOFT等西餐语义；不得被茶空间、咖啡或普通氛围餐厅替代 |
| `bench_brain_date_diet_001` | “这周末女朋友想减脂，帮我安排晚饭” | 必须保留`healthy_light/light_meal/light_food/dinner`画像；餐厅节点命中清淡、低卡、轻食、日式料理、蒸、汤、椰子鸡等低负担语义；不得落到火锅、烧烤、麻辣、茶空间或咖啡 |
| `bench_brain_date_light_meal_001` | “这周末想和女朋友吃点清淡的” | 未声明下午时默认进入晚餐窗口；最后餐厅必须命中清淡正餐语义；不得落到火锅、烧烤、烤肉、麻辣等重口味节点 |

### 30.2通过标准

1. `extract_dining_preference()`必须输出`explicit=true`、原始短语、扩展词、受控标签和预算提示。
2. 如果当前候选池存在开放画像命中餐厅，`CandidateRetriever`必须开启餐厅槽位硬门控。
3. 餐厅Top1命中用户明说的食物/菜系/饮食目标，P0目标100%。
4. 用餐为主的约会请求不再默认把手作当第一节点，除非用户明说手作/DIY。
5. 回归样例不得暴露Prompt、模型推理链、底层权重、API Key或failure injection。

### 30.3离线评测建议

| 指标 | 通过标准 |
| --- | --- |
| Open Dining Alignment Hit Rate | 开放餐饮样例Top1餐厅命中对应语义，P0目标100% |
| Wrong Fallback Rate | 明确吃X时落到咖啡、茶空间、普通氛围餐厅或不相关活动的比例为0 |
| Diet Safety Hit Rate | 减脂/清淡样例不得命中火锅、烧烤、麻辣、酸菜鱼等重口味节点 |
| New Term Generalization | 新增食物词通过短语抽取、扩展词和POI文本匹配进入候选，而不是要求新增固定POI ID规则 |
## 31. 2026-05-24追加：时间锚点与赛事闭环回归

新增后端回归：

| 用例 | 输入 | 核心断言 |
| --- | --- | --- |
| `test_current_time_anchor_does_not_force_weekend_afternoon_start` | `current_time=2026-05-23T18:00:00+08:00`，用户说“周末下午我想去一个人散散心，顺便喝杯酒。” | `time_window.start_time`必须为`2026-05-24T15:00:00+08:00`，不得从18:00直接开始；`constraints.planning_anchor_time`保留原始当前时间 |

P0 runner同步增加：

```text
test_current_time_anchor_weekend_afternoon
```

通过标准：

1. 首页当前时间字段不会覆盖自然语言时间窗口。
2. “周末下午”在周六18:00之后滚动到周日可执行下午窗口。
3. “下午+喝杯酒”允许生成15:00-19:00的低压力活动窗口。
4. 原有“我想下午一个人找个地方散散心”仍稳定为14:00-18:00。

## 32. 2026-05-24追加：投票与Mock执行体验验收

新增体验验收点：

| 能力 | 验收 |
| --- | --- |
| 投票动态预算 | 投票页填写人均预算后，动态预览出现“人均不超过X元”；finalize后共识约束使用预算下限 |
| 投票路线偏好 | 步行容忍选择“少走路/能少走就少走”后，动态预览提示路线压低步行；finalize后`must_have`包含`low_walking` |
| 候选摘要 | `candidate_plans`包含`timeline_summary`、预算和可执行窗口，普通页不展示内部DraftPlan |
| Mock订座 | 执行成功结果展示Mock订座号，并能看到订座前余桌/排队摘要 |
| Mock预约 | 执行成功结果展示Mock预约号，并能看到预约前余票摘要 |
| 风险分支 | 餐厅无桌或活动满员时仍进入版本化Recovery，保留`original/replacement/diff/updated_plan_id` |

自动化建议：

1. Playwright覆盖首页默认时间锚点，提交“周末下午独处小酌”后检查首个时间不是18:00。
2. Playwright覆盖朋友局投票页预算/路线预览和提交后进入共识页。
3. 后端TestClient覆盖Mock订座返回`available_tables_before/queue_minutes/reservation_expires_at`。

## 33. 2026-05-24追加：多节点纪念日长窗口回归

新增后端回归：

| 用例 | 输入 | 核心断言 |
| --- | --- | --- |
| `test_anniversary_explicit_long_window_generates_multi_stop_itinerary` | `current_time=2026-05-23T09:00:00+08:00`，用户说“今晚想给纪念日安排一段轻松一点的约会，不夸张，预算适中，路线别太折腾。安排4-5个活动。下午一点出发，晚上十点钟回来” | `time_window`为13:00-22:00；`target_stop_count_range=[4,5]`；真实POI节点为4-5个；首个POI 13:00开始；晚餐不早于17:30；预算和Verifier均通过。 |

P0 runner同步增加：

```text
test_anniversary_long_multi_stop_window
```

数据与工具验收：

1. `tools/gaode_data_factory/generate_lifepilot_dataset.py --help`中路线默认近邻应为4，不再是1。
2. `mock_inventory.json`至少包含可演示的晚餐时段slot，使MockAPI能返回余桌和排队分钟。
3. `validate_mock_data.py`、`contract_scan.py`和`run_backend_p0_tests.py`必须通过。
4. 前端`npm run typecheck`必须通过，确保PlanContract多节点timeline仍可渲染。

## 34. 2026-05-26追加：重构验收基线

重构后的最小验收基线如下：

| 类别 | 命令 | 通过标准 |
| --- | --- | --- |
| 后端P0 | `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/run_backend_p0_tests.py` | 25项P0与推荐回归全部PASS |
| 契约扫描 | `PYTHONPATH=backend python3 scripts/contract_scan.py` | 不出现旧路径、敏感字段、误导真实执行文案 |
| Mock数据 | `PYTHONPATH=backend python3 scripts/validate_mock_data.py` | fixture引用完整，Mock状态引擎spot check通过 |
| Python编译 | `PYTHONPATH=backend python3 -m compileall -q backend/app scripts tests tools/...` | 无语法错误 |
| 前端类型 | `cd frontend && npm run typecheck` | TypeScript无错误 |
| 前端Lint | `cd frontend && npm run lint` | 无ESLint warning/error |
| E2E Smoke | `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/run_p0_frontend_smoke.py` | 后端、前端、契约、Mock校验和Playwright E2E均通过 |

当前本机全局Python 3.13环境下，标准`python3 -m pytest ...`仍可能以`-1`无输出退出，视为环境问题；同批核心断言必须进入`run_backend_p0_tests.py`或其他项目runner覆盖。

Playwright默认单worker执行，以降低重型计划生成在本地开发机上的代理超时和连接重置概率。并发压测应另设专项性能测试，不作为P0 smoke默认模式。
