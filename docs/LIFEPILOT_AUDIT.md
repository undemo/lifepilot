# LifePilot 项目结构审计

审计时间：2026-06-03  
审计范围：当前工作区代码与文档结构。只做结构、职责和风险判断，不涉及功能新增或业务代码修改。

## 1. 总体判断

当前项目结构适合实现 LifePilot V1 的核心 Demo：用户输入一句模糊目标，系统输出一条可执行的本地生活时间线。主链路已经围绕 `PlanContract` 建立，并且覆盖了出发时间、活动安排、餐厅/休息点、路线与耗时、预算、风险、Plan B 和推荐理由。

当前更像一个“比赛 Demo + 快速迭代后的可运行系统”，不是一个边界已经完全稳定的长期工程。它的主要问题不是主链路缺失，而是语义规则、推荐规则、展示标签和兜底逻辑散落在多个模块里，导致职责边界偏厚、重复逻辑较多，后续扩展新场景或新数据源时容易牵一发动全身。

结论：

- 可以继续在当前结构上收敛 V1 主链路，不需要推倒重来。
- V1 前不建议大规模重构 `CandidateRetriever`、`PlanGenerator`、`PlanContractBuilder`、`VerifierService`。
- V1 后应优先做“薄门面 + 内部拆分”的低风险重构，而不是改 API 契约或重写 PlanContract。

## 2. 当前目录结构

```text
.
├── AGENTS.md
├── README.md
├── docs/                       # 00-08 权威产品/架构/Schema/API/工作流文档；本审计新增独立文件
├── agent_docs/                 # 当前实现状态、代码地图、数据流、差距报告等交接文档
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI app、router 注册、异常处理
│   │   ├── api/                # HTTP Controller，业务 API 在 api/v1 下
│   │   ├── core/               # 错误、响应、上下文、时间、ID、常量
│   │   ├── schemas/            # 请求模型与内部智能结构
│   │   ├── services/           # Agent 编排、计划、候选、校验、执行、恢复、共识、反馈
│   │   ├── rules/              # 推荐 taxonomy、策略、POI 特征、权重
│   │   └── storage/            # JSON 文件存储
│   ├── data/                   # Mock 数字孪生 fixture 与运行态 JSON 混放
│   └── requirements.txt
├── frontend/
│   ├── app/                    # Next.js App Router 页面
│   ├── components/             # 计划、执行、共识、记忆、通用 UI 组件
│   ├── lib/                    # API client、ViewModel、格式化、trace、幂等
│   ├── types/                  # 手写 TS 契约类型
│   └── e2e/                    # Playwright 冒烟用例
├── tests/                      # 后端核心测试和 golden cases
├── scripts/                    # 契约扫描、Mock 数据校验、P0 回归、前端 smoke
├── tools/                      # 高德数据工厂、Qwen 数据工厂、规则评测工具
├── reports/                    # 历史运行报告与日志
├── experiments/ / exp_docs/    # 实验记录
└── lifepilot-dev/              # 本地 agent/dev 辅助脚本与 skill
```

结构特点：

- 后端是 FastAPI + JSON 文件存储，符合比赛 Demo 的交付速度。
- 前端是 Next.js App Router，页面和组件按业务视图分组。
- `backend/app/services/` 是实际复杂度中心；`backend/app/rules/` 承载了部分可复用推荐规则。
- `backend/data/` 同时放固定 fixture 和运行态文件，便于 Demo，但不利于环境初始化和回归隔离。

## 3. 核心体验映射

| 核心体验字段 | 当前承载位置 | 判断 |
|---|---|---|
| 出发时间 | `PlanContract.time_window.start_time`、`timeline[0].start_time` | 已具备 |
| 活动安排 | `PlanContract.timeline` 中 `type=activity/service/walk_spot` 等节点 | 已具备 |
| 餐厅/休息点 | `timeline` 中 `type=restaurant/service`，以及 `backup_plans` | 已具备 |
| 路线与耗时 | `type=transport` 节点、`estimated_route.duration_minutes` | 已具备 |
| 预算 | `PlanContract.budget` | 已具备 |
| 风险 | `PlanContract.risks`、`verifier_result` | 已具备 |
| Plan B | `PlanContract.backup_plans`、执行/恢复时的 `RecoveryResult` | 已具备 |
| 推荐理由 | `ExplanationAgent` 输出，经 `ResponseAssembler` 放入用户可见投影 | 已具备，但前端主要仍直接渲染 PlanContract |

