## 高德 POI Data Factory 接入

本次新增 `tools/gaode_data_factory`，用于把高德 Web 服务 POI 搜索接口拉取到的真实地点数据转换成当前 `tools/qwen_data_factory` 生产的 `mock_pois.json` 同形结构。实现时参考了 `docs/03_schema.md`、`docs/05_agent_workflow.md`、`docs/06_mock_api_design.md` 和 qwen data factory 的 POI 清洗/字段约束，没有修改 `docs/00_project_vision.md` 到 `docs/08_evaluation_design.md`，也没有改后端业务逻辑。

新增文件：

- `tools/gaode_data_factory/generate_pois.py`：正式脚本。读取 `AMAP_KEY` 或 `--key`，调用高德 `https://restapi.amap.com/v3/place/text`，固定 `city=杭州`、`citylimit=true`、`extensions=all`，按餐饮、活动、步道、服务、交通锚点多组关键词和类型码检索。
- `tools/gaode_data_factory/README.md`：记录运行方式、输出位置和转换规则。
- `tools/gaode_data_factory/__init__.py`：包标记文件。

输出文件：

- `tools/gaode_data_factory/output/mock_pois.json`：转换后的 LifePilot POI fixture，顶层保持 `{"version":"v0.1","area":"杭州下沙/金沙湖/高教园区","pois":[]}`。本次真实生成 60 个 POI，覆盖 `restaurant / activity / walk_spot / service / transport_anchor`，覆盖 `下沙 / 金沙湖 / 高教园区`。每个 POI 保持 qwen data factory 兼容字段：`poi_id,name,category,sub_category,tags,location,area,address,price_per_person,rating,opening_hours,suitable_scenarios,risk_tags,mock_only,created_at,updated_at`。
- `tools/gaode_data_factory/output/gaode_raw_poi_responses.json`：高德原始 JSON 响应归档。每条包含无 key 的请求参数、LifePilot 映射意图和高德完整 `response`，用于后续分析 `type/typecode/location/biz_ext.rating/biz_ext.cost/biz_ext.open_time/photos/tel` 等字段。API key 没有写入该文件。
- `tools/gaode_data_factory/reports/generate_pois_report.json`：本次生成报告，记录 accepted 数量、请求摘要、类别覆盖、区域覆盖、缺失场景等，不含 key。

关键转换策略：

- 坐标：解析高德 `location` 的 `lng,lat`，再按下沙、金沙湖、高教园区边界过滤；不在边界内的高德结果不进入转换后的 POI。
- 类别：通过搜索配置把高德类型映射到 LifePilot 五类 POI，不把高德原始类型直接写入 `mock_pois.json`，避免破坏现有字段白名单；原始类型保留在 raw 文件。
- 评分/人均：优先读取高德 `biz_ext.rating`、`biz_ext.cost`，缺失时按 LifePilot 类别给默认值。
- 营业时间：优先解析高德 `biz_ext.open_time` 的 `HH:MM-HH:MM` 段，解析失败时按类别使用默认营业时间。
- 标签/场景：根据搜索规格和地点文本补齐 `tags`、`suitable_scenarios`、`risk_tags`，保证兼容 P0 Demo 的 CandidateRetriever/Verifier 输入。
- Mock 边界：转换后的 POI 仍保留 `mock_only:true`。含义是这些真实地点被用作 Demo 数字孪生 fixture；状态、余位、票务、订座等仍不是高德或商家真实执行状态。
- 限流：真实测试中高德个人 key 触发过 `10021 CUQPS_HAS_EXCEEDED_THE_LIMIT`，脚本已加入指数退避重试，并把默认请求间隔调到 `0.35s`。

验证结果：

- 已运行真实高德请求生成正式输出：`python tools/gaode_data_factory/generate_pois.py --target 60 --per-spec 10 --output tools/gaode_data_factory/output`。
- 已做本地 JSON/字段检查：脚本语法可解析，`mock_pois.json` 有 60 个 POI，五类 category 都存在，三个 area 都存在，无必填字段缺失。
- 已检查 `gaode_raw_poi_responses.json`：包含 15 组高德原始响应，未包含本次使用的 API key 字符串。

后续重构建议：

- 可以把高德原始 `typecode` 到 LifePilot `category/sub_category` 的映射抽到单独 YAML，方便人工调整。
- 现在只生成 POI。后续若接入路线、天气或状态，仍应保持“真实来源数据”和“LifePilot Mock 可执行状态”分离，避免把高德地点存在误读成真实订座/票务能力。
- 如果要把高德 POI 正式替换 `backend/data/mock_pois.json`，需要同步重建 `mock_status.json`、`mock_inventory.json`、`mock_routes.json`、`mock_social_signals.json` 等引用 POI 的派生文件。

## 高德 POI 临时可视化页

本次追加 `tools/gaode_data_factory/viewer.html`，用于临时查看高德 raw 响应和转换后的 `mock_pois.json`。

页面能力：

- 自动读取 `output/mock_pois.json` 和 `output/gaode_raw_poi_responses.json`。
- 概览区展示 Mock POI 数、Raw 响应数、Raw POI 数、类别覆盖、区域覆盖、评分/人均覆盖。
- 用条形图展示 `category` 和 `area` 分布。
- 用无地图底图的坐标散点展示 POI 在下沙/金沙湖/高教园区边界内的大致分布。
- `Mock POI` 页提供名称/地址/标签搜索，以及类别、区域筛选。
- `高德 Raw` 页展示每个高德请求批次，并用 JSON 结构树展开 raw 文件。结构树默认只截取每个响应前 3 个 POI，避免页面一次性渲染过重；完整 raw 数据仍保存在 JSON 文件中。
- `单点对比` 页按 POI 名称匹配转换后对象和高德原始对象，方便查看 `rating/cost/open_time/type/typecode/location` 等字段如何映射。

使用方式：

```bash
cd tools/gaode_data_factory
python -m http.server 8765
```

然后访问：

```text
http://127.0.0.1:8765/viewer.html
```

验证结果：

- 已启动本地静态服务。
- `curl -I http://127.0.0.1:8765/viewer.html` 返回 200。
- `output/mock_pois.json` 和 `output/gaode_raw_poi_responses.json` 都可通过 HTTP 读取并通过 `python -m json.tool` 解析。

## 关键词建模 vs 坐标周边搜索评估

本次新增 `tools/gaode_data_factory/compare_poi_strategies.py`，用于客观比较两种 POI 建模策略：

- 关键词建模：复用 `generate_pois.py` 已生成的 `v3/place/text` 结果，即多组预制关键词 + 杭州城市限制 + 区域边界过滤。
- 坐标周边搜索：调用高德 `v3/place/around`，围绕金沙湖中心、高教园区中心、下沙中心三个坐标，以 `radius=1800` 米搜索餐饮、休闲活动、景点步道、生活服务、交通设施，再按高德 POI id 去重并转换成 LifePilot POI。

新增输出：

- `tools/gaode_data_factory/output/around_mock_pois.json`：周边搜索转换后的 LifePilot POI。
- `tools/gaode_data_factory/output/gaode_around_raw_poi_responses.json`：周边搜索高德 raw 响应。
- `tools/gaode_data_factory/output/combined_deduped_mock_pois.json`：关键词和周边两种模型按名称+坐标去重后的合并结果。
- `tools/gaode_data_factory/output/poi_strategy_evaluation.json`：两种策略的指标评估结果。
- `tools/gaode_data_factory/reports/generate_around_pois_report.json`：周边搜索生成报告。

评估指标：

- `accepted_poi_count`：转换后符合 LifePilot POI 字段的数量。
- `raw_unique_poi_count`：高德返回的去重原始 POI 数。
- `raw_duplicate_rate`：同策略内部 raw POI 重复比例。
- `accepted_per_request`：每次 API 响应最终留下的可用 POI 数。
- `accepted_from_raw_unique_rate`：去重 raw POI 进入 LifePilot 边界和字段转换的比例。
- `category_coverage_ratio`：五类 LifePilot POI 覆盖比例。
- `area_coverage_ratio`：下沙/金沙湖/高教园区覆盖比例。
- `scenario_coverage_ratio`：三类 P0 scenario 覆盖比例。
- `price_coverage`：转换后有数值型人均价格的 POI 比例。
- `coordinate_bbox_km2`：转换后 POI 坐标外接矩形面积，用于观察空间覆盖范围。
- `raw_field_coverage`：高德 raw 中 `id/type/typecode/location/address/rating/cost/open_time/photos/tel` 等字段覆盖率。

本次真实测试结果：

- 两种策略都生成 60 个 LifePilot POI。
- 周边搜索：`raw_unique_poi_count=300`，`accepted_per_request=5.0`。
- 关键词建模：`raw_unique_poi_count=229`，`accepted_per_request=4.0`。
- 两种策略的 `category_coverage_ratio`、`area_coverage_ratio`、`scenario_coverage_ratio` 都是 `1.0`。
- 关键词建模的 `accepted_from_raw_unique_rate=0.262`，周边搜索为 `0.2`。
- 关键词建模的 `price_coverage=0.8333`，周边搜索为 `0.7333`。
- 关键词建模的 `coordinate_bbox_km2=17.6017`，周边搜索为 `4.801`。
- 两种 raw 的高德 id 重合数为 19；去重合并后的 `combined_mock_poi_count=119`，按名称+坐标移除重复 1 条。

可视化更新：

- `viewer.html` 新增“策略评估”tab，读取 `poi_strategy_evaluation.json` 展示指标表、winner、类别分布和 raw 字段覆盖率。
- `viewer.html` 的概览页新增“高德静态地图”面板，可选择关键词 POI、周边 POI 或合并去重 POI。
- 地图面板使用高德 `v3/staticmap`。根据官方文档，该接口可以返回真实地图图片，并支持 markers。页面要求本地输入高德 Web 服务 Key 后再加载图片，Key 不写入任何仓库文件。

验证结果：

- 已运行：`python tools/gaode_data_factory/compare_poi_strategies.py --target 60 --radius 1800 --per-query 5 --output tools/gaode_data_factory/output`。
- 已验证 `http://127.0.0.1:8876/viewer.html` 返回 200。
- 已验证 `output/poi_strategy_evaluation.json` 可通过 HTTP 读取并通过 `python -m json.tool` 解析。
- 已临时请求高德 `v3/staticmap`，返回 `200 image/png`，响应头和 PNG 魔数均正常。

## 高德 API 字段还原能力实验

本次新增 `tools/gaode_data_factory/gaode_api_capability_probe.py`，目标不是马上重建 500 条全量数据，而是小规模验证：如果要把原先 LLM 生成的模拟地点换成真实地点，高德 Web 服务到底能真实还原哪些字段，哪些字段仍然必须 Mock、规则推断或 AI 生成。

实验范围：

