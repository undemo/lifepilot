# 09_demo_script.md

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 文档名称 | `09_demo_script.md` |
| 项目名称 | LifePilot |
| 产品定位 | 生活时间导航Agent |
| 文档类型 | Demo脚本、现场演示、视频脚本、彩排指南 |
| 文档版本 | v0.1 |
| 面向读者 | 演示负责人、前端、后端、Agent、Mock、测试、答辩同学、评委 |
| 当前范围 | 比赛Demo阶段，P0闭环优先 |
| Demo区域 | 杭州下沙/金沙湖/高教园区 |
| 默认时区 | Asia/Shanghai |
| 技术假设 | React/Next.js Web Demo、Backend API Service、JSON/SQLite Demo存储 |
| 契约基准 | 00-08文档 |

本文件是演示执行文档，不是新的产品、接口或数据契约。文中出现的“镜头脚本”“讲解话术”“预置状态”“彩排清单”均为演示辅助内容，不进入`03_data_schema.md`或`04_api_contract.md`。

## 2. 文档目标与边界

09回答以下问题：

| 问题 | 09中的交付 |
| --- | --- |
| 评委3分钟内如何理解LifePilot不是普通推荐器 | 总叙事、逐秒脚本、结尾金句 |
| 演示人员按什么顺序点击页面 | 页面级操作脚本、三条核心演示线 |
| 每个页面应该讲哪一句话 | 逐秒话术、话术库、视频旁白 |
| 哪些Trace、Verifier、MockAPI、Recovery、Consensus、LifeMemory信息需要展示 | 页面展示清单、Debug Trace说明、联调检查 |
| 哪些内容只给评委/Debug看，哪些不能给普通用户看 | Demo红线、Trace可见性、Mock边界 |
| 现场失败如何兜底 | 失败兜底表、预置数据清单 |
| 彩排时如何检查P0闭环 | P0/P1/P2验收清单、10分制自查表 |

09不回答以下问题：

| 不回答 | 原因 |
| --- | --- |
| 09不是PRD | 产品范围、P0/P1/P2以`01_prd.md`为准 |
| 09不是API契约 | HTTP路径、标准响应、错误码、幂等规则以`04_api_contract.md`为准 |
| 09不是Schema | 字段、ID前缀、状态枚举、对象结构以`03_data_schema.md`为准 |
| 09不是Mock实现文档 | MockAPI路径、fixture、失败注入以`06_mock_api_design.md`为准 |
| 09不新增功能 | 只把已有功能组织成评委可理解、团队可执行的Demo |

## 3. 来源文档与契约优先级

实际来源中数据契约文件名为`03_schema.md`，正文统一使用最终文件名`03_data_schema.md`。

| 优先级 | 来源 | 09中的使用方式 |
| ---: | --- | --- |
| 1 | `03_data_schema.md` | 字段、ID前缀、状态枚举、PlanContract、VerifierResult、RecoveryResult、ExecutionResult、Consensus、LifeMemory、TraceLog最终权威 |
| 2 | `04_api_contract.md` | API路径、标准响应、错误码、幂等键、Mock接口路径、Debug边界最终权威 |
| 3 | `05_agent_workflow.md` | Agent编排顺序、Verifier闸门、Executor、Recovery、Consensus、LifeMemory流程最终权威 |
| 4 | `06_mock_api_design.md` | MockAPI路径、Mock标识、failure_injection、Mock凭证、Mock边界最终权威 |
| 5 | `07_frontend_design.md` | 前端页面、路由、ViewModel、移动端、Debug Trace、错误展示最终权威 |
| 6 | `08_evaluation_design.md` | 评测指标、Demo验收、红线扫描、彩排测试、评委评分最终权威 |
| 7 | `02_system_architecture.md` | 系统分层、模块职责、端到端链路 |
| 8 | `01_prd.md` | 产品范围、页面需求、P0/P1/P2、用户流程 |
| 9 | `00_project_vision.md` | 产品定位、核心隐喻、Demo故事、创新点、不做什么 |

冲突处理规则：

1. 任何字段、枚举、ID前缀、状态、Schema必填项冲突，一律以`03_data_schema.md`为准。
2. 任何API路径、错误码、响应格式、幂等规则冲突，一律以`04_api_contract.md`为准。
3. 任何Agent流程、Verifier闸门、Recovery版本化策略冲突，一律以`05_agent_workflow.md`为准。
4. 任何Mock路径、Mock标识、failure_injection可见性冲突，一律以`06_mock_api_design.md`为准。
5. 任何前端页面、路由、组件、普通用户/Debug可见性冲突，一律以`07_frontend_design.md`为准。
6. 任何Demo评分、彩排、红线验收冲突，一律以`08_evaluation_design.md`为准。
7. 09不得新增领域Schema字段、API路径、错误码、Trace事件名、ToolAction.type、Mock能力。
8. 09可以定义“Demo内部脚本对象”“彩排清单”“镜头脚本”“讲解话术”，但必须标注为演示辅助内容，不进入03 Schema或04 API契约。

## 4. Demo总叙事

Storyline：

```text
用户不是缺推荐，而是缺一个能把“这一段时间怎么过”规划、验证、锁定、恢复并解释清楚的生活导航Agent。
```

痛点开场：

用户说“随便、都行、别太远、别太贵”，真实问题不是没有地点，而是多人偏好、时间窗口、孩子年龄、饮食约束、排队风险、天气路线和执行失败交织在一起，没人愿意拍板，也没人能保证这段时间真的可执行。

LifePilot一句话定位：

```text
高德导航的是一段路，LifePilot导航的是一段生活时间。
```

LifePilot不是普通POI搜索、聊天机器人、静态攻略生成器、真实交易平台或不透明画像系统。它从一句自然语言目标出发，生成可共识、可验证、可执行、可恢复的本地生活计划。

核心闭环：

```text
自然语言目标
→ 意图解析
→ 约束抽取
→ 候选POI/餐厅/路线/天气状态查询
→ 生成PlanContract
→ Verifier检查可执行性
→ 展示可执行窗口、风险和PlanB
→ 用户/群体确认
→ Executor模拟预约、排号、订票、下单、发消息
→ 失败时Recovery生成新PlanContract
→ 低打扰反馈
→ LifeMemory候选更新
→ Trace可解释展示
```

三个创新能力：

