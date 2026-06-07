## 高德 500 POI 候选池与路线生成器

本轮按要求参考了项目文档和现有 `tools/qwen_data_factory` / `tools/gaode_data_factory` 实现，新增高德版 500 条精品 POI 候选池与路线生成能力。没有直接重建或覆盖 `backend/data` 里的 500 条数据，也没有修改 `docs/00_project_vision.md` 到 `docs/08_evaluation_design.md` 原文。

### 参考约束

- `docs/03_schema.md`：`mock_pois.json`、`mock_routes.json` 字段、ID 前缀、`RouteEstimate` 必填字段、`transport_mode` 枚举。
- `docs/04_api_contract.md`：Mock 数据仍使用 `/api/v1` 业务契约，Mock 标识和错误边界不改变。
- `docs/05_agent_workflow.md`：POI、路线、状态必须来自 MockAPI/规则/工具层，不能由 LLM 直接决定可执行状态。
- `docs/06_mock_api_design.md`：POI/路线可以接入真实来源，但状态、库存、订座、票务、失败注入仍必须保持 Mock/测试边界。
- `docs/07_frontend_design.md`：普通用户页不展示底层调试字段；本次新增字段放在 `tools/gaode_data_factory` 本地 viewer 和 sidecar，不进入前端主应用 ViewModel。
- `docs/08_evaluation_design.md`：不新增评测领域契约，不把 `failure_injection`、benchmark 样例伪装成高德真实能力。
- `tools/gaode_data_factory/api_doc.md`：参考了高德周边搜索、POI ID 查询、步行路径、驾车路径、公交/地铁换乘、天气、静态地图等能力。

### 新增/修改内容

- 新增 `tools/gaode_data_factory/generate_lifepilot_dataset.py`。
  - 默认使用高德 `v3/place/around` 周边搜索，不使用关键词枚举。
  - 围绕金沙湖、下沙、高教园区的多个商业/生活中心坐标搜索。
  - type 覆盖餐饮、咖啡甜品、购物商场、休闲娱乐、电影剧场、健身运动、景区公园、书店文化。
  - 机器过滤大学、学院、学校、校区、教学楼、宿舍、公司、产业园、写字楼、汽修、建材、银行、营业厅等噪声。
  - 默认剔除有评分且低于 `--min-rating 4.0` 的 POI；缺评分默认剔除，可用 `--allow-unrated` 放开。
  - 输出 `mock_pois.json` 时保持 LifePilot POI Schema 安全字段，不额外塞入 `gaode_id/source/photos/tel`，避免破坏现有 validator。
  - 图片、电话、高德 id、type/typecode、business_area、原始营业时间、质量分等写入 sidecar：`gaode_poi_enrichment.json`、`gaode_poi_review_candidates.json`。
  - 路线生成默认对入选 POI 的近邻 pair 调用步行、驾车、公交/地铁换乘接口，并映射为 `walk/drive/subway` 三类 `RouteEstimate`。
  - 高德路线 raw、steps/polyline/换乘摘要等写入 `gaode_route_raw_responses.json`；`mock_routes.json` 只保留契约字段，`source` 仍为 `mock_api`。

- 修改 `tools/gaode_data_factory/README.md`。
  - 增加 500 POI 候选池生成命令。
  - 增加 `--skip-routes` 和 `--raw-input` dry run 示例。
  - 记录新增输出文件和 500 候选池生成规则。

- 修改 `tools/gaode_data_factory/viewer.html`。
  - 新增 “500 候选池” tab。
  - 读取 `reports/generate_lifepilot_dataset_report.json`、`output/gaode_poi_review_candidates.json`、`output/gaode_poi_enrichment.json`。
  - 展示目标/入选 POI、review 候选、enrichment 数量、路线数量、类别分布、过滤统计和人工复核 Top 50。

### 默认生成命令

```bash
export AMAP_KEY="你的高德 Web 服务 Key"
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --target-pois 500 \
  --route-neighbors 1 \
  --max-route-pairs 500
```

只生成 POI、不调用路线：

```bash
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --target-pois 500 \
  --skip-routes
```

已有 raw 归档 dry run：

```bash
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --raw-input tools/gaode_data_factory/output/gaode_capability_probe_raw.json \
  --target-pois 20 \
  --output /tmp/lifepilot_gaode_dryrun \
  --skip-routes \
  --allow-unrated
```

### 本地验证结果

当前 shell 没有设置 `AMAP_KEY`，因此本轮没有真实调用高德生成 500 条最终数据和路线矩阵，也没有覆盖 `backend/data`。已用现有 `gaode_capability_probe_raw.json` 做 dry run：

- Raw POI：300
- dry run 目标：20
- 入选 POI：20
- 类别：restaurant 13、activity 7
- 区域：下沙 15、金沙湖 5
- 路线：dry run 使用 `--skip-routes`，未调用高德路线接口

已执行校验：

```bash
python -m py_compile tools/gaode_data_factory/generate_lifepilot_dataset.py
python tools/gaode_data_factory/generate_lifepilot_dataset.py --help
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --raw-input tools/gaode_data_factory/output/gaode_capability_probe_raw.json \
  --target-pois 20 \
  --output /tmp/lifepilot_gaode_dryrun \
  --skip-routes \
  --allow-unrated
node --check /tmp/gaode_viewer_script.js
```

### 输出文件设计

- `output/mock_pois.json`：Schema 安全 POI 数据，保留 `mock_only:true`。
- `output/mock_routes.json`：Schema 安全路线数据，包含 `walk/drive/subway` 三类 `RouteEstimate`。
- `output/gaode_lifepilot_raw.json`：POI 周边搜索 raw 归档，不含 API key。
- `output/gaode_poi_enrichment.json`：POI sidecar，含图片、电话、高德 id、type/typecode、business_area、质量分等。
- `output/gaode_poi_review_candidates.json`：人工筛选核查用候选表。
- `output/gaode_route_raw_responses.json`：路线 raw 归档，不含 API key。
- `reports/generate_lifepilot_dataset_report.json`：生成报告。

### 边界结论

- POI：高可还原，但 LifePilot 契约仍按 Demo 数字孪生 fixture 使用，保留 `mock_only:true`。
- 路线：高可还原，可从高德步行/驾车/公交换乘获取距离、耗时、步骤和 polyline；`mock_routes.json` 只保存契约字段，raw 另存。
- 图片/电话/typecode/open_time：有用，但不进入 `mock_pois.json`，统一放在 enrichment/review sidecar。
- 状态、库存、订座、余票、排队、失败注入、benchmark：本轮不生成，也不应由高德伪装生成。