- 固定区域：钱塘区，`adcode=330114`。
- 中心点：金沙湖、下沙、高教园区。
- 半径：2500 米。
- 查询方式：`v3/place/around` 周边搜索。
- 只取精品吃喝玩乐白名单 type：餐饮、咖啡甜品、休闲娱乐、景点公园、书店文化。
- 噪声过滤：汽车、汽修、维修、建材、家具、家居、公司、产业园、写字楼、房产、中介、充电站、加油站、银行、厕所、卫生间、营业厅等。
- 评分策略：有评分时低于 4.0 的 POI 先过滤；无评分不直接过滤，因为部分景点/文化点可能没有 `biz_ext.rating`。

本次真实调用结果：

- Raw POI：300。
- 低评分过滤：131。
- 重复过滤：13。
- 噪声过滤：2。
- 过滤后精品候选：154。
- Top 样例包括：星巴克臻选(龙湖杭州金沙天街店)、杭电游泳健身中心、DEDE CANTEEN咖啡食堂、优格瑜伽(天街店)、东北菜馆(高沙小区店)、元祖食品(下沙店)、Jahan·疆客Cafe。

接口验证：

- POI 周边搜索 `v3/place/around`：可用于精品 POI 发现，并返回 `id/name/type/typecode/location/address/adcode/biz_ext.rating/biz_ext.cost/biz_ext.open_time/photos/tel/tag` 等字段。
- POI ID 查询 `v3/place/detail`：已对 3 个 Top POI 调用成功，可作为单点补全和 raw 归档。
- 步行路线 `v3/direction/walking`：2 组 POI pair 调用成功，可得到 `distance/duration/steps/polyline`。
- 驾车路线 `v3/direction/driving`：2 组 POI pair 调用成功，可得到 `distance/duration/strategy/steps/polyline`。
- 公交/地铁综合路线 `v3/direction/transit/integrated`：2 组 POI pair 调用成功，可得到 `distance/duration/cost/segments`，其中示例成本为 2 元。
- 天气 `v3/weather/weatherInfo`：`base` 和 `all` 都调用成功。`base` 返回钱塘区实时天气、温度、风向、风力、湿度；`all` 返回未来天气预报 casts。

字段还原矩阵：

- `mock_pois.json`：高可还原。可真实使用 `name/type/typecode/location/adcode/address/cost/rating/open_time/photos/tel`；仍需规则或 AI 生成 `suitable_scenarios/risk_tags/LifePilot category mapping/curated tags`。本次覆盖率：rating 0.6818，cost 0.539，open_time 0.6623，photos 1.0，tel 1.0。
- `mock_routes.json`：高可还原。可真实使用步行/驾车/公交路线的距离、耗时、路线步骤和 polyline；仍需规则归一化 `confidence`、非驾车 `traffic_level` 和预计算哪些 POI pair。
- `mock_weather.json`：中等可还原。可真实使用天气、温度、风向、风力、湿度和预报；仍需规则生成 `rain_probability/outdoor_risk_level/suggested_recovery/time_range`。
- `mock_status.json`：低到中等可还原。可由 `open_time` 推断 `open_status/available`；但 `available_tables/queue_minutes/ticket_available/remaining_tickets/reservation_available/execute_status` 高德 Web 服务不提供，仍需 Mock/规则。
- `mock_inventory.json`：低可还原。可用营业时间锚定时段，但桌位、预约占用、活动余票仍需 Mock/规则。
- `mock_social_signals.json`：元数据中等可还原，评论正文低可还原。可用 rating/cost/tag/photos_count 作为 AI 摘要输入；全网口碑、评论正文、正负标签、热度和 mock_sources 仍需 AI/Mock。
- `mock_failure_scenarios.json`：不可由高德还原，仍是 Demo/测试 failure injection。
- `benchmark_samples.json`：不可由高德还原，仍是产品验收样例和断言。

本次新增输出：

- `tools/gaode_data_factory/output/gaode_capability_probe_report.json`：完整能力报告。
- `tools/gaode_data_factory/output/gaode_capability_probe_raw.json`：探针 raw 响应归档，不含 API key。
- `tools/gaode_data_factory/reports/gaode_capability_probe_summary.json`：简版报告。

可视化更新：

- `viewer.html` 新增 “API 能力” tab，展示每个目标 JSON 文件的真实可还原字段、覆盖率和仍需 Mock/规则/AI 的字段。

下一步建议：

- 不建议再把所有高德返回 POI 都纳入数据集。应建立“精品 POI 白名单 typecode + 噪声黑名单 + 最低评分/字段完整度 + 钱塘区 adcode”的采集策略。
- 下一轮可以把 `mock_pois.json` 的目标从 500 改为“500 个精品候选池”，再由规则抽取 120-200 个高质量 Demo 常用 POI；否则 500 条全塞会稀释体验。
- 路线建议不生成全量 500x500 矩阵。应只对计划候选链路、区域锚点、Top POI 间邻近 pair 生成 `mock_routes.json`，否则调用量和文件体积都会失控。
- 状态和库存不要伪装真实商家能力。真实字段只用营业时间和 POI 类型做约束，桌位、排队、余票、可预约仍标记 Mock。

## 2026-05-24 规则模块解耦与规则评测数据集

本轮回应“游乐园 + 自助餐”召回失败：旧链路会把“自助餐”当开放餐饮短语，但没有受控 `buffet` 语义和餐厅槽位硬门控；同时家庭场景默认的 `light_food` 会污染开放餐饮画像，导致普通面馆/包子/牛肉汤等清淡正餐有机会替代“自助餐”。

代码结构调整：

- 新增 `backend/app/rules/` 作为内部规则包：
  - `intent_rules.py`：单人散心等意图规则。
  - `recommendation_taxonomy.py`：受控标签、开放餐饮画像、区域/语义归一。
  - `recommendation_policy_engine.py`：规则版推荐策略、显式餐饮锚点和组合评分。
- 原 `backend/app/core/intent_rules.py`、`backend/app/core/recommendation_taxonomy.py`、`backend/app/services/brain_recommendation_engine.py` 改为兼容转发层，避免旧导入一次性断裂。
- `IntentParser`、`ConstraintExtractor`、`CandidateRetriever`、`ServiceContainer` 改为消费 `app.rules`，规则层不再作为 service 内部散落实现。

规则修复：

- 新增受控标签 `buffet`，覆盖“自助餐 / 自助烤肉 / 自助烧烤 / 自助火锅 / 自助小火锅 / 放题 / 海鲜自助”等表达。
- `extract_dining_preference()` 的 `specific_tags` 只来自用户明说的餐饮文本，不再把外部 base tags（例如家庭场景默认 `light_food`）升级成显式餐饮硬约束。
- `recommendation_policy.json` 和默认策略加入 `buffet` 显式餐饮锚点：用户明说自助餐时，餐厅槽位必须命中自助餐/放题语义。
- POI 语义补全：餐厅名称命中自助餐相关词时补 `buffet/proper_dining/slow_dining`；活动名称命中“游乐园/嘉年华/儿童乐园/童宇宙”时补 `amusement/child_friendly/kid_safe/family_time`。
- 家庭行程中，饭前 tail 节点避免再塞普通正餐，减少“晚饭前先吃一顿”的机械组合。

新增规则评测数据集：

- `tools/rule_evaluation/generate_rule_eval_dataset.py`：确定性生成脚本。
- `tools/rule_evaluation/rule_eval_dataset.json`：200 条 Mock-only 评测样例，schema 为 `rule_eval.v1`。
- 分布：
  - `family_parent_child`: 45
  - `date_dining_anchor`: 50
  - `friend_group`: 30
  - `solo_mood_relief`: 30
  - `city_light_explore`: 25
  - `edge_constraints`: 20
- 每条样例包含 `/api/v1/plans/create` 请求体片段、期望 scenario、party_size、must_have 标签、活动/餐厅槽位应命中标签、应排除词，方便人工或 AI 做召回率和槽位对齐评测。

验证结果：

- 手动验证“这周末想和老婆孩子去游乐园，然后吃一顿自助餐”：
  - scenario=`family_parent_child`
  - `constraints.must_have` 包含 `amusement/buffet/dinner`
  - 活动命中“爱玩嘉年华/亲子游乐”类节点
  - 餐厅命中“举高高自助小火锅”，不再落到“马走日·露馅包子·大骨牛肉汤”
- 新增 `tests/test_rule_modules.py`：
  - 验证 `buffet` specific tag 不被家庭默认 `light_food` 污染。
  - 验证规则评测数据集为 200 条且 case_id 唯一。
  - 验证“游乐园 + 自助餐”端到端计划命中 amusement 和 buffet，不出现包子/牛肉汤。

## 2026-05-24 POI 特征层与推荐排序升级

本轮把“继续补规则”推进为可评测的混合推荐架构：规则不再只是在线兜底，而是负责离线 POI 语义建模、在线硬约束和排序特征输入；大模型后续只适合做意图归一、离线标注增强和 Top-N 解释，不直接决定最终 POI。

同时去掉内部策略文案里的脑科学类比，不再把推荐链路解释成“感知/边缘系统/奖励”等概念。当前实现按工程事实命名：语义词典、场景适配、硬约束、路线适配和排序分数。

调研结论：

- 工业推荐的通用形态不是“一个超强提示词直接生成结果”，而是多阶段漏斗：召回把大候选集缩到几百个，排序模型再用更丰富的用户/物料特征挑最终结果。YouTube 推荐系统论文采用候选生成 + 排序的两阶段架构，TensorFlow Recommenders 也把 retrieval/ranker 作为标准组件。
- 特征层是更可控的长期资产。Feast 的 feature store 设计强调离线训练/批处理特征和在线低延迟服务一致，适合把 POI 的评分、价位、菜系、关系适配、雨天/亲子/约会/单人等维度沉淀为可审计数据。
- 因此当前推荐引擎更适合演进成“离线特征层 + 受控意图归一 + 多路召回 + 硬约束过滤 + 可解释排序/重排”。大模型只放在语义归一、离线弱标注、解释生成和冷启动扩展，不承担最终硬约束判断。

新增离线特征层：

- `backend/app/rules/poi_feature_store.py`
  - 从 `mock_pois.json` 和 `gaode_poi_enrichment.json` 生成 `poi_features.v1`。
  - 每个 POI 输出 `semantic_tags / facets / scores / evidence / confidence`。
  - 覆盖餐饮形态、菜系、活动类型、关系适配、场景适配、风险标记、质量先验等维度。
- `tools/rule_evaluation/build_poi_features.py`
  - 生成 `backend/data/poi_features.json`，当前 501 个 POI 全量建模。

在线推荐接入：

- `ServiceContainer` 注入 `POIFeatureStore`。
- `CandidateRetriever` 的 `_semantic_tags()` 先读取离线特征，再叠加规则/策略。
- `backend/app/rules/ranking_weights.py` 定义 `recommendation_ranker_weights.v1`，把原来散落在代码里的特征权重抽成只读配置。
- `backend/data/recommendation_ranker_weights.json` 当前由偏好集校准脚本生成，运行时读取该文件；缺失时使用等价默认值，保证复制数据目录和测试环境稳定。
- `_item_score()` 新增特征驱动分数：
  - family/date/friend/solo/visitor fit。
  - buffet/amusement/light_meal/proper_dining/quality 等槽位分数。
  - casual/snack/low_fit 等惩罚项。
