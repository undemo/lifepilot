# LifePilot 本地生活时间导航 Agent

LifePilot 是一个面向比赛 Demo 的本地生活时间导航 Agent。它不是只推荐几个地点，而是把用户一句生活目标转成一段可验证、可协同、可执行、可恢复的生活时间线。

本目录是线上提交版。评审和复现请以 `SUBMISSION.md`、`scripts/verify_submission.sh`、`backend/`、`frontend/`、`tests/` 为入口；外层同名仓库目录只作为开发工作区参考。

当前实现聚焦杭州下沙 / 金沙湖 / 高教园区的 Mock 数字孪生场景。POI、路线、天气、状态、库存、投票、执行凭证和恢复分支都通过后端契约统一生成或校验，普通用户页面不会展示 Prompt、API Key、模型推理链、failure_injection 等底层调试信息。

## 当前能力

- 自然语言建计划：识别人群、关系、预算、时间窗口、出发锚点、餐饮偏好和活动偏好。
- PlanContract 核心契约：所有用户可见计划都落到结构化 `PlanContract`，不暴露内部 DraftPlan。
- 可解释 POI 推荐：受控标签、POI 语义特征、开放餐饮画像、硬约束门控、路线和状态共同参与排序。
- Mock 数字孪生：餐厅余桌、活动余票、排队、天气、路线、口碑信号和失败场景均标注为 Mock/模拟。
- Verifier 闸门：预算、路线、天气、余位、排队、执行窗口等统一校验。
- 好友投票与共识：朋友局可生成候选方案、投票页和最终共识方案。
- 模拟执行：确认计划后生成 Mock 订座、预约、消息、凭证和执行结果。
- Recovery：执行窗口过期、资源不足或风险变化时生成版本化替代方案，保留 `original`、`replacement`、`diff`、`updated_plan_id`。
- LifeMemory：反馈后产出可确认 / 可忽略的候选记忆，高敏内容不进入普通页面。
- 模型设置页：支持 DeepSeek / Qwen OpenAI-compatible 配置，凭证只保存在运行态设置或环境变量中，接口只返回脱敏状态。
- 数据工具：包含高德 POI / 路线候选池生成、Qwen 数据工厂和规则评测工具。

## V1 主链路

```text
frontend/app/page.tsx
  -> frontend/lib/api.ts api.createPlan
  -> POST /api/v1/plans/create
  -> backend/app/services/plan_service.py PlanService.create_plan
  -> backend/app/services/agent_orchestrator.py AgentOrchestrator.create_plan
  -> IntentParser
  -> ConstraintExtractor
  -> LatentIntentInterpreter / FoodSemanticAgent / ActivitySemanticAgent
  -> RetrievalIntentCompiler
  -> CandidateRetriever.retrieve
  -> CandidateCriticAgent
  -> PlanGenerator.generate
  -> PlanContractBuilder
  -> VerifierService
  -> SchemaValidator
  -> PlanRanker
  -> ExplanationAgent
  -> ResponseAssembler
  -> 保存 PlanContract
  -> frontend/app/plans/[planId]/page.tsx
```

## 目录说明

```text
backend/                         FastAPI 后端，业务 API 均在 /api/v1 下
backend/app/api                  路由层，主业务入口和 MockAPI 入口
backend/app/services             Agent 编排、MockAPI、Verifier、Executor、Recovery 等服务
backend/app/rules                推荐语义、规则策略、POI 特征和排序权重
backend/app/schemas              请求体与内部结构 schema
backend/app/storage              JSON 文件存储封装
backend/data                     Demo 数字孪生 fixture、辅助数据和本地运行态 JSON
frontend/app                     首页、计划页、投票页、执行页、反馈页、记忆页、设置页
frontend/components              UI 组件和计划展示卡片
frontend/lib                     API client、trace、幂等、view-model mapper
frontend/types                   前端契约类型和 ViewModel 类型
scripts                          契约扫描、Mock 数据校验、P0 回归和前端 smoke runner
tests                            后端核心测试
tools                            高德/Qwen 数据工厂和规则评测工具
docs                             产品、Schema、API 契约、Agent 工作流和验收设计文档
agent_docs                       Agent 交接、代码地图、清理计划和维护规则
reports                          本地运行报告、日志、截图和临时数据快照
exp_docs                         历史实验日志，提交评审无需运行
```

主链路目录是 `backend/app/api`、`backend/app/services`、`backend/app/rules`、`frontend/app`、`frontend/components`、`frontend/lib` 和 `frontend/types`。`scripts`、`tools`、`agent_docs` 和 `exp_docs` 分别服务验证、数据生成、维护交接和历史实验参考。

## 标签体系

标签注册、中文展示和通用关键词 helper 的权威来源是 `backend/app/rules/recommendation_taxonomy.py`。`machine_tag` 用于规则、检索、排序和测试；`display_label` 用于普通用户页面；`rule_keyword` 用于从用户输入或 POI 文本识别标签；`raw_poi_tag` 只是高德或 Mock 数据源证据，不直接等同于 machine tag。

推荐策略在 `backend/app/rules/recommendation_policy_engine.py`，POI 特征增强在 `backend/app/rules/poi_feature_store.py`。前端 `frontend/lib/view-models.ts` 的标签中文表只做 fallback，后端已输出中文展示时前端直接展示，不重新定义业务含义。