| 创新能力 | Demo表达 | 评委应该记住 |
| --- | --- | --- |
| 共识导航 SocialConsensusPlanning | 朋友局候选方案、投票、反选、预算、文字反馈、ConsensusSummary | 把群聊拉扯压缩成低摩擦选择题，再转成可执行约束 |
| 机会导航 ExecutableWindow + LifeOption | 家庭亲子可执行窗口、风险、PlanB、过期刷新 | LifePilot不只说“去哪”，还说“现在还能不能成行、窗口多久失效” |
| 情绪导航 Emotion-awarePlanning | 纪念日轻仪式流程、自然话术、备注边界 | 不是推荐高评分餐厅，而是把用心落成动作 |

技术可信点：

| 技术点 | 现场展示方式 |
| --- | --- |
| PlanContract | 计划页以时间线、预算、可执行窗口、ToolAction、Verifier摘要渲染 |
| Verifier | 展示`VerifierResult.status=pass/warning/fail`摘要、检查项和风险 |
| MockAPI | 标注Demo模拟数据，状态和凭证来自MockAPI，不由LLM或前端编造 |
| Executor | 只执行`ToolAction`，执行类接口携带`X-Idempotency-Key` |
| Recovery | 餐厅满座返回`NO_TABLE_AVAILABLE`，生成`updated_plan_id`的新计划 |
| Trace | Debug页展示脱敏Trace，不展示Prompt、推理链、API Key |
| LifeMemory | 反馈后生成MemoryCandidate，用户确认或忽略，高敏不保存 |

## 5. 推荐Demo时长方案

### 5.1 90秒极速版

| 时间 | 内容 | 页面 |
| --- | --- | --- |
| 0:00-0:15 | 痛点：用户不是缺地点，是缺这段时间怎么安排得不踩雷 | 口播或首页 |
| 0:15-1:00 | 家庭亲子输入→计划生成→PlanContract时间线→Verifier→可执行窗口 | `/`、`/plans/creating`、`/plans/[planId]` |
| 1:00-1:20 | 确认执行→餐厅满座→Recovery Diff→`updated_plan_id` | `/execution/[executionId]` |
| 1:20-1:30 | 总结：可验证、可执行、可恢复、可解释 | `/debug/traces/[traceId]`或计划页 |

### 5.2 3分钟标准版

这是比赛主版本，优先稳定跑通家庭亲子和朋友局，纪念日作为快速横切展示。

| 时间 | 内容 |
| --- | --- |
| 0:00-0:20 | 痛点开场：不是去哪，而是怎么安排得不踩雷 |
| 0:20-0:40 | 一句话输入与目标理解 |
| 0:40-1:20 | 家庭亲子PlanContract、时间线、可执行窗口、Verifier |
| 1:20-1:50 | Executor执行与餐厅满座Recovery |
| 1:50-2:25 | 朋友局投票与Consensus |
| 2:25-2:45 | 纪念日情绪导航快速展示 |
| 2:45-3:00 | Trace、Mock边界、总结金句 |

### 5.3 5分钟答辩版

| 增加内容 | 展示价值 |
| --- | --- |
| Debug Trace页 | 解释Agent不是黑盒聊天壳，Trace覆盖`input_log`到`error_log` |
| LifeMemory候选 | 证明不是不透明画像，候选需要确认或忽略 |
| Benchmark/评测结果入口 | 对齐08评测，说明如何证明P0闭环 |
| 前后端契约解释 | 展示`/api/v1`路径、标准响应、幂等键、错误码白名单 |
| P0/P1/P2边界说明 | 说明6月7日前能稳定交付什么，未来接入真实平台时如何扩展 |

## 6. 3分钟标准Demo逐秒脚本

| 时间段 | 演示页面/动作 | 讲解话术 | 页面应展示 | 技术点 | 兜底方案 |
| --- | --- | --- | --- | --- | --- |
| 0:00-0:20 | 打开`/`，展示输入框和快捷样例 | “我们解决的不是‘附近有什么’，而是这一段生活时间怎么安排得不踩雷。比如孩子5岁、配偶减脂、别太远、还要能订得上。” | 首页标题、一句话输入、家庭/朋友/纪念日样例 | 产品定位，非普通推荐器 | 若首页加载慢，直接播放首页录屏并切到预置`plan_id` |
| 0:20-0:32 | 在`/`输入家庭亲子样例，点击“开始导航这一段生活时间” | “我只输入一句话，LifePilot先理解目标和约束，而不是直接扔几个地点。” | 输入文本：今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。 | `POST /api/v1/plans/create`，建议带`X-Idempotency-Key` | 用固定Demo模板创建预置计划 |
| 0:32-0:40 | 进入`/plans/creating` | “生成中不是等LLM闲聊，而是在做结构化规划：理解目标、查候选、查状态、估路线、准备PlanB。” | 进度：理解目标、检索地点、检查余位、估算路线、准备PlanB | Agent主链路，Trace摘要 | 生成超过8秒，跳转预置`/plans/[planId]` |
| 0:40-1:00 | 打开`/plans/[planId]`，停留目标理解和时间线 | “这里已经把一句话落成一段时间线：亲子活动、低卡餐厅、轻松散步和返程。孩子5岁、配偶减脂、别太远都变成约束。” | 目标摘要、孩子5岁、低卡/轻食、不远、不赶、活动+餐厅+散步/返程时间线 | PlanContract、ConstraintSet、PlanStep | 若地图卡异常，只讲时间线和约束摘要 |
| 1:00-1:20 | 展示可执行窗口、风险与PlanB、工具调用链 | “这不是静态攻略。Verifier会检查路线、天气、余位、排队和预算，并给出当前可执行窗口。窗口过期后必须重新校验。” | `ExecutableWindow`、预算、风险、BackupPlan、`trace_id`摘要、确认执行按钮 | VerifierResult、ExecutableWindow、BackupPlan不是完整PlanContract | 若窗口显示过期，点击`POST /api/v1/plans/{plan_id}/refresh-window` |
| 1:20-1:32 | 点击确认执行，进入`/execution/[executionId]` | “执行也不是页面自己判断成功，Executor只按PlanContract里的ToolAction调用Mock工具。” | 活动预约、餐厅订座/排号、消息生成进度 | `POST /api/v1/plans/{plan_id}/execute`，执行类接口必须带`X-Idempotency-Key` | 若执行页慢，刷新执行页或读取`GET /api/v1/plans/{plan_id}`摘要 |
| 1:32-1:50 | 触发餐厅满座，展示Recovery Diff和`updated_plan_id` | “这里模拟餐厅执行时满座，返回`NO_TABLE_AVAILABLE`。LifePilot不会原地改旧计划，而是生成新的`updated_plan_id`，替换同区域低卡餐厅，并重新Verifier。” | 失败动作、用户文案、Recovery Diff、`updated_plan_id`、新计划Verifier pass/warning、Mock凭证 | `NO_TABLE_AVAILABLE`、RecoveryResult、版本化Recovery | 如果没触发，切Debug失败注入样例或预置执行结果 |
| 1:50-2:02 | 切到朋友局输入或预置`/vote/[votePageId]` | “第二条线是朋友局。群聊里最难的是‘都行’，LifePilot把拉扯变成候选方案和低摩擦投票。” | 候选方案卡片、二维码/分享卡、多选/反选入口 | `POST /api/v1/consensus/create`、`GET /api/v1/vote-pages/{vote_page_id}` | 用预置投票页和3-4条投票 |
| 2:02-2:15 | 在`/vote/[votePageId]`提交朋友偏好 | “朋友可以多选、反选、填预算，也可以写‘不想走太多’。这些会进入Consensus，而不是只算票数。” | liked/disliked、预算、人均、文字反馈、提交成功 | `POST /api/v1/consensus/{consensus_session_id}/vote`，投票校验 | 若没人操作，用预置投票数据 |
| 2:15-2:25 | 打开`/consensus/[consensusSessionId]`并finalize | “finalize后生成ConsensusSummary，把冲突压缩成共识约束，并重新生成最终PlanContract，再走Verifier。” | 投票统计、冲突压缩、共识约束、最终方案、群聊消息草案或Mock消息 | `POST /api/v1/consensus/{consensus_session_id}/finalize`，最终计划重Verifier | 若finalize失败，用预置ConsensusSummary |
| 2:25-2:45 | 打开纪念日预置计划`/plans/[planId]` | “第三条线是情绪导航。它不是推荐高档餐厅，而是识别‘不夸张但用心’，安排看展/散步、安静餐厅、蛋糕备注、合照点和自然邀请话术。” | 轻仪式流程、靠窗/蛋糕备注、合照点、可复制邀请话术、Mock订座或Mock消息边界 | Emotion-awarePlanning、`order_item`可选、`send_message` Mock | 用静态预置计划页截图 |
| 2:45-3:00 | 打开`/debug/traces/[traceId]`或计划页Trace摘要 | “最后强调边界：这里是Demo模拟数据，MockAPI模拟查询和执行；Trace展示可见工具调用摘要，不展示Prompt、推理链或API Key。高德导航一段路，LifePilot导航一段生活时间。” | `input_log`到`error_log`脱敏Trace、Mock标识、Verifier、Recovery、Executor摘要 | TraceLog、Mock边界、隐私边界 | Trace加载失败时展示静态Trace截图 |