- 显式需求改为硬约束优先：
  - 自助餐、日料、居酒屋、烤肉、手工 DIY、桌游、音乐、咖啡等不再允许被普通商铺/小吃/甜品随意替代。
  - 修正 `居酒屋` 被单字“酒”误判为“想喝酒”的问题，饮酒只由“喝酒/喝点酒/小酌/酒吧/酒馆”等明确表达触发。
  - 兜底阶段过滤已被硬约束判为无效的候选，避免无效 POI 在没有组合解时重新混入结果。

评测脚本：

- `tools/rule_evaluation/score_rule_eval_dataset.py`
  - 端到端跑 200 条 `rule_eval_dataset.json`。
  - 使用临时数据目录，不污染 `backend/data/plans.json` 等运行态文件。
  - 输出 `tools/rule_evaluation/reports/rule_eval_report.json`。
  - 支持 `--limit`、`--fail-fast`、`--strict`、`--progress-every`。
- `tools/rule_evaluation/generate_ranking_preference_dataset.py`
  - 从 `poi_features.json` 生成 pairwise preference 数据，当前 65 对。
  - 覆盖亲子活动、亲子清淡餐、约会正餐、日料、朋友桌游、单人音乐/散步、城市轻探索和自助餐等偏好。
- `tools/rule_evaluation/calibrate_ranker_weights.py`
  - 读取偏好对并验证/生成 `backend/data/recommendation_ranker_weights.json`。
  - 默认不自动放大权重，只输出偏好覆盖、pair accuracy 和 feature support，避免未审核数据直接改变线上排序。
  - 支持 `--apply-adjustments` 做有界感知机式校准，后续可在人工审核后启用。
- `tools/rule_evaluation/export_plan_review_set.py`
  - 端到端生成真实 `PlanContract`，导出 `tools/rule_evaluation/reports/plan_review_set.json`。
  - 每条样例保留用户输入、期望、最终时间线、POI display tags、离线 semantic_tags、核心 feature scores、路线摘要和用户可见文案。
  - 内置人工/AI 评审表：`intent_fit / activity_fit / restaurant_fit / route_fit / product_delight`。
  - 预留 `suggested_pairwise_preference` 字段，评审者可以把“应选 A、不应选 B”的判断转成后续排序偏好数据。
- `tools/rule_evaluation/plan_quality.py`
  - 新增确定性的 plan-level 自动质量评审，不替代人工评审，但先筛掉明显不该过的产品方案。
  - 评审维度从“单点标签命中”推进到“完整方案体验”：核心槽位、餐饮替代风险、低适配活动、转场长度、体验链路完整性。
  - 典型拦截：自助餐被包子/小吃替代、餐饮槽被咖啡甜品伪装、招待家人时选棋牌/KTV/剧本杀、约会正式晚饭却用餐饮 POI 伪装活动。
  - 输出 `auto_quality_review` 和 `auto_quality_summary`，已接入 `plan_review_set.json` 和一键质量门禁。
- `tools/rule_evaluation/import_review_preferences.py`
  - 从 `plan_review_set.json` 中读取 `suggested_pairwise_preference`。
  - 只有 `ready_for_import=true`、POI id 存在、role 合法、reason 非空且不是重复偏好时才导入。
  - 默认输出到 `tools/rule_evaluation/reports/ranking_preference_dataset.review_imported.json`，不直接覆盖主偏好集。
  - 同步生成 `review_preference_import_report.json`，记录 imported/skipped 明细和跳过原因。

关键评测结果：

- 升级前完整跑批：115 / 200，通过率 57.5%。
- 接入特征层和第一轮硬约束后：165 / 200，通过率 82.5%。
- 修复 `居酒屋`、预算/氛围/雨天/商场/聊天/桌游/喝点酒等高频意图后：184 / 200，通过率 92.0%。
- 修复 `light_food` 被意图标签上限截断后，`scripts/run_backend_p0_tests.py` 全部通过；200 条评测保持 184 / 200，没有回退。
- 继续修复单人散心和边界否定：
  - `activity` 搜索使用 must_have + 归一语义联合召回，但只把用户明说的 `coffee` 当硬门槛，避免“聊天”误压桌游。
  - 酒咖/小酒馆这类 activity POI 可承担单人“喝一杯”的 restaurant/短停靠槽位，解决饮酒意图没有餐饮槽的问题。
  - 音乐 POI 的识别改为看名称/类型，不再被地址里的“音乐喷泉”误标为音乐活动。
  - “喝酒/音乐 + 晚上几点前回家”默认从傍晚开始，避免下午 14:00 状态校验误杀民谣/酒馆。
  - “不要咖啡”“不喝酒”等否定表达进入硬排除，不再只做扣分。
- 最终完整跑批：200 / 200，通过率 100%。
- `scripts/run_backend_p0_tests.py` 最终全部通过。
- 排序偏好集：65 / 65，pair accuracy 100%；`recommendation_ranker_weights.json` 包含 28 个排序权重和 feature support 统计。
- 接入权重文件后再次跑批，200 条规则评测仍为 200 / 200，P0 仍全部通过。
- 产品级审阅集：`plan_review_set.json` 导出 200 / 200，0 个生成失败，覆盖与规则评测相同的 6 个场景分组。
- 导出审阅集后再次验证：200 条规则评测仍为 200 / 200，P0 仍全部通过。
- 审阅偏好导入：
  - 当前未填写审阅集导入结果为 0 imported / 200 skipped，跳过原因均为 `not_ready_for_import`，符合预期。
  - 使用临时 ready 样本验证可成功导入 1 条 review preference，并保留 `source_review_case_id/source_plan_id`。
  - 对导入输出跑 `calibrate_ranker_weights.py`，偏好集仍为 65 / 65。
  - 导入器接入后再次验证：200 条规则评测仍为 200 / 200，P0 仍全部通过。
- 产品级自动质量评审：
  - 第一版自动评审曾误把解释文案里的“不用小吃替代”当作 POI 身份命中，已修正为只用 POI 名称和标签判断替代风险。
  - 自动评审暴露了两个真实产品问题：
    - “我姐来下沙，别安排棋牌和KTV，吃饭想有杭州这边的体面感”曾选到剧本杀；已修复否定表达，`棋牌/KTV/剧本杀/电竞` 这类低适配活动在 city_light_explore 下进入硬排除。
    - “女朋友想吃日料，但不要日式快餐和咖啡，想像正式约会晚饭”曾把面包店/茶饮当活动和收尾，导致跨区长转场；已修复为活动/餐厅组合层加入总转场惩罚，并允许不强行塞 tail。
  - 边界样例修复后：
    - 姐姐招待 case：改为 `蕉个朋友DIY手工 -> 星巴克臻选 -> 狐狸爱上椰子鸡`，总转场约 7 分钟，auto quality 100。
    - 正式日料 case：改为 `横店电影城(宝龙商业中心店) -> 烧鸟仙人(下沙宝龙店)`，总转场约 6 分钟，auto quality 100。
  - 全量 `plan_review_set.json` 自动质量：200 / 200 pass，min_score 92，avg_score 99.68，critical_issue_count 0，major_issue_count 0。
  - 剩余非阻断 warning：`route_long_warning` 6 条，`route_simple_not_compact` 2 条，后续可通过真实路线/更多 POI 替代关系继续优化。
- 继续清理剩余路线 warning：
  - 发现亲子场景里“手工粉/手工面/手作酸奶”这类餐饮 POI 被“手工/手作”误标为手作体验，已在 `poi_feature_store`、`CandidateRetriever` 和策略语义层加入“手工食品 != 手作体验”的排除。
  - 发现 dinner_last 方案会因为 tail 单点分高而强行串入第二个亲子活动，导致“为了凑节点而拉长路线”。已加入 tail inclusion penalty：亲子短路线中，如果 tail 与主活动语义重复或让总转场超过紧凑阈值，就优先不塞 tail。
  - 亲子分组回归：45 / 45 自动质量 100，warning 清零。
  - 完整门禁回归后，`plan_review_auto_quality` 升级为 200 / 200 pass，min_score 100，avg_score 100.0，critical_issue_count 0，major_issue_count 0，issue_counts 为空。
- 本轮针对真实不满意样例继续补强：
  - `唱K/KTV` 从泛化的 `group_ok` 拆成受控语义 `karaoke`，进入意图解析、约束抽取、POI 离线特征、排序偏好和 plan-level 评测；朋友局明说唱K时活动槽必须命中 KTV，不再用影院/咖啡替代。
  - 单人散心在没有明确吃饭/喝酒/咖啡时，餐厅槽改为可选，避免把“晚上十点前到家/附近走走”强行拼成正餐链路。
  - 新增 `solo_forced_meal`、`solo_food_stop_repetition`、`solo_food_as_activity` 等自动质量检查，拦截低压力散心被多段餐饮/饮品稀释，或错类餐饮 POI 伪装成活动。
  - 修复错类 POI 特征：`奶吧/鲜奶/牛奶` 归入饮品甜品语义，`馄饨/水饺/面家/米粉/螺蛳粉` 归入小吃简餐语义；这类错类数据不再借 `mall/lake/light_walk` 标签穿透成活动。
  - 朋友局如果已经明确要自助/烤肉等正餐，活动槽不再允许另一个正餐餐厅冒充“坐坐”。
  - 定向回归：`friend_group` 30 / 30 自动质量 100；`solo_mood_relief` 30 / 30 自动质量 100。
  - 上一轮完整门禁：`rule_eval` 200 / 200；`plan_review_auto_quality` 200 / 200 pass，min_score 92，avg_score 99.96，critical_issue_count 0，major_issue_count 0，剩余 1 个非阻断 `route_simple_not_compact` warning，已在下一条“饭后坐聊”修复中清零。
- 继续修复“饭后坐聊”类顺序语义：
  - 根因：系统只识别到 `dinner/buffet/bbq` 时默认使用 `dinner_last`，但“饭后找地方坐着聊”“吃自助餐再找地方坐坐”本质是正餐先发生、聊天停留点在后的时间顺序约束。
  - 新增内部约束 `post_meal_conversation`：显式“饭后/餐后/吃完饭”会触发；“餐饮锚点在前 + 再/然后/之后 + 坐坐/聊天”也会触发，避免只靠单个关键词。
  - `CandidateRetriever` 对该 marker 使用 `restaurant_first`，同时禁止影院、酒场、第二个正餐或无关 tail 冒充饭后坐聊；正餐后只保留短转场的咖啡/茶饮/甜品/安静停留点。
  - `PlanGenerator` 对 restaurant-first 文案区分“先吃正餐再坐聊”和“先小酌再散心”，不再复用喝酒场景文案。
  - `plan_quality.py` 新增饭后坐聊顺序检查：正餐必须在前，正餐后必须有低噪声停留点。
  - 离线 POI 特征补上 `friend_group + coffee/dessert/quiet_stay/conversation => group_ok`，解决“四个人坐聊”在语义层没有 group_ok 的泛化缺口。
  - 定向回归：
    - `饭后找地方坐着聊` 2 / 2：正餐先行，后接 0.85-0.99km 的咖啡/茶饮坐聊点，自动质量 100。
    - `吃自助餐再找地方坐坐` 4 / 4：正餐先行，后接 1.83-1.96km 的坐聊点，自动质量 100。
  - 最新完整门禁：`rule_eval` 200 / 200；`plan_review_auto_quality` 200 / 200 pass，min_score 100，avg_score 100.0，critical_issue_count 0，major_issue_count 0，issue_counts 为空。