## 4. 用户输入、语义解析、规划生成、UI 展示位置

### 4.1 用户输入处理

| 层 | 文件 | 职责 |
|---|---|---|
| 前端首页 | `frontend/app/page.tsx` | 文本输入、场景快捷入口、区域/时间/时长设置，调用 `api.createPlan` |
| 前端 API client | `frontend/lib/api.ts` | 统一拼 `/api/v1`，处理 trace、幂等键、标准响应 |
| 后端 Controller | `backend/app/api/v1/plans.py` | `POST /api/v1/plans/create` 接收请求，转给 `PlanService` |
| 请求 Schema | `backend/app/schemas/requests.py` | `PlanCreateRequest` 定义 `input_text`、位置、时间、候选生成、记忆开关等字段 |
| 应用服务 | `backend/app/services/plan_service.py` | 输入校验、创建幂等、调用 Agent、保存 PlanContract |

### 4.2 语义解析和约束抽取

| 模块 | 文件 | 职责 |
|---|---|---|
| 场景和意图初判 | `backend/app/services/intent_parser.py` | 规则 + 可选 LLM，输出 `user_goal` |
| 约束抽取 | `backend/app/services/constraint_extractor.py` | 人数、时间窗、预算、区域、节奏、饮食/活动偏好 |
| 潜在意图 | `backend/app/services/latent_intent_interpreter.py` | 将旧标签和文本映射成 canonical tags |
| 餐饮语义 | `backend/app/services/food_semantic_agent.py` | 识别长尾餐饮词、菜品、口味、低卡/不辣/儿童餐等 |
| 活动语义 | `backend/app/services/activity_semantic_agent.py` | 识别活动类型、父类、强度、室内/户外、亲子/长辈适配 |
| 检索意图编译 | `backend/app/services/retrieval_intent_compiler.py` | 把语义结果编译成机器可消费的过滤、偏好、slot 和 verifier expectations |
| 语义/推荐规则 | `backend/app/rules/recommendation_taxonomy.py`、`backend/app/rules/recommendation_policy_engine.py` | 控制标签、别名、词表、场景策略、POI 语义打分 |

### 4.3 规划生成和校验

| 模块 | 文件 | 职责 |
|---|---|---|
| 总编排 | `backend/app/services/agent_orchestrator.py` | 串起解析、候选、草案、构建、校验、排序、解释、响应 |
| 候选检索 | `backend/app/services/candidate_retriever.py` | 从 MockAPI/数据中选活动、餐厅、休息/收尾点，补状态/路线/天气/备选 |
| 候选批评 | `backend/app/services/candidate_critic_agent.py` | 对已取回候选做语义降权，不决定真实状态 |
| 草案生成 | `backend/app/services/plan_generator.py` | 把候选 POI 排成时间线草案，含多节点和场景节奏 |
| 契约构建 | `backend/app/services/plan_contract_builder.py` | 将内部草案转为 `PlanContract`，生成 ToolAction、预算、BackupPlan |
| 可执行性校验 | `backend/app/services/verifier_service.py` | 校验预算、路线、天气、状态、窗口、ToolAction、执行资格 |
| Schema 校验 | `backend/app/services/schema_validator.py` | 最小结构校验 |
| 排序 | `backend/app/services/plan_ranker.py` | 候选计划排序 |
| 推荐解释 | `backend/app/services/explanation_agent.py` | 基于结构化输入生成“为什么推荐/为什么未选/风险提醒/附加建议” |
| 响应组装 | `backend/app/services/response_assembler.py` | 返回完整 `plan_contract` 和 `UserVisiblePlanProjection` |