## 7. 页面级操作脚本

### 7.1 首页/一句话输入页

| 项 | 内容 |
| --- | --- |
| 路由 | `/` |
| 操作 | 输入“今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。” |
| 点击 | “开始导航这一段生活时间” |
| API | `POST /api/v1/plans/create` |
| 页面应该出现 | 一句话输入、快捷样例、Demo模拟数据提示 |
| 讲解 | “LifePilot不是搜索地点，而是把一句生活目标变成一段可验证、可执行、可恢复的时间线。” |
| 注意 | 不展示Prompt、模型链路、底层Mock fixture |

### 7.2 计划生成中页面

| 项 | 内容 |
| --- | --- |
| 路由 | `/plans/creating` |
| 操作 | 等待生成进度走完，必要时直接跳预置计划 |
| 页面应该出现 | 理解目标、检索地点、检查余位、估算路线、准备PlanB |
| 讲解 | “这里展示的是结构化规划过程，不是等待LLM闲聊。最终以API返回的PlanContract为准。” |
| Trace摘要 | 可展示用户可见的`input_log`、`intent_log`、`constraint_log`、`poi_log`、`tool_log` |
| 注意 | 普通用户页不展示`failure_injection`、Prompt、推理链、API Key |

### 7.3 计划结果页

| 项 | 内容 |
| --- | --- |
| 路由 | `/plans/[planId]` |
| 依赖API | `GET /api/v1/plans/{plan_id}`、`POST /api/v1/plans/{plan_id}/verify`、`POST /api/v1/plans/{plan_id}/refresh-window`、`POST /api/v1/plans/{plan_id}/execute`、`GET /api/v1/plans/{plan_id}/trace` |
| 页面必须展示 | 目标理解摘要、时间线、地图/路线卡、可执行窗口、预算、风险与PlanB、工具调用链、确认执行按钮、`trace_id`摘要 |
| 讲解重点 | “PlanContract驱动前端渲染；Verifier检查可执行性；MockAPI状态来自工具，不由LLM编造；当前方案在窗口内可执行。” |
| 可见内容 | 工具调用中文摘要、Mock弱提示、Verifier摘要、风险和PlanB |
| 不可见内容 | `failure_injection`细节、Mock fixture、Prompt、推理链、高敏MemoryCandidate |

### 7.4 执行结果页

| 项 | 内容 |
| --- | --- |
| 路由 | `/execution/[executionId]` |
| 依赖API | `GET /api/v1/plans/{plan_id}`、可选`GET /api/v1/executions/{execution_id}`、`GET /api/v1/executions/{execution_id}/actions`、`POST /api/v1/plans/{plan_id}/recover`、`GET /api/v1/plans/{plan_id}/trace` |
| 页面必须展示 | 活动预约Mock凭证、餐厅订座/排号Mock凭证、消息发送Mock凭证、失败动作、Recovery Diff、`updated_plan_id`、新计划重新Verifier |
| 讲解重点 | “执行结果是Mock凭证，不是真实商家订座；失败后Recovery版本化生成新计划，不覆盖旧PlanContract。” |
| 正确凭证文案 | Mock预约号已生成、Mock订座号已生成、Mock订单号已生成、模拟消息已生成 |
| 失败展示 | 用户只看`error.user_message`，Debug可看错误码和脱敏Trace |

### 7.5 朋友投票页

| 项 | 内容 |
| --- | --- |
| 路由 | `/vote/[votePageId]` |
| 依赖API | `GET /api/v1/vote-pages/{vote_page_id}`、`POST /api/v1/consensus/{consensus_session_id}/vote` |
| 页面必须展示 | 候选方案卡片、多选、反选、预算选择、文字反馈、提交反馈 |
| 讲解 | “这里不是群聊里继续争，而是把偏好变成结构化投票：喜欢什么、反对什么、预算多少、排队和步行能不能接受。” |
| 注意 | 投票页不展示完整ToolAction payload，不展示参与者内部ID，不展示Debug payload |

### 7.6 共识结果页