- 最终分项：
  - scenario: 200 / 200
  - party_size: 200 / 200
  - must_have_tags: 200 / 200
  - activity_slot: 200 / 200
  - restaurant_slot: 200 / 200
  - exclusions: 200 / 200

最终分组：

- `family_parent_child`: 45 / 45
- `date_dining_anchor`: 50 / 50
- `friend_group`: 30 / 30
- `city_light_explore`: 25 / 25
- `solo_mood_relief`: 30 / 30
- `edge_constraints`: 20 / 20

一键质量门禁：

- 新增 `tools/rule_evaluation/run_recommendation_quality_gate.py`，把推荐质量闭环串成一个可重复命令：
  - 构建 `poi_features.json`。
  - 生成 200 条规则评测集。
  - 生成 65 对排序偏好集并校准 `recommendation_ranker_weights.json`。
  - 端到端评分 200 条用例。
  - 导出 200 条产品级 `plan_review_set.json`。
  - 校验 plan-level 自动质量评审。
  - 导入已确认的审阅偏好，并校验 review-imported 偏好集。
  - 跑后端 P0。
- 推荐本地验收命令：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py --progress-every 100
```

- 本次门禁报告：`tools/rule_evaluation/reports/recommendation_quality_gate.json`。
- 本次门禁结果：`quality_gate=PASS`。
  - `poi_features`: 501 个 POI 特征。
  - `ranker_preferences`: 65 / 65，pair accuracy 100%。
  - `rule_eval`: 200 / 200，通过率 100%。
  - `plan_review_set`: 200 条，0 个生成失败。
  - `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0，0 critical，0 major，issue_counts 为空。
  - `review_preference_import`: 当前未标注审阅集 0 imported / 200 skipped，原因均为 `not_ready_for_import`，符合预期。
  - `review_imported_preferences`: 65 / 65，pair accuracy 100%。
  - `backend_p0_tests`: 19 / 19，0 failed。

## 2026-05-24 推荐引擎通用化补强

本轮针对“不要继续只补规则，是否应该把离线数据多维建模、让大模型只承担小部分能力”的问题做了实现层验证。结论：当前方向应该从“提示词泛化”转成“离线特征资产 + 多路召回 + 可解释排序 + 受控大模型文案/兜底”的推荐架构。

外部调研依据：

- YouTube 推荐系统论文采用候选生成和排序两阶段架构，先从大规模候选里召回数百个，再用排序网络精排。这和 LifePilot 当前的 `CandidateRetriever -> ranker -> PlanGenerator` 边界一致。
- Google Wide & Deep 的核心价值是同时保留记忆能力和泛化能力：对 LifePilot 来说，显式硬约束、禁忌、场景标签是“记忆”，离线特征分和偏好权重是“泛化”。
- TensorFlow Recommenders 文档也把推荐系统拆成 retrieval 和 ranker 两段：先召回候选，再对候选打分形成短名单。LifePilot 不必在比赛 Demo 里训练大模型，但应该沿这个结构做可解释的轻量实现。

架构落点：

- 大模型不负责“猜餐厅/猜路线/猜状态”，只做受控 JSON 文案润色、少量语义归一兜底和后续人工评审辅助。
- 真正决定推荐质量的核心资产是 `poi_features.v1`：POI 的品类、餐型、适合人群、约会/亲子/朋友/单人适配、价格、评分、路线锚点、风险标签、显式禁忌和可替代关系。
- 规则不再是散落 if/else，而是分层承担不同职责：硬约束负责不能错，特征层负责可召回，排序权重负责偏好，plan-level quality gate 负责防止用户可见方案退化。

本轮新增/修复：

- 前端计划页把“类脑推荐优先级”改为“推荐匹配优先级”，避免把工程能力包装成生硬脑科学概念。
- 新增通用时序 marker `restaurant_first_request`：覆盖“先吃饭，饭后 KTV/散步/聊天”等表达，不再只为“饭后坐聊”写单点规则。
- 新增 `light_walk` 显式散步语义和 `walk_spot` 召回通路；同时修正单人散心默认约束，避免“想听音乐坐坐”被误判为必须散步。
- 新增 `宝龙滨河步道` 作为下沙宝龙附近 Mock 步道候选，补齐“西餐后附近散步”的真实短转场资产。
- 强化咖啡否定：`不要日式快餐和咖啡`、`不想再喝咖啡` 等表达进入 `must_not_have=coffee`，不再污染候选。
- 路线敏感场景中，如果加入 tail 会把总转场拉长到 3km 以上，排序层强烈倾向不塞 tail，避免为了凑节点破坏体验。
- restaurant-first 文案按归一化餐饮标签生成，不再把西餐、日料等统一写成“自助/烤肉硬需求”。

数据集更新：

- 200 条规则评测保持总量不变，新增覆盖：
  - `四个人晚上先吃自助烤肉，饭后去KTV唱歌，别太远。`
  - `和女朋友先吃西餐，吃完想在附近散步，不想再喝咖啡。`
  - 两条样例的“如果附近没有就给备选但说明是模拟”变体。
- 新增期望标签包括 `restaurant_first_request / karaoke / light_walk`，并加入 `timeline_order=restaurant_first`。

本轮定向结果：

- 饭后 KTV：`鲜肉多齐齐哈尔自助烤肉(福雷德广场店) -> SEEUKTV(文泽和达城店)`，总转场约 0.9km，auto quality 100。
- 西餐后散步：`73号.LOFT西餐厅 -> 宝龙滨河步道`，总转场约 0.08km，auto quality 100。
- 单人音乐散心：恢复为 `燎原民谣精酿酒馆`，不再被步道覆盖。
- 正式日料且不要咖啡：`横店电影城(宝龙商业中心店) -> 宝龙滨河步道 -> 烧鸟仙人(下沙宝龙店)`，总转场约 0.33km，auto quality 100。

最新完整门禁：

- 命令：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py --progress-every 100
```

- 结果：`quality_gate=PASS`。
- `poi_features`: 501。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_set`: 200 / 200，0 生成失败。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0，0 critical，0 major，issue_counts 为空。
- `ranker_preferences`: 65 / 65，pair accuracy 100%。
- `backend_p0_tests`: 19 / 19，0 failed。

## 2026-05-24 推荐策略命名迁移

本轮继续去掉“类脑/brain”作为主叙事：推荐能力不再以脑科学隐喻命名，而是明确拆成可维护的 recommendation policy、POI feature store、ranker weights 和 plan quality gate。

代码迁移：

- 新增 `backend/app/rules/recommendation_policy_engine.py`，主类为 `RecommendationPolicyEngine`，评分返回对象为 `RecommendationScore`。
- 新增 `backend/data/recommendation_policy.json`，替代运行主链路中的 `brain_policy.json`。
- `ServiceContainer` 改为注入 `recommendation_policy_engine`。
- `CandidateRetriever` 改为消费 `policy_engine`，内部方法从 `_brain_item_score/_brain_chain_score` 改为 `_policy_item_score/_policy_chain_score`。
- 保留 `backend/app/rules/brain_recommendation_engine.py` 和 `backend/app/services/brain_recommendation_engine.py` 作为薄兼容层，避免旧导入立刻断裂；主链路不再依赖这些文件。
- P0 测试和本地 P0 runner 的样例名从 `test_brain_*` 改为 `test_recommendation_*`。

验证：

- 语法检查通过：

```bash
python3 -m py_compile backend/app/rules/recommendation_policy_engine.py backend/app/rules/brain_recommendation_engine.py backend/app/services/recommendation_policy_engine.py backend/app/services/brain_recommendation_engine.py backend/app/services/candidate_retriever.py backend/app/services/container.py scripts/run_backend_p0_tests.py tests/test_p0_plan_create.py
```

- `backend/data/recommendation_policy.json` 通过 `python3 -m json.tool` 校验。
- 后端 P0：19 / 19 pass，输出已改为 `test_recommendation_*`。
- 规则评测：200 / 200 pass，`activity_slot / restaurant_slot / scenario / party_size / must_have_tags / exclusions` 全部 100%。
- 完整推荐质量门禁已重新刷新正式报告：`quality_gate=PASS`，`plan_review_auto_quality` 200 / 200 pass，min_score 100，avg_score 100.0，P0 stdout 已不再包含旧 `test_brain_*` 样例名。

后续优化方向：

- 当前 200 条规则评测已全过，但它仍是 Mock-only 的验收集，不等价于真实线上泛化。
- 下一步应把 `poi_features.v1` 扩展成可人工复核的标注资产：补充真实评分、价格置信度、评论摘要、适合人群、禁忌场景、营业时间可信度和可替代关系。
- 数据资产应继续补“多维标签 + 负样本 + 替代关系”，优先沉淀在离线特征和偏好集中，而不是继续把泛化压力放到 prompt。
- 人工或 AI judge 应优先评审 `plan_review_set.json`，因为它展示的是用户实际看到的完整方案，而不是单个 POI 标签。
- 评审后把低分 case 的 `suggested_pairwise_preference.ready_for_import` 标为 true，经 `import_review_preferences.py` 输出 review-imported 偏好集，再用 `calibrate_ranker_weights.py --apply-adjustments` 生成候选权重，只有在 P0、200 条规则评测、偏好集、审阅集生成和一键质量门禁都通过后再进入运行态。

参考：

- Google Research, Deep Neural Networks for YouTube Recommendations: https://research.google.com/pubs/archive/45530.pdf
- Google Research, Wide & Deep Learning for Recommender Systems: https://research.google/pubs/pub45413
- TensorFlow Recommenders Retrieval API: https://www.tensorflow.org/recommenders/api_docs/python/tfrs/tasks/Retrieval
- Feast Feature Store: https://github.com/feast-dev/feast

## 2026-05-24 数据优先推荐架构调研

核心判断：

- 用户提出的方向成立：继续堆规则只能提高已知 case 的覆盖，不能形成真正通用的推荐能力。更稳的路线是“离线多维建模 + 在线轻量排序 + 大模型窄口辅助”。
- 大模型不应该直接承担“从全量 POI 中凭提示词选方案”的主决策。它更适合做受控意图理解、离线标签抽取、评论摘要、候选解释、失败 case 归因和 AI judge。
- 推荐质量的主资产应从 prompt 转移到数据资产：`poi_features.v1`、偏好对、负样本、替代关系、路线簇、场景适配分、证据和置信度。

外部调研要点：