### 4.4 UI 展示

| 页面/组件 | 文件 | 职责 |
|---|---|---|
| 首页 | `frontend/app/page.tsx` | 输入目标，创建计划 |
| 创建中 | `frontend/app/plans/creating/page.tsx` | 前端进度投影，最终以 API 返回 PlanContract 为准 |
| 计划页 | `frontend/app/plans/[planId]/page.tsx` | 拉取计划和 trace，组织计划页各卡片 |
| 计划卡片 | `frontend/components/plan/PlanCards.tsx` | 目标理解、时间线、路线、窗口、预算、风险、PlanB、工具链 |
| ViewModel | `frontend/lib/view-models.ts` | 时间线和工具链映射，机器标签中文化，敏感/内部词替换 |
| TS 契约 | `frontend/types/schema.ts` | 手写 `PlanContract`、`PlanStep`、`Budget`、`Risk` 等类型 |

## 5. 职责混乱、重复逻辑与强耦合

### 5.1 职责偏厚

`backend/app/services/candidate_retriever.py` 约 3318 行，是当前最重的业务文件。它同时承担：

- Mock 数据搜索；
- 机器意图候选合并；
- POI 语义和特征读取；
- 场景硬规则和软规则；
- 链路组合；
- 路线/天气/状态补齐；
- backup 候选生成；
- 部分排序和 veto 逻辑。

这使它成为最高风险修改点。任何新增场景、餐饮类目、路线策略或候选源，都可能改到同一个文件。

`backend/app/services/plan_generator.py` 约 797 行，同时负责：

- 场景节奏；
- 时间布局；
- 多节点行程；
- POI step 文案；
- transport step 生成；
- dinner-first / activity-first 等流程变体。

它适合 V1 继续使用，但 V1 后应拆出时间布局和文案策略。

`frontend/components/plan/PlanCards.tsx` 约 638 行，将多个卡片、fallback 工具调用明细、PlanB 文案、数字孪生摘要放在同一文件。短期可接受，长期会影响 UI 迭代速度。

### 5.2 语义规则重复

同一类标签和词表在多处出现：

- `backend/app/rules/recommendation_taxonomy.py`
- `backend/app/rules/recommendation_policy_engine.py`
- `backend/app/services/intent_parser.py`
- `backend/app/services/constraint_extractor.py`
- `backend/app/services/latent_intent_interpreter.py`
- `backend/app/services/candidate_retriever.py`
- `backend/app/services/response_assembler.py`
- `frontend/lib/view-models.ts`

重复类型包括：

- 场景枚举：`family_parent_child`、`friend_group`、`anniversary_emotion`、`fallback_unknown`；
- 餐饮标签：`light_food`、`hotpot`、`bbq`、`cuisine_japanese` 等；
- 活动标签：`karaoke`、`hands_on`、`amusement` 等；
- 用户可见中文 label；
- Mock/API/debug 词替换。

短期风险：新加一个标签时，后端能识别但前端不展示，或者前端展示了但排序/解释没跟上。  
长期风险：同一个用户意图在不同模块被二次解释，导致候选、解释和 UI 标签不一致。

### 5.3 PlanService 中存在旧兜底逻辑

`backend/app/services/plan_service.py` 当前主要职责应是：

- 输入校验；
- 幂等；
- 调用 `AgentOrchestrator`；
- 保存和读取计划；
- 调用 execute/recover/verify。

但文件内仍保留 `_build_plan_contract`、旧版 `_mock_action_result`、旧版 recover/execute fallback 等逻辑。虽然当前容器会注入 `ExecutorService` 和 `RecoveryService`，这些分支大多不会走，但它们会干扰读代码时对真实链路的判断。

### 5.4 API client 暴露了未完全实现的 P1/P2 接口

`frontend/lib/api.ts` 已封装：

- `/memory`
- `/memory/candidates`
- `/traces/{trace_id}`
- `/traces/{trace_id}/events`

