# LifePilot 标签体系审计

生成时间：2026-06-03，Asia/Shanghai。

## 1. Current Tag Sources

| 文件路径 | 标签/关键词 | 用途 | 是否权威 | 风险 |
|---|---|---|---|---|
| `backend/app/rules/recommendation_taxonomy.py` | `CONTROLLED_TAGS`、`TAG_ALIASES`、`OPEN_TERM_PATTERNS`、`DINING_*`、`TagDefinition` | machine tag 注册、display label、rule keyword、开放餐饮画像和意图归一化 | 是 | 文件同时承载意图词和 POI 识别词，后续要避免继续扩成业务判断层 |
| `backend/app/rules/recommendation_policy_engine.py` | `DEFAULT_RECOMMENDATION_POLICY.lexicon`、`scenario_profiles`、`tag_implications` | 推荐策略、场景偏好、避让和标签蕴含 | 部分：策略权威，不是展示权威 | 仍有少量策略专用词表，例如品质餐饮、低端连锁，需要标注为 policy keyword |
| `backend/app/rules/poi_feature_store.py` | `*_WORDS`、`semantic_tags`、overlay `semantic_tags` | 从 POI 名称、类型、raw tag、enrichment 派生 machine tag | 部分：POI 特征权威，不是标签展示权威 | raw POI tag、派生 semantic tag、业务 machine tag 容易混用 |
| `backend/app/services/candidate_retriever.py` | 槽位筛选中的 tag set 和少量名称词表 | 候选召回、排序和安全闸门 | 否 | 文件较大，容易继续堆新场景条件；本轮只收敛共享词表，不拆模块 |
| `backend/app/services/response_assembler.py` | 用户可见 `display_tags` 投影 | 普通用户页面中文标签和敏感字段过滤 | 否，消费 taxonomy | 之前有本地 `label_map`，会造成中文名多处维护 |
| `backend/app/services/explanation_agent.py` | fallback explanation、LLM 输出清洗 | 用户可见解释和 addon 建议 | 否，消费 taxonomy | LLM 输出可能带 machine tag 或工程词，需要清洗 |
| `frontend/lib/view-models.ts` | `FALLBACK_TAG_LABELS`、`mapUserLabels` | 前端兜底展示和内部词隐藏 | 否，fallback only | 不能重新定义业务含义；后端输出 display label 时前端应直接展示 |
| `tests/test_p0_plan_create.py`、`scripts/run_backend_p0_tests.py` | 正/负向关键词断言 | P0 行为回归 | 否，消费 taxonomy | 之前复制了“亲子/手作/清淡/日料”等关键词列表 |
| `backend/data/fixtures/`、`backend/data/poi_features.json`、`backend/data/poi_activity_attributes.json` | POI `tags`、`suitable_scenarios`、overlay `semantic_tags` | 稳定 Mock source 和 POI 特征数据 | 否，数据来源 | raw_poi_tag 不等于 machine_tag，运行态快照不能作为标签权威 |
| `backend/data/runtime/` | 本地 plans/traces/idempotency 快照中的历史 tags | 本地运行态写入 | 否 | 搜索命中很多历史 machine tag，只能作为调试参考 |

## 2. Current Problems