- YouTube 推荐系统论文采用候选生成和排序两阶段结构：先从大规模物料中召回小候选集，再用更丰富特征做排序。这说明工业推荐系统通常不是一个通用 prompt 一步生成。
- TensorFlow Recommenders 把数据准备、模型、训练、评估、部署视为完整推荐工作流，并明确支持 item/user/context 信息进入推荐模型。
- Feast 的 feature store 设计强调离线特征和在线低延迟特征服务的一致性，这正好对应 LifePilot 需要的 POI 离线建模和运行时读取。
- LLM + 推荐系统方向的研究也把 LLM 放在 feature engineering、feature encoder、ranking、interaction、pipeline controller 等多个位置；但 LLM 作为在线 ranker 会有位置偏置、热门偏置、延迟和成本问题，适合谨慎小流量接入。

和当前 LifePilot 的对应关系：

- `IntentParser` 已经把大模型限制在受控 JSON 意图层：场景、摘要、受控标签、情绪目标和置信度。
- `POIFeatureStore` 已经是雏形 feature store：从 `mock_pois.json` 和 `gaode_poi_enrichment.json` 离线生成 `semantic_tags / facets / scores / evidence / confidence`。
- `CandidateRetriever` 已经在 `_feature_rank_score()` 里读取特征分和 `recommendation_ranker_weights.json`，可以继续从手写权重演进到学习排序。
- `ranking_preference_dataset.json` 和 `calibrate_ranker_weights.py` 已经形成 pairwise preference 的入口；下一步可以把人工/AI review 的低分样例转成可训练偏好对。
- `plan_review_set.json` 和 `auto_quality_review()` 已经从“单点 POI 是否命中”升级到“整条时间线是否像一个好方案”。

建议的通用模式：

1. 意图层输出结构化需求，而不是模板：`must_have / should_have / must_not_have / soft_preferences / budget / route / party / weather / mood / slot_order`。
2. POI 层做多维离线建模：
   - 基础维度：品类、子类、菜系、餐型、活动类型、价格、评分、营业时间、区域。
   - 场景维度：亲子、约会、朋友、单人、招待家人、雨天、饭后、轻松、少走路。
   - 体验维度：正餐充分度、仪式感、聊天友好、安静度、排队风险、拥挤风险、孩子安全、适合停留时长。
   - 风险维度：快餐/小吃替代、重口味、低适配活动、强社交、酒精、运动强度、商场依赖、电影依赖。
   - 关系维度：可替代、可搭配、同楼层/同商圈、饭后衔接、雨天替代、无库存替代。
   - 证据维度：来自名称、类目、标签、评分、评论摘要、人工标注还是大模型推断；每个特征都带置信度。
3. 召回层使用多路召回：
   - 硬约束召回：自助餐、KTV、日料、不要咖啡、不要电影等。
   - 语义召回：约会氛围、饭后坐聊、亲子低负担、单人散心。
   - 地理召回：同商圈、步行可达、路线簇。
   - 替代召回：目标不可用时找同类或相邻体验，但必须保留“为什么替代”。
4. 排序层先保持可解释轻量模型：
   - 短期继续用线性权重 + pairwise preference 校准。
   - 中期可接 LightGBM/LambdaMART 这类 learning-to-rank，把人工/AI judge 偏好、用户反馈和自动质量结果变成训练样本。
   - 排序目标不只看 POI 分，还要看整条链路效用：匹配度、质量、转场、预算、节奏、风险、体验递进。
5. 大模型只占小比例但更关键：
   - 在线：受控意图解析、少量候选解释、异常 case 复核，不直接越权选全量 POI。
   - 离线：从评论/详情页抽取标签、生成特征证据、聚类长尾 POI、生成 adversarial eval case。
   - 评测：对 `plan_review_set.json` 做 AI judge，产出问题代码和 pairwise preference 建议，再进入人工确认或白名单导入。

可集成方案：

- 第一阶段：扩展 `poi_features.v1` schema，不改 API。新增 `experience_scores`、`risk_scores`、`relation_edges`、`evidence_sources`、`review_summary`、`feature_confidence`。
- 第二阶段：扩展偏好数据集。把 65 对扩到 300-500 对，覆盖正负样本、替代样本、路线样本和“看似可行但体验差”的反例。
- 第三阶段：新增 `tools/rule_evaluation/generate_adversarial_review_cases.py`，让大模型或规则生成边界样例，但必须经过 deterministic quality gate。
- 第四阶段：引入可切换 ranker adapter。默认仍走当前线性权重；当偏好集足够时，接入学习排序模型，但输出仍只影响内部候选排序，不改变 `PlanContract`。
- 第五阶段：建立反馈闭环。用户点选、人工 review、AI judge 只写入偏好数据或特征修正，不直接改 prompt。

这套方案可以集成到现有“类脑/推荐策略引擎”里，但工程命名建议继续保持 `RecommendationPolicyEngine`。对外可以讲“类脑引擎”，对内应表达为 feature store + policy engine + ranker + quality gate，避免脑科学隐喻掩盖真实可维护边界。

优先级：

1. 先补特征 schema 和证据字段，因为这是所有后续模型的地基。
2. 再扩偏好对和 adversarial eval，优先覆盖“不想要 X”“饭前/饭后顺序”“想要某餐型但容易被小吃替代”“少走路但不想商场/电影”等失败高发区。
3. 最后再考虑学习排序模型。当前样本量太小，直接上模型容易只是把规则过拟合换成模型过拟合。

新增参考：

- Deep Neural Networks for YouTube Recommendations, RecSys 2016: https://doi.org/10.1145/2959100.2959190
- TensorFlow Recommenders: https://www.tensorflow.org/recommenders
- Feast Feature Store documentation: https://docs.feast.dev/v0.42-branch
- How Can Recommender Systems Benefit from Large Language Models: A Survey: https://arxiv.org/abs/2306.05817
- Large Language Models are Zero-Shot Rankers for Recommender Systems: https://arxiv.org/abs/2305.08845
- LLM4Rerank: LLM-based Auto-Reranking Framework for Recommendations: https://arxiv.org/abs/2406.12433

## 2026-05-24 数据优先推荐引擎落地

本轮把上一节的调研方案落到代码层：不继续扩大 prompt，也不把概念包装成脑科学隐喻，而是增强 `POIFeatureStore -> CandidateRetriever -> ranking_preferences -> quality_gate` 这条可审计推荐链路。

代码更新：

- `backend/app/rules/poi_feature_store.py`
  - `poi_features.v1` 保持向后兼容，新增 `dimension_groups` 描述当前特征组。
  - 每个 POI 新增 `experience_scores`：`dining_substance / ritual_fit / conversation_fit / quiet_fit / kid_safety / walkability / rain_comfort / stay_duration_fit / plan_anchor_strength`。
  - 每个 POI 新增 `risk_scores`：`snack_substitution / heavy_meal / low_fit_activity / strong_social / alcohol_risk / mall_dependency / movie_dependency / dinner_substitution / child_safety_risk / route_fragility / intent_mismatch`。
  - 每个 POI 新增 `relation_edges`，最多 8 条，表达 `substitute / pairs_after_meal / pairs_with_meal / light_stop_before_meal`，为后续 PlanB、替代推荐和组合学习留入口。
  - 每个 POI 新增 `evidence_sources / feature_confidence / review_summary`，把特征来源和置信度显式化，方便人工或 AI review。
- `backend/app/rules/ranking_weights.py`
  - 排序权重从 28 个扩到 38 个，新增体验分和风险分权重，例如 `activity.experience_fit`、`restaurant.snack_substitution_risk`、`risk.route_fragility`。
- `backend/app/services/candidate_retriever.py`
  - `_feature_rank_score()` 开始读取 `experience_scores` 和 `risk_scores`，让路线、餐型、聊天、亲子安全、商场/电影依赖、小吃替代等因素进入排序。
  - 修正亲子 + 显式餐型场景的预算解释：没有明说预算时，西餐等餐饮预算 hint 不再把整条亲子行程的人均总价卡死，避免为了低价西餐牺牲“别太远”。
- `tools/rule_evaluation/ranking_feature_vectors.py`
  - 新增统一 pairwise feature vector，供偏好集生成和权重校准共同使用，避免生成逻辑与训练/验证逻辑漂移。
- `tools/rule_evaluation/generate_ranking_preference_dataset.py`
  - 偏好模板从 11 类扩到 24 类。
  - 覆盖亲子游乐/手作、约会手作/散步/西餐/日料/羊排/火锅/清淡、朋友 KTV/桌游/饭后聊天/自助/烤肉、单人音乐/散步/安静咖啡、家人来访/湖边/不想商场、收尾聊天散步等场景。
  - 偏好对从 65 对扩到 432 对，schema 升级为 `ranking_preferences.v2`。

关键修正：

- 新特征初次接入后，完整门禁出现 5 个非阻断 `route_simple_not_compact` warning，集中在“亲子 + 西餐 + 别太远”场景。
- 根因是 `western_cuisine` 的餐饮预算 hint 被当成整条行程总预算，较近但稍贵的酒店西餐被排除，系统选择了更远的低价西餐。
- 已修正为：没有显式预算时，餐饮 hint 主要服务餐厅候选和价格预估，不应压过短转场产品体验。
- 定向家庭亲子 review：45 / 45 pass，min_score 100，issue_counts 为空。

最新完整门禁：