## backend/data 旧模拟数据清理

用户明确要求不合并旧模拟数据，准备使用高德重新生成，因此本次清理 active 的 `backend/data` fixture 文件。处理方式是保留文件和顶层 JSON 结构，清空条目，避免后端读取文件时因为缺文件或 JSON 非法直接异常。

已清空：

- `backend/data/mock_pois.json`：`pois=[]`
- `backend/data/mock_routes.json`：`routes=[]`
- `backend/data/mock_status.json`：`statuses={}`
- `backend/data/mock_inventory.json`：`restaurant_slots=[]`、`activity_slots=[]`
- `backend/data/mock_social_signals.json`：`signals=[]`
- `backend/data/mock_failure_scenarios.json`：`scenarios=[]`
- `backend/data/benchmark_samples.json`：`samples=[]`

未清理运行态数据：

- `plans.json`
- `traces.json`
- `executions.json`
- `feedback.json`
- `consensus.json`
- `idempotency.json`
- `mock_idempotency_store.json`

说明：

- 当前 shell 仍未设置 `AMAP_KEY`，所以没有在本轮直接调用高德重建 `backend/data/mock_pois.json` 和 `backend/data/mock_routes.json`。
- 清空后 `scripts/validate_mock_data.py` 按旧 P0 覆盖规则会失败，这是预期状态；等高德 POI/路线生成并补齐必要 Mock 状态后再跑完整校验。
- 后续直接写入后端数据目录的命令：

```bash
export AMAP_KEY="你的高德 Web 服务 Key"
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --target-pois 500 \
  --output backend/data \
  --route-neighbors 1 \
  --max-route-pairs 500
```

## tqdm 进度条补充

按用户要求，`tools/gaode_data_factory/generate_lifepilot_dataset.py` 已加入可选 `tqdm` 进度条。覆盖阶段：

- `gaode_poi_around`：高德周边搜索请求进度。
- `load_raw_archive`：从已有 raw 归档加载响应进度。
- `curate_pois`：POI 规则过滤和转换进度。
- `route_pairs`：近邻路线 pair 构建进度。
- `gaode_routes`：步行/驾车/公交或地铁换乘路线请求进度。

实现为软依赖：安装了 `tqdm` 就显示进度条，未安装时自动退化为普通运行，不影响脚本执行。

## Mock状态引擎改造

按审计结论，将后端从依赖静态状态JSON升级为可复现Mock状态引擎，保留`MockAPIService`作为统一入口。

代码变更：

- 新增`backend/app/services/mock_state_engine.py`：
  - `MockClock`：统一读取`LIFEPILOT_DEMO_NOW`，生成状态更新时间和过期窗口。
  - `DeterministicSeedService`：读取`LIFEPILOT_DEMO_SEED`，用POI、日期、时段、人数、场景生成稳定hash。
  - `WeatherMockEngine`：缺少天气fixture时按季节、日期hash和小时段生成天气、降雨概率、温度、户外风险。
  - `StatusMockEngine`：缺少状态fixture时按营业时间、时段、评分、风险标签生成人流、排队、营业和TTL。
  - `InventoryMockEngine`：缺少库存fixture时即时生成餐厅slot和活动slot，不再要求全量写入`mock_inventory.json`。
  - `FailureMockEngine`：提供低概率但确定性的失败判定，避免运行时随机漂移。
  - `SocialSignalMockEngine`：缺少口碑fixture时基于POI rating、price、tags、risk_tags生成结构化Mock摘要。
- 修改`backend/app/services/mock_api_service.py`：
  - `mock_status.json`、`mock_inventory.json`、`mock_weather.json`、`mock_social_signals.json`均改为override优先。
  - `poi_status()`、`restaurant_status()`缺状态fixture时不再返回`MOCK_STATUS_MISSING`，改由状态引擎生成。
  - `weather()`仅在区域和时间范围匹配时使用`mock_weather.json`，否则由天气引擎生成。
  - `social_signal()`缺fixture时不再404阻断，返回`is_mock=true/source_type=mock_social_signal`的生成摘要。
  - 执行预约活动时使用`booking_time`参与状态生成，保证同一目标日期/时段可复现。
  - 执行窗口过期判断改用`MockClock`，避免评委模式固定`LIFEPILOT_DEMO_NOW`时被真实系统时间误判过期。
- 修改`tests/test_mock_api.py`：
  - 测试不再绑定旧`poi_restaurant_001/poi_activity_003`，改从当前高德POI和路线fixture动态选取。
  - 增加固定`LIFEPILOT_DEMO_NOW`和`LIFEPILOT_DEMO_SEED`的可复现断言。
  - 失败剧本在测试临时目录内写入，不要求active `mock_failure_scenarios.json`预置全量数据。
- 修改`scripts/validate_mock_data.py`：
  - 不再强制每个POI都有静态`mock_status`，也不要求active failure fixture预置所有剧本。
  - 新增状态引擎spot check，验证餐厅状态、活动状态、天气换日期变化和口碑Mock标识。

文档追加：

- `docs/06_mock_api_design.md`追加“6.5 可复现Mock状态引擎补充”。
- `docs/08_evaluation_design.md`追加“6.5 可复现Mock状态引擎评测补充”。

验证记录：

- `PYTHONPATH=backend python -m py_compile backend/app/services/mock_state_engine.py backend/app/services/mock_api_service.py tests/test_mock_api.py scripts/validate_mock_data.py` 通过。
- `PYTHONPATH=backend python scripts/validate_mock_data.py` 通过。
- `PYTHONPATH=backend python scripts/contract_scan.py` 通过。
- 使用`fastapi.testclient.TestClient`手动验证POI状态、餐厅状态、未知区域天气、口碑Mock、失败剧本、活动预约和同输入确定性均返回预期。
- `python -m pytest ...`在当前全局Python 3.13环境启动阶段发生pytest capture段错误，尚未进入项目代码；`backend/.venv`未安装pytest，因此未完成标准pytest运行。

## DeepSeek接入与模型接口设置页

按要求将后端受控LLM调用从本地Qwen默认切换为DeepSeek，并在前端新增模型接口设置页。

代码变更：