| 项 | 内容 |
| --- | --- |
| 路由 | `/consensus/[consensusSessionId]` |
| 依赖API | `POST /api/v1/consensus/{consensus_session_id}/finalize`、`GET /api/v1/plans/{final_plan_id}`、可选`GET /api/v1/consensus/{consensus_session_id}/summary` |
| 页面必须展示 | 投票统计、冲突压缩说明、最终方案、重新Verifier结果、群聊消息草案或Mock消息 |
| 讲解 | “ConsensusSummary不是投票结果截图，而是把预算、反选、步行容忍度和文字反馈压缩成共识约束，再生成最终PlanContract。” |
| 注意 | 未finalize时不能伪造ConsensusSummary；finalize后最终PlanContract必须重新Verifier |

### 7.7 纪念日快速展示页

| 项 | 内容 |
| --- | --- |
| 路由 | 可用预置`/plans/[planId]` |
| 页面必须展示 | 轻仪式流程、靠窗/蛋糕备注、合照点、自然邀请话术 |
| 讲解 | “纪念日不是简单推荐高分餐厅，而是把‘不夸张但用心’拆成可执行动作。” |
| Mock边界 | 订座、备注、蛋糕服务、消息都只能是Mock凭证或可复制草案 |
| 注意 | 不说真实微信已发送、真实订座、真实支付或真实锁票 |

### 7.8 反馈与LifeMemory候选页

| 项 | 内容 |
| --- | --- |
| 路由 | `/feedback/[planId]`、`/memory` |
| 依赖API | `GET /api/v1/feedback/questions?plan_id=...`、`POST /api/v1/feedback`、`GET /api/v1/memory/candidates`、`POST /api/v1/memory/candidates/{candidate_id}/confirm`、`POST /api/v1/memory/candidates/{candidate_id}/ignore` |
| 页面必须展示 | 低打扰问题、最多1-2个追问、MemoryCandidate、确认/忽略入口、记忆来源 |
| 讲解 | “LifeMemory不是偷偷画像。它只生成候选，用户能确认或忽略；高敏信息默认不保存；用户可控、可审计。” |
| 注意 | 中敏如孩子年龄、配偶近期减脂需要确认；高敏不展示细节、不保存 |

### 7.9 Debug Trace页

| 项 | 内容 |
| --- | --- |
| 路由 | `/debug/traces/[traceId]` |
| 依赖API | `GET /api/v1/traces/{trace_id}`、`GET /api/v1/traces/{trace_id}/events`、`GET /api/v1/plans/{plan_id}/trace` |
| 页面必须展示 | `input_log`、`intent_log`、`constraint_log`、`poi_log`、`tool_log`、`verifier_log`、`recovery_log`、`executor_log`、`feedback_log`、`error_log` |
| 讲解 | “Trace展示的是可见工具调用摘要和脱敏Debug投影，不展示Prompt、推理链、API Key或高敏MemoryCandidate。” |
| 普通用户 | 只看到摘要和中文状态 |
| Debug/评委 | 可看`trace_id`、event_type、module、created_at、API路径摘要、状态摘要、error_code、Recovery链路、`updated_plan_id`、Mock标识、脱敏payload |

## 8. 三条核心演示线

### 8.1 主线A：家庭亲子机会导航 + Recovery

| 步骤 | 操作 | 价值表达 |
| --- | --- | --- |
| 1 | `/`输入“今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。” | 一句话目标包含关系、年龄、饮食、距离和节奏约束 |
| 2 | `/plans/creating`展示理解目标、检索地点、查余位、估路线、准备PlanB | Agent在做结构化规划，不是闲聊生成攻略 |
| 3 | `/plans/[planId]`展示亲子活动+低卡餐厅+散步/返程时间线 | LifePilot导航的是一段生活时间 |
| 4 | 展示`ExecutableWindow`、风险与PlanB | “现在能不能成行”和“多久失效”可见 |
| 5 | 展示Verifier摘要 | 余位、路线、天气、预算、排队由Verifier检查 |
| 6 | 点击确认执行 | Executor只执行`ToolAction`，不是执行自然语言文案 |
| 7 | `reserve_restaurant`返回`NO_TABLE_AVAILABLE` | 演示动态失败，不靠成功路径美化Demo |
| 8 | 展示Recovery Diff：原`poi_light_food_003`替换为备选低卡餐厅，生成`updated_plan_id` | Recovery版本化，不原地覆盖旧PlanContract |
| 9 | 展示新计划重新Verifier | 修复后仍要过闸门，不能凭LLM说“可行” |
| 10 | 展示Mock预约/排号/消息凭证 | Mock边界诚实：这是模拟凭证，不是真实订座或真实发送 |
| 11 | `/feedback/[planId]`提交低打扰反馈，生成MemoryCandidate | 反馈转候选记忆，用户确认/忽略，低打扰可审计 |

### 8.2 主线B：朋友局共识导航

| 步骤 | 操作 | 价值表达 |
| --- | --- | --- |
| 1 | 输入“下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。” | 朋友局的问题是共识，不是单人推荐 |
| 2 | 生成候选方案组 | 每个方案有预算、路线、排队、活动节奏差异 |
| 3 | `POST /api/v1/consensus/create`创建投票页 | 把群聊拉扯变成可分享链接/二维码/分享卡 |
| 4 | `/vote/[votePageId]`朋友多选、反选、预算、文字反馈 | 低摩擦收集“喜欢什么”和“明确不要什么” |
| 5 | `/consensus/[consensusSessionId]`finalize | ConsensusSummary压缩冲突和硬约束 |
| 6 | 生成最终PlanContract | 共识不是结果截图，而是生成可执行计划 |
| 7 | 最终方案重新Verifier | 多人共识后仍要检查余位、路线、预算、窗口 |
| 8 | 展示群聊消息草案或Mock消息 | 减少群聊反复确认；只展示“模拟消息已生成”或“可复制消息已生成” |

主线B的核心话术：

```text
朋友局最消耗人的不是找地点，而是把“都行、别太远、别太贵、不想走太多”变成一致决定。LifePilot把群聊拉扯压缩成低摩擦选择题，再把结果转成可验证的PlanContract。
```

### 8.3 主线C：纪念日情绪导航

| 步骤 | 操作 | 价值表达 |
| --- | --- | --- |
| 1 | 输入“想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。” | 识别关系经营场景，而不是普通餐厅搜索 |
| 2 | 展示目标理解：轻仪式感、安静、不夸张、用心 | 情绪约束进入计划，不靠夸张消费表达 |
| 3 | 展示“散步/看展→安静餐厅→蛋糕/座位备注→合照点→返程” | 把情绪价值落成动作顺序 |
| 4 | 展示自然邀请话术 | LLM可参与文案润色，但不决定可执行状态 |
| 5 | 展示Mock订座/备注/消息边界 | 订座、备注、消息都是模拟或草案，不是真实平台执行 |
| 6 | 展示Verifier摘要 | 即使是情绪场景，也要经过路线、时间、餐厅状态检查 |