- 命令：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py --progress-every 100
```

- 结果：`quality_gate=PASS`。
- `poi_features`: 501 个 POI，全部包含 `experience_scores / risk_scores / relation_edges / evidence_sources / feature_confidence`。
- `ranking_preferences`: 432 / 432，pair accuracy 100%，`recommendation_ranker_weights.json` 当前 38 个权重。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0，0 critical，0 major，issue_counts 为空。
- `backend_p0_tests`: 19 / 19，0 failed。

关键样例抽查：

- 亲子 + 游乐园 + 西餐 + 别太远：`爱玩嘉年华(龙湖杭州金沙天街店) -> CHAGEE霸王茶姬(上沙路店) -> 杭州龙湖皇冠假日酒店·滟澜全日餐厅`，总转场约 0.3km，auto quality 100。
- 亲子 + 手工 DIY + 西餐 + 别太远：`小喜·DIY手工坊·拼豆·油画 -> CHAGEE霸王茶姬(上沙路店) -> 杭州龙湖皇冠假日酒店·滟澜全日餐厅`，总转场约 0.32km，auto quality 100。
- 单人音乐散心：`燎原民谣精酿酒馆`，auto quality 100。
- 饭后 KTV：`鲜肉多齐齐哈尔自助烤肉(福雷德广场店) -> 搭唛AI智慧自助KTV`，auto quality 100。
- 西餐后散步：`73号.LOFT西餐厅 -> 宝龙滨河步道`，auto quality 100。

下一步：

- 继续把 `relation_edges` 用到 Recovery/PlanB，而不只是离线特征。
- 把人工或 AI judge 对 `plan_review_set.json` 的低分原因转成 `ranking_preferences.v2` 的新模板或 ready-for-import 偏好对。
- 在样本超过 1000 对且人工 review 稳定后，再考虑接 LightGBM/LambdaMART 这类 learning-to-rank；当前仍以可解释线性权重作为主排序模型。

## 2026-05-24 Recovery / PlanB 接入 relation_edges

本轮把 `relation_edges` 从离线特征推进到可执行替代链路，目标是让 PlanB 不再只做“同区域找一个能订的餐厅”，而是优先按原 POI 的语义关系、餐型约束、相邻路线和 Mock 状态筛选替代。

代码更新：

- `backend/app/rules/poi_feature_store.py`
  - 收紧 `substitute` 关系生成：餐厅替代只能由自助、火锅、烤肉/羊排、日料、西餐、轻食、咖啡/甜品等餐型/菜系簇触发。
  - 湖边、散步、拍照、安静等场景标签不再让两个餐厅互相成为 `substitute`，避免“酒店西餐 -> 茶饮/咖啡食堂”这类错误边。
  - 活动替代仍保留散步、手作、KTV、桌游、游乐、音乐、影院等活动语义簇。
- `backend/app/services/recovery_service.py`
  - Recovery 候选顺序改为：`relation_edges` 候选 -> 同区域搜索 -> 全局 fallback，并用统一评分排序。
  - `relation_edges` 候选会写入 `replacement.source / relation / relation_score / reason`，便于调试和后续 AI judge 复盘。
  - 餐厅替代增加全候选语义守卫：如果原计划或约束明确是 `buffet / hotpot / bbq / cuisine_japanese / western_cuisine / light_meal`，fallback 也必须匹配对应餐型；找不到就返回无有效替代，不再用快餐、小吃、包子、咖啡硬替。
  - 区分显式低排队和默认低排队：用户明确“不排队”时保持严格；默认低排队下，高语义替代可进入 verifier 的 warning 区间，由验证器继续判断是否可接受。
  - 修复 Recovery 失败响应：`updated_plan_contract` 为 `None` 时 API 不再因为读取 trace_id 触发 500，而是返回标准 RecoveryResult。
- `tests/test_p0_plan_create.py` 与 `scripts/run_backend_p0_tests.py`
  - 新增 `test_recovery_relation_replacement`：日料不可订时，Recovery 必须使用 `poi_relation_edge + substitute`，且替代餐厅仍是日料语义，不可退化成咖啡/茶饮。
  - 新增 `test_recovery_does_not_replace_buffet_with_fast_food`：自助餐不可订时，不能替换为肯德基、包子、面馆、咖啡、甜品等错误餐型；没有同餐型可用替代时返回无有效替代。

关键样例抽查：

- `烧鸟仙人(下沙宝龙店)` 的 `substitute` 关系现在集中在日料候选：`松鮨亭和风料理`、`御水月日式会席料理`、`懂肉记日式烧肉`、`無忧浅草君洋风料理`、`池奈·日式咖喱蛋包饭`、`争鲜回转寿司`、`鲔吞自慢日本料理`。
- `杭州龙湖皇冠假日酒店·滟澜全日餐厅` 不再因为 `lake / light_walk` 与茶饮、咖啡空间互为餐厅替代，保留西餐/披萨等更接近的同餐型替代。
- “亲子 + 游乐园 + 自助餐”场景下，若自助餐不可订且没有同餐型可用替代，Recovery 返回无有效替代，不会把自助餐替换成肯德基、包子或咖啡。

最新完整门禁：

- 命令：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py --progress-every 100
```

- 结果：`quality_gate=PASS`。
- `poi_features`: 501 个 POI。
- `ranking_preferences`: 432 / 432，pair accuracy 100%，权重数 38。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0，0 critical，0 major，issue_counts 为空。
- `review_import`: 200 条 review case 暂未导入偏好对，全部为 `not_ready_for_import`，保持人工/AI judge 审核入口。
- `backend_p0_tests`: 21 / 21，0 failed。

下一步：

- 把 Recovery 的失败原因进一步拆成“无同语义可订座”“同语义有位但路线/天气失败”“同语义有位但排队超偏好”，用于前端展示更像真实 PlanB 的解释。
- 将人工或 AI judge 标注的 Recovery 失败样例转成 `ranking_preferences.v2` 或 relation 修正样本，避免手工继续补 if-else。

## 2026-05-24 Recovery 失败原因结构化

本轮继续推进 PlanB 产品体验：上一轮已经避免了“自助餐被快餐/包子硬替”的错误，但失败时用户仍只看到泛化文案。现在 Recovery 会把失败原因拆成可展示、可统计、可回流评测的数据。

代码更新：

- `backend/app/services/recovery_service.py`
  - Recovery 候选筛选会累计 `candidate_summary`：候选总数、relation edge 候选数、语义不匹配数、预算过滤数、状态检查数、无可用资源数、排队超限数、天气不安全数。
  - 无法找到替代时，`replacement` 会带上 `failure_reason_code / failure_reasons / candidate_summary / user_visible_reason`。
  - 找到替代节点但整条计划未过 verifier 时，`diff.recovery_diagnostics` 会记录 `verifier_failed_checks / verifier_warnings`，并把失败原因归类为天气、路线、预算、容量或通用校验失败。
  - `user_explanation` 不再固定写“重新生成计划”，而是优先使用结构化诊断生成的用户可见原因。
- `frontend/components/execution/ExecutionCards.tsx`
  - 执行结果页的 Recovery 卡片会展示失败原因和候选统计。
  - 用户能看到“没有输出不符合原意的餐厅替代”“同餐型候选存在，但资源状态不足”等原因，而不是误以为系统没尝试。
- `tests/test_p0_plan_create.py` 与 `scripts/run_backend_p0_tests.py`
  - 自助餐失败回归新增断言：失败结果必须包含 `failure_reason_code`、用户可见原因，以及 `required_semantic_tags == ["buffet"]` 的候选诊断。

关键样例：

- 输入：`这周末想和老婆孩子去游乐园,然后吃一顿自助餐`
- 当原自助餐不可订且同餐型候选不满足桌位/排队时，Recovery 返回：
  - `failure_reason_code`: `same_semantic_restaurant_capacity_or_queue_failed`
  - `user_explanation`: `找到同餐型候选，但桌位或排队时间未通过校验。`
  - `candidate_summary`: 检查 102 个候选，其中 4 个 relation edge 同语义候选、98 个语义不匹配、1 个无可用资源、3 个排队超出偏好。
- 这说明系统没有把自助餐错误降级成快餐/包子，而是保留真实意图，并明确告诉用户为什么 PlanB 暂时不可用。

验证：

- `python3 -m py_compile backend/app/services/recovery_service.py backend/app/api/v1/plans.py tests/test_p0_plan_create.py scripts/run_backend_p0_tests.py`：通过。
- `cd frontend && npm run typecheck`：通过。
- `scripts/run_backend_p0_tests.py`：21 / 21，0 failed。
- 完整质量门禁：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py --progress-every 100
```

- 结果：`quality_gate=PASS`。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0，0 critical，0 major。
- `ranking_preferences`: 432 / 432，pair accuracy 100%，权重数 38。
- `backend_p0_tests`: 21 / 21，0 failed。

下一步：

- 把这些 `failure_reason_code` 汇总到 review import 或 feedback import 中，让“同语义候选不足/资源不足/路线天气失败”自动变成可训练的偏好或特征修正样本。
- 针对天气风险继续优化路线生成：如果计划里已经出现中高天气风险，不应等 Recovery 后才发现，而应在初始候选排序阶段压低户外散步节点。

## 2026-05-24 Recovery 失败回流到偏好/特征修正

本轮把上一节的 `failure_reason_code` 从展示信息推进到数据闭环：Recovery 失败不再只是日志或页面文案，而会自动导出成可审计样例，再转成 pairwise preference 和 feature correction 候选。

代码更新：

- `backend/app/services/recovery_service.py`
  - `candidate_summary` 增加少量候选样本：`semantic_mismatch_samples / not_available_samples / queue_exceeded_samples / budget_exceeded_samples / weather_unsafe_samples`。
  - 样本只保留 POI、名称、公开语义标签和 Mock 状态摘要，用于离线训练/评测，不暴露 Prompt、API Key 或推理链。
- `tools/rule_evaluation/export_recovery_failure_set.py`
  - 新增确定性 Recovery failure 导出脚本。
  - 当前覆盖两个高价值失败类型：
    - `same_semantic_restaurant_capacity_or_queue_failed`：自助餐语义保留，但同餐型候选桌位/排队不满足。
    - `replacement_plan_weather_failed`：已找到同语义替代，但整条计划仍因天气风险未通过 verifier。
- `tools/rule_evaluation/import_recovery_failure_preferences.py`
  - 将 Recovery failure 转成两类数据：
    - `ranking_preferences`：把“同语义但当前资源不足的候选”作为 preferred，把“语义不匹配的硬替代候选”作为 rejected，形成可训练 pairwise preference。
    - `feature_corrections`：把“同餐型库存/关系缺口”“天气路线风险”保留为特征修正候选，后续可进入人工或 AI judge 队列。
- `tools/rule_evaluation/run_recommendation_quality_gate.py`
  - 完整门禁新增三步：`export_recovery_failure_set`、`import_recovery_failure_preferences`、`validate_recovery_imported_preferences`。
  - 新增检查项：Recovery failure set 必须有失败样例，import 必须产出可行动 pairwise 或 feature correction，导入后的偏好集必须保持 ranker pair accuracy。

新增数据结果：

- `recovery_failure_set.v1`: 2 / 2 failure cases。
- failure codes:
  - `same_semantic_restaurant_capacity_or_queue_failed`
  - `replacement_plan_weather_failed`
- `recovery_failure_import_report.v1`:
  - base preference cases: 432
  - imported pairwise preferences: 14
  - feature correction candidates: 2
  - output preference cases: 446
  - skipped: 2 duplicate preference，1 no_pairwise_samples
- `recommendation_ranker_weights.recovery_imported.json`:
  - preference_case_count: 446
  - pair_accuracy: 446 / 446，rate 1.0

关键意义：

- “自助餐不可订”这类失败不会再只停留在“恢复失败”，而会形成可复用偏好：即使同语义候选当前排队或无位，它也仍然优于包子、快餐、咖啡这类离题替代。
- “找到替代但天气失败”不会直接变成餐厅偏好，而会进入 feature correction：提示初始排序阶段应更早压低中高天气风险下的户外/步道节点。
- 这比继续补 prompt 或 if-else 更接近数据驱动推荐系统：线上/评测失败 -> 结构化原因 -> 偏好对/特征修正 -> ranker 校验。

最新完整门禁：

- 命令：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py --progress-every 100
```

- 结果：`quality_gate=PASS`。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0，0 critical，0 major。
- `ranking_preferences`: 432 / 432，pair accuracy 100%。
- `recovery_imported_preferences`: 446 / 446，pair accuracy 100%。
- `backend_p0_tests`: 21 / 21，0 failed。

下一步：