- 新增`backend/app/services/llm_client.py`：
  - 默认Provider为`deepseek`。
  - DeepSeek默认`base_url=https://api.deepseek.com`，默认模型`deepseek-v4-flash`。
  - 使用OpenAI-compatible `/chat/completions`，非流式，`response_format={"type":"json_object"}`。
  - DeepSeek默认关闭思考模式，避免普通Trace或业务页涉及推理链。
  - 保留`qwen` Provider配置，作为后续切换入口。
  - 访问凭证只保存在运行时配置中，响应只返回`credential_configured`和`credential_mask`。
- 保留`backend/app/services/qwen_client.py`兼容导出，避免旧引用断裂。
- 修改`backend/app/services/container.py`，IntentParser和PlanGenerator改用`LLMClient`。
- 修改`backend/app/services/intent_parser.py`、`backend/app/services/plan_generator.py`，日志模块名从Qwen适配改为通用`LLM*Adapter`。
- 新增`backend/app/api/v1/settings.py`：
  - `GET /api/v1/settings/llm`
  - `PATCH /api/v1/settings/llm`
- 修改`backend/app/main.py`挂载设置Router。
- 修改`backend/app/schemas/requests.py`新增`LLMSettingsPatch`。
- 新增`frontend/app/settings/page.tsx`，提供DeepSeek/Qwen切换、Base URL、Model、访问凭证、temperature、max tokens、timeout、retry、思考模式和启用状态配置。
- 修改`frontend/components/common/AppShell.tsx`，在页面头部加入设置入口。
- 修改`frontend/lib/api.ts`和`frontend/types/schema.ts`新增设置接口类型。
- 修改`frontend/app/globals.css`新增设置页表单样式。
- 修改`tests/test_p0_plan_create.py`补充设置接口脱敏断言。
- 修改`scripts/run_backend_p0_tests.py`和相关测试fixture，测试运行默认禁用DeepSeek真实调用。
- 修改`scripts/contract_scan.py`，将新的受控LLM客户端加入敏感字段扫描白名单；运行时代码仍不允许普通页面暴露底层字段。

文档追加：

- `docs/04_api_contract.md`追加“25.1 2026-05-23追加：受控LLM接口设置契约”。
- `docs/07_frontend_design.md`追加“28. 2026-05-23追加：模型接口设置页”。

验证记录：

- 参考DeepSeek官方文档确认OpenAI-compatible `base_url=https://api.deepseek.com`、`/chat/completions`、Bearer认证、`deepseek-v4-flash/deepseek-v4-pro`模型和JSON Output的`response_format={"type":"json_object"}`规则。
- `PYTHONPATH=backend python -m py_compile backend/app/services/llm_client.py backend/app/services/qwen_client.py backend/app/services/container.py backend/app/services/intent_parser.py backend/app/services/plan_generator.py backend/app/api/v1/settings.py backend/app/main.py backend/app/schemas/requests.py`通过。
- `cd frontend && npx tsc --noEmit`通过。
- `cd frontend && npx next lint`通过，仍有既有页面`useEffect`依赖warning。
- `PYTHONPATH=backend python scripts/contract_scan.py`通过。
- `PYTHONPATH=backend python scripts/run_backend_p0_tests.py`通过。
- 使用`fastapi.testclient.TestClient`手动验证`GET/PATCH /api/v1/settings/llm`不返回明文凭证。
- 启动`uvicorn`和`next dev`后，用Playwright打开`http://127.0.0.1:3000/settings`，确认设置页可渲染、显示DeepSeek、访问凭证输入存在，页面不包含明文凭证。
- 标准`python -m pytest tests/test_p0_plan_create.py tests/test_verifier_service.py -q`在当前全局Python环境仍以code -1无输出退出，延续此前pytest环境问题；已用项目P0 runner和手动TestClient覆盖本次改动。

## 2026-05-23 受控标签归一化、Goal-aware POI推荐与模拟初始状态

本次目标：

- 避免三种预设场景都落到少数偶然可连通POI，例如“大疆体验店+蜜雪冰城”。
- 在路线矩阵缺失时，由后端Mock路线引擎按POI经纬度生成可解释转场，不让计划页出现“暂无转场明细”。
- 首页增加模拟初始状态，支持设定当前区域、当前位置、当前时间和可规划时长。
- 设计并实现“开放输入 → 受控标签 → 推荐画像 → POI组合打分”的标签模式，减少LLM标签发散。

代码变更：

- 新增`backend/app/core/recommendation_taxonomy.py`：
  - 定义`CONTROLLED_TAGS`、别名归一化、区域识别和`normalize_intent_profile`。
  - 将开放表达映射到`route_simple`、`low_key`、`date_friendly`、`low_queue`、`quiet_dining`等受控标签。
- 修改`backend/app/services/intent_parser.py`：
  - LLM标签先进入受控归一化，不再把散乱英文标签直接合并到用户可见`intent_tags`。
- 修改`backend/app/services/constraint_extractor.py`：
  - 读取`user_location`、`preferred_start_time`、`preferred_end_time`。
  - 在`constraints`中写入`preferred_area`、`planning_start_time`、`planning_end_time`和`recommendation_profile`。
- 修改`backend/app/services/candidate_retriever.py`：
  - 从旧的首个可连通组合，改为活动/餐厅/收尾节点组合打分。
  - 打分维度包含意图匹配、Mock状态、路线距离、预算、区域、评分和POI质量惩罚。
  - 纪念日场景对纯零售/数码/棋牌/KTV/奶茶类POI降权，优先自然、低调、路线简单的组合。
- 修改`backend/app/services/mock_api_service.py`：
  - `estimate_route`在fixture缺失时按经纬度生成`route_engine_` Mock路线。
  - 不支持的交通模式仍返回`ROUTE_DELAY`。
- 修改`backend/app/services/verifier_service.py`：
  - Verifier接受`route_engine_` Mock路线。
  - 活动/服务节点状态按计划节点`start_time`查询，而不是按系统当前时间误判营业。
  - 对已可订座餐厅的长排队风险降级为warning，保留PlanB但不直接阻断。
- 修改`frontend/app/page.tsx`：
  - 首页新增“模拟初始状态”模块，设置区域、位置、当前时间和规划时长。
- 修改`frontend/lib/api.ts`、`frontend/types/schema.ts`：
  - 创建计划请求支持初始状态字段；`RouteEstimate`同步`distance_km`。
- 修改`frontend/components/plan/PlanCards.tsx`：
  - 路线卡展示起终点、模拟路况、交通方式、距离和时长。

文档追加：