主线C的核心话术：

```text
纪念日不是推荐高评分餐厅，而是把“我想显得用心，但不想太夸张”拆成一段自然、有节奏、可执行的生活时间。
```

## 9. 讲解话术库

| 场景 | 话术 |
| --- | --- |
| 10秒产品定位话术 | “LifePilot是生活时间导航Agent。高德导航的是一段路，LifePilot导航的是一段生活时间。” |
| 20秒痛点开场话术 | “本地生活里最难的不是找一个地点，而是把孩子、伴侣、朋友、预算、天气、路线、排队和时间窗口放在一起，安排一个真的能成行、失败了还能改道的下午。” |
| 30秒技术可信话术 | “我们用PlanContract承载计划，用Verifier检查可执行性，用MockAPI提供余位、路线和天气状态，用Executor只执行ToolAction。失败时Recovery生成新的`updated_plan_id`并重新Verifier，Trace串起整个链路。” |
| 30秒产品创新话术 | “LifePilot有三条核心能力：朋友局的SocialConsensusPlanning，把群聊拉扯压缩成选择题；家庭亲子的ExecutableWindow和LifeOption，告诉用户现在能不能成行、多久失效；纪念日的Emotion-awarePlanning，把关系经营落成自然动作。” |
| 15秒Mock边界说明 | “这里是Demo模拟数据。系统通过MockAPI模拟查询余位、路线、天气和执行凭证，不代表真实支付、真实订座、真实锁票或真实发送微信/短信。” |
| 15秒隐私与LifeMemory说明 | “LifeMemory坚持低打扰、可审计、用户可控。反馈只生成候选记忆，用户确认或忽略；高敏信息默认不保存。” |
| 15秒Recovery说明 | “当餐厅执行时满座，系统不会原地改旧计划，而是生成新的`updated_plan_id`，展示Diff，并对新计划重新Verifier。” |
| 15秒Trace说明 | “Trace展示的是可见工具调用摘要和脱敏Debug信息，不展示Prompt、LLM推理链、API Key或高敏MemoryCandidate。” |
| 20秒结尾金句 | “LifePilot不是告诉你哪里不错，而是告诉你这个下午现在怎么过、能不能成行、失败了怎么改道。高德导航的是一段路，LifePilot导航的是一段生活时间。” |

## 10. 镜头脚本/视频脚本

| 镜头编号 | 时长 | 画面 | 旁白 | 屏幕操作 | 字幕 | 注意事项 |
| --- | ---: | --- | --- | --- | --- | --- |
| 1 | 8s | 朋友群聊天样式：随便、都行、别太远、别太贵 | “本地生活最难的不是去哪，而是怎么让这段时间不踩雷。” | 无，概念引入 | 不是缺推荐，是缺生活时间导航 | 不出现真实微信发送结果 |
| 2 | 8s | LifePilot首页 | “输入一句话，LifePilot开始导航这一段生活时间。” | 输入家庭亲子样例 | 一句话目标 | 真实页面操作 |
| 3 | 10s | 计划生成中页面 | “系统正在理解目标、抽取约束、检索地点、检查状态和准备PlanB。” | 展示进度条 | 结构化规划，不是闲聊 | 不展示Prompt |
| 4 | 15s | 家庭亲子计划页 | “孩子5岁、配偶减脂、别太远，都变成了时间线和约束。” | 滚动时间线 | PlanContract时间线 | 地图/路线卡可读 |
| 5 | 12s | 可执行窗口和Verifier | “Verifier检查路线、余位、天气、预算和排队，给出当前窗口。” | 展开Verifier摘要 | 可验证、可执行 | 不让前端自行判断状态 |
| 6 | 15s | 执行页餐厅满座 | “执行时模拟餐厅满座，系统触发Recovery。” | 点击确认执行，展示失败动作 | `NO_TABLE_AVAILABLE` | 标注Demo模拟 |
| 7 | 15s | Recovery Diff | “Recovery生成新的`updated_plan_id`，替换同区域低卡餐厅，并重新Verifier。” | 展示Diff和新计划 | 失败可恢复 | 不说覆盖旧计划 |
| 8 | 15s | 朋友投票页 | “朋友局把都行、反选、预算和文字反馈压缩成低摩擦选择题。” | 多选、反选、提交 | SocialConsensusPlanning | 用预置3-4条票 |
| 9 | 12s | 共识结果页 | “finalize后生成ConsensusSummary和最终PlanContract，重新Verifier。” | 点击finalize | 共识转约束 | 不把普通投票说成共识 |
| 10 | 12s | 纪念日计划页 | “情绪导航把‘不夸张但用心’落成看展、安静餐厅、备注和自然话术。” | 展示话术和备注 | Emotion-awarePlanning | 不暗示真实发送 |
| 11 | 12s | Debug Trace页 | “Trace串起输入、工具、Verifier、Recovery和执行，但不展示Prompt和推理链。” | 打开Trace | 可解释、可审计 | 脱敏payload |
| 12 | 6s | 回到计划页或产品名 | “高德导航的是一段路，LifePilot导航的是一段生活时间。” | 停在LifePilot标识 | 生活时间导航Agent | 收束价值 |

## 11. Mock数据与预置状态准备清单

以下是Demo准备项，不是新增Schema或API。

| 准备项 | 用途 | 最低要求 |
| --- | --- | --- |
| 家庭亲子正常计划数据 | 主线A成功路径 | 活动+低卡餐厅+散步/返程时间线，Verifier pass/warning |
| 家庭亲子餐厅满座失败注入 | Recovery演示 | `POST /api/v1/mock/restaurants/{poi_id}/reserve`返回`NO_TABLE_AVAILABLE` |
| 活动满员失败注入，可选 | Recovery备选演示 | `POST /api/v1/mock/activities/{poi_id}/book`返回`ACTIVITY_FULL` |
| 朋友局候选方案组 | 主线B投票 | 至少3个候选方案，有预算、步行、排队差异 |
| 朋友投票样例3-4条 | 节省现场时间 | 包含多选、反选、预算、文字反馈 |
| 纪念日计划样例 | 主线C快速展示 | 看展/散步→安静餐厅→蛋糕/座位备注→合照点→返程 |
| 天气低风险样例 | 正常Verifier | 户外散步可行 |
| 天气高风险样例，可选 | PlanB演示 | 户外改室内或风险warning |
| 路线估计样例 | 时间线和窗口 | 每段路线有`RouteEstimate` |
| 可执行窗口有效样例 | 主演示 | `expire_at`在演示时间之后 |
| 可执行窗口过期样例 | refresh-window兜底 | 返回`PLAN_EXECUTABLE_WINDOW_EXPIRED`并可刷新 |
| Mock预约凭证 | 活动执行成功 | 含`mock_only:true` |
| Mock订座/排号凭证 | 餐厅执行成功 | 含`mock_only:true` |
| Mock订单凭证，如果P0实现了订单 | 蛋糕/服务可选 | 使用`order_item`，含`mock_only:true` |
| Mock消息凭证 | 群聊或纪念日消息 | 使用`send_message`，文案为“模拟消息已生成” |
| MemoryCandidate样例 | 反馈与记忆 | 低敏/中敏候选，确认/忽略，高敏不保存 |
| TraceLog样例 | Debug兜底 | 覆盖11类event_type中的主链路关键事件 |

