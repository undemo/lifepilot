# LifePilot 维护规则

生成时间：2026-06-03，Asia/Shanghai。

## 文件删除规则

删除前必须先用 `rg` 搜索引用，并记录结果。允许删除：

```text
空文件
空目录
.DS_Store 等系统文件
__pycache__、.pytest_cache、frontend/.next 等缓存或构建产物
本地运行日志和 pid 文件
明确无引用的临时 debug/staging 文件
已被新版文档完整替代且保留跳转说明的旧文档
```

不要删除整个 `docs/`、`agent_docs/`、`tools/`、`scripts/`、`tests/`、`backend/data/`、`exp_docs/`、`reports/` 目录。`reports/logs/backend.log`、`reports/logs/frontend.log` 可以删现有内容，但路径约定由脚本重新生成。

## 文档合并规则

合并文档时先确认目标文档能覆盖源文档的事实信息、命令、风险和历史结论。中风险以上文档合并必须保留原路径跳转说明至少一个迭代周期，不直接删除源文件。

建议后续合并方向：

```text
agent_docs/CODEMAP.md -> agent_docs/CODE_MAP.md
agent_docs/HANDOFF_CURRENT.md + PROJECT_STATE.md + MODULE_STATUS.md -> CURRENT_STATE.md
agent_docs/API_IMPLEMENTATION_MAP.md + DATA_FLOW_ACTUAL.md -> IMPLEMENTATION_MAP.md
reports/p0_*_report.md -> reports/P0_HISTORY_INDEX.md
```

## 标签新增规则

机器标签和用户可见文案必须分开。`backend/app/rules/recommendation_taxonomy.py` 是标签注册、中文展示和通用关键词 helper 的唯一权威来源，前端 `view-models.ts` 只做展示兜底和内部词隐藏。

新增标签时同步检查：

```text
backend/app/rules/recommendation_taxonomy.py: TagDefinition、display_label、keywords、user_visible
backend/app/rules/recommendation_policy_engine.py: desired_tags、avoid_tags、role_positive、policy 专用关键词
backend/app/rules/poi_feature_store.py: POI 特征派生和 raw_poi_tag 到 machine_tag 的映射
backend/app/services/response_assembler.py: 普通用户投影应消费 taxonomy display label
frontend/lib/view-models.ts: fallback label，仅在后端还不能输出 display label 时兜底
tests/
frontend/e2e/p0-no-raw-english-tags.spec.ts
scripts/contract_scan.py（如涉及用户可见字段或禁止词）
```

不要在测试中散落复制标签关键词列表，优先引用 `get_tag_keywords()`。`machine_tag` 不等于 `raw_poi_tag`；高德或 mock 数据自带标签只能作为证据来源。不要让普通用户页面展示 `quiet_alone`、`mood_relief`、`mock_api`、`verifier_log`、`failure_injection` 等原始机器词。

## 场景新增规则

新增场景时先定义验收样例和边界，再接入解析、约束、检索、生成和展示。优先增加测试，不要直接在 `CandidateRetriever` 堆条件。

检查点：

```text
IntentParser 是否识别场景
ConstraintExtractor 是否抽取必要硬约束
LatentIntentInterpreter/FoodSemanticAgent/ActivitySemanticAgent 是否输出可计算语义
RetrievalIntentCompiler 是否生成稳定 machine intent
CandidateRetriever 是否只做候选检索和排序，不承载过多场景业务
PlanGenerator 是否保持输出结构不变
ResponseAssembler 和前端 ViewModel 是否有用户可见投影
```

## 数据路径规则

`backend/data/fixtures/` 存放稳定 Mock source，当前包括核心 POI、路线、状态、库存和天气 fixture。`backend/data/runtime/` 存放本地运行态写入，包括 plans、consensus、feedback、traces、executions、业务幂等、Mock 幂等和 runtime activity POI 缓存。

新增或迁移 data JSON 文件时必须先更新：

```text
backend/app/core/data_paths.py
backend/data/README.md
agent_docs/CODE_MAP.md
相关服务、脚本和测试
```

业务服务不要手写 `Path(...)/"data"/"xxx.json"` 或散落裸 JSON 路径。测试应优先复制 `backend/data` 到临时目录，或通过 `JsonFileStore`/路径常量映射读写，避免污染真实 `backend/data/runtime/`。

## API 契约变更规则

默认不改 `/api/v1` 路径、标准响应格式、幂等规则和错误码语义。需要变更时必须同步：

```text
docs/04_api_contract.md
backend/app/api/v1/*
backend/app/core/responses.py
backend/app/core/errors.py
frontend/lib/api.ts
tests/
scripts/contract_scan.py
```

Mock 能力必须明确标注 Mock/模拟，不能表述成真实履约、真实订座、真实票务、真实消息或真实支付。

## PlanContract 变更规则

`PlanContract` 是核心契约，不要把内部 `DraftPlan` 或 `PlanBuildCandidate` 暴露到用户 API/UI。变更字段必须同步：

```text
docs/03_schema.md
backend/app/services/plan_contract_builder.py
backend/app/services/schema_validator.py
backend/app/services/verifier_service.py
backend/app/services/response_assembler.py
frontend/types/schema.ts
frontend/lib/view-models.ts
frontend/components/plan/PlanCards.tsx
tests/
```

不要绕过 `VerifierService`、`SchemaValidator` 或 `PlanContractBuilder`。

## 前后端类型同步规则

当前 TS 类型是手写，后续建议从 Schema 生成或至少增加契约扫描。任何后端字段新增、删除、重命名都要同步：

```text
frontend/types/schema.ts
frontend/types/view-model.ts
frontend/lib/api.ts
frontend/lib/view-models.ts
frontend/e2e/
```

前端只能做展示兜底，不应重新解释预算、路线、营业状态、排队、余位或真实执行结果。

## 测试要求

低风险文档/文案改动至少运行契约扫描和前端类型检查。涉及后端主链路时优先运行：

```bash
python -m pytest tests
PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/run_backend_p0_tests.py
PYTHONPATH=backend python3 scripts/contract_scan.py
PYTHONPATH=backend python3 scripts/validate_mock_data.py
```

涉及前端页面时优先运行：

```bash
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
```

如果命令因依赖、环境或历史问题失败，最终报告必须记录命令、结果、失败原因和是否影响本次修改判断。