- `docs/05_agent_workflow.md`追加“23. 2026-05-23追加：受控标签归一化与Goal-aware推荐编排”。
- `docs/06_mock_api_design.md`追加“28. 2026-05-23追加：Mock路线兜底引擎”。
- `docs/07_frontend_design.md`追加“29. 2026-05-23追加：首页模拟初始状态”。

验证记录：

- `python3 -m compileall backend/app/core/recommendation_taxonomy.py backend/app/services/intent_parser.py backend/app/services/constraint_extractor.py backend/app/services/candidate_retriever.py backend/app/services/mock_api_service.py backend/app/services/verifier_service.py`通过。
- `cd frontend && npm run lint`通过，仍有既有页面`useEffect`依赖warning。
- `cd frontend && npm run build`通过，仍有同样既有warning。
- 使用`fastapi.testclient.TestClient`手动创建纪念日计划，返回完整`PlanContract`，状态为`executable/warning`，时间线包含后端Mock路线转场，不再落到“大疆体验店+蜜雪冰城”。
- 标准`pytest`在当前环境仍以code -1无输出退出；本轮继续用`compileall`、前端lint/build和手动TestClient覆盖。

补充验证与运行状态：

- 本地后端`127.0.0.1:8000`已有进程占用，本轮验证改用`http://127.0.0.1:8010`启动FastAPI。
- 本地前端`127.0.0.1:3000`已有进程占用，本轮验证改用`http://127.0.0.1:3010`启动Next.js。
- 使用Playwright打开`http://127.0.0.1:3010`验证：
  - 首页可见“模拟初始状态”模块。
  - 点击纪念日预设并生成计划后，计划页不包含`DJI`、`大疆`或`蜜雪`。
  - 计划页包含`路线与转场`，展示起终点、步行约2分钟、距离约0.0km等后端Mock路线信息。
  - 普通计划页仍只展示Mock/模拟提示、Verifier摘要、风险和PlanB，不展示`failure_injection`、Prompt、API Key或推理链。
- `PYTHONPATH=backend python3 scripts/contract_scan.py`通过。
- `bash lifepilot-dev/scripts/scan_contract_redlines.sh .`未通过，命中来自`.next`构建产物、`node_modules`、历史报告和文档反例中的既有示例文案；运行时代码使用的`contract_scan.py`已通过。

## 2026-05-23 类脑POI推荐引擎二次优化与Benchmark问题复盘

本次针对`benchmark.md`中的两个失败案例继续优化POI推荐引擎，未修改`docs/00_project_vision.md`到`docs/08_evaluation_design.md`原文。

问题复盘：

- Q1“有点不开心，想找地方喝点酒”：旧链路虽然识别出`alcohol`，但POI数据里的酒吧/酒馆没有标准`alcohol`标签，按标签召回失败后退回通用低压力节点，最终出现“荟盈棋牌 + 瑞幸咖啡”。
- Q2“纪念日约会，不夸张，预算适中，路线别折腾”：旧链路把当前位置区域当成强区域约束，并且路线距离分过强，导致“福雷德广场 -> 米村拌饭 -> 福雷德广场”这种近但低质、重复、缺少氛围的组合。
- Prompt问题不是唯一原因。更关键的是“用户硬偏好 -> 受控画像 -> POI语义特征 -> 组合排序”之间断层：LLM/prompt可以提取意图，但检索层如果看不懂POI名称里的“酒馆、民谣、精酿、影院、湖畔、料理”，仍会选错。

代码变更：

- 修改`backend/app/core/intent_rules.py`和`backend/app/core/recommendation_taxonomy.py`：
  - 补充“不开心、难过、喝点酒、喝一杯”等情绪/小酌触发词。
  - 保证喝酒类输入进入`alcohol/light_drink`画像。
- 修改`backend/app/services/intent_parser.py`：
  - 优化受控LLM意图prompt，要求显式保留硬偏好：喝酒必须包含`alcohol/light_drink`，音乐必须包含`music`，纪念日必须包含`date_friendly/low_key/quiet_dining/route_simple`。
  - 合并标签时改成优先保留硬偏好和关系/氛围标签，避免按字母截断把关键标签挤掉。
- 修改`backend/app/services/constraint_extractor.py`：
  - 不再把`user_location.area`默认写成`preferred_area`强约束；只有用户文本明确提到“金沙湖/下沙/高教园区”时才强约束区域。
  - 喝酒/小酌场景默认预算从普通散心的80元提高到120元，避免把酒馆排除后退回咖啡/低价棋牌。
- 修改`backend/app/services/candidate_retriever.py`：
  - 新增POI名称语义补全：从“酒吧/酒馆/精酿/Lounge/Bar/民谣/音乐/影院/剧院/湖畔/料理/茶空间”等名称推断`alcohol/music/theater/proper_dining/lounge`等排序特征。
  - 喝酒场景允许把酒馆类`activity`作为饮酒主节点候选，不再只从`restaurant`类别硬找`alcohol`标签。
  - 纪念日场景加大对棋牌、KTV、剧本杀、电竞、泛商场/美食街、快餐/连锁简餐、奶茶等节点的惩罚。
  - 降低路线距离在总分里的权重，避免“距离最近”压过“体验合适”。
  - 收尾节点排除已选POI，避免同一广场/同一节点重复出现。
- 修改`backend/app/services/plan_generator.py`：
  - 喝酒优先时改为先生成小酌节点；没有音乐诉求时不再文案声称“轻音乐空间”。
  - fallback散心餐饮文案不再默认写“轻食或咖啡”。
- 修改`tests/test_p0_plan_create.py`：
  - 增加两个benchmark回归断言：Q1首个POI必须体现小酌/酒馆且不能回到棋牌/咖啡；Q2不能包含米村拌饭、福雷德广场重复和典型快餐/棋牌退化。

验证记录：

- `PYTHONPATH=backend python3 -m py_compile backend/app/core/intent_rules.py backend/app/core/recommendation_taxonomy.py backend/app/services/intent_parser.py backend/app/services/constraint_extractor.py backend/app/services/candidate_retriever.py backend/app/services/plan_generator.py tests/test_p0_plan_create.py`通过。
- `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/run_backend_p0_tests.py`通过。
- `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/contract_scan.py`通过。
- `cd frontend && npx tsc --noEmit`通过。
- `cd frontend && npx next lint`通过，仍为既有`useEffect`依赖warning。
- 标准`PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 -m pytest tests/test_p0_plan_create.py -q`在当前Python环境仍以code -1无输出退出，延续此前pytest环境问题；本轮用项目P0 runner和手动TestClient覆盖。
- 使用`fastapi.testclient.TestClient`手动验证两个benchmark：
  - Q1返回酒馆/小酌主节点，不再以棋牌或咖啡作为首站。
  - Q2不再出现米村拌饭、福雷德广场重复和典型快餐/棋牌退化。