但后端当前主路由没有完整实现这些通用端点。对 V1 主链路影响不大，但会让前端能力边界看起来比后端实际能力更宽。记忆页和通用 trace 页属于 P1/P2 或调试能力，不应阻塞 V1。

### 5.5 前端展示仍偏工程解释

计划页普通视图没有暴露 Prompt、API Key、模型推理链或 `failure_injection`，符合安全边界。但页面上仍出现 `PlanContract`、`Verifier`、`工具调用链` 等工程表达。比赛 Demo 下这有助于解释技术亮点；若转向真实用户产品，需将这些词降级到调试页或评委模式。

### 5.6 固定数据和运行态数据混放

`backend/data/` 既有固定 Mock fixture，也有 `plans.json`、`executions.json`、`traces.json`、`consensus.json` 等运行态文件。Demo 方便，但测试、回归和提交前状态清理会更难。

## 6. 不破坏现有功能的重构建议

建议按“先收敛边界，再拆内部”的顺序做。

### 6.1 V1 前只做低风险收敛

1. 冻结 V1 主链路输入输出：`POST /api/v1/plans/create` 到 `/plans/{planId}` 页面必须稳定。
2. 不改 `PlanContract` 字段，不改 `/api/v1` 路径，不改 Recovery 字段结构。
3. 保持 `AgentOrchestrator` 的外部编排顺序不变。
4. 只补必要测试或文档，不做大规模服务拆分。

### 6.2 V1 后拆 CandidateRetriever，但保留门面

保留 `CandidateRetriever.retrieve(...)` 作为外部入口，内部逐步拆成：

- `CandidateSourceGateway`：只负责从 MockAPI/数据源取 POI、状态、路线、天气；
- `CandidateSemanticMatcher`：只负责 machine intent 和 POI 语义匹配；
- `CandidateScorer`：只负责场景、预算、排队、路线、语义分；
- `ItineraryChainBuilder`：只负责活动/餐厅/休息点组合；
- `BackupCandidateBuilder`：只负责 PlanB 候选。

这样可以不改 `AgentOrchestrator` 和测试入口，降低重构风险。

### 6.3 V1 后拆 PlanGenerator

保留 `PlanGenerator.generate(...)` 入口，内部拆成：

- `TimelineLayoutBuilder`：时间窗、节点顺序、转场插入；
- `ScenarioPacingPolicy`：亲子、朋友局、纪念日、独处等节奏策略；
- `StepTextPresenter`：节点说明和用户可见 notes；
- `DraftPlanFactory`：只负责组装内部草案。

这样可避免新增场景时直接堆进 `PlanGenerator`。

### 6.4 收敛标签和用户可见 label

建议确定一个后端权威标签表，再由前端消费生成后的用户可见投影：

- 标签、别名、场景词表尽量集中在 `backend/app/rules/recommendation_taxonomy.py` 或数据 JSON；
- `ResponseAssembler` 输出更完整的 `UserVisiblePlanProjection`；
- 前端优先渲染投影，`PlanContract` 作为 Debug/兜底；
- `frontend/lib/view-models.ts` 只保留展示层兜底映射。

### 6.5 清理 PlanService 旧兜底

V1 稳定后，将 `PlanService` 中旧版 `_build_plan_contract`、旧版 execute/recover mock fallback 迁移到：

- `LegacyPlanFactory`；
- 或测试 fixture helper；
- 或在确认无调用后删除。

清理前先加覆盖：确保容器注入 `ExecutorService` / `RecoveryService` 后主链路不经过旧分支。

### 6.6 区分 fixture 与运行态数据

建议保留当前 `backend/data` 兼容路径，同时逐步引入：

```text
backend/data/fixtures/
backend/data/runtime/
```

先通过 `JsonFileStore` 配置映射实现，不要直接批量移动文件。等测试和脚本都支持后再物理迁移。

### 6.7 TS 类型生成或契约扫描

`frontend/types/schema.ts` 是手写宽松类型，适合快速联调，但会和 `docs/03_schema.md` 漂移。建议后续：