- 后端多处定义同一标签：存在。`recommendation_taxonomy.py`、`recommendation_policy_engine.py`、`poi_feature_store.py`、`candidate_retriever.py` 都有过 POI 识别关键词。本轮已把亲子、酒饮、日料、火锅、自助、烤肉、西餐、健康轻食等共享词表向 taxonomy helper 收敛。
- 前端重复翻译标签：存在。`frontend/lib/view-models.ts` 原先维护业务标签中文名。本轮已改成 `FALLBACK_TAG_LABELS` 并标注 canonical 来源在后端 taxonomy。
- 测试断言关键词和推荐规则不一致：存在。P0 测试和 P0 runner 中的手作、亲子、清淡、火锅、烤肉、日料等断言已改为 `get_tag_keywords()`。
- machine tag 和用户中文文案混用：存在。PlanContract 仍保留 machine tag；普通用户投影和前端 view-model 负责转中文，不改变契约字段。
- POI 原始 tag 和系统业务 tag 混用：存在。`mock_pois.tags`、高德 enrichment、overlay `semantic_tags` 都会进入特征派生，不能直接视为 canonical machine tag。
- debug label 暴露到用户页面：未发现专门 debug panel，但普通页面曾可能通过标签兜底显示英文 tag。本轮后端投影会过滤未知英文 machine tag，前端也隐藏英文 enum fallback。
- core/rules 双权威残留风险：低。`backend/app/core/recommendation_taxonomy.py` 已是兼容壳，canonical 文件是 `backend/app/rules/recommendation_taxonomy.py`。

## 3. Canonical Tag Model

machine_tag:

稳定英文机器标签，用于规则、检索、测试、排序和 PlanContract 内部字段。例如 `child_friendly`、`kid_safe`、`light_meal`。

display_label:

用户可见中文短标签，例如“亲子友好”“适合孩子”“清淡餐”。权威定义在 `TagDefinition.display_label`。

rule_keyword:

用于从用户输入、POI 名称、POI 类型、raw tag、enrichment 中识别 machine_tag 的关键词，例如“嘉年华”“儿童”“乐园”。权威读取入口是 `get_tag_keywords(tag)`。

raw_poi_tag:

高德或 mock 数据源自带标签，例如 POI fixture 的 `tags` 或 enrichment 类型。它是证据来源，不直接等同于 machine_tag。

debug_label:

仅用于 trace、diagnostics、reason_code 或评委模式的调试标签。普通用户页面不展示 raw debug label。

## 4. Canonical Source Recommendation

唯一标签注册与中文展示权威是：

```text
backend/app/rules/recommendation_taxonomy.py
```

原因：

- 它位于 `backend/app/rules/`，与当前推荐规则权威目录一致。
- 它已被意图归一化、餐饮画像和候选规则链路消费。
- 本轮新增 `TagDefinition`、`TAG_DEFINITIONS`、`get_tag_keywords()`、`get_display_labels()` 等小 helper，后端服务和测试可以复用。
- 前端无法直接 import Python，因此只保留 fallback label，不作为业务含义权威。

推荐策略权威仍是 `backend/app/rules/recommendation_policy_engine.py`；POI 特征增强权威仍是 `backend/app/rules/poi_feature_store.py`。二者消费 taxonomy，但不负责定义用户可见中文名。

## 5. Migration Plan

本轮已做：

- 在 taxonomy 中新增 `TagDefinition`、`TAG_DEFINITIONS` 和查询 helper。
- 将 policy engine 中亲子、低适配、酒饮、音乐、KTV、自助、火锅、日料、西餐、轻食等默认词表部分改为 helper 读取。
- 将 POI feature store 和 CandidateRetriever 的共享 POI 识别词表部分改为 helper 读取。
- 将 ResponseAssembler 的用户可见标签投影改为读取 taxonomy display label，并过滤未知英文 machine tag。
- 将 ExplanationAgent 的用户可见清洗补充 taxonomy display label 替换。
- 将前端标签表改为 `FALLBACK_TAG_LABELS`，并明确只做 fallback。
- 将 P0 测试和 P0 runner 中的通用业务关键词断言改为 `get_tag_keywords()`。

后续建议：

- 为 `quality_dining`、`proper_dining`、`coffee`、`dessert`、`light_meal` 这类“用户输入词”和“POI 识别词”不同的标签增加更细分字段，例如 `input_keywords` / `poi_keywords`。
- 将 `candidate_retriever.py` 中剩余的大段场景 gate 逐步迁移为小型 policy helper，避免继续堆条件。
- 如需新增标签，先更新 `TagDefinition`，再同步 policy 使用点、测试和前端 fallback。