## 12. 接口与页面联调检查清单

| 检查项 | 页面 | 要求 |
| --- | --- | --- |
| `POST /api/v1/plans/create` | `/`、`/plans/creating` | 返回`plan_id`、`trace_id`和PlanContract或创建响应；建议携带`X-Idempotency-Key` |
| `GET /api/v1/plans/{plan_id}` | `/plans/[planId]`、`/execution/[executionId]` | 可读取完整PlanContract |
| `POST /api/v1/plans/{plan_id}/verify` | `/plans/[planId]` | VerifierResult合法，status只可为`pass/warning/fail` |
| `POST /api/v1/plans/{plan_id}/refresh-window` | `/plans/[planId]` | 窗口过期后由后端Mock状态查询和Verifier刷新 |
| `POST /api/v1/plans/{plan_id}/execute` | `/plans/[planId]` | 必须携带`X-Idempotency-Key`，只执行ToolAction |
| `POST /api/v1/plans/{plan_id}/recover` | `/execution/[executionId]` | 必须或按前端实现作为必须携带`X-Idempotency-Key`，生成RecoveryResult |
| `GET /api/v1/plans/{plan_id}/trace` | 计划页Trace摘要 | 返回用户可见Trace投影，不是完整TraceLog本体 |
| `POST /api/v1/consensus/create` | `/plans/[planId]` | 创建`consensus_session_id`、`vote_page_id`、`plan_group_id` |
| `GET /api/v1/vote-pages/{vote_page_id}` | `/vote/[votePageId]` | 读取候选方案和投票配置 |
| `POST /api/v1/consensus/{consensus_session_id}/vote` | `/vote/[votePageId]` | 支持多选、反选、预算、文字反馈，投票校验 |
| `POST /api/v1/consensus/{consensus_session_id}/finalize` | `/consensus/[consensusSessionId]` | 生成ConsensusSummary和`final_plan_id`，最终计划重Verifier |
| `POST /api/v1/feedback` | `/feedback/[planId]` | 生成反馈记录和MemoryCandidate |
| Memory候选相关接口 | `/feedback/[planId]`、`/memory` | 04已有`GET /api/v1/memory/candidates`、confirm、ignore；P0按04预留或最小实现，不新增路径 |

联调通用要求：

1. 执行类接口必须携带`X-Idempotency-Key`，包括`POST /api/v1/plans/{plan_id}/execute`和Mock执行接口。
2. 普通用户页只展示`error.user_message`，不展示`error.message`或`error.details`。
3. Debug页可展示脱敏Trace、API路径摘要、错误码、Recovery链路和Mock标识。
4. 所有写操作必须关联`trace_id`。
5. Trace事件只能使用`input_log`、`intent_log`、`constraint_log`、`memory_log`、`poi_log`、`tool_log`、`verifier_log`、`recovery_log`、`executor_log`、`feedback_log`、`error_log`。

## 13. 现场失败兜底方案

| 失败情况 | 现场表现 | 兜底操作 | 讲解话术 |
| --- | --- | --- | --- |
| 网络失败 | 页面请求失败 | 使用预置`plan_id`或录屏片段 | “这里我们切换到预置样例，数据结构与刚才实时链路一致。” |
| LLM生成慢 | 生成页停留太久 | 使用固定Demo模板或预置PlanContract | “比赛Demo阶段我们保留规则模板兜底，保证P0闭环稳定。” |
| 可执行窗口过期 | 确认按钮不可用 | 点击`refresh-window` | “本地生活计划有时效性，过期后必须重新校验。” |
| 餐厅Recovery没触发 | 执行成功了 | 使用Debug失败注入样例 | “这里切换到测试场景，模拟餐厅满座。” |
| 投票页没人操作 | 无投票数据 | 使用预置3-4条投票 | “为了节省现场时间，我们预置了几位朋友的投票。” |
| Trace页加载失败 | Debug为空 | 使用静态Trace截图或JSON摘要 | “Trace只是展示投影，不影响主链路。” |
| 页面卡顿 | 操作不流畅 | 切换录屏备份 | “下面用彩排录屏展示完整闭环。” |
| Mock状态缺失 | 某卡片显示未知 | 切换预置fixture或隐藏非核心卡片 | “当前地点状态未知时系统会降级展示，不让LLM编造状态。” |
| finalize失败 | 共识页报错 | 使用预置ConsensusSummary和最终`final_plan_id` | “这里切换到已完成投票样例，finalize后仍然会重新Verifier。” |

## 14. 评委问答准备