- 把 `replacement_plan_weather_failed` 对应的 feature correction 真正接到初始候选排序：天气中高风险时，压低户外步道/湖边散步节点，优先室内轻停留或室内活动。
- 把真实用户 feedback 的 `selected_options / free_text` 也转成同一套 import 格式，形成 `review / recovery / feedback` 三路数据闭环。

## 2026-05-24 天气风险前移到初始排序

本轮把上一节发现的 `replacement_plan_weather_failed` 从 Recovery 事后诊断前移到初始候选排序。目标是：中高天气风险下，不再先生成户外步道/湖边散步节点，再等 verifier 或 Recovery 才发现计划不可执行。

代码更新：

- `backend/app/rules/poi_feature_store.py`
  - 离线 POI 特征新增 `risk_scores.weather_exposure` 和兼容字段 `weather_exposure_risk`。
  - `walk_spot` 会被建模为轻步行节点；如果名称/子类含 `室内 / 地下 / 连通 / 雨天 / 温室 / 避雨`，会被识别为 `indoor / rain_safe`，否则进入 `outdoor` 暴露风险。
  - `review_summary` 会标出“雨天户外暴露高”，方便人工或 AI judge 审核。
- `backend/app/rules/ranking_weights.py` 与 `tools/rule_evaluation/ranking_feature_vectors.py`
  - 排序权重新增 `risk.weather_exposure`，当前默认权重为 `-42.0`。
  - Pairwise preference 向量把 activity/tail 的天气暴露作为可校验特征。
- `backend/app/services/candidate_retriever.py`
  - 初始排序增加在线天气上下文：按候选所在区域、计划开始时间和角色估算窗口读取 Mock Weather。
  - 高风险天气下，暴露型 activity/tail 直接压出候选；中风险天气下强降权。
  - 室内、雨天友好、咖啡/甜品/安静停留点在中高天气风险下获得小幅上下文加分。
  - `_best_tail` 不再只看路线亲近度，也会把 tail 自身排序分纳入选择，避免“最近但明显不合适”的收尾节点压过更安全的室内节点。
- `backend/app/services/verifier_service.py`
  - 修正 `walk` 类型的一刀切户外判断：先识别 `rain_safe / indoor / 室内 / 地下 / 连通 / 雨天 / 温室 / 避雨`，再决定是否按户外节点进入天气校验。
- `tools/rule_evaluation/generate_ranking_preference_dataset.py`
  - 新增 `tail_rain_safe_over_exposed_walk_when_weather_risky` 模板，把雨天友好收尾优先于裸露步道纳入偏好数据。
- `tests/test_p0_plan_create.py` 与 `scripts/run_backend_p0_tests.py`
  - 日料约会场景新增断言：初始计划不得出现 `weather_risk=fail`。

关键样例：

- 输入：`周末想和女朋友出去放松一下,晚上想吃日料`
- 修复前：初始计划包含 `宝龙滨河步道`，2026-05-24 下午下沙天气为高户外风险，`weather_risk=fail`。
- 修复后：初始计划不再插入该户外步道，`weather_risk=pass`；计划状态从 fail 降为 warning，剩余 warning 来自餐厅桌位/排队资源风险。
- Recovery failure set 中的 `replacement_plan_weather_failed` 已消失，说明这个问题已从事后恢复前移到初始排序。

最新数据结果：

- `ranking_preferences.v2`: 446 cases，新增天气收尾偏好模板后仍保持 100% pair accuracy。
- `recommendation_ranker_weights.json`: weight_count 39，`pair_accuracy`: 446 / 446，rate 1.0。
- `recovery_failure_set.v1`: 2 个导出场景中只剩 1 个真实失败样例，failure code 为 `same_semantic_restaurant_capacity_or_queue_failed`。
- `recovery_failure_import_report.v1`:
  - base preference cases: 446
  - imported pairwise preferences: 16
  - feature correction candidates: 1
  - output preference cases: 462
  - skipped: 1 no_pairwise_samples
- `recommendation_ranker_weights.recovery_imported.json`: 462 / 462，pair accuracy 1.0。
- `backend_p0_tests`: 22 / 22，0 failed。

验证：

- `python3 -m py_compile backend/app/services/candidate_retriever.py backend/app/services/verifier_service.py backend/app/rules/poi_feature_store.py backend/app/rules/ranking_weights.py tools/rule_evaluation/ranking_feature_vectors.py tools/rule_evaluation/generate_ranking_preference_dataset.py scripts/run_backend_p0_tests.py tests/test_p0_plan_create.py`：通过。
- `scripts/run_backend_p0_tests.py`：22 / 22，0 failed。
- 分段定位：`score_rule_eval_dataset.py --limit 60 --progress-every 20`：60 / 60，通过率 100%。
- 完整质量门禁：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py
```

- 结果：`quality_gate=PASS`。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0，0 critical，0 major。
- `ranking_preferences`: 446 / 446，pair accuracy 100%。
- `recovery_imported_preferences`: 462 / 462，pair accuracy 100%。
- `backend_p0_tests`: 22 / 22，0 failed。

下一步：

- 把当前在线天气上下文的耗时纳入质量门禁性能观测；本轮完整门禁中 `score_rule_eval_dataset` 与 `export_plan_review_set` 各约 498 秒，说明大批量评测时需要进一步缓存状态/天气查询或减少候选重复打分。
- 继续把 feedback import 接入同一闭环，让真实用户的“不满意原因”进入 `ranking_preferences / feature_corrections`，而不是继续靠 prompt 或规则补丁。

## 2026-05-24 Feedback 负反馈回流到偏好/特征修正

本轮把用户反馈链路接入推荐数据闭环。此前 `FeedbackService` 只把 `rating / selected_options / free_text` 保存为候选记忆；现在它们会被离线导入为可审计的 pairwise preference 或 feature correction，和 review/recovery 使用同一套 ranker 校验流程。

代码更新：

- `backend/app/rules/poi_feature_store.py`
  - POI 特征纳入 `risk_tags`，避免 `queue_risk / capacity_risk` 只停留在原始 POI 数据里。
  - 新增 `risk_scores.queue_pressure` 和兼容字段 `queue_pressure_risk`。
  - `review_summary` 会标出“排队压力偏高”，用于人工/AI judge 审核。
- `backend/app/rules/ranking_weights.py`
  - 新增 `risk.queue_pressure`，默认权重 `-28.0`。
- `backend/app/services/candidate_retriever.py`
  - 当 `queue_tolerance=low` 或用户意图包含 `low_queue / queue` 时，初始排序会对 `queue_pressure` 做静态降权。
  - 运行时状态仍然由 `status_score` 和 verifier 兜底；静态风险用于更早减少明显容易排队的候选。
- `tools/rule_evaluation/import_feedback_preferences.py`
  - 新增反馈导入脚本。
  - 支持从 `backend/data/feedback.json` 读取真实反馈，从 `plans.json` 找到对应计划节点。
  - `selected_options/free_text` 会映射成结构化 issue：
    - `queue / queue_too_long / 少排队` -> `queue_pressure`
    - `restaurant_not_good / 餐厅不合适` -> `restaurant_fit`
    - `too_rushed / distance / 太赶 / 太远` -> `route_tempo`
    - `child_not_interested / child_bored` -> `activity_interest`
  - 只有在当前 feature store 能识别被拒绝 POI，并能找到 ranker 已支持的更优替代时，才生成 pairwise preference。
  - 如果反馈引用的是旧计划或外部/过期 POI，会进入 `stale_or_external_poi` feature correction，不强行制造偏好对。
- `tools/rule_evaluation/run_recommendation_quality_gate.py`
  - 完整门禁新增两步：
    - `import_feedback_preferences`
    - `validate_feedback_imported_preferences`
  - 新增检查项：
    - `feedback_import_actionable`
    - `feedback_imported_preferences_valid`

当前真实反馈导入结果：

- `feedback_count`: 2
- `negative_signal_count`: 2
- `imported_count`: 0
- `feature_correction_count`: 5
- `skipped_summary`: `{"rejected_poi_not_in_feature_store": 4}`

解释：

- 现有两条 demo feedback 都是真实负反馈信号：
  - `queue` / `下次继续少排队`
  - `restaurant_not_good + queue`
- 但它们引用的计划节点来自早期 mock 数据，相关 POI 不在当前 `poi_features.json` 里。
- 因此本轮没有强行生成 pairwise preference，而是保留为 feature correction：
  - `feedback_signal`: 用户明确表达少排队或餐厅不合适。
  - `stale_or_external_poi`: 反馈引用旧计划 POI，需要做数据版本/特征库存修正。
- 这比硬造训练样本更稳：反馈不会丢，但也不会污染 ranker。

额外验证：

- 用临时当前 POI 夹具验证导入器：`restaurant_not_good` 能成功生成 pairwise preference。
- 示例导入：
  - preferred: `無忧浅草君洋风料理下沙宝龙一号店`
  - rejected: `陳八两面家(杭州郡原蓝湖国际店)`
  - preferred_score: 146.6652
  - rejected_score: -172.1322

最新完整门禁：

- 命令：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py
```

- 结果：`quality_gate=PASS`。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0，0 critical，0 major。
- `ranking_preferences`: 446 / 446，pair accuracy 100%。
- `recovery_imported_preferences`: 462 / 462，pair accuracy 100%。
- `feedback_imported_preferences`: 446 / 446，pair accuracy 100%。
- `backend_p0_tests`: 22 / 22，0 failed。
- `recommendation_ranker_weights`: weight_count 40。

下一步：

- 做一层反馈数据版本治理：当 feedback 引用的计划 POI 已不在当前 feature store 时，尝试按名称/区域/语义标签映射到当前 POI，而不是只能进入 stale correction。
- 进一步优化质量门禁耗时：本轮 `score_rule_eval_dataset` 约 502 秒，`export_plan_review_set` 约 517 秒，需要缓存状态/天气/候选打分，降低大规模评测成本。

## 2026-05-24 Feedback 旧 POI 映射到当前特征库存

本轮继续补上一节的缺口：用户反馈经常引用的是历史计划里的 POI，但当前 `poi_features.json` 可能已经重建，旧 `poi_id` 不再存在。之前这类反馈只能进入 `stale_or_external_poi` 修正队列；现在导入器会先尝试把旧 POI 映射到当前 feature store，能验证的再生成 pairwise preference。

代码更新：

- `tools/rule_evaluation/import_feedback_preferences.py`
  - 新增 `resolve_stale_slot`：
    - 先按角色过滤：restaurant 只映射餐厅，activity 只映射活动/步行/服务，tail 映射轻停留候选。
    - 再按场景过滤：优先保持 `family_parent_child / friend_group / anniversary_emotion` 兼容。
    - 综合标题相似度、语义 token 重叠、display_tags 与当前 semantic_tags 重叠计算映射置信度。
    - 对关键生活语义做领域加权：`咖啡 / 轻食 / 阅读 / 宠物 / 室内 / 避雨`。
  - 新增 `mapped_stale_poi` feature correction：
    - 记录旧 `affected_poi_id`、映射后的 `mapped_poi_id`、`mapping_confidence` 和 `mapping_reason`。
    - 生成 pairwise 时保留 `source_rejected_poi_id` 和 `rejected_mapping_confidence`，方便人工抽检。
  - 低置信或无法找到可用替代时，不强行导入 pairwise，仍保留 `stale_or_external_poi / no_preferred_candidate`。