- 从 JSON Schema 生成 TS 类型；或
- 在契约扫描中增加关键字段存在性检查；或
- 维护一个最小 `PlanContract` fixture 同时跑后端校验和前端类型测试。

## 7. V1 最小主线链路

V1 应只保证一条“输入目标 -> 计划页可读可执行”的主线闭环。

### 7.1 后端主链路

```text
POST /api/v1/plans/create
  -> plans.py:create_plan
  -> PlanService.create_plan
  -> AgentOrchestrator.create_plan
  -> IntentParser.parse
  -> ConstraintExtractor.extract
  -> LatentIntentInterpreter / FoodSemanticAgent / ActivitySemanticAgent
  -> RetrievalIntentCompiler
  -> CandidateRetriever.retrieve
  -> CandidateCriticAgent.review
  -> PlanGenerator.generate
  -> PlanContractBuilder.to_build_candidate
  -> PlanContractBuilder.build_for_verifier
  -> VerifierService.verify_plan_contract
  -> PlanContractBuilder.build_final
  -> SchemaValidator.validate_plan_contract
  -> PlanRanker.rank
  -> ExplanationAgent.explain
  -> ResponseAssembler.assemble
  -> 保存 PlanContract
```

### 7.2 前端主链路

```text
frontend/app/page.tsx
  -> api.createPlan
  -> /plans/creating?plan_id=...
  -> frontend/app/plans/[planId]/page.tsx
  -> api.getPlan + api.getPlanTrace
  -> PlanCards 渲染目标、时间线、路线、预算、风险、PlanB、工具链
```

### 7.3 V1 最小验收标准

对一个模糊目标，例如：

```text
今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭要清淡一点。
```

最小结果必须满足：

- `plan_contract.plan_id`、`trace_id` 存在；
- `user_goal.goal_summary` 能解释目标；
- `time_window.start_time/end_time` 存在；
- `timeline` 至少包含活动/餐饮节点，最好包含转场；
- 每个节点有 `start_time/end_time/title`；
- 路线节点有 `estimated_route.duration_minutes`；
- `budget.estimated_total` 和 `price_per_person` 存在；
- `risks` 可为空，但不能暴露底层 debug；
- `backup_plans` 至少有一个可读 Plan B；
- `verifier_result.status` 为 `pass` 或 `warning`；
- 前端计划页不展示 Prompt、API Key、模型推理链、`failure_injection`。

## 8. 可以先不动的文件和区域

在只收敛 V1 主链路时，以下区域可以先不动：

- `docs/00_project_vision.md` 到 `docs/08_evaluation_design.md`：当前为权威设计文档，除非有明确契约变更，不应改。
- `tools/gaode_data_factory/`、`tools/qwen_data_factory/`、`tools/rule_evaluation/`：数据和评测工具，不是 V1 主链路阻塞项。
- `reports/`、`experiments/`、`exp_docs/`、`agent_docs/`：历史报告和交接材料。
- `frontend/app/memory/page.tsx`、`frontend/components/memory/`：记忆完整闭环尚未成为 V1 主线。
- `frontend/app/debug/`、`frontend/components/debug/`：调试页，不影响普通计划主链路。
- `backend/app/api/v1/consensus.py`、`vote_pages.py`、`backend/app/services/consensus_service.py`：朋友局可以作为 P0+，但不应影响单人/亲子/纪念日主链路。
- `backend/app/api/v1/feedback.py`、`backend/app/services/feedback_service.py`：反馈和记忆候选可以作为执行后增强。
- `backend/app/api/v1/settings.py`：模型设置不是计划主链路核心。
- `backend/app/services/executor_service.py`、`backend/app/services/recovery_service.py`：如果本阶段只审计“生成可执行时间线”，执行与恢复可以先保持现状。
- `backend/data/*.json`：除非要修复具体候选质量或 Mock 数据校验失败，否则不要随意改。
- `frontend/e2e/`、`tests/`、`scripts/`：没有功能改动时不需要调整测试。

## 9. 高风险修改点