- 按Browser技能说明尝试使用浏览器能力；本会话没有暴露专用in-app browser控制工具，因此使用Playwright/Chromium做等价浏览器验证。
- 启动最新后端`18768`和前端`18769`后，用Playwright完成两条benchmark页面级验证并保存截图：
  - `reports/screenshots/benchmark-q1-browser.png`
  - `reports/screenshots/benchmark-q2-browser.png`
- 浏览器验证断言通过：Q1页面展示酒馆/可小酌信息且不含旧的“荟盈棋牌”；Q2页面不含“米村拌饭”和“福雷德广场”。

## 2026-05-23 类脑推荐画像三场景核心优化

本次目标来自三条产品体验问题：

- “不开心，想喝点酒，晚上十点前到家”：不能退化到棋牌/咖啡，必须理解低压力小酌和截止时间。
- “周末和女朋友做手工，顺便漂亮饭”：不能推荐萨莉亚、米村、快餐或纯饮品，要有约会氛围、参与感和品质正餐。
- “姐姐来下沙找我玩”：不能机械堆地点，要体现招待、代表性、好聊天、路线别折腾。

实现思路：

- 将推荐从“标签命中”升级为类脑画像：
  - `need_state`：情绪小酌、约会陪伴、家人来访。
  - `scene_frame`：小酌收住、手作约会、下沙招待。
  - `preference_axes`：人数、关系、区域、预算、品质、动线、排队。
  - `poi_semantics`：从POI名称补全酒馆、精酿、手作、陶艺、漂亮饭、招待友好、低端连锁、低匹配活动等语义。
  - `chain_scoring`：活动/餐厅/收尾节点组合评分，最后仍交给Verifier。
- 收束LLM边界：LLM仍只做意图和文案辅助；POI状态、路线、可订、营业、余位仍来自MockAPI/规则/Verifier。
- 增加评分缓存：单POI状态与语义评分在组合排序中复用，避免500 POI候选池上重复状态查询。

代码变更：

- 修改`backend/app/core/recommendation_taxonomy.py`：
  - 增加`city_light_explore`受控场景标签。
  - 增加`hands_on/craft/beautiful_dining/quality_dining/ambience_dining/host_guest/visiting_family/showcase_local`等受控标签。
  - 将“女朋友、手工、漂亮饭、姐姐、来下沙”等开放表达映射到类脑推荐画像。
- 修改`backend/app/services/intent_parser.py`：
  - 将“女朋友/约会”映射到现有`anniversary_emotion`约会情绪场景。
  - 将“姐姐/家人来下沙找我玩”映射到`city_light_explore`。
  - 无LLM时生成更贴近手作约会和家人来访的目标摘要。
- 修改`backend/app/services/constraint_extractor.py`：
  - 识别女朋友/姐姐为2人同行。
  - 小酌预算默认提升，避免酒馆被预算过早排除。
  - 漂亮饭默认预算提升，避免约会正餐退化到低价连锁。
  - 家人来访不强加预算上限，避免招待场景被压成饮品/快餐。
- 修改`backend/app/services/candidate_retriever.py`：
  - 对POI名称做语义补全：酒馆/精酿/民谣、DIY/手作/陶艺、湖畔/料理/茶空间/酒店餐厅、低端连锁、棋牌/KTV/电竞/健身等。
  - 小酌场景餐厅位必须使用`restaurant`类酒馆，活动位可使用第二个酒馆/音乐空间。
  - 手作约会强推参与型活动，漂亮饭场景惩罚萨莉亚、米村、达美乐、奶茶、纯咖啡等退化节点。
  - 家人来访惩罚棋牌/KTV/电竞/健身/低端快餐饮品，优先下沙/金沙湖代表性、好聊天和正餐。
  - 组合评分使用缓存，避免重复调用状态引擎。
- 修改`backend/app/services/plan_generator.py`：
  - 手作约会节点文案强调参与感和可带走的小记忆。
  - 漂亮饭文案明确“有氛围和品质感的正餐，不用低价连锁凑数”。
  - 家人来访文案强调招待、聊天、代表性和不折腾。
  - 收尾节点若为activity，不再错误显示为service。
- 修改`frontend/components/plan/PlanCards.tsx`、`frontend/lib/view-models.ts`：
  - 计划页新增“类脑推荐优先级”中文投影。
  - 增加手作体验、漂亮饭、品质正餐、招待友好、下沙代表性等中文标签。
- 修改`tests/test_p0_plan_create.py`和`scripts/run_backend_p0_tests.py`：
  - 增加三条类脑推荐回归断言。
  - P0 runner覆盖小酌、手作漂亮饭、姐姐来访三条体验样例。

文档追加：

- `docs/05_agent_workflow.md`追加“24. 2026-05-23追加：类脑推荐画像与POI语义建模”。
- `docs/07_frontend_design.md`追加“30. 2026-05-23追加：类脑推荐优先级展示”。
- `docs/08_evaluation_design.md`追加“26. 2026-05-23追加：类脑POI推荐体验回归”。

验证记录：

- `PYTHONPATH=backend python3 -m py_compile backend/app/core/recommendation_taxonomy.py backend/app/services/intent_parser.py backend/app/services/constraint_extractor.py backend/app/services/candidate_retriever.py backend/app/services/plan_generator.py tests/test_p0_plan_create.py`通过。
- `cd frontend && npx tsc --noEmit`通过。
- `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/run_backend_p0_tests.py`通过，新增三条类脑推荐样例均PASS。
- 标准`PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 -m pytest tests/test_p0_plan_create.py -q`在当前全局Python 3.13环境仍以code -1无输出退出，延续此前pytest环境问题；本轮以P0 runner、py_compile和手动TestClient覆盖。

收尾修正：