| 问题 | 回答 |
| --- | --- |
| 1. 这和美团/大众点评推荐有什么区别？ | 推荐器通常回答“哪里不错”。LifePilot回答“这个下午怎么过、能不能成行、失败了怎么改道”。它以PlanContract组织时间线、Verifier检查可执行性、Executor执行Mock动作、Recovery处理失败。 |
| 2. 为什么叫生活时间导航？ | 因为目标不是单个地点，而是一段连续生活时间：出发、活动、吃饭、散步、返程，每一步都有时间、路线、预算、风险和执行动作。 |
| 3. 为什么需要PlanContract？ | PlanContract是前端、Verifier、Executor、Recovery、Trace共享的结构化契约。没有它，Demo就会退化成聊天文本，无法验证、执行和恢复。 |
| 4. Verifier解决什么问题？ | Verifier负责把“看起来不错”变成“当前可执行”。它检查时间、营业/开放、距离、预算、餐厅余位、活动票务、排队、天气风险等。 |
| 5. LLM会不会编造餐厅有位？ | 不允许。LLM可以参与理解、摘要和文案，但餐厅余位、路线、天气和执行成功必须来自MockAPI、规则、Verifier或Executor。 |
| 6. MockAPI是不是假？ | 它是比赛Demo阶段的可控工具层抽象，不伪装真实平台。它让余位、路线、天气、失败和凭证可复现，便于评测Verifier、Executor和Recovery。 |
| 7. 未来怎么接真实美团能力？ | 保持PlanContract、ToolAction、Verifier、Executor边界不变，把MockAPI适配成真实平台工具接口。真实交易仍需用户授权、平台权限和合规边界。 |
| 8. 朋友局共识和普通投票有什么区别？ | 普通投票只统计票数。LifePilot会把多选、反选、预算、步行/排队容忍度和文字反馈压缩成ConsensusSummary，再生成最终PlanContract并重新Verifier。 |
| 9. Recovery为什么要版本化？ | 本地生活状态会变。版本化用`updated_plan_id`保留原计划和新计划的关系，便于解释、追踪和回滚；不能原地覆盖旧PlanContract。 |
| 10. LifeMemory会不会偷偷画像？ | 不会。P0只生成MemoryCandidate，用户确认或忽略；中敏信息需确认，高敏默认不保存；来源和使用解释可审计。 |
| 11. 你们如何保护隐私？ | 数据最小化、用户可控、Trace脱敏。普通用户页和Debug页都不展示Prompt、推理链、API Key、高敏MemoryCandidate或未脱敏个人信息。 |
| 12. 为什么P0只做杭州下沙/金沙湖/高教园区？ | P0目标是闭环可验证，不是覆盖城市。固定区域能让Mock状态、路线、天气、POI和失败注入可复现，保证比赛Demo稳定。 |
| 13. 如何证明系统不是聊天壳？ | 看三点：输出是PlanContract；执行前有Verifier和ExecutableWindow；执行失败有Recovery和Trace。聊天文本无法支持这些契约和闸门。 |
| 14. 如何评测Demo质量？ | 按08的P0指标评测：Schema通过率、Verifier Gate、ToolAction完整性、Recovery成功率、ExecutableWindow正确性、Trace覆盖率、隐私合规率。 |
| 15. 如果餐厅满座，系统怎么处理？ | 执行`reserve_restaurant`时MockAPI返回`NO_TABLE_AVAILABLE`，Executor触发Recovery，替换同区域、同预算、同饮食偏好的餐厅，生成`updated_plan_id`并重新Verifier。 |
| 16. 如果朋友意见冲突很大，系统怎么处理？ | ConsensusSummary记录`detected_conflicts`，把强约束如低预算、少走路、少排队优先进入共识约束；若冲突无法解决，提示发起人确认或调整。 |
| 17. 纪念日场景为什么不是推荐高档餐厅？ | 因为用户说“不想太夸张，但希望她觉得我用心”。系统要识别轻仪式感，安排自然流程和话术，而不是简单用价格或评分表达用心。 |
| 18. 你们的最大创新点是什么？ | 把本地生活从“地点推荐”推进到“生活时间导航”：可共识、可验证、可执行、可恢复、可解释。 |
| 19. 项目6月7日前能交付什么？ | P0可交付家庭亲子主链路、朋友局基础共识、纪念日预置演示、PlanContract生成、Verifier、Executor、餐厅满座或活动满员Recovery、Trace、Feedback到MemoryCandidate最小闭环。 |
| 20. P1/P2扩展方向是什么？ | P1做LifeMemory完整管理、SocialSignalMock增强、Benchmark结果卡、更多窗口刷新和异常；P2做PlanReward、Goal-aware POI Reranker、多模态反馈和更真实的第三方工具接入。 |

## 15. 彩排验收清单

### 15.1 P0阻塞项

| 检查项 | 通过标准 |
| --- | --- |
| 三类输入至少能跑通两类 | 家庭亲子和朋友局必须稳定 |
| `POST /api/v1/plans/create`成功 | 返回可读取计划和`trace_id` |
| PlanContract通过Schema | 必填字段、ID前缀、ISO时间合法 |
| VerifierResult合法 | status只为`pass/warning/fail` |
| ExecutableWindow存在且可展示 | 包含`expire_at`、窗口说明和置信度 |
| Executor只执行ToolAction | 不执行自然语言文案 |
| 执行类接口有幂等键 | `X-Idempotency-Key`存在 |
| Recovery触发后生成`updated_plan_id` | 新计划是完整PlanContract |
| 朋友局finalize后重新Verifier | 最终`final_plan_id`可读取 |
| 普通页面不展示Prompt、推理链、API Key、failure_injection | 页面截图和日志扫描通过 |
| Mock凭证明确标注模拟 | 含`mock_only:true`和Mock文案 |
| Trace事件使用最终枚举 | 不出现`mock_call`、`mock_log`、`api_log` |
| 移动端375px可演示 | 首页、计划页、投票页、执行页无遮挡 |

### 15.2 P1重要项

| 检查项 | 通过标准 |
| --- | --- |
| LifeMemory候选确认/忽略 | 中敏候选待确认，高敏不保存 |
| Debug Trace页清楚 | 可解释`input_log`到`error_log` |
| 纪念日脚本自然 | 不夸张，不硬推高消费 |
| 可执行窗口刷新 | 过期后能调用`refresh-window` |
| 预算/路线/天气/排队卡片可读 | 普通用户能看懂风险 |
| 评委能在3分钟理解核心价值 | 彩排后随机复述“生活时间导航” |

### 15.3 P2加分项

| 检查项 | 通过标准 |
| --- | --- |
| 视频脚本完整 | 真实页面操作占主体 |
| Benchmark入口或结果卡 | 展示P0指标或样例结果 |
| Mock口碑雷达标注清楚 | `is_mock:true`，缺失不阻断 |
| UI动效顺滑 | 生成、执行、Recovery状态切换自然 |
| 答辩Q&A准备充分 | 20题至少能稳定回答15题 |

## 16. 最终Demo评分自查表

| 维度 | 分值 | 自查问题 |
| --- | ---: | --- |
| 痛点表达清晰 | 1 | 评委是否在20秒内理解“不是去哪，而是怎么安排得不踩雷” |
| 生活时间导航差异化 | 1.5 | 是否明确区别于推荐器、聊天助手、静态攻略 |
| PlanContract结构化可信 | 1 | 是否展示时间线、预算、窗口、风险、ToolAction和`trace_id` |
| Verifier和ExecutableWindow可信 | 1 | 是否说明状态来自MockAPI和Verifier，不是LLM编造 |
| Recovery演示完整 | 1 | 是否触发`NO_TABLE_AVAILABLE`并生成`updated_plan_id` |
| Consensus朋友局有记忆点 | 1 | 是否展示反选、预算、文字反馈转共识约束 |
| 前端流畅和移动端体验 | 1 | 375px是否可操作，页面跳转是否顺 |
| Mock边界诚实清晰 | 0.75 | 是否主动说明不真实支付、订座、锁票、发送 |
| Trace可解释 | 0.75 | 是否展示脱敏Trace且不泄露Prompt/推理链 |
| 结尾价值表达 | 1 | 是否用金句收束“导航一段生活时间” |
| 总分 | 10 | 8分以上可上场，9分以上可答辩主Demo |