| 文件/区域 | 风险原因 | 建议 |
|---|---|---|
| `backend/app/services/agent_orchestrator.py` | 主编排中心，顺序改变会影响全链路 | V1 前不改编排顺序；只做极小修补 |
| `backend/app/services/candidate_retriever.py` | 最大复杂度文件，混合检索、排序、规则、路线、备选 | V1 前避免重构；V1 后保留门面分步拆 |
| `backend/app/services/plan_generator.py` | 时间线生成核心，影响出发时间、餐饮顺序、转场 | 任何改动必须跑 golden cases |
| `backend/app/services/plan_contract_builder.py` | 内部草案到 PlanContract 的边界 | 不随意改 ToolAction、Budget、BackupPlan 结构 |
| `backend/app/services/verifier_service.py` | 执行前闸门，涉及风险、状态、可执行窗口 | 改动需要覆盖 pass/warning/fail 三类 |
| `backend/app/services/schema_validator.py` | 决定哪些 PlanContract 能返回/保存 | 不要在 V1 前突然收紧大范围字段 |
| `backend/app/services/mock_api_service.py` | Mock 状态、路线、凭证事实来源 | 不要让 LLM 或 UI 绕过此层判断真实状态 |
| `backend/app/services/plan_service.py` | 幂等、持久化、读写计划、调用执行/恢复 | 清理旧分支前必须确认无调用 |
| `backend/app/services/container.py` | 依赖注入中心 | 少量改动可能导致大量服务变成 None 或走旧 fallback |
| `backend/app/rules/recommendation_taxonomy.py` | 控制标签和语义入口 | 改标签需同步推荐、解释、前端 label |
| `backend/app/rules/recommendation_policy_engine.py` | 场景和 POI 打分策略 | 调权会直接影响候选质量 |
| `backend/app/rules/poi_feature_store.py` | POI 特征派生 | 改动可能改变候选和解释一致性 |
| `frontend/lib/api.ts` | 所有页面请求入口 | 路径或幂等键变化会影响多页面 |
| `frontend/types/schema.ts` | 前端对 PlanContract 的理解 | 与后端漂移会造成运行时空值/展示缺失 |
| `frontend/lib/view-models.ts` | 标签中文化和敏感词替换 | 改错会暴露机器词或隐藏有效信息 |
| `frontend/components/plan/PlanCards.tsx` | 计划页核心展示 | 容易造成用户看不到时间线/风险/PlanB |
| `frontend/app/page.tsx` | 创建计划入口 | 改请求体会影响后端解析 |
| `frontend/app/plans/[planId]/page.tsx` | 计划结果页入口 | 改加载逻辑会影响候选、执行、投票 |
| `backend/data/*.json` | Mock 数字孪生事实源 | 数据改动会影响推荐、Verifier、测试稳定性 |
| `docs/03_schema.md`、`docs/04_api_contract.md` | 契约权威 | 变更必须同步前后端、测试、契约扫描 |

## 10. 建议的近期工作顺序

1. 保持现有代码不动，确认 V1 主链路样例稳定。
2. 用 `agent_docs/DATA_FLOW_ACTUAL.md` 和本审计文档作为开发导航，不再从散落代码里猜链路。
3. 若必须修问题，优先在最靠近问题的模块做小修，不跨层改契约。
4. V1 后先抽共享标签/label，再拆 `CandidateRetriever`，最后拆 `PlanGenerator`。
5. 在拆分前补 golden cases，尤其覆盖亲子、朋友局、纪念日、独处、长尾餐饮和活动语义。

## 11. 最终结论

当前代码可以支撑 LifePilot 的 V1 Demo 主线。它已经不是一个纯聊天应用，而是以 `PlanContract` 为核心，连接了自然语言理解、Mock 数字孪生、候选推荐、时间线生成、Verifier、PlanB、执行和恢复的 Agent 系统。

但当前结构还不适合无限扩展场景。最大工程风险集中在候选检索、计划生成、语义规则和展示映射的重复与耦合。V1 前应避免重构这些核心点；V1 后应以保持外部接口不变为前提，逐步拆分内部职责。