## 数据目录

核心 Mock fixture 和本地运行态数据已经分离：

```text
backend/data/fixtures/   稳定 Mock source：POI、路线、状态、库存、天气
backend/data/runtime/    本地运行态写入：plans、consensus、feedback、traces、executions、idempotency、runtime_activity_pois
```

业务服务不要硬编码 `backend/data` JSON 路径。新增数据文件时先在 `backend/app/core/data_paths.py` 增加路径常量，再通过 `JsonFileStore` 读取或写入。测试应复制 `backend/data` 到临时目录，避免污染真实 `runtime/`。

## 高风险文件

以下文件不建议随便改；需要改动时先确认不会改变 API 契约、PlanContract 字段、Agent 主编排顺序或普通用户页面行为：

```text
backend/app/services/agent_orchestrator.py
backend/app/services/candidate_retriever.py
backend/app/services/plan_generator.py
backend/app/services/plan_contract_builder.py
backend/app/services/verifier_service.py
backend/app/services/schema_validator.py
backend/app/services/mock_api_service.py
backend/app/services/plan_service.py
backend/app/services/container.py
backend/app/rules/recommendation_taxonomy.py
backend/app/rules/recommendation_policy_engine.py
backend/app/rules/poi_feature_store.py
frontend/lib/api.ts
frontend/types/schema.ts
frontend/lib/view-models.ts
frontend/components/plan/PlanCards.tsx
frontend/app/page.tsx
frontend/app/plans/[planId]/page.tsx
docs/03_schema.md
docs/04_api_contract.md
```

## 快速启动

### 1. 启动后端

```bash
cd backend
python3 -m pip install -r requirements.txt
PYTHONPATH=. DEEPSEEK_ENABLED=false QWEN_ENABLED=false \
  python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

后端健康检查：

```bash
curl http://127.0.0.1:8010/health
```

### 2. 启动前端

```bash
cd frontend
npm install
BACKEND_ORIGIN=http://127.0.0.1:8010 npm run dev -- --hostname 127.0.0.1 --port 3000
```

打开：

```text
http://127.0.0.1:3000
```

### 3. 可选：配置模型

默认建议先禁用外部模型，使用规则链路完成 Demo：

```bash
export DEEPSEEK_ENABLED=false
export QWEN_ENABLED=false
```

如需启用 DeepSeek：

```bash
export DEEPSEEK_ENABLED=true
export DEEPSEEK_API_KEY="你的 DeepSeek Key"
export DEEPSEEK_BASE_URL="https://api.deepseek.com"
export DEEPSEEK_MODEL="deepseek-v4-flash"
```

也可以在前端 `/settings` 页面运行态设置 Provider、Base URL、模型名和凭证。凭证不会写入普通响应或用户页面。

## 常用验证

后端 P0 回归：

```bash
PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false \
  python3 scripts/run_backend_p0_tests.py
```

契约和 Mock 数据检查：

```bash
PYTHONPATH=backend python3 scripts/contract_scan.py
PYTHONPATH=backend python3 scripts/validate_mock_data.py
```

前端检查：

```bash
cd frontend
npm run typecheck
npm run lint
```

完整前端 smoke：

```bash
PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false \
  python3 scripts/run_p0_frontend_smoke.py
```

## 使用教程

1. 在首页输入一句自然语言目标，例如“今天下午想和老婆孩子出去玩几个小时，孩子5岁，别太远，不排长队，晚饭要清淡一点”。
2. 如需调整 Demo 当前状态，点击输入框旁的位置按钮，设置区域、当前位置、当前时间锚点和规划时长。
3. 点击“生成计划”，进入计划页查看目标理解、时间线、路线转场、预算、风险、PlanB 和工具调用摘要。
4. 如果是朋友局，计划页可发起投票；好友在投票页提交预算、步行、排队和自由意见后，可生成最终共识方案。
5. 点击“确认模拟执行”，后端会按 ToolAction 生成 Mock 订座、活动预约、消息和凭证。
6. 执行后可提交低打扰反馈；候选记忆需要用户确认或忽略，不会偷偷写入长期画像。
7. 调试时可从计划页进入 Trace 页面查看脱敏工具链路。普通用户页不会展示底层敏感字段。

## 数据与工具

- `tools/gaode_data_factory/generate_lifepilot_dataset.py` 可从高德 Web 服务生成 POI 候选池、路线 sidecar 和 review 候选。
- `tools/gaode_data_factory/viewer.html` 可本地查看高德 raw、转换后 POI、策略评估和 API 能力报告。
- `tools/rule_evaluation/` 用于构建规则评测样例、POI 特征、排序偏好集和质量门禁。
- `tools/qwen_data_factory/` 用于本地 Qwen 兼容接口的数据生成实验。

高德工具示例：

```bash
export AMAP_KEY="你的高德 Web 服务 Key"
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --target-pois 500 \
  --output backend/data \
  --route-neighbors 4 \
  --max-route-pairs 1600
```

## Mock 边界

本项目是比赛 Demo。即使地点来自高德等真实来源，计划中的余桌、余票、订座、预约、消息、凭证、失败注入和执行状态仍是 Mock/模拟能力。用户页面和文档必须清楚标注这些边界，避免把模拟结果表述成真实履约成功。