- 漂亮饭场景不再允许“只有湖畔位置但缺少品质/氛围/正餐语义”的普通餐馆通过硬门槛；湖景类餐厅需要客单价和语义共同支撑，避免把商圈普通餐馆包装成约会正餐。
- 约会和家人来访的饭后收尾节点排除第二家完整正餐餐厅，只保留咖啡、甜品、散步点或轻量活动，避免出现“正餐后又安排正餐”的机械组合。
- 手动TestClient复核：
  - 小酌样例返回酒吧/精酿优先链路。
  - 手作漂亮饭样例返回“手工 + Modern湖畔餐厅 + 饭后咖啡/公园”链路，不再出现萨莉亚/米村/低价饮品。
  - 姐姐来访样例识别为`city_light_explore`、2人、下沙招待场景，并排除棋牌/KTV/电竞/健身/低端快餐饮品。

## 2026-05-23 显式餐饮锚点与亲子安全闸门二次优化

本轮针对用户新增两条真实测试失败用例：

- 亲子下午几小时、孩子5岁、不排长队、晚饭清淡：旧结果会把电竞/棋牌/泛商场节点混入亲子链路，晚饭也可能被手工坊、茶饮或重口味餐厅替代。
- 女朋友下午放松、晚上想吃火锅：旧结果能识别约会氛围，但没有把“火锅”建成硬约束，最终可能给咖啡、茶空间或普通餐厅。

问题判断：

- 不是单纯因为路线边`neighbor=1`。当前路线缺边时已有坐标估算兜底，真正缺口在“显式餐饮诉求”和“亲子安全”没有进入硬约束。
- POI种类已经有真实高德火锅、手作、亲子游乐、轻餐等候选；问题是类脑画像没有把这些候选的语义和用户关系/时段绑定起来。
- 需要让LLM智能体现在“开放表达→受控画像→硬约束→组合编排”上，而不是让LLM直接编造地点或状态。

代码变更：

- 修改`backend/app/core/recommendation_taxonomy.py`：
  - 新增受控标签`hotpot/dinner/light_dinner/kid_safe/spicy_heavy`。
  - 将“火锅、晚饭、晚上吃、清淡、不排长队”等开放表达映射到受控画像。
- 修改`backend/app/services/intent_parser.py`：
  - 受控LLM提示中要求保留火锅、晚饭、清淡等硬偏好。
  - 规则标签合并时优先保留`hotpot/dinner/light_meal/low_queue`。
- 修改`backend/app/services/constraint_extractor.py`：
  - “下午+晚饭/晚上吃”默认规划窗口改为15:00到20:30/21:30。
  - 清淡诉求进入`dietary_preference`和`must_have`。
  - 火锅诉求进入`must_have=hotpot,dinner`。
  - 亲子场景追加`low_queue/kid_safe`和成人高刺激节点避让。
- 修改`backend/app/services/candidate_retriever.py`：
  - 从POI名称补全火锅、清淡餐、重口味、亲子安全、咖啡甜品等语义。
  - 用户明说火锅时，餐厅候选必须是火锅语义，不再允许茶空间/咖啡/普通正餐替代。
  - 用户明说清淡且未要求火锅时，火锅、烧烤、麻辣、干锅等重口味晚饭被硬排除。
  - 亲子活动增加硬闸门：电竞、网咖、棋牌、KTV、台球、健身、酒吧等不再只是低分，而是不可作为核心/收尾节点。
  - 泛商场/美食街不能仅靠近距离成为亲子活动，必须有亲子/手作/儿童可参与语义。
  - 新增`dinner_last`组合顺序：下午活动 → 轻休息/收尾 → 晚饭餐厅。
- 修改`backend/app/services/plan_generator.py`：
  - 支持`dinner_last`时间线生成，晚饭餐厅锚定到17:30左右。
  - 亲子文案强调孩子参与、低强度和低排队；清淡晚饭文案明确避开重口味。
  - 火锅文案明确“按你们明说的火锅来选”。
- 修改`tests/test_p0_plan_create.py`和`scripts/run_backend_p0_tests.py`：
  - 新增亲子清淡晚饭回归断言。
  - 新增情侣晚饭火锅回归断言。

文档追加：

- `docs/05_agent_workflow.md`追加“25. 2026-05-23追加：显式餐饮锚点与亲子安全闸门”。
- `docs/08_evaluation_design.md`追加“27. 2026-05-23追加：显式餐饮与亲子安全体验回归”。

当前手动复核效果：

- 亲子清淡晚饭样例输出为“小豆豆DIY手作 → DEDE CANTEEN咖啡食堂 → 兰溪手擀面”，晚饭在17:30后，未出现电竞/棋牌/KTV/健身/火锅/烧烤/麻辣。
- 情侣火锅样例输出为“第一回合(杭州金沙印象城) → 星巴克臻选(金沙印象城店) → 乐炽炽火锅鸡/梅溪徐记鲜牛肉火锅等火锅店”，火锅为最后餐厅节点，未再被咖啡或茶空间替代。

## 2026-05-23 类脑策略层解耦、训练故事与烤肉锚点修复

本轮回应“不要只局限在几个示例”的问题：把散落在检索器里的类脑推荐逻辑抽成独立内部服务，并补齐“晚上想吃烤肉/烧烤”的显式餐饮锚点。

机制设计：

- 新增`BrainRecommendationEngine`作为内部类脑评分层。
  - 感知皮层：从POI名称、类别、标签和地址补全语义。
  - 前额叶：消费`UserGoal.intent_tags`和`ConstraintSet.recommendation_profile`。
  - 基底节：执行硬门控，例如显式餐饮锚点、亲子安全。
  - 边缘系统：按约会、亲子、家人来访、一个人散心等关系目标调制排序。
  - 海马体：保留路线、区域、时间窗口等时空上下文。
  - 多巴胺奖励：汇总意图匹配、角色槽位、评分先验和链路质量。
- 新增`backend/data/brain_policy.json`，把可维护策略从代码中拆出来。
  - 可维护`lexicon`：如`bbq/grill/hotpot/hands_on/low_fit_activity`。
  - 可维护`explicit_dining_anchors`：如火锅、烤肉、烧烤。
  - 后续可继续扩展场景画像和角色槽位偏好，不需要改变公开API。
- `CandidateRetriever`接入类脑层：
  - 单POI打分调用`score_item()`。
  - 组合链路调用`chain_score()`。
  - 显式餐饮锚点不再靠软排序，餐厅槽位必须命中对应语义。
- 补齐烤肉/烧烤泛化：
  - `IntentParser`保留`bbq/grill/dinner`。
  - `ConstraintExtractor.must_have`追加`bbq/grill/dinner`。
  - `CandidateRetriever`从“烤肉、烧烤、烧肉、炭烤、烤串、烤吧、自助烤肉、日式烧肉、韩式烤肉”等名称补全语义。
  - `PlanGenerator`在约会场景中生成“晚饭按你们明说的烤肉来选”的节点说明。