当前真实反馈变化：

- `feedback_count`: 2
- `negative_signal_count`: 2
- `imported_count`: 1
- `feature_correction_count`: 5
- `output_case_count`: 447
- `skipped_summary`: `{"no_preferred_candidate": 2, "rejected_poi_not_in_feature_store": 1}`

导入的 pairwise：

- 来源：`fb_20260521_3d10e669`
- issue: `restaurant_fit`
- 旧 rejected POI: `poi_restaurant_453`
- 映射后 rejected POI: `poi_gaode_restaurant_019_0d7331`
- rejected 原标题：`金沙天街·B1 层‘雨歇’轻食与咖啡吧`
- preferred: `京桥亭日本料理(华元十六街区店)`
- rejected_mapping_confidence: 0.641
- preferred_score: 141.8026
- rejected_score: 134.3226

仍未导入的反馈：

- `queue_pressure` 相关反馈仍有 2 条 `no_preferred_candidate`。
- 原因是当前餐厅特征库存里大多数候选都有 `queue_risk`，没有足够干净的低排队替代候选。
- 这说明下一步不是硬调 ranker，而是补数据：需要更明确的 `low_queue` 候选、运行时排队采样，或更细的排队风险分桶。

最新完整门禁：

- 命令：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py
```

- 结果：`quality_gate=PASS`。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0。
- `ranking_preferences`: 446 / 446，pair accuracy 100%。
- `recovery_imported_preferences`: 462 / 462，pair accuracy 100%。
- `feedback_imported_preferences`: 447 / 447，pair accuracy 100%。
- `backend_p0_tests`: 22 / 22，0 failed。

下一步：

- 为排队反馈补充真正的低排队候选特征：新增或标注 `low_queue`、按时段生成更细的 `queue_pressure` 分桶，避免所有餐厅都只被粗略标成 `queue_risk`。
- 继续降低质量门禁耗时：本轮 `score_rule_eval_dataset` 约 488 秒，`export_plan_review_set` 约 499 秒。

## 2026-05-24 Queue Pressure 状态采样与反馈偏好落地

本轮解决上一节留下的排队反馈问题：之前 `queue_pressure` 主要来自 `queue_risk` 粗标签，导致当前 304 个餐厅几乎全部被视为高排队风险；用户说“少排队”时，系统很难找到可信的 preferred 候选。现在 `poi_features.json` 会在离线构建时采样 MockAPI 状态，形成更细的排队风险分桶。

代码更新：

- `tools/rule_evaluation/build_poi_features.py`
  - 构建特征时调用 MockAPI 对 restaurant/activity 采样典型时段：
    - `2026-05-24T14:30:00+08:00`
    - `2026-05-24T17:30:00+08:00`
    - `2026-05-24T20:00:00+08:00`
  - 输出 `status_signals`：
    - `queue_minutes_avg`
    - `effective_queue_minutes_avg`
    - `effective_queue_minutes_peak`
    - `availability_ratio`
    - `queue_bucket`
    - `queue_pressure`
- `backend/app/rules/poi_feature_store.py`
  - `build_poi_feature_document` 支持传入 `status_signals`。
  - `build_poi_feature` 会根据 `queue_bucket` 补充：
    - `low_queue`
    - `queue_medium`
    - `long_queue`
    - `limited_capacity`
  - `risk_scores.queue_pressure` 由状态采样结果主导，`queue_risk / capacity_risk` 只作为静态下限，不再让所有餐厅一刀切 high。
- `tools/rule_evaluation/score_rule_eval_dataset.py` 与 `tools/rule_evaluation/export_plan_review_set.py`
  - 批量评测时关闭 MockAPI 工具日志，避免 200 条批量生成过程中高频写 `traces.json` 触发临时文件 replace 竞态。

排队特征分布变化：

- activity:
  - medium: 151
  - high: 45
- restaurant:
  - medium: 51
  - high: 253
- walk_spot:
  - low: 1

这还不是最终理想状态，但已经从“餐厅全 high”变成了可以区分中高排队风险，足以让 queue feedback 形成偏好对。

Feedback 导入变化：

- 修复前：
  - `imported_count`: 1
  - `feature_correction_count`: 5
  - 只有 `restaurant_fit` 能导入 pairwise。
- 修复后：
  - `imported_count`: 3
  - `feature_correction_count`: 5
  - `output_case_count`: 449
  - `feedback_imported_preferences`: 449 / 449，pair accuracy 100%。

新增导入的 queue pairwise：

- `queue_pressure`: `鱼你说酸菜鱼米饭(蓝湖国际店)` 优于旧计划里的 `金沙湖地下连廊·雨歇咖啡角`。
- `queue_pressure`: `杭州龙湖皇冠假日酒店·滟澜全日餐厅` 优于旧计划里的 `金沙天街·B1 层‘雨歇’轻食与咖啡吧`。

仍未完全解决：

- 还有 1 条 `rejected_poi_not_in_feature_store`，来自旧计划 activity `poi_activity_369`。
- 餐厅低排队候选仍偏少，大部分当前餐厅是 medium/high；后续还需要更细的时段、人群、区域维度。

最新完整门禁：

- 命令：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py
```

- 结果：`quality_gate=PASS`。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0。
- `feedback_imported_preferences`: 449 / 449，pair accuracy 100%。
- `backend_p0_tests`: 22 / 22，0 failed。
- `build_poi_features`: 8.491 秒。
- `score_rule_eval_dataset`: 352.471 秒。
- `export_plan_review_set`: 340.223 秒。

下一步：

- 把 queue bucket 从全局三时段采样升级为“计划时间窗相关”的特征或缓存，避免下午低排队和晚饭高峰混在一起。
- 补足低排队餐厅库存：需要在 Mock POI/status 里显式覆盖一些 `low_queue` 正餐/轻食候选，而不是主要靠咖啡/甜品兜底。

## 2026-05-24 Queue Profile 时间窗分桶与 Dinner Anchor 对齐

本轮把上一节的“全局三时段采样”继续落到实际推荐链路：`queue_pressure` 不再只看全局均值，而是可以按计划节点时间读取 afternoon / dinner / evening 对应的排队压力。

代码更新：

- `tools/rule_evaluation/build_poi_features.py`
  - `status_signals` 新增 `queue_profile`：
    - `afternoon`: `2026-05-24T14:30:00+08:00`
    - `dinner`: `2026-05-24T17:30:00+08:00`
    - `evening`: `2026-05-24T20:00:00+08:00`
  - 每个时间窗独立输出 `queue_minutes_avg / effective_queue_minutes_avg / availability_ratio / queue_bucket / queue_pressure`。
- `tools/rule_evaluation/ranking_feature_vectors.py`
  - pairwise 样本如果包含 `queue_segment` 或 `rejected_start_time`，`risk.queue_pressure` 会读取对应时间窗的 `queue_profile`。
  - 没有时间窗时回退到全局 `status_signals.queue_pressure` 或 `risk_scores.queue_pressure`。
- `tools/rule_evaluation/import_feedback_preferences.py`
  - feedback 导入的 queue case 会记录：
    - `rejected_start_time`
    - `queue_segment`
    - `preferred_queue_pressure`
    - `rejected_queue_pressure`
  - 候选排序加入时间窗 queue delta，避免下午低排队和晚饭高峰被混成一个均值。
- `backend/app/services/candidate_retriever.py`
  - runtime 排序在 `queue_tolerance=low` 或显式 `low_queue/queue` 时，按角色推算到达时间读取 `queue_profile`。
  - `dinner_last` 场景的餐厅状态与 queue profile 改为使用和 `PlanGenerator._dinner_anchor` 一致的 17:30 晚饭锚点；之前会按开始后约 90 分钟估算，导致下午状态和真实晚饭状态不一致。

时间窗分布：

- 全局 bucket：
  - activity: medium 151, high 45
  - restaurant: medium 51, high 253
- afternoon:
  - activity: low 18, medium 148, high 30
  - restaurant: medium 157, high 147
- dinner:
  - activity: medium 152, high 44
  - restaurant: medium 65, high 239
- evening:
  - activity: medium 165, high 31
  - restaurant: medium 68, high 236

Feedback 导入结果：

- `feedback_count`: 2
- `negative_signal_count`: 2
- `imported_count`: 3
- `feature_correction_count`: 5
- `output_case_count`: 449
- `skipped_summary`: `{"rejected_poi_not_in_feature_store": 1}`

新增 queue pairwise 保留了时间窗证据：

- dinner: `鱼你说酸菜鱼米饭(蓝湖国际店)` queue 0.585 优于 `金沙湖地下连廊·雨歇咖啡角` queue 0.9856。
- afternoon: `杭州龙湖皇冠假日酒店·滟澜全日餐厅` queue 0.5767 优于 `金沙天街·B1 层‘雨歇’轻食与咖啡吧` queue 0.8467。

原始问题抽查：

- 请求：`这周末想和老婆孩子去游乐园,然后吃一顿自助餐`
- 抽查结果：
  - activity: `爱玩嘉年华(龙湖杭州金沙天街店)`
  - activity: `蕉个朋友DIY手工`
  - restaurant: `七个烧烤自助餐厅(高沙小区店)`
- 结论：
  - 已不再把包子、牛肉汤、咖啡轻食等误当成自助餐。
  - verifier 为 `warning`，原因是当前 Mock 数据里 5 个自助餐在 dinner 时间窗全部是 high queue，其中可用候选也仍超过低排队阈值；这是库存/状态数据问题，不是餐饮语义识别问题。

最新完整门禁：

- 命令：

```bash
PYTHONPATH=backend LIFEPILOT_DEMO_NOW=2026-05-21T13:30:00+08:00 DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 tools/rule_evaluation/run_recommendation_quality_gate.py
```

- 结果：`quality_gate=PASS`。
- `rule_eval`: 200 / 200，通过率 100%。
- `plan_review_auto_quality`: 200 / 200 pass，min_score 100，avg_score 100.0。
- `ranking_preferences`: 446 / 446，pair accuracy 100%。
- `recovery_imported_preferences`: 462 / 462，pair accuracy 100%。
- `feedback_imported_preferences`: 449 / 449，pair accuracy 100%。
- `backend_p0_tests`: 22 / 22，0 failed。
- 耗时：
  - `build_poi_features`: 7.824 秒。
  - `score_rule_eval_dataset`: 338.115 秒。
  - `export_plan_review_set`: 338.89 秒。
  - `backend_p0_tests`: 56.529 秒。

下一步：

- 给自助餐、亲子正餐、轻食正餐补更多低排队/可订桌库存，否则“想吃自助餐 + 少排队”在数据层面只有 high queue 候选。
- 将 `queue_profile` 从固定三点采样扩展成“工作日/周末 + 小时桶 + party_size”的状态表，减少当前三点采样的粒度损失。