## 17. 附录

### 17.1 推荐输入文案

| 场景 | 输入 |
| --- | --- |
| 家庭亲子主线 | 今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。 |
| 朋友局主线 | 下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。 |
| 纪念日主线 | 想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。 |
| 异常恢复 | 下午带孩子玩室内活动，最好能预约，晚饭吃清淡一点，别排队。 |
| 窗口过期 | 现在还能不能安排金沙湖附近轻松一点的亲子活动？别太赶。 |
| 隐私反馈 | 上次有点赶，下次带孩子出门别安排太满。 |
| 朋友冲突 | 一个人不想走路，一个人预算低，一个人想拍照，下午4个人轻松玩。 |
| 天气风险 | 下午想在金沙湖附近散步吃饭，如果下雨就换室内。 |

### 17.2 推荐结尾金句

```text
高德导航的是一段路，LifePilot导航的是一段生活时间。
```

```text
LifePilot不是告诉你哪里不错，而是告诉你这个下午现在怎么过、能不能成行、失败了怎么改道。
```

可选收束：

```text
从一句自然语言目标，到PlanContract、Verifier、Executor、Recovery和Trace，LifePilot让本地生活从“推荐地点”变成“导航一段可执行的生活时间”。
```

### 17.3 禁止文案清单

以下表述不能出现在页面、讲解、视频字幕或Debug投影中，除非明确作为“禁用表达”被标注：

| 禁止文案/写法 | 正确表达 |
| --- | --- |
| 已真实支付 | Mock订单号已生成 |
| 已真实发送微信 | 模拟消息已生成/可复制消息已生成 |
| 已真实发送短信 | 模拟消息已生成 |
| 已真实订座 | Mock订座号已生成 |
| 已真实锁票 | Mock预约号已生成 |
| 实时抓取小红书/抖音/点评 | 口碑雷达Mock或Demo模拟数据 |
| LLM判断餐厅有位 | MockAPI返回餐厅状态，Verifier检查 |
| 前端判断路线通畅 | 后端Mock路线估计和Verifier结果 |
| Recovery覆盖旧计划 | Recovery生成`updated_plan_id`的新PlanContract |
| BackupPlan是完整PlanContract | BackupPlan/LifeOption只是备选分支 |
| `session_id` | `consensus_session_id` |
| `group_0001` | `plangrp_0001` |
| `vote_page_0001` | `vpage_0001` |
| `original_step_id` | `original.step_id` |
| `original_poi` | `original` |
| `new_poi` | `replacement` |
| `changes` | `diff` |
| `create_order` | `order_item` |
| `MOCK_API_FAILED` | 使用04定义错误码，如`MOCK_STATUS_MISSING`或`SOCIAL_SIGNAL_MOCK_REQUIRED` |
| `PLAN_CREATE_FAILED` | 使用`PLAN_SCHEMA_INVALID`、`PLAN_TIMELINE_INVALID`或04定义通用错误码 |
| `RESTAURANT_FULL` | `NO_TABLE_AVAILABLE` |
| `TICKET_SOLD_OUT` | `ACTIVITY_FULL` |
| `UNKNOWN_STATUS` | `MOCK_STATUS_MISSING` |
| 展示Prompt | 不展示 |
| 展示LLM推理链 | 不展示 |
| 展示API Key | 不展示 |
| 普通用户页展示`failure_injection` | 仅Debug/测试/评委模式可见 |
| 展示高敏MemoryCandidate | 默认不保存、不展示细节 |

正确边界表达：

```text
这里是Demo模拟数据。
系统通过MockAPI模拟查询余位、路线和天气。
这里返回的是Mock订座凭证，不是真实商家订座。
这一步展示的是未来可接入真实平台能力的工具抽象。
Trace展示的是可见工具调用摘要，不展示Prompt和推理链。
```

## 18. 2026-05-25追加：美团风格前端讲法

本轮前端重设计后的讲解重点从“页面能点”升级为“用户一眼知道它在导航一段生活时间”。

答辩开场可以这样说：

```text
LifePilot不是一个地点列表，也不是单纯的行程模板。
它把用户一句生活目标，变成一个可验证、可协同、可恢复的本地生活时间导航方案。
```

四个页面板块讲法：

| 页面 | 讲解重点 |
| --- | --- |
| 首页 | 用户用一句话描述今天想怎么过，系统结合当前时间锚点、可规划时长和本地状态生成计划 |
| 计划页/执行页 | 不是推荐几个地方，而是展示时间线、路线转场、预算、Verifier结果和模拟执行凭证 |
| 投票/共识页 | 多人场景中收集喜欢、不喜欢、预算、步行和排队容忍，再由后端生成新的共识PlanContract |
| 记忆页 | 把用户反馈沉淀为分级生活记忆，下一次计划时优先避开禁忌、尊重偏好 |

当前优势需要在页面与讲解中同时出现：

1. `PlanContract`让计划结构稳定，前端只消费用户可见投影。
2. Verifier先检查预算、时间窗、余位、路线和天气风险，再允许执行。
3. Recovery失败后生成新版本计划，保留原节点、替换节点、差异和`updated_plan_id`。
4. 朋友局不是简单投票，而是把多人约束压缩成可执行共识方案。
5. LifeMemory把反馈变成可控、可确认、可忽略的长期偏好。

推荐体验目标：

```text
用户看到网站时应该感受到：这不是冷冰冰的AI聊天框，而是一个懂时间、懂约束、懂同伴、也懂失败改道的生活导航员。
```

## 19. 2026-05-26追加：重构后Demo讲解补充

当前Demo讲解时需要补充三点：

1. 模型接口设置页只管理运行态Provider配置；仓库没有内置明文模型凭证，未配置凭证时系统仍用规则链路完成P0闭环。
2. 前端看起来是美团风格移动端应用，但不是静态样例页；首页、计划、投票、执行、记忆和设置都走真实`/api/v1`接口。
3. smoke测试按单worker串行跑端到端链路，目标是稳定验证产品闭环；并发吞吐不是本次比赛Demo的P0指标。