训练故事：

- P0不依赖训练，规则版类脑引擎必须可独立运行。
- P1/P2可以在双卡5090服务器训练本地reranker或reward model。
- 训练输入不使用固定POI ID作为主特征，而使用用户目标、关系场景、POI文本、类别、价格、评分、区域、路线、Mock状态等泛化特征。
- 模型只输出排序分或偏好分，不输出PlanContract字段，不确认真实余位/路线/天气/执行成功。
- `brain_policy.json`硬门控和Verifier始终在模型之后兜底，保证可维护、可回滚和可审计。

代码变更：

- 新增`backend/app/services/brain_recommendation_engine.py`。
- 新增`backend/data/brain_policy.json`。
- 修改`backend/app/services/container.py`注入类脑引擎。
- 修改`backend/app/core/recommendation_taxonomy.py`新增`bbq/grill`受控标签和开放表达映射。
- 修改`backend/app/services/intent_parser.py`、`constraint_extractor.py`、`candidate_retriever.py`、`plan_generator.py`，接入烤肉锚点和类脑评分。
- 修改`frontend/lib/view-models.ts`，增加`bbq/grill/hotpot/light_meal/light_dinner`中文投影。
- 修改`tests/test_p0_plan_create.py`和`scripts/run_backend_p0_tests.py`，新增情侣烤肉晚饭回归断言。

文档追加：

- `docs/02_system_architecture.md`追加“22. 2026-05-23追加：类脑推荐引擎与可训练重排层”。
- `docs/05_agent_workflow.md`追加“28. 2026-05-23追加：类脑策略层解耦与烤肉餐饮锚点”。
- `docs/08_evaluation_design.md`追加“28. 2026-05-23追加：类脑策略层与烤肉锚点回归”。

验证记录：

- `PYTHONPATH=backend python3 -m py_compile backend/app/services/brain_recommendation_engine.py backend/app/services/container.py backend/app/core/recommendation_taxonomy.py backend/app/services/intent_parser.py backend/app/services/constraint_extractor.py backend/app/services/candidate_retriever.py backend/app/services/plan_generator.py tests/test_p0_plan_create.py scripts/run_backend_p0_tests.py`通过。
- `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/run_backend_p0_tests.py`通过，新增`test_brain_date_bbq` PASS。
- `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/contract_scan.py`通过。
- 手动TestClient复核“周末想和女朋友出去放松一下,下午活动你来安排,但晚上我们想去吃烤肉”：
  - `intent_tags`包含`bbq/grill/dinner/date_friendly`。
  - `must_have`包含`bbq/grill/dinner`。
  - 最后餐厅节点为“牛表妹烤肉(杭州旗舰店)”，`display_tags`含`bbq/grill/proper_dining`。

## 2026-05-23 POI语义对齐层与日料泛化修复

本轮回应“是不是可以从POI数据上做文章”：把用户一句话和开放POI池之间补成一层可维护的语义对齐机制。目标不是继续堆示例，而是让“日料/寿司/居酒屋”等表达能泛化到未来新增POI。

机制设计：

- POI不再只是静态Mock列表，而是语义资产：
  - 从名称、类别、标签、地址、价格、评分和区域中抽取可对齐语义。
  - 当前先用`brain_policy.json`和taxonomy维护词典，P1可接embedding/reranker。
- 新增受控标签：
  - `cuisine_japanese`
  - `sushi`
  - `izakaya`
- 新增触发词：
  - 日料、日式、日本料理、寿司、刺身、居酒屋、烧鸟、鮨、和风、会席、日式咖喱、回转寿司。
- 明确硬锚点：
  - 用户明说日料/日本料理/寿司/居酒屋时，餐厅槽位必须命中`cuisine_japanese/sushi/izakaya`之一。
  - 普通`quality_dining/ambience_dining`不能替代显式餐饮锚点。
  - 茶空间、咖啡、M Stand、瑞幸、库迪不得作为日料请求的餐厅答案。
- 约会场景质量调制：
  - 日本料理、鮨、会席、烧鸟等更像正餐/约会的POI加权。
  - 日式咖喱、蛋包饭、回转寿司等快餐式POI降级为低优先级备选。
- 时间窗口修复：
  - 用户只说“想和女朋友吃日料/吃火锅/吃烤肉”但没写“下午”时，默认进入晚餐窗口，而不是从当前时间硬排到18:00前。

代码变更：

- 修改`backend/app/core/recommendation_taxonomy.py`：
  - 新增`cuisine_japanese/sushi/izakaya`受控标签、开放表达映射和消费轴归类。
- 修改`backend/app/services/intent_parser.py`：
  - LLM受控提示要求保留日料硬偏好。
  - 规则标签合并优先保留`cuisine_japanese/sushi/izakaya/dinner`。
- 修改`backend/app/services/constraint_extractor.py`：
  - 日料表达进入`must_have`和默认预算。
  - 未声明下午但声明吃正餐时，默认晚餐时间窗口。
- 修改`backend/app/services/candidate_retriever.py`：
  - POI名称语义增强新增日料、寿司、居酒屋识别。
  - 餐厅槽位新增日料硬门控。
  - 约会日料排序加入高质量日料词加分和快餐式日式餐降权。
- 修改`backend/app/services/plan_generator.py`：
  - 约会日料餐厅说明改为“晚饭按你们明说的日料来选”。
- 修改`backend/app/services/brain_recommendation_engine.py`和`backend/data/brain_policy.json`：
  - 补充日料显式餐饮锚点和标签蕴含。
- 修改`frontend/lib/view-models.ts`：
  - 新增`日料/寿司/居酒屋`中文投影。
- 修改`tests/test_p0_plan_create.py`和`scripts/run_backend_p0_tests.py`：
  - 新增情侣日料晚饭回归断言。

文档追加：

- `docs/02_system_architecture.md`追加“23. 2026-05-23追加：POI语义资产与一句话对齐层”。
- `docs/05_agent_workflow.md`追加“29. 2026-05-23追加：POI语义对齐与日料餐饮锚点”。
- `docs/08_evaluation_design.md`追加“29. 2026-05-23追加：POI语义对齐与日料泛化回归”。

当前手动复核效果：

- “周末想和女朋友出去放松一下,晚上想吃日料”
  - `intent_tags`包含`cuisine_japanese/dinner/date_friendly`。
  - `must_have`包含`cuisine_japanese/dinner`。
  - 最后餐厅节点为“烧鸟仙人(下沙宝龙店)”，`display_tags`含`cuisine_japanese/izakaya/proper_dining`。
- “周末想和女朋友吃日料”
  - 默认时间窗口为17:00-21:30。
  - 最后餐厅节点仍命中日料语义，不再落到茶空间或咖啡。

训练故事：

- P0继续由规则版类脑引擎保证可控输出。
- P1可用双卡5090训练本地reranker：输入用户一句话、受控画像、POI文本/类别/价格/评分/区域/状态/路线，输出候选POI或候选链路排序分。
- P2可训练reward model学习“同一句话下哪个POI更像人会选的地方”，但模型只能影响排序，不能越过显式餐饮锚点、亲子安全、Mock状态和Verifier边界。

## 2026-05-23 开放餐饮偏好画像与泛化门控修复

本轮回应“不能我说烤羊排就只修烤羊排，下次西餐、减脂、清淡又继续补丁”的问题。根因是原类脑层仍以少数显式餐饮锚点为主：火锅、烤肉、日料能被硬门控，但“吃X”里的开放短语没有变成可召回、可门控、可解释的餐厅槽位约束。

机制设计：

- 新增`extract_dining_preference()`开放餐饮画像：
  - 从“吃X/晚饭X/减脂/清淡”等表达中抽取`raw_terms`。
  - 生成`positive_terms`扩展词，用于POI文本召回。
  - 生成`specific_tags`受控标签，用于`must_have`和排序。
  - 生成`budget_max_per_person_hint`，让西餐、烤制肉类、低负担餐饮有合理预算。
- `ConstraintExtractor`接入画像：
  - 用餐为主且未声明“下午”时，默认进入晚餐窗口。
  - `must_have`只追加受控标签，如`lamb/bbq/grill/western_cuisine/healthy_light/light_meal/dinner`。
  - `dining_preference`保留在约束中便于审计，但不展示底层权重、Prompt或推理链。
- `CandidateRetriever`接入开放门控：
  - 从当前POI池中找开放画像命中餐厅。
  - 如果命中候选存在，最终餐厅必须命中该画像。
  - 通用`quality_dining/ambience_dining/date_friendly`只能加分，不能替代用户明说的食物目标。
  - 用餐为主且用户未明说手作时，降低手作/餐饮型活动在活动槽位的默认优先级。
- POI语义增强：
  - 新增`western_cuisine/steak/lamb/healthy_light`受控标签。
  - POI名称中“羊庄/羊肉炉/内蒙/西餐/LOFT/蒸/椰子鸡/日式料理”等可自动进入语义匹配。
  - 清淡/减脂样例避开火锅、烧烤、麻辣、酸菜鱼等重口味节点。

代码变更：

- 修改`backend/app/core/recommendation_taxonomy.py`：
  - 新增开放餐饮画像抽取、扩展词、预算提示和新受控标签。
- 修改`backend/app/services/constraint_extractor.py`：
  - 接入`dining_preference`、晚餐默认窗口、预算提示和`must_have`受控标签。
- 修改`backend/app/services/candidate_retriever.py`：
  - 新增开放餐饮候选召回、餐厅槽位硬门控、POI文本匹配和活动槽位降噪。
- 修改`backend/app/services/intent_parser.py`：
  - 合并优先级保留`western_cuisine/steak/lamb/healthy_light/explicit_dining`等新标签。
- 修改`backend/app/services/brain_recommendation_engine.py`：
  - 语义词典补充西餐、牛排、羊肉和低负担餐饮。
- 修改`backend/app/services/plan_generator.py`：
  - 约会餐厅说明可使用“晚饭按你们明说的X来选”。
- 修改`frontend/lib/view-models.ts`：
  - 新增西餐、牛排、羊肉、低负担中文投影，并隐藏内部`explicit_dining`。
- 修改`tests/test_p0_plan_create.py`和`scripts/run_backend_p0_tests.py`：
  - 新增烤羊排、西餐、减脂晚饭、清淡晚饭四条回归。

文档追加：

- `docs/02_system_architecture.md`追加“24. 2026-05-23追加：开放餐饮偏好画像与餐厅槽位门控”。
- `docs/05_agent_workflow.md`追加“30. 2026-05-23追加：开放餐饮偏好画像与泛化门控流程”。
- `docs/08_evaluation_design.md`追加“30. 2026-05-23追加：开放餐饮偏好画像回归”。

当前手动复核效果：

- “这周末想和女朋友吃烤羊排”
  - `intent_tags`包含`bbq/grill/lamb/dinner/date_friendly`。
  - `must_have`包含`bbq/grill/lamb/dinner`。
  - 最后餐厅节点为“正宗内蒙烧烤(高沙小区店)”，`display_tags`含`bbq/grill/lamb/proper_dining`。
  - 不再落到“蕉个朋友DIY手工 + 茶空间/M Stand”。
- “这周末想和女朋友吃西餐”
  - 最后餐厅节点为“73号.LOFT西餐厅”，命中`western_cuisine`。
- “这周末女朋友想减脂，帮我安排晚饭”
  - 最后餐厅节点命中`light_meal/light_food`，不再用咖啡或茶空间充当正餐。
- “这周末想和女朋友吃点清淡的”
  - 默认进入晚餐窗口，最后餐厅命中清淡正餐语义。

验证记录：

- `PYTHONPATH=backend python3 -m py_compile backend/app/core/recommendation_taxonomy.py backend/app/services/intent_parser.py backend/app/services/constraint_extractor.py backend/app/services/brain_recommendation_engine.py backend/app/services/candidate_retriever.py backend/app/services/plan_generator.py tests/test_p0_plan_create.py scripts/run_backend_p0_tests.py`通过。
- `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/run_backend_p0_tests.py`通过，新增`test_brain_date_lamb_chop/test_brain_date_western/test_brain_date_diet/test_brain_date_light_meal`均PASS。
- `PYTHONPATH=backend DEEPSEEK_ENABLED=false QWEN_ENABLED=false python3 scripts/contract_scan.py`通过。
- `cd frontend && npm run typecheck`通过。
- `python3 -m pytest`在当前本机Python 3.13环境启动时发生pytest自身段错误，已用`scripts/run_backend_p0_tests.py`覆盖P0主回归。
