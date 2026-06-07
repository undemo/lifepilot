
# 06_mock_api_design.md

## 1.文档信息

| 项目 | 内容 |
|---|---|
| 文档名称 | 06_mock_api_design.md |
| 项目名称 | LifePilot |
| 产品定位 | 生活时间导航Agent |
| 文档类型 | MockAPI与数字孪生数据设计文档 |
| 文档版本 | v0.1 |
| 面向读者 | 后端、Mock数据、Agent、Verifier、Executor、Recovery、前端联调、测试、评委 |
| 当前范围 | 比赛Demo阶段，优先支持P0闭环：家庭亲子、朋友局共识、纪念日情绪导航 |
| Mock区域 | 杭州下沙/金沙湖/高教园区 |
| 技术假设 | React/Next.js Web Demo；Backend API Service可用Node.js或Python FastAPI；Demo存储使用JSON文件或SQLite；后续可扩展PostgreSQL |
| 时间格式 | ISO 8601，例如`2026-05-20T13:00:00+08:00` |
| 核心约束 | MockAPI不伪装真实平台能力，不做真实支付、真实短信/微信、真实订座、真实票务、真实第三方爬取 |

LifePilot的统一表达为：

> 高德导航的是一段路，LifePilot导航的是一段生活时间。

---

## 2.文档目标与边界

### 2.1文档目标

本文档回答LifePilot Demo阶段MockAPI和数字孪生数据如何实现、造数、注入失败、联调和测试。

| 问题 | 06回答方式 |
|---|---|
| MockAPI在系统中扮演什么角色 | 定义MockAPI是Demo阶段真实工具层抽象，而不是真实平台代理 |
| MockAPI如何服务Agent各模块 | 明确CandidateRetriever、Verifier、Executor、Recovery、Frontend Debug调用边界 |
| Mock数据如何组织 | 以杭州下沙/金沙湖/高教园区构建生活时间线式数字孪生区域 |
| P0需要哪些Mock接口 | 按04最终路径定义11个Mock接口的实现要点 |
| 状态与执行如何区分 | 明确GET状态快照与POST模拟锁定动作不同 |
| failure_injection如何支持测试 | 定义餐厅满座、活动满员、窗口过期等可复现场景 |
| Mock状态如何影响ExecutableWindow | 定义`expire_at`、TTL、安全缓冲与Verifier输入关系 |
| 如何避免伪装真实能力 | 所有Mock POI、状态、凭证、消息、SocialSignal按对象类型标识 |
| 测试如何验收 | 给出MockAPI、Verifier、Executor、Recovery和前端Debug验收标准 |

### 2.2文档边界

本文档不重新写PRD、不重新写系统架构、不复制03完整Schema、不复制04完整API契约、不重新定义05 Agent工作流。

| 不做 | 原因 |
|---|---|
| 不重新定义PlanContract字段 | 以03_data_schema.md为最终权威 |
| 不新增API路径 | 以04_api_contract.md的`/api/v1/mock/...`路径为准 |
| 不新增ToolAction.type | 以03/04定义为准，订单动作使用`order_item` |
| 不新增错误码 | 只使用04已定义错误码 |
| 不让LLM决定状态 | 餐厅余位、票务、路线、天气、执行成功必须来自MockAPI、规则、Verifier或Executor |
| 不承诺真实交易 | 预约、订座、订单、消息都只返回Mock凭证 |
| 不把SocialSignal写成真实爬取 | SocialSignalMock仅为Mock或可扩展能力 |
| 不展示failure_injection给普通用户 | 只允许Debug/测试/评委模式展示 |

---

## 3.来源文档与契约优先级

### 3.1来源文档

| 优先级 | 来源 | 06使用方式 |
|---:|---|---|
| 1 | 03_data_schema.md | 字段命名、ID前缀、JSONSchema、时间格式、状态枚举、TraceLog、PlanContract、POI、POIStatus、RestaurantStatus、WeatherStatus、RouteEstimate、SocialSignalMock、ToolAction、ExecutionResult、RecoveryResult最终权威 |
| 2 | 04_api_contract.md | HTTP路径、标准响应、错误码、幂等键、Mock接口路径、Mock标识规范、failure_injection边界最终权威 |
| 3 | 05_agent_workflow.md | Agent调用顺序、MockAPI与CandidateRetriever/Verifier/Executor/Recovery协作边界最终权威 |
| 4 | 02_system_architecture.md | MockAPI在系统架构中的位置、Mock数据目录、服务分层、调用关系基础 |
| 5 | 01_prd.md | 页面范围、P0/P1/P2、用户流程和验收标准 |
| 6 | 00_project_vision.md | 产品定位、核心隐喻、核心闭环、P0场景、不做什么 |

### 3.2冲突处理规则

1. 01/02中的早期字段、路径、对象示意若与03/04/05冲突，以03/04/05为准。
2. MockAPI路径统一使用`/api/v1/mock/...`，不得使用`/api/mock/...`。
3. ToolAction订单动作统一使用`order_item`，不得使用`create_order`。
4. HTTP订单接口路径为`POST /api/v1/mock/orders/create`，但ToolAction.type仍为`order_item`。
5. TraceLog事件名只能使用03/04/05定义的枚举，MockAPI调用统一写`event_type:"tool_log"`。
6. Recovery采用版本化策略，生成新的完整PlanContract，不能原地覆盖原计划。
7. DraftPlan、PlanBuildCandidate、fixture内部字段都不是03/04领域契约，不能直接返回给前端当作PlanContract。

### 3.3最终MockAPI路径

| 能力 | HTTP路径 | P0 |
|---|---|---:|
| POI搜索 | `GET /api/v1/mock/poi/search` | 是 |
| 餐厅搜索 | `GET /api/v1/mock/restaurants/search` | 是 |
| POI状态 | `GET /api/v1/mock/poi/{poi_id}/status` | 是 |
| 餐厅状态 | `GET /api/v1/mock/restaurants/{poi_id}/status` | 是 |
| 路线估计 | `GET /api/v1/mock/routes/estimate` | 是 |
| 天气查询 | `GET /api/v1/mock/weather` | 是 |
| 活动预约 | `POST /api/v1/mock/activities/{poi_id}/book` | 是 |
| 餐厅订座/排号 | `POST /api/v1/mock/restaurants/{poi_id}/reserve` | 是 |
| 创建Mock订单 | `POST /api/v1/mock/orders/create` | P0可选，若生成ToolAction必须可执行 |
| 模拟消息发送 | `POST /api/v1/mock/messages/send` | 是 |
| Mock口碑信号 | `GET /api/v1/mock/social-signals/{poi_id}` | P1，P0预留 |

### 3.4 06文档的契约让位原则

`06_mock_api_design.md`只定义MockAPI实现策略、fixture组织方式、失败注入、状态生成规则和联调验收标准。

凡涉及以下内容，必须以03/04/05为最终权威：

| 内容 | 最终权威 |
|---|---|
| 领域对象字段、字段类型、必填项、枚举 | `03_data_schema.md` |
| HTTP路径、请求参数、标准响应、错误码、幂等规则 | `04_api_contract.md` |
| Agent调用顺序、Verifier/Executor/Recovery协作边界 | `05_agent_workflow.md` |

06中出现的内部fixture字段、内部文件、内部计算字段，仅用于`MockAPIService`实现，不得进入`PlanContract`、HTTP响应或03领域Schema。

---

## 4.MockAPI总体设计原则

### 4.1MockAPI不是伪装真实平台

MockAPI是Demo阶段对真实工具层的抽象，负责提供可控、可复现、可测试的本地生活状态和模拟执行结果。

它可以模拟：

| 能力 | P0处理方式 |
|---|---|
| POI/餐厅候选 | 读取数字孪生fixture |
| 营业状态 | 基于fixture opening规则和arrival_time计算 |
| 餐厅余位 | 基于party_size、arrival_time、reservations和failure_injection计算 |
| 排队时间 | 基于时段、人数、场景风险计算 |
| 活动余票 | 基于time_slot、remaining_tickets、booking_available计算 |
| 路线时间 | 基于`mock_routes.json`和时段交通系数计算 |
| 天气风险 | 基于mock_weather规则计算 |
| 执行凭证 | 生成Mock预约号、Mock订座号、Mock订单号、Mock message_id |
| 社交口碑 | P1返回SocialSignalMock，不真实抓取 |

它不能声称：

| 禁止表达 |
|---|
| 已真实支付 |
| 已真实发送微信/短信 |
| 已真实订座 |
| 已真实锁票 |
| 已实时抓取小红书/抖音/点评 |
| 已调用真实商家系统 |
| 真实平台确认可用 |

### 4.2MockAPI必须稳定服务下游模块

| 下游模块 | MockAPI责任 |
|---|---|
| CandidateRetriever | 提供可筛选的POI、餐厅、路线、天气、可选口碑候选 |
| VerifierService | 提供POIStatus、RestaurantStatus、RouteEstimate、WeatherStatus，用于硬约束检查 |
| ExecutorService | 提供活动预约、餐厅订座、订单、消息的模拟执行动作 |
| RecoveryPlanner | 在失败后提供替代POI、重新状态查询、重新路线估计和重新天气判断 |
| Frontend Debug | 提供工具调用摘要、脱敏payload、失败注入结果和Trace串联 |
| Testing | 提供可复现fixture和failure_scenario，支持自动化验收 |

### 4.3查询快照不等于执行成功

必须区分：

```text
状态查询：当前快照，用于Verifier和ExecutableWindow。
执行动作：用户确认后的模拟锁定动作，用于Executor。
查询时可用不保证执行时一定成功。
执行动作可能因状态过期、并发占用或failure_injection返回NO_TABLE_AVAILABLE/ACTIVITY_FULL。
执行失败后由RecoveryPlanner触发版本化Recovery。
````

示例：

```text
13:00查询餐厅4人位剩余2桌，expire_at=13:18。
13:20用户才确认，ExecutableWindow已过期。
Executor不得继续假装订座成功，应返回PLAN_EXECUTABLE_WINDOW_EXPIRED或先触发refresh-window。
```

---

## 5.MockAPI在LifePilot架构中的位置

### 5.1服务位置

```text
Backend API Service
├── Agent Orchestrator
│   ├── CandidateRetriever
│   │   └── MockAPIService：search/status/route/weather
│   ├── VerifierService
│   │   └── MockAPIService：status/route/weather
│   └── RecoveryPlanner
│       └── MockAPIService：alternative search/status/route/weather
├── ExecutorService
│   └── MockAPIService：book/reserve/order/send_message
├── Frontend Debug Controller
│   └── MockAPIService：debug-only direct calls
└── LoggingService
    └── TraceLog：tool_log/error_log
```

### 5.2主链路关系

05最终链路必须保持为：

```text
DraftPlan
→ PlanBuildCandidate预检
→ Verifier
→ PlanContractBuilder
→ Full SchemaValidator
→ 返回完整PlanContract
```

MockAPI在该链路中提供状态和执行依据，但不直接组装PlanContract，也不替代Verifier。

### 5.3模块调用边界

| 模块                  | 可以调用的Mock接口                                                                               | 不允许做的事                   |
| ------------------- | ----------------------------------------------------------------------------------------- | ------------------------ |
| CandidateRetriever  | `poi/search`、`restaurants/search`、`routes/estimate`、`weather`、P1 `social-signals`         | 不直接确认余位和执行成功             |
| VerifierService     | `poi/{poi_id}/status`、`restaurants/{poi_id}/status`、`routes/estimate`、`weather`           | 不让LLM补状态                 |
| ExecutorService     | `activities/{poi_id}/book`、`restaurants/{poi_id}/reserve`、`orders/create`、`messages/send` | 不跳过幂等键，不伪造真实凭证           |
| RecoveryPlanner     | search/status/route/weather重新查询                                                           | 不原地覆盖PlanContract        |
| Frontend普通用户页       | 一般不直接调用Mock接口，只消费Plan/Execution聚合结果                                                       | 不展示failure_injection     |
| Frontend Debug/评委模式 | 可直接调用Mock接口辅助演示                                                                           | 不展示Prompt、API Key、LLM推理链 |

---

## 6.数字孪生区域与Mock数据分层

### 6.1固定区域

P0固定数字孪生区域：

```text
杭州下沙/金沙湖/高教园区
```

目标不是全城覆盖，而是构建一个“小而完整”的生活时间导航试验区。

### 6.2生活时间线式组织

Mock数据不能只是随机地点列表，而要围绕“几小时生活时间线”组织：

```text
transport_anchor
→ activity / walk_spot
→ restaurant
→ walk_spot / service
→ transport_anchor
```

### 6.3POI组织类别

以下类别用于Mock fixture组织，不作为03 Schema强制枚举扩展。

| Mock组织类别         | 用途                 | 示例                   |
| ---------------- | ------------------ | -------------------- |
| activity         | 亲子、看展、桌游、儿童书店等活动节点 | 亲子科学空间、轻展览、桌游馆、儿童书店  |
| restaurant       | 餐饮节点               | 轻食、家庭餐厅、安静约会餐厅、低预算餐厅 |
| walk_spot        | 低成本时间填充与情绪节奏节点     | 湖边步道、商场室内动线、合照点      |
| service          | 仪式感或辅助服务           | 蛋糕、鲜花、停车点            |
| transport_anchor | 起终点或交通锚点           | 家、地铁口、商场入口           |

进入PlanStep时，仍应映射到03允许的PlanStep.type，例如`activity`、`restaurant`、`walk`、`service`、`transport`、`return_home`。

### 6.4数字孪生数据分层

| 层级      | 文件/规则                                           | 是否P0 | 说明                                    |
| ------- | ----------------------------------------------- | ---: | ------------------------------------- |
| 静态POI层  | `mock_pois.json`                                |    是 | 地点骨架、标签、价格、人群适配                       |
| 动态状态层   | `mock_status.json`、`mock_inventory.json`        |    是 | 营业、余位、余票、排队、TTL                       |
| 路线规则层   | `mock_routes.json`                              |    是 | 距离、耗时、交通时段系数；内部可拆分route_rules子结构       |
| 天气规则层   | `mock_weather.json`                             |    是 | 天气、降雨、户外风险                            |
| 执行状态层   | `executions.json`、`mock_idempotency_store.json` |    是 | Mock凭证、幂等记录、执行结果                      |
| 失败注入层   | `mock_failure_scenarios.json`                   |    是 | NO_TABLE_AVAILABLE、ACTIVITY_FULL、窗口过期 |
| 口碑Mock层 | `mock_social_signals.json`                      |   P1 | SocialSignalMock，不阻断P0                |

### 6.5 可复现Mock状态引擎补充（2026-05-23追加）

当前实现允许`mock_status.json`、`mock_inventory.json`、`mock_weather.json`、`mock_failure_scenarios.json`、`mock_social_signals.json`作为人工覆盖文件，但它们不再是状态能力的唯一来源。

`MockAPIService`内部应按以下优先级生成状态：

```text
POI/路线基础事实：
mock_pois.json
mock_routes.json

人工覆盖：
mock_status.json
mock_inventory.json
mock_weather.json
mock_failure_scenarios.json
mock_social_signals.json

缺省状态：
MockClock
DeterministicSeedService
WeatherMockEngine
StatusMockEngine
InventoryMockEngine
FailureMockEngine
SocialSignalMockEngine
```

种子规则以`demo_seed + area + poi_id + target_date + hour_bucket + party_size + scenario`为核心输入。同一日期、同一POI、同一时段和同一人数必须稳定返回相同天气、余位、排队、余票和口碑Mock摘要；切换目标日期或时段时允许生成不同世界状态。

实现边界：

| 能力 | 缺省策略 |
|---|---|
| POI状态 | 先查`mock_status.json`覆盖；缺失时基于POI营业时间、标签、评分、时段和人数生成 |
| 餐厅库存 | 先查`mock_inventory.json`覆盖；缺失时按时段、评分、人气和人数即时生成slot |
| 活动库存 | 先查`mock_inventory.json`覆盖；缺失时按活动类别、室内/户外、日期和人数即时生成余票 |
| 天气 | 仅当`mock_weather.json`区域和时间范围匹配时覆盖；缺失时按季节、日期hash和小时段生成 |
| 失败 | `mock_failure_scenarios.json`用于Demo精确剧本；默认低概率失败只能由确定性种子产生，不得随机漂移 |
| 口碑 | 先查`mock_social_signals.json`覆盖；缺失时基于POI rating、price、tags、risk_tags生成结构化Mock摘要 |

普通前端仍不得展示`failure_injection`、Prompt、API Key或模型推理链。调试/评委模式可以展示状态来自fixture覆盖还是规则生成，但该信息不得进入普通用户页的PlanContract展示。

---

## 7.Mock数据文件与Fixture设计

> 文件名为建议实现名。若与项目代码最终命名不完全一致，以项目实现为准。06新增文件若不是03/04领域对象，只作为Mock内部fixture文件，不进入PlanContract Schema。

### 7.1文件总览

#### 03 Demo契约文件

以下文件结构以03为准，`MockAPIService Loader`必须优先读取这些结构。HTTP响应必须由这些数据投影回03/04对象。

| 文件 | 顶层结构 | 是否HTTP响应来源 | 是否对齐03 |
|---|---|---:|---:|
| `mock_pois.json` | `pois` | 是 | 是 |
| `mock_status.json` | `statuses` | 是 | 是 |
| `mock_routes.json` | `routes` | 是 | 是 |
| `mock_weather.json` | `weather_snapshots` | 是 | 是 |
| `mock_social_signals.json` | `signals` | P1 | 是 |
| `executions.json` | `executions`或实现自定 | 是，作为ExecutionResult来源 | 是 |
| `traces.json` | `traces`或实现自定 | Debug/摘要 | 是 |

#### 06内部实现fixture

以下文件只服务MockAPI内部计算、Debug和测试，不覆盖03 Demo文件契约。

| 文件 | 用途 | 是否进入03 Schema | 是否允许前端直接依赖 |
|---|---|---:|---:|
| `mock_inventory.json` | 餐厅桌位、活动余票、时段库存 | 否 | 否 |
| `mock_failure_scenarios.json` | Debug/测试失败注入 | 否 | 否 |
| `mock_idempotency_store.json` | 执行类HTTP幂等记录 | 否 | 否 |

内部fixture字段可以参与状态生成，但HTTP响应必须先投影回03/04对象。

### 7.2`mock_pois.json`

#### 用途

保存杭州下沙/金沙湖/高教园区的Mock POI骨架，用于POI搜索、餐厅搜索和Recovery备选检索。

#### 顶层结构

```json
{
  "version": "v0.1",
  "area": "杭州下沙/金沙湖/高教园区",
  "pois": []
}
```

#### 核心字段

| 字段                   | 说明                              | 是否进入03 Schema |
| -------------------- | ------------------------------- | ------------: |
| `poi_id`             | `poi_`前缀                        |             是 |
| `name`               | POI名称                           |             是 |
| `category`           | 03 POI类别或兼容字段                   |       是，按03为准 |
| `mock_group`         | Mock内部组织类别，如activity/restaurant |             否 |
| `location`           | 经纬度与城市区域                         |             是 |
| `area`               | 下沙/金沙湖/高教园区                     | 可进入POI地理信息或标签 |
| `address`            | Mock展示地址                          |             是 |
| `tags`               | 检索标签                            |     是或作为POI标签 |
| `suitable_scenarios` | 适配场景                            |        可映射为标签 |
| `price_per_person`   | 人均预算估计                          |         可映射预算 |
| `rating`             | Mock评分                           |             是 |
| `opening_hours`      | 营业时间                             |             是 |
| `mock_only`          | Mock POI标识                      |     是，必须为true |
| `created_at`         | ISO 8601                        |             是 |
| `updated_at`         | ISO 8601                        |             是 |

#### 最小样例

```json
{
  "poi_id": "poi_child_science_001",
  "name": "金沙湖儿童科学空间",
  "category": "activity",
  "mock_group": "activity",
  "sub_category": "child_science",
  "tags": ["child_friendly", "interactive", "indoor", "not_tiring"],
  "location": {
    "city": "杭州",
    "area": "金沙湖",
    "lat": 30.3123,
    "lng": 120.3512
  },
  "area": "金沙湖",
  "address": "杭州市钱塘区金沙湖示范区Mock地址",
  "suitable_scenarios": ["family_parent_child"],
  "price_per_person": 40,
  "rating": 4.7,
  "opening_hours": {
    "weekday": [["10:00", "20:00"]],
    "weekend": [["09:30", "21:00"]]
  },
  "risk_tags": ["ticket_required"],
  "mock_only": true,
  "created_at": "2026-05-20T09:00:00+08:00",
  "updated_at": "2026-05-20T09:00:00+08:00"
}
```

`mock_group`等内部字段只能用于Mock召回和排序。HTTP响应前必须执行POI投影：

```text
InternalFixturePOI
→ POIProjection
→ 03 POI Schema校验
→ HTTP Response
```

### 7.3`mock_status.json`

#### 用途

保存基础状态模板和按时段变化规则，为POIStatus和RestaurantStatus生成提供输入。

#### 顶层结构

```json
{
  "version": "v0.1",
  "statuses": {}
}
```

#### 核心字段

| 字段            | 说明                         | 是否进入03 Schema |
| ------------- | -------------------------- | ------------: |
| `poi_id`      | 对应POI                      |             是 |
| `open_status` | 营业状态，必须映射到03合法状态           |             是 |
| `risk_level`  | `low/medium/high/blocking` |             是 |
| `ttl_minutes` | 状态有效期，用于生成`expire_at`      |        否，内部规则 |
| `source`      | `mock_api`                 |             是 |
| `updated_at`  | ISO 8601                   |             是 |

#### 最小样例

```json
{
  "version": "v0.1",
  "statuses": {
    "poi_light_food_003": {
      "query_status": {
        "available": true,
        "open_status": "open",
        "available_tables": 2,
        "queue_minutes": 12,
        "reservation_available": true,
        "risk_level": "medium",
        "source": "mock_api",
        "updated_at": "2026-05-20T13:00:00+08:00",
        "expire_at": "2026-05-20T13:18:00+08:00"
      },
      "internal_rules": {
        "queue_minutes_base": 12,
        "ttl_minutes": 18
      }
    }
  }
}
```

### 7.4`mock_inventory.json`

#### 用途

保存餐厅桌位、活动余票、时段预约情况，支持查询和执行动作的差异。

#### 顶层结构

```json
{
  "version": "v0.1",
  "restaurant_slots": [],
  "activity_slots": []
}
```

#### 最小样例

```json
{
  "restaurant_slots": [
    {
      "poi_id": "poi_light_food_003",
      "slot_start": "2026-05-20T15:30:00+08:00",
      "slot_end": "2026-05-20T16:30:00+08:00",
      "base_tables": 4,
      "reserved_tables": 2,
      "max_party_size": 4
    }
  ],
  "activity_slots": [
    {
      "poi_id": "poi_child_science_001",
      "slot_start": "2026-05-20T14:00:00+08:00",
      "slot_end": "2026-05-20T16:00:00+08:00",
      "remaining_tickets": 12,
      "booking_available": true
    }
  ]
}
```

### 7.5`mock_routes.json`

#### 用途

生成RouteEstimate，避免LLM估算路线。`mock_routes.json`是03定义的Demo路线文件；实现内部可在该文件中保留`time_multipliers`等规则字段，但HTTP响应必须投影为03 RouteEstimate。

#### 最小样例

```json
{
  "version": "v0.1",
  "routes": [
    {
      "route_id": "route_home_child_001",
      "origin_poi_id": "poi_home_anchor_001",
      "destination_poi_id": "poi_child_science_001",
      "transport_mode": "taxi",
      "distance_km": 5.2,
      "duration_minutes": 25,
      "traffic_level": "medium",
      "confidence": 0.82,
      "source": "mock_api",
      "updated_at": "2026-05-20T13:00:00+08:00",
      "base_duration_minutes": 22,
      "time_multipliers": [
        {
          "start": "2026-05-20T13:00:00+08:00",
          "end": "2026-05-20T14:30:00+08:00",
          "multiplier": 1.15,
          "traffic_level": "medium"
        }
      ]
    }
  ]
}
```

### 7.6`mock_weather.json`

#### 用途

生成WeatherStatus，用于Verifier的`weather_risk`检查。

#### 最小样例

```json
{
  "version": "v0.1",
  "weather_snapshots": [
    {
      "weather_id": "weather_20260520_jinshahu_001",
      "area": "jinshahu",
      "time_range": {
        "start_time": "2026-05-20T13:00:00+08:00",
        "end_time": "2026-05-20T18:00:00+08:00"
      },
      "weather": "cloudy",
      "temperature": 27,
      "rain_probability": 0.2,
      "outdoor_risk_level": "low",
      "suggested_recovery": null,
      "source": "mock_api",
      "updated_at": "2026-05-20T12:50:00+08:00"
    }
  ]
}
```

### 7.7`mock_failure_scenarios.json`

#### 用途

为Demo和自动化测试提供可复现失败脚本。

#### 最小样例

```json
{
  "scenarios": [
    {
      "failure_scenario_id": "fail_no_table_family_001",
      "enabled": true,
      "trigger": {
        "path": "POST /api/v1/mock/restaurants/{poi_id}/reserve",
        "poi_id": "poi_light_food_003",
        "plan_id": "plan_20260520_family_001"
      },
      "error_code": "NO_TABLE_AVAILABLE",
      "visible_to_user": false
    },
    {
      "failure_scenario_id": "fail_activity_full_001",
      "enabled": true,
      "trigger": {
        "path": "POST /api/v1/mock/activities/{poi_id}/book",
        "poi_id": "poi_child_science_001"
      },
      "error_code": "ACTIVITY_FULL",
      "visible_to_user": false
    }
  ]
}
```

---

## 8.MockAPI接口总览

| 接口                                               | ToolAction.type         | 主要调用方                                             | 查询/执行 | 幂等                    | 主要错误码                                                                        |
| ------------------------------------------------ | ----------------------- | ------------------------------------------------- | ----- | --------------------- | ---------------------------------------------------------------------------- |
| `GET /api/v1/mock/poi/search`                    | -                       | CandidateRetriever、RecoveryPlanner、Debug          | 查询    | GET天然幂等               | `BAD_REQUEST`、`RESOURCE_NOT_FOUND`                                           |
| `GET /api/v1/mock/restaurants/search`            | -                       | CandidateRetriever、RecoveryPlanner、Debug          | 查询    | GET天然幂等               | `BAD_REQUEST`、`RESOURCE_NOT_FOUND`                                           |
| `GET /api/v1/mock/poi/{poi_id}/status`           | `get_poi_status`        | Verifier、CandidateRetriever、Debug                 | 查询    | GET天然幂等               | `PLAN_STEP_POI_NOT_FOUND`、`MOCK_STATUS_MISSING`                              |
| `GET /api/v1/mock/restaurants/{poi_id}/status`   | `get_restaurant_status` | Verifier、Debug                                    | 查询    | GET天然幂等               | `PLAN_STEP_POI_NOT_FOUND`、`MOCK_STATUS_MISSING`                              |
| `GET /api/v1/mock/routes/estimate`               | `estimate_route`        | CandidateRetriever、Verifier、RecoveryPlanner、Debug | 查询    | GET天然幂等               | `PLAN_STEP_POI_NOT_FOUND`、`ROUTE_DELAY`                                      |
| `GET /api/v1/mock/weather`                       | `get_weather`           | CandidateRetriever、Verifier、Debug                 | 查询    | GET天然幂等               | `BAD_REQUEST`、`WEATHER_RISK_HIGH`                                            |
| `POST /api/v1/mock/activities/{poi_id}/book`     | `book_activity`         | ExecutorService                                   | 执行    | 必须`X-Idempotency-Key` | `ACTIVITY_FULL`、`IDEMPOTENCY_CONFLICT`、`PLAN_EXECUTABLE_WINDOW_EXPIRED`      |
| `POST /api/v1/mock/restaurants/{poi_id}/reserve` | `reserve_restaurant`    | ExecutorService                                   | 执行    | 必须`X-Idempotency-Key` | `NO_TABLE_AVAILABLE`、`IDEMPOTENCY_CONFLICT`、`PLAN_EXECUTABLE_WINDOW_EXPIRED` |
| `POST /api/v1/mock/orders/create`                | `order_item`            | ExecutorService                                   | 执行    | 必须`X-Idempotency-Key` | `BAD_REQUEST`、`IDEMPOTENCY_CONFLICT`                                         |
| `POST /api/v1/mock/messages/send`                | `send_message`          | ExecutorService                                   | 执行    | 必须`X-Idempotency-Key` | `BAD_REQUEST`、`IDEMPOTENCY_CONFLICT`                                         |
| `GET /api/v1/mock/social-signals/{poi_id}`       | -                       | CandidateRetriever、Frontend Debug                 | 查询    | GET天然幂等               | `SOCIAL_SIGNAL_MISSING`、`SOCIAL_SIGNAL_MOCK_REQUIRED`                        |

---

## 9.POI与餐厅检索Mock设计

### 9.1GET /api/v1/mock/poi/search

#### 接口定位

用于搜索活动、散步点、服务点、transport_anchor，为CandidateRetriever和RecoveryPlanner提供可选地点池。

#### 是否P0

是。

#### 调用方

CandidateRetriever / RecoveryPlanner / Frontend Debug。

#### 是否允许前端直接调用

普通用户页不直接调用；Debug/评委模式可直接调用。

#### Request Headers

| Header         | 是否必填 | 说明                                   |
| -------------- | ---: | ------------------------------------ |
| `Accept`       |    是 | `application/json`                   |
| `X-Trace-Id`   |   建议 | 业务链路复用PlanContract.trace_id；Debug可新建 |
| `X-Debug-Mode` |    否 | 为true时可返回脱敏fixture命中信息               |

#### Request Parameters

| 字段             | 类型      | 是否必填 | 来源                     | 说明                                                          |
| -------------- | ------- | ---: | ---------------------- | ----------------------------------------------------------- |
| `scenario`     | string  |    否 | ConstraintSet/UserGoal | `family_parent_child`、`friend_group`、`anniversary_emotion`等 |
| `area`         | string  |    否 | user_location/默认区域     | `xiasha`、`jinshahu`、`gaojiao`                               |
| `category`     | string  |    否 | CandidateRetriever     | activity、walk_spot、service、transport_anchor等Mock组织类别        |
| `tags`         | string  |    否 | ConstraintSet          | 逗号分隔，如`child_friendly,indoor`                               |
| `radius_km`    | number  |    否 | CandidateRetriever     | 默认5，不承诺全城覆盖                                                 |
| `limit`        | integer |    否 | CandidateRetriever     | 默认10                                                        |
| `arrival_time` | string  |    否 | PlanBuildCandidate     | ISO 8601，用于排序，不直接表示可执行状态                                    |

#### Response Data

| 字段                  | 来源                 | 是否进入03 Schema | 说明                |
| ------------------- | ------------------ | ------------: | ----------------- |
| `items`             | `mock_pois.json`经POIProjection |     是，作为03完整POI列表 | Mock POI列表        |
| `items[].mock_only` | 固定                 |             是 | 必须为true           |
| `match_reason`      | Mock内部规则           |             否 | Debug可展示，普通用户页不展示 |
| `expanded_query`    | CandidateRetriever |             否 | 候选不足时记录是否放宽标签     |

内部fixture字段如`mock_group`、`sort_weight`、`fixture_tags`、`scenario_weight`不得直接返回给普通业务调用方。`GET /api/v1/mock/poi/search`必须返回03定义的完整POI对象。

#### Mock标识

Mock POI必须带：

```json
{
  "mock_only": true
}
```

#### 幂等规则

GET天然幂等。相同fixture版本、相同查询参数应返回稳定排序结果。

#### failure_injection

P0一般不对搜索接口注入失败。测试可用Debug参数触发空结果，普通用户页不得展示`failure_injection`。

#### TraceLog

| event_type  | module           | visible_to_user | payload摘要                        |
| ----------- | ---------------- | --------------: | -------------------------------- |
| `poi_log`   | `CandidateRetriever` |               是 | 搜索类别、候选数量                        |
| `tool_log`  | `MockAPIService` |               是 | `tool_name:"search_poi"`、query摘要 |
| `error_log` | `MockAPIService` |               否 | 参数错误或fixture缺失                   |

#### 错误码

`BAD_REQUEST`、`RESOURCE_NOT_FOUND`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

搜索结果只作为候选，不能替代状态查询。Verifier仍必须对选中POI重新调用状态、路线和天气相关Mock接口。

#### 示例

```http
GET /api/v1/mock/poi/search?scenario=family_parent_child&area=jinshahu&category=activity&tags=child_friendly,indoor&radius_km=5&limit=5
X-Trace-Id: trace_20260520_0001
```

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
        "location": {
          "city": "杭州",
          "area": "金沙湖",
          "lat": 30.3123,
          "lng": 120.3512
        },
        "area": "金沙湖",
        "address": "杭州市钱塘区金沙湖示范区Mock地址",
        "price_per_person": 40,
        "rating": 4.7,
        "opening_hours": {
          "weekday": [["10:00", "20:00"]],
          "weekend": [["09:30", "21:00"]]
        },
        "suitable_scenarios": ["family_parent_child"],
        "risk_tags": ["ticket_required"],
        "mock_only": true,
        "created_at": "2026-05-20T09:00:00+08:00",
        "updated_at": "2026-05-20T09:00:00+08:00"
      }
    ],
    "page_info": { "page_size": 5, "next_page_token": null, "has_more": false }
  },
  "error": null
}
```

#### 验收标准

1. 返回POI的`poi_id`必须为`poi_`前缀。
2. 每个Mock POI必须包含`mock_only:true`。
3. 无结果时允许返回空数组，不直接中断主流程。
4. CandidateRetriever应能扩大半径或放宽标签后重查。
5. 普通用户页不得展示fixture内部排序细节。
6. 所有时间字段必须为ISO 8601。

---

### 9.2GET /api/v1/mock/restaurants/search

#### 接口定位

用于搜索餐厅候选，支持家庭低卡、朋友局低预算、安静约会、家庭友好等P0场景。

#### 是否P0

是。

#### 调用方

CandidateRetriever / RecoveryPlanner / Frontend Debug。

#### 是否允许前端直接调用

普通用户页不直接调用；Debug/评委模式可直接调用。

#### Request Headers

| Header         | 是否必填 | 说明                 |
| -------------- | ---: | ------------------ |
| `Accept`       |    是 | `application/json` |
| `X-Trace-Id`   |   建议 | 复用上游trace          |
| `X-Debug-Mode` |    否 | 返回脱敏排序原因           |

#### Request Parameters

| 字段                      | 类型      | 是否必填 | 来源                 | 说明                        |
| ----------------------- | ------- | ---: | ------------------ | ------------------------- |
| `scenario`              | string  |    否 | UserGoal           | 场景                        |
| `area`                  | string  |    否 | ConstraintSet      | 区域                        |
| `dietary_preference`    | string  |    否 | ConstraintSet      | 如`low_calorie,light_food` |
| `budget_max_per_person` | number  |    否 | ConstraintSet      | 人均预算                      |
| `party_size`            | integer |    否 | ConstraintSet      | 用于排序，不直接锁位                |
| `tags`                  | string  |    否 | CandidateRetriever | 如`quiet,family_friendly`  |
| `arrival_time`          | string  |    否 | PlanBuildCandidate | ISO 8601                  |
| `limit`                 | integer |    否 | CandidateRetriever | 默认10                      |

#### Response Data

| 字段                  | 来源               |  是否进入03 Schema | 说明         |
| ------------------- | ---------------- | -------------: | ---------- |
| `items`             | `mock_pois.json`经POIProjection | 是，作为03完整餐厅POI列表 | 不新增与03冲突字段 |
| `items[].mock_only` | 固定               |              是 | 必须为true    |
| `ranking_reason`    | Mock排序规则         |              否 | Debug可见    |

餐厅搜索响应同样必须返回03完整POI。餐厅余位、排队、订座可用性不得夹带在搜索结果中，必须通过`GET /api/v1/mock/restaurants/{poi_id}/status`获取。

#### Mock标识

餐厅POI同样是Mock POI，必须带`mock_only:true`。

#### 幂等规则

GET天然幂等。

#### failure_injection

可在Debug模式触发“只返回高风险餐厅”或“空餐厅列表”，用于测试Recovery候选不足；普通用户页不可见。

#### TraceLog

| event_type  | module           | visible_to_user | payload摘要                       |
| ----------- | ---------------- | --------------: | ------------------------------- |
| `poi_log`   | `CandidateRetriever` |               是 | 餐厅候选数量、场景                       |
| `tool_log`  | `MockAPIService` |               是 | `tool_name:"search_restaurant"` |
| `error_log` | `MockAPIService` |               否 | 参数错误                            |

#### 错误码

`BAD_REQUEST`、`RESOURCE_NOT_FOUND`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

搜索只返回候选餐厅。Verifier必须再调用`GET /api/v1/mock/restaurants/{poi_id}/status`检查`available_tables`、`queue_minutes`、`reservation_available`、`risk_level`和`expire_at`。

#### 示例

```http
GET /api/v1/mock/restaurants/search?scenario=family_parent_child&area=jinshahu&dietary_preference=low_calorie,light_food&party_size=3&arrival_time=2026-05-20T15:55:00+08:00
X-Trace-Id: trace_20260520_0001
```

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "items": [
      {
        "poi_id": "poi_light_food_003",
        "name": "轻盈厨房金沙湖店",
        "category": "restaurant",
        "sub_category": "light_food",
        "tags": ["low_calorie", "light_food", "family_friendly"],
        "location": {
          "city": "杭州",
          "area": "金沙湖",
          "lat": 30.315,
          "lng": 120.352
        },
        "area": "金沙湖",
        "address": "杭州市钱塘区金沙湖商圈Mock地址3号",
        "price_per_person": 60,
        "rating": 4.6,
        "opening_hours": {
          "weekday": [["10:00", "21:30"]],
          "weekend": [["10:00", "22:00"]]
        },
        "suitable_scenarios": ["family_parent_child", "anniversary_emotion"],
        "risk_tags": ["limited_tables"],
        "mock_only": true,
        "created_at": "2026-05-20T09:00:00+08:00",
        "updated_at": "2026-05-20T09:00:00+08:00"
      }
    ],
    "page_info": { "page_size": 10, "next_page_token": null, "has_more": false }
  },
  "error": null
}
```

#### 验收标准

1. 支持低卡轻食、家庭友好、安静约会、低预算检索。
2. 返回餐厅必须带`mock_only:true`。
3. 不得返回“真实余位已确认”这类表述。
4. party_size只能影响排序和后续状态查询，不代表锁位。
5. RecoveryPlanner能用相同条件找到备选餐厅。

---

## 10.POIStatus与RestaurantStatus状态Mock设计

### 10.1状态生成原则

POIStatus和RestaurantStatus必须来自MockAPI或规则计算，不能由LLM生成。

状态生成至少考虑：

| 因素                  | 影响                               |
| ------------------- | -------------------------------- |
| 基础静态状态              | 默认营业、默认风险、默认容量                   |
| 时间段动态状态             | 高峰期排队变长、票务减少                     |
| `party_size`        | 影响餐厅可用桌数和风险等级                    |
| `arrival_time`      | 影响营业、余位、排队、活动场次                  |
| 天气                  | 影响户外walk_spot风险                  |
| `open_status`       | 影响Verifier的`opening_hours`       |
| `queue_minutes`     | 影响Verifier的`queue_time`          |
| `available_tables`  | 影响Verifier的`restaurant_capacity` |
| `remaining_tickets` | 影响Verifier的`activity_ticket`     |
| `expire_at`         | 影响ExecutableWindow               |
| `source`            | 必须标记为`mock_api`                  |

### 10.2状态伪代码

```text
status_updated_at = now()
base = read(mock_status[poi_id])
inventory = read(mock_inventory[poi_id, arrival_time_slot])

if poi is restaurant:
    available_tables = max(0, base_tables - reserved_tables_in_time_slot - failure_injection_delta)
    if party_size > max_party_size:
        available_tables = 0
    queue_minutes = queue_minutes_base + peak_time_delta
    reservation_available = available_tables > 0
    risk_level = derive_risk(available_tables, queue_minutes)

if poi is activity:
    remaining_tickets = slot.remaining_tickets - booked_tickets - failure_injection_delta
    ticket_available = remaining_tickets >= party_size
    booking_available = slot.booking_available and ticket_available
    risk_level = derive_risk(remaining_tickets, booking_available)

expire_at = min(status_updated_at + ttl_minutes, arrival_time - safety_buffer)
source = "mock_api"
```

伪代码中的`ttl_minutes`、`failure_injection_delta`、`safety_buffer`是Mock内部fixture/规则，不进入03/04领域Schema。

### 10.3GET /api/v1/mock/poi/{poi_id}/status

#### 接口定位

用于查询活动、散步点、服务点等POI状态。活动类POI必须支持票务和预约相关状态。

#### 是否P0

是。

#### 调用方

CandidateRetriever / VerifierService / RecoveryPlanner / Frontend Debug。

#### 是否允许前端直接调用

普通用户页不直接调用；Debug/评委模式可直接调用。

#### Request Headers

| Header         | 是否必填 | 说明                 |
| -------------- | ---: | ------------------ |
| `Accept`       |    是 | `application/json` |
| `X-Trace-Id`   |   建议 | 复用上游trace          |
| `X-Debug-Mode` |    否 | 可返回脱敏状态计算说明        |

#### Request Parameters

| 字段                    | 类型          | 是否必填 | 来源                  | 说明        |
| --------------------- | ----------- | ---: | ------------------- | --------- |
| `poi_id`              | path string |    是 | PlanStep.poi_id     | `poi_`前缀  |
| `arrival_time`        | string      |    否 | PlanStep.start_time | ISO 8601  |
| `party_size`          | integer     |    否 | ConstraintSet       | 活动票务校验    |
| `scenario`            | string      |    否 | UserGoal            | 影响风险解释    |
| `failure_scenario_id` | string      |    否 | Debug/测试            | 普通用户页不得使用 |

#### Response Data

| 字段                  | 来源                       | 是否进入03 Schema | 说明                         |
| ------------------- | ------------------------ | ------------: | -------------------------- |
| `poi_id`            | path                     |             是 | POI ID                     |
| `available`         | 规则                       |             是 | 是否当前可用                    |
| `open_status`       | `mock_status.json`+规则    |             是 | 必须合法                       |
| `available_tables`  | 固定null或规则               |             是 | 非餐厅通常为null                 |
| `queue_minutes`     | 固定null或规则               |             是 | 非排队类可为null                 |
| `ticket_available`  | `mock_inventory.json`+规则 |             是 | 活动类使用                      |
| `remaining_tickets` | `mock_inventory.json`+规则 |             是 | 活动类使用                      |
| `booking_available` | `mock_inventory.json`+规则 |             是 | 活动类使用                      |
| `reservation_available` | 固定null或规则            |             是 | 非餐厅通常为null                 |
| `risk_level`        | 规则                       |             是 | `low/medium/high/blocking` |
| `status_message`    | 规则                       |             是 | 用户可读状态摘要                  |
| `expire_at`         | TTL规则                    |             是 | 必须ISO 8601                 |
| `source`            | 固定                       |             是 | `mock_api`                 |

POIStatus响应必须按03/04完整状态对象返回。即使某类字段不适用，也应显式返回`null`，避免Verifier和前端实现分叉。

#### Mock标识

Mock状态必须带`source:"mock_api"`或`mock_only:true`。推荐状态对象统一返回`source:"mock_api"`。

#### 幂等规则

GET天然幂等。同一fixture版本、同一`arrival_time`、同一`party_size`返回稳定结果；随系统时间计算`expire_at`时，应在测试模式固定`now`。

#### failure_injection

支持Debug/测试触发高风险或不可用状态。GET状态查询不得返回`ACTIVITY_FULL`作为执行失败错误码；应返回`available:false`、`risk_level:"blocking"`、`remaining_tickets:0`、`booking_available:false`等状态快照，由Verifier生成fail/warning。普通用户页不得展示`failure_scenario_id`和内部注入原因。

#### TraceLog

| event_type  | module           | visible_to_user | payload摘要                                    |
| ----------- | ---------------- | --------------: | -------------------------------------------- |
| `tool_log`  | `MockAPIService` |               是 | `tool_name:"get_poi_status"`、poi_id、status摘要 |
| `error_log` | `MockAPIService` |               否 | 状态缺失、POI不存在、注入失败                             |

#### 错误码

`PLAN_STEP_POI_NOT_FOUND`、`MOCK_STATUS_MISSING`、`BAD_REQUEST`、`RESOURCE_NOT_FOUND`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

返回结果用于Verifier的`opening_hours`、`activity_ticket`、`executable_window`等检查。Executor执行预约时必须再次检查或原子扣减库存，不能只依赖旧查询结果。

#### 示例

```http
GET /api/v1/mock/poi/poi_child_science_001/status?arrival_time=2026-05-20T14:05:00+08:00&party_size=3
X-Trace-Id: trace_20260520_0001
```

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "poi_id": "poi_child_science_001",
    "available": true,
    "open_status": "open",
    "available_tables": null,
    "queue_minutes": null,
    "ticket_available": true,
    "remaining_tickets": 12,
    "booking_available": true,
    "reservation_available": null,
    "risk_level": "low",
    "status_message": "当前场次余票充足，可模拟预约。",
    "expire_at": "2026-05-20T13:18:00+08:00",
    "source": "mock_api",
    "mock_only": true,
    "updated_at": "2026-05-20T13:00:00+08:00"
  },
  "error": null
}
```

#### 验收标准

1. 必须包含`expire_at`。
2. 活动类必须支持`ticket_available`、`remaining_tickets`、`booking_available`。
3. `risk_level`必须为合法枚举。
4. 状态缺失返回`MOCK_STATUS_MISSING`。
5. POI不存在返回`PLAN_STEP_POI_NOT_FOUND`或`RESOURCE_NOT_FOUND`，按调用上下文处理。
6. 不得由LLM生成状态字段。

---

### 10.4GET /api/v1/mock/restaurants/{poi_id}/status

#### 接口定位

用于查询餐厅在指定到达时间和人数下的可用性、排队和订座风险。

#### 是否P0

是。

#### 调用方

VerifierService / CandidateRetriever / RecoveryPlanner / Frontend Debug。

#### 是否允许前端直接调用

普通用户页不直接调用；Debug/评委模式可直接调用。

#### Request Headers

| Header         | 是否必填 | 说明                 |
| -------------- | ---: | ------------------ |
| `Accept`       |    是 | `application/json` |
| `X-Trace-Id`   |   建议 | 复用上游trace          |
| `X-Debug-Mode` |    否 | 可返回脱敏计算说明          |

#### Request Parameters

| 字段                    | 类型          | 是否必填 | 来源                       | 说明                 |
| --------------------- | ----------- | ---: | ------------------------ | ------------------ |
| `poi_id`              | path string |    是 | PlanStep.poi_id          | 餐厅POI              |
| `arrival_time`        | string      |    是 | PlanStep.start_time      | ISO 8601           |
| `party_size`          | integer     |    是 | ConstraintSet.party_size | 影响available_tables |
| `scenario`            | string      |    否 | UserGoal                 | 用于解释风险             |
| `failure_scenario_id` | string      |    否 | Debug/测试                 | 普通用户页不得使用          |

#### Response Data

| 字段                      | 来源    | 是否进入03 Schema | 说明         |
| ----------------------- | ----- | ------------: | ---------- |
| `poi_id`                | path  |             是 | 餐厅POI      |
| `available`             | 规则    |             是 | 是否当前可用     |
| `open_status`           | 状态规则  |             是 | 营业状态       |
| `available_tables`      | 库存规则  |             是 | 可用桌数       |
| `queue_minutes`         | 状态规则  |             是 | 排队时间       |
| `ticket_available`      | 固定null |             是 | 餐厅通常为null |
| `remaining_tickets`     | 固定null |             是 | 餐厅通常为null |
| `booking_available`     | 固定null |             是 | 餐厅通常为null |
| `reservation_available` | 规则    |             是 | 是否可订座      |
| `risk_level`            | 规则    |             是 | 余位/排队综合风险  |
| `status_message`        | 规则    |             是 | 用户可读状态摘要   |
| `expire_at`             | TTL规则 |             是 | 必须ISO 8601 |
| `source`                | 固定    |             是 | `mock_api` |

RestaurantStatus响应必须按03/04完整状态对象返回。不适用字段显式返回`null`。

#### Mock标识

状态对象必须带`source:"mock_api"`或`mock_only:true`。推荐`source:"mock_api"`。

#### 幂等规则

GET天然幂等。测试模式固定`now`时，响应完全可复现。

#### failure_injection

支持Debug/测试注入：

| 注入目标 | 返回                                                                |
| ---- | ----------------------------------------------------------------- |
| 餐厅满座 | `available:false`+`available_tables:0`+`reservation_available:false`+`risk_level:"blocking"` |
| 排队升高 | P1/P2可映射到`ROUTE_DELAY`或高风险warning，不新增错误码                          |
| 状态缺失 | `MOCK_STATUS_MISSING`                                             |

GET状态查询不得返回`NO_TABLE_AVAILABLE`作为执行失败错误码；`NO_TABLE_AVAILABLE`只保留给POST订座执行动作。普通用户页不得显示`failure_injection`字段。

#### TraceLog

| event_type  | module           | visible_to_user | payload摘要                                                                    |
| ----------- | ---------------- | --------------: | ---------------------------------------------------------------------------- |
| `tool_log`  | `MockAPIService` |               是 | `tool_name:"get_restaurant_status"`、available_tables、queue_minutes、expire_at |
| `error_log` | `MockAPIService` |               否 | `MOCK_STATUS_MISSING`、参数错误等                                  |

#### 错误码

`PLAN_STEP_POI_NOT_FOUND`、`MOCK_STATUS_MISSING`、`RESOURCE_NOT_FOUND`、`BAD_REQUEST`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

返回结果用于Verifier的`restaurant_capacity`和`queue_time`检查。Executor执行`reserve_restaurant`时必须重新根据库存和幂等规则生成Mock订座号，查询可用不保证执行成功。

#### 示例

```http
GET /api/v1/mock/restaurants/poi_light_food_003/status?arrival_time=2026-05-20T15:55:00+08:00&party_size=3
X-Trace-Id: trace_20260520_0001
```

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
    "remaining_tickets": null,
    "booking_available": null,
    "reservation_available": true,
    "risk_level": "medium",
    "status_message": "4人位剩余2桌，建议尽快确认。",
    "expire_at": "2026-05-20T13:18:00+08:00",
    "source": "mock_api",
    "mock_only": true,
    "updated_at": "2026-05-20T13:00:00+08:00"
  },
  "error": null
}
```

#### 验收标准

1. `arrival_time`和`party_size`必须参与状态计算。
2. 必须返回`available`、`available_tables`、`queue_minutes`、`reservation_available`、`risk_level`、`expire_at`。
3. `party_size`超过餐厅支持人数时必须风险升高或不可订。
4. 查询状态不得生成订座凭证。
5. 执行订座仍可能失败并触发Recovery。

---

## 11.RouteEstimate路线Mock设计

### 11.1GET /api/v1/mock/routes/estimate

#### 接口定位

生成两个POI之间的Mock路线估计，用于时间线、距离约束和ExecutableWindow计算。

#### 是否P0

是。

#### 调用方

CandidateRetriever / VerifierService / RecoveryPlanner / Frontend Debug。

#### 是否允许前端直接调用

普通用户页不直接调用；Debug/评委模式可直接调用。

#### Request Headers

| Header         | 是否必填 | 说明                   |
| -------------- | ---: | -------------------- |
| `Accept`       |    是 | `application/json`   |
| `X-Trace-Id`   |   建议 | 复用上游trace            |
| `X-Debug-Mode` |    否 | 可返回脱敏`mock_routes`命中信息 |

#### Request Parameters

| 字段                   | 类型     | 是否必填 | 来源                      | 说明                                  |
| -------------------- | ------ | ---: | ----------------------- | ----------------------------------- |
| `origin_poi_id`      | string |    是 | PlanStep.from_poi_id    | `poi_`前缀                            |
| `destination_poi_id` | string |    是 | PlanStep.to_poi_id      | `poi_`前缀                            |
| `transport_mode`     | string |    是 | PlanStep.transport_mode | `walk/taxi/drive/subway/bike/mixed` |
| `departure_time`     | string |    是 | PlanStep.start_time     | ISO 8601                            |

#### Response Data

RouteEstimate必须包含完整字段：

| 字段                   | 来源                 | 是否进入03 Schema | 说明                                 |
| -------------------- | ------------------ | ------------: | ---------------------------------- |
| `route_id`           | 系统生成               |             是 | `route_`前缀                         |
| `origin_poi_id`      | 请求                 |             是 | 起点                                 |
| `destination_poi_id` | 请求                 |             是 | 终点                                 |
| `transport_mode`     | 请求                 |             是 | 交通方式                               |
| `distance_km`        | `mock_routes.json` |             是 | 距离                                 |
| `duration_minutes`   | 规则计算               |             是 | 时长                                 |
| `traffic_level`      | 时段规则               |             是 | `none/smooth/medium/heavy/unknown` |
| `confidence`         | 规则                 |             是 | 0-1                                |
| `source`             | 固定                 |             是 | 必须为`mock_api`                      |
| `updated_at`         | 系统时间               |             是 | ISO 8601                           |

#### Mock标识

RouteEstimate使用`source:"mock_api"`。

#### 幂等规则

GET天然幂等。相同`mock_routes.json`版本和相同请求参数返回稳定估计。

#### failure_injection

P1/P2可注入`ROUTE_DELAY`，用于测试Recovery压缩活动时长或替换更近POI。P0可保留但不强依赖。

#### TraceLog

| event_type  | module           | visible_to_user | payload摘要                                                   |
| ----------- | ---------------- | --------------: | ----------------------------------------------------------- |
| `tool_log`  | `MockAPIService` |               是 | `tool_name:"estimate_route"`、duration_minutes、traffic_level |
| `error_log` | `MockAPIService` |               否 | POI不存在、路线规则缺失                                               |

#### 错误码

`PLAN_STEP_POI_NOT_FOUND`、`ROUTE_DELAY`、`BAD_REQUEST`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

RouteEstimate用于Verifier的`time_feasibility`、`distance_constraint`和Recovery替代方案差异计算。路线估计不能由LLM生成。

#### 示例

```http
GET /api/v1/mock/routes/estimate?origin_poi_id=poi_home_anchor_001&destination_poi_id=poi_child_science_001&transport_mode=taxi&departure_time=2026-05-20T13:40:00+08:00
X-Trace-Id: trace_20260520_0001
```

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "route_id": "route_20260520_0001",
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

#### 验收标准

1. `route_id`必须为`route_`前缀。
2. `source`必须为`mock_api`。
3. 返回字段必须完整。
4. POI不存在时不能编造路线。
5. Recovery替换餐厅后必须重新估算路线。
6. 所有时间字段必须为ISO 8601。

---

## 12.WeatherStatus天气Mock设计

### 12.1GET /api/v1/mock/weather

#### 接口定位

返回固定区域和时间窗口内的Mock天气状态，用于判断户外节点风险。

#### 是否P0

是。

#### 调用方

CandidateRetriever / VerifierService / RecoveryPlanner / Frontend Debug。

#### 是否允许前端直接调用

普通用户页不直接调用；Debug/评委模式可直接调用。

#### Request Headers

| Header         | 是否必填 | 说明                 |
| -------------- | ---: | ------------------ |
| `Accept`       |    是 | `application/json` |
| `X-Trace-Id`   |   建议 | 复用上游trace          |
| `X-Debug-Mode` |    否 | 可返回脱敏天气fixture命中信息 |

#### Request Parameters

| 字段           | 类型     | 是否必填 | 来源                          | 说明                        |
| ------------ | ------ | ---: | --------------------------- | ------------------------- |
| `area`       | string |    是 | ConstraintSet/user_location | `xiasha/jinshahu/gaojiao` |
| `start_time` | string |    是 | Plan.time_window.start_time | ISO 8601                  |
| `end_time`   | string |    是 | Plan.time_window.end_time   | ISO 8601                  |
| `location`   | string |    否 | POI/area                    | 可选更细位置                    |

#### Response Data

| 字段              | 来源                     | 是否进入03 Schema | 说明                  |
| --------------- | ---------------------- | ------------: | ------------------- |
| WeatherStatus字段 | `mock_weather.json`+规则 |             是 | 必须返回03完整WeatherStatus |
| `source`        | 固定                     |             是 | `mock_api` |
| `mock_only`     | 固定                     |             是 | 推荐返回，明确Mock状态 |
| `updated_at`    | 系统时间                   |             是 | ISO 8601            |

#### Mock标识

Mock状态必须带`source:"mock_api"`或`mock_only:true`。推荐天气状态返回`source:"mock_api"`。

天气接口不得使用06自造的简化对象，例如`condition`、`time_start`、`time_end`。请求字段以04为准，响应字段以03 WeatherStatus为准。

#### 幂等规则

GET天然幂等。P0可使用固定天气或时段规则。

#### failure_injection

P1/P2可注入`WEATHER_RISK_HIGH`，用于测试户外改室内。P0可作为预留，不阻断主流程。

#### TraceLog

| event_type  | module           | visible_to_user | payload摘要                             |
| ----------- | ---------------- | --------------: | ------------------------------------- |
| `tool_log`  | `MockAPIService` |               是 | `tool_name:"get_weather"`、area、risk摘要 |
| `error_log` | `MockAPIService` |               否 | 天气fixture缺失、参数错误                      |

#### 错误码

`BAD_REQUEST`、`WEATHER_RISK_HIGH`、`MOCK_STATUS_MISSING`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

天气影响Verifier的`weather_risk`检查。若户外节点风险升高，Recovery可将walk_spot替换为室内动线或儿童书店。

#### 示例

```http
GET /api/v1/mock/weather?area=jinshahu&start_time=2026-05-20T13:30:00+08:00&end_time=2026-05-20T18:00:00+08:00
X-Trace-Id: trace_20260520_0001
```

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "weather_id": "weather_20260520_jinshahu_001",
    "area": "jinshahu",
    "time_range": {
      "start_time": "2026-05-20T13:30:00+08:00",
      "end_time": "2026-05-20T18:00:00+08:00"
    },
    "weather": "cloudy",
    "temperature": 27,
    "rain_probability": 0.2,
    "outdoor_risk_level": "low",
    "suggested_recovery": null,
    "source": "mock_api",
    "mock_only": true,
    "updated_at": "2026-05-20T12:50:00+08:00"
  },
  "error": null
}
```

#### 验收标准

1. 不承诺真实天气。
2. 必须影响户外节点Verifier检查。
3. 天气缺失可降级warning，不得让LLM补真实天气。
4. P1/P2注入高天气风险时，Recovery能改室内方案。
5. 普通用户页不得显示failure_injection细节。

---

## 13.活动预约、餐厅订座、下单、消息发送Mock设计

### 13.1执行类接口通用规则

执行类Mock接口包括：

```text
POST /api/v1/mock/activities/{poi_id}/book
POST /api/v1/mock/restaurants/{poi_id}/reserve
POST /api/v1/mock/orders/create
POST /api/v1/mock/messages/send
```

统一规则：

| 项        | 规则                                                                                              |
| -------- | ----------------------------------------------------------------------------------------------- |
| 幂等       | 必须要求`X-Idempotency-Key`                                                                         |
| 凭证       | 成功必须返回Mock凭证，且带`mock_only:true`                                                                 |
| 真实能力     | 不做真实支付、真实短信/微信、真实订座、真实票务                                                                        |
| 状态       | 执行前必须检查窗口、库存和failure_injection                                                                  |
| Trace    | 成功写`tool_log`和`executor_log`；失败写`tool_log`和必要`error_log`                                        |
| Recovery | `NO_TABLE_AVAILABLE`、`ACTIVITY_FULL`、`PLAN_EXECUTABLE_WINDOW_EXPIRED`应触发Recovery或refresh-window |
| 幂等冲突     | 同一key复用于不同plan/action返回`IDEMPOTENCY_CONFLICT`                                                   |

执行类HTTP接口不得把具体凭证字段统一改名为`voucher_id`。HTTP响应必须使用04定义的具体凭证字段：活动预约为`booking_id`，餐厅订座为`reservation_id`，订单为`order_id`，消息为`message_id`。`voucher`只作为`ExecutionResult.vouchers`聚合展示层概念。

执行类HTTP接口的幂等键以Header `X-Idempotency-Key`为准。`ToolAction.idempotency_key`是Agent内部动作字段，不能替代HTTP Header；若body中出现兼容旧示例的`idempotency_key`，必须与Header一致，否则返回`BAD_REQUEST`。

### 13.2POST /api/v1/mock/activities/{poi_id}/book

#### 接口定位

Executor用于模拟活动预约，生成Mock预约号。

#### 是否P0

是。

#### 调用方

ExecutorService。

#### 是否允许前端直接调用

普通用户页不直接调用；Debug/评委模式可直接调用测试。

#### Request Headers

| Header              | 是否必填 | 说明                      |
| ------------------- | ---: | ----------------------- |
| `Content-Type`      |    是 | `application/json`      |
| `X-Trace-Id`        |    是 | 复用PlanContract.trace_id |
| `X-Idempotency-Key` |    是 | 执行类接口必填                 |
| `X-Debug-Mode`      |    否 | 可触发测试场景                 |

#### Request Body

| 字段                    | 类型      | 是否必填 | 来源                    | 说明         |
| --------------------- | ------- | ---: | --------------------- | ---------- |
| `plan_id`             | string  |    是 | ToolAction.plan_id    | 当前计划       |
| `action_id`           | string  |    是 | ToolAction.action_id  | 当前动作       |
| `party_size`          | integer |    是 | ToolAction.payload    | 人数         |
| `booking_time`        | string  |    是 | ToolAction.payload    | ISO 8601   |
| `arrival_time`        | string  |    否 | ToolAction.payload    | ISO 8601   |
| `trace_id`            | string  |    否 | PlanContract.trace_id | 可与header一致 |
| `failure_scenario_id` | string  |    否 | Debug/测试              | 普通用户不可用    |

#### Response Data

| 字段           | 来源               |             是否进入03 Schema | 说明       |
| ------------ | ---------------- | ------------------------: | -------- |
| `booking_id` | MockAPI生成        | 可进入ExecutionResult.result | Mock预约号  |
| `poi_id`     | path             |                  是/执行结果引用 | 活动POI    |
| `plan_id`    | 请求               |                  是/执行结果引用 | 计划       |
| `action_id`  | 请求               |                  是/执行结果引用 | 动作       |
| `status`     | Executor/MockAPI |                  是/执行结果引用 | success  |
| `mock_only`  | 固定               |                         是 | 必须true   |
| `created_at` | 系统               |                         是 | ISO 8601 |

#### Mock标识

凭证必须带：

```json
{
  "mock_only": true
}
```

#### 幂等规则

1. 缺少`X-Idempotency-Key`返回`BAD_REQUEST`。
2. 同一`X-Idempotency-Key`+同一plan/action重复请求，返回同一Mock预约号。
3. 同一`X-Idempotency-Key`被不同plan/action复用，返回`IDEMPOTENCY_CONFLICT`。
4. 幂等记录写入`mock_idempotency_store.json`或SQLite表。

#### failure_injection

支持`ACTIVITY_FULL`、`PLAN_EXECUTABLE_WINDOW_EXPIRED`。失败后Executor触发RecoveryPlanner。

#### TraceLog

| event_type     | module            | visible_to_user | payload摘要                                 |
| -------------- | ----------------- | --------------: | ----------------------------------------- |
| `tool_log`     | `MockAPIService`  |               是 | `tool_name:"book_activity"`、poi_id、status |
| `executor_log` | `ExecutorService` |               是 | action_id、执行结果                            |
| `error_log`    | `MockAPIService`  |               否 | `ACTIVITY_FULL`等                          |

#### 错误码

`BAD_REQUEST`、`ACTIVITY_FULL`、`PLAN_EXECUTABLE_WINDOW_EXPIRED`、`IDEMPOTENCY_CONFLICT`、`PLAN_STEP_POI_NOT_FOUND`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

Verifier只检查当前可预约性。Executor调用本接口才生成Mock预约号。若返回`ACTIVITY_FULL`，Recovery应替换活动或调整时间后重新Verifier。

#### 示例

```http
POST /api/v1/mock/activities/poi_child_science_001/book
Content-Type: application/json
X-Trace-Id: trace_20260520_0001
X-Idempotency-Key: idem_act_book_0001
```

```json
{
  "plan_id": "plan_20260520_0001",
  "action_id": "act_book_0001",
  "party_size": 3,
  "booking_time": "2026-05-20T14:05:00+08:00"
}
```

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "booking_id": "mock_booking_20260520_0001",
    "poi_id": "poi_child_science_001",
    "plan_id": "plan_20260520_0001",
    "action_id": "act_book_0001",
    "status": "success",
    "display_text": "Mock预约号已生成",
    "mock_only": true,
    "created_at": "2026-05-20T13:05:00+08:00"
  },
  "error": null
}
```

#### 验收标准

1. 无`X-Idempotency-Key`必须失败。
2. 成功凭证必须`mock_only:true`。
3. 满员只能返回`ACTIVITY_FULL`，不得返回`TICKET_SOLD_OUT`。
4. 重复幂等请求返回同一预约号。
5. 不得出现“真实票务已锁定”。

---

### 13.3POST /api/v1/mock/restaurants/{poi_id}/reserve

#### 接口定位

Executor用于模拟餐厅订座或排号，生成Mock订座号或排号。

#### 是否P0

是。

#### 调用方

ExecutorService。

#### 是否允许前端直接调用

普通用户页不直接调用；Debug/评委模式可直接调用测试。

#### Request Headers

| Header              | 是否必填 | 说明                      |
| ------------------- | ---: | ----------------------- |
| `Content-Type`      |    是 | `application/json`      |
| `X-Trace-Id`        |    是 | 复用PlanContract.trace_id |
| `X-Idempotency-Key` |    是 | 执行类接口必填                 |
| `X-Debug-Mode`      |    否 | Debug/测试                |

#### Request Body

| 字段                    | 类型      | 是否必填 | 来源                   | 说明            |
| --------------------- | ------- | ---: | -------------------- | ------------- |
| `plan_id`             | string  |    是 | ToolAction.plan_id   | 当前计划          |
| `action_id`           | string  |    是 | ToolAction.action_id | 当前动作          |
| `party_size`          | integer |    是 | ToolAction.payload   | 人数            |
| `arrival_time`        | string  |    是 | ToolAction.payload   | ISO 8601      |
| `reservation_note`    | string  |    否 | ToolAction.payload   | 纪念日、靠窗等Mock备注 |
| `failure_scenario_id` | string  |    否 | Debug/测试             | 普通用户不可用       |

#### Response Data

| 字段                 | 来源        |      是否进入03 Schema | 说明                           |
| ------------------ | --------- | -----------------: | ---------------------------- |
| `reservation_id`   | MockAPI生成 | 可进入ExecutionResult | Mock订座号或排号                   |
| `reservation_type` | 规则        |            可进入执行结果 | `reservation`或`queue_number` |
| `poi_id`           | path      |             是/执行引用 | 餐厅                           |
| `plan_id`          | 请求        |             是/执行引用 | 计划                           |
| `action_id`        | 请求        |             是/执行引用 | 动作                           |
| `mock_only`        | 固定        |                  是 | 必须true                       |
| `created_at`       | 系统        |                  是 | ISO 8601                     |

#### Mock标识

凭证必须带`mock_only:true`。

#### 幂等规则

同活动预约接口。重复请求返回同一Mock订座号；不同plan/action复用key返回`IDEMPOTENCY_CONFLICT`。

#### failure_injection

支持`NO_TABLE_AVAILABLE`、`PLAN_EXECUTABLE_WINDOW_EXPIRED`。查询时有位不保证执行时仍有位。

#### TraceLog

| event_type     | module            | visible_to_user | payload摘要                                      |
| -------------- | ----------------- | --------------: | ---------------------------------------------- |
| `tool_log`     | `MockAPIService`  |               是 | `tool_name:"reserve_restaurant"`、poi_id、status |
| `executor_log` | `ExecutorService` |               是 | action_id、凭证摘要                                 |
| `error_log`    | `MockAPIService`  |               否 | `NO_TABLE_AVAILABLE`等                          |

#### 错误码

`BAD_REQUEST`、`NO_TABLE_AVAILABLE`、`PLAN_EXECUTABLE_WINDOW_EXPIRED`、`IDEMPOTENCY_CONFLICT`、`PLAN_STEP_POI_NOT_FOUND`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

若返回`NO_TABLE_AVAILABLE`，Executor必须触发RecoveryPlanner。Recovery使用备选餐厅或重新搜索餐厅，重新查询路线、余位、预算，再重新Verifier，生成`updated_plan_id`。

#### 示例

```http
POST /api/v1/mock/restaurants/poi_light_food_003/reserve
Content-Type: application/json
X-Trace-Id: trace_20260520_0001
X-Idempotency-Key: idem_act_reserve_0001
```

```json
{
  "plan_id": "plan_20260520_0001",
  "action_id": "act_reserve_0001",
  "party_size": 3,
  "arrival_time": "2026-05-20T15:55:00+08:00",
  "reservation_note": "家庭亲子，偏安静座位"
}
```

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "reservation_id": "mock_reservation_20260520_0001",
    "reservation_type": "reservation",
    "poi_id": "poi_light_food_003",
    "plan_id": "plan_20260520_0001",
    "action_id": "act_reserve_0001",
    "status": "success",
    "display_text": "Mock订座号已生成",
    "mock_only": true,
    "created_at": "2026-05-20T13:06:00+08:00"
  },
  "error": null
}
```

失败示例：

```json
{
  "success": false,
  "trace_id": "trace_20260520_0001",
  "data": null,
  "error": {
    "code": "NO_TABLE_AVAILABLE",
    "message": "No available table for party_size=3 at 2026-05-20T15:55:00+08:00.",
    "user_message": "原餐厅当前已满，我会尝试为你切换到备选餐厅。",
    "recoverable": true,
    "details": {}
  }
}
```

#### 验收标准

1. 必须要求`X-Idempotency-Key`。
2. 满座只能返回`NO_TABLE_AVAILABLE`。
3. 成功凭证必须`mock_only:true`。
4. 查询可用后执行失败必须能触发Recovery。
5. 不得出现“真实餐厅已订座”。

---

### 13.4POST /api/v1/mock/orders/create

#### 接口定位

用于模拟创建订单，对应ToolAction.type=`order_item`。P0可选，但如果PlanContract生成了`order_item`动作，则必须可执行。

#### 是否P0

P0可选；纪念日蛋糕/鲜花服务可使用。若出现ToolAction则必须实现。

#### 调用方

ExecutorService。

#### 是否允许前端直接调用

普通用户页不直接调用；Debug/评委模式可直接调用测试。

#### Request Headers

| Header              | 是否必填 | 说明                      |
| ------------------- | ---: | ----------------------- |
| `Content-Type`      |    是 | `application/json`      |
| `X-Trace-Id`        |    是 | 复用PlanContract.trace_id |
| `X-Idempotency-Key` |    是 | 执行类接口必填                 |

#### Request Body

| 字段               | 类型     | 是否必填 | 来源                       | 说明       |
| ---------------- | ------ | ---: | ------------------------ | -------- |
| `plan_id`        | string |    是 | ToolAction.plan_id       | 当前计划     |
| `action_id`      | string |    是 | ToolAction.action_id     | 当前动作     |
| `poi_id`         | string |    否 | ToolAction.target_poi_id | 服务点      |
| `items`          | array  |    是 | ToolAction.payload       | Mock订单项目 |
| `scheduled_time` | string |    否 | ToolAction.payload       | ISO 8601 |
| `note`           | string |    否 | ToolAction.payload       | 备注       |

#### Response Data

| 字段             | 来源        |      是否进入03 Schema | 说明        |
| -------------- | --------- | -----------------: | --------- |
| `order_id`     | MockAPI生成 | 可进入ExecutionResult | Mock订单号   |
| `order_status` | MockAPI   |            可进入执行结果 | `created` |
| `mock_only`    | 固定        |                  是 | 必须true    |
| `created_at`   | 系统        |                  是 | ISO 8601  |

#### Mock标识

Mock订单凭证必须带`mock_only:true`。

#### 幂等规则

必须要求`X-Idempotency-Key`。重复请求返回同一Mock订单号。

#### failure_injection

P0一般不作为主阻断点。订单失败可由Executor标记`skipped`或`failed`，按05执行策略处理；不能影响核心行程，除非该服务被标记为must_have。

#### TraceLog

| event_type     | module            | visible_to_user | payload摘要                       |
| -------------- | ----------------- | --------------: | ------------------------------- |
| `tool_log`     | `MockAPIService`  |               是 | `tool_name:"order_item"`、status |
| `executor_log` | `ExecutorService` |               是 | action_id、订单凭证摘要                |
| `error_log`    | `MockAPIService`  |               否 | 参数错误、幂等冲突                       |

#### 错误码

`BAD_REQUEST`、`IDEMPOTENCY_CONFLICT`、`RESOURCE_NOT_FOUND`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

Verifier检查ToolAction完整性，不检查真实支付。Executor只生成Mock订单号，不做支付。失败通常不阻断主行程。

#### 示例

```http
POST /api/v1/mock/orders/create
Content-Type: application/json
X-Trace-Id: trace_20260520_0003
X-Idempotency-Key: idem_act_order_0001
```

```json
{
  "plan_id": "plan_20260520_0003",
  "action_id": "act_order_0001",
  "poi_id": "poi_cake_service_001",
  "items": [
    {
      "name": "小蛋糕",
      "amount": 98
    }
  ],
  "scheduled_time": "2026-05-20T17:30:00+08:00",
  "note": "轻仪式感，不写夸张祝福"
}
```

```json
{
  "success": true,
  "trace_id": "trace_20260520_0003",
  "data": {
    "order_id": "mock_order_20260520_0001",
    "order_status": "created",
    "display_text": "Mock订单号已生成",
    "mock_only": true,
    "created_at": "2026-05-20T13:10:00+08:00"
  },
  "error": null
}
```

#### 验收标准

1. ToolAction.type必须为`order_item`。
2. HTTP路径必须为`POST /api/v1/mock/orders/create`。
3. 不得写`create_order`。
4. 不得出现真实支付表述。
5. 成功必须返回`mock_only:true`。

---

### 13.5POST /api/v1/mock/messages/send

#### 接口定位

模拟消息发送，用于朋友局群聊消息、纪念日邀请话术、家庭行程通知等。

#### 是否P0

是。

#### 调用方

ExecutorService。

#### 是否允许前端直接调用

普通用户页不直接调用；前端可展示消息草案，Debug/评委模式可直接调用模拟发送。

#### Request Headers

| Header              | 是否必填 | 说明                      |
| ------------------- | ---: | ----------------------- |
| `Content-Type`      |    是 | `application/json`      |
| `X-Trace-Id`        |    是 | 复用PlanContract.trace_id |
| `X-Idempotency-Key` |    是 | 执行类接口必填                 |

#### Request Body

| 字段               | 类型     | 是否必填 | 来源                          | 说明                                              |
| ---------------- | ------ | ---: | --------------------------- | ----------------------------------------------- |
| `plan_id`        | string |    是 | ToolAction.plan_id          | 当前计划                                            |
| `action_id`      | string |    是 | ToolAction.action_id        | 当前动作                                            |
| `channel`        | string |    是 | ToolAction.payload          | `mock_wechat`、`mock_sms`、`copyable_text`等Mock通道 |
| `recipient_type` | string |    否 | ToolAction.payload          | spouse/group/self                               |
| `content`        | string |    是 | messages/ToolAction.payload | 消息内容                                            |
| `scheduled_time` | string |    否 | ToolAction.payload          | ISO 8601                                        |

#### Response Data

| 字段                | 来源        |      是否进入03 Schema | 说明               |
| ----------------- | --------- | -----------------: | ---------------- |
| `message_id`      | MockAPI生成 | 可进入ExecutionResult | Mock message_id  |
| `delivery_status` | MockAPI   |            可进入执行结果 | `mock_generated` |
| `mock_only`       | 固定        |                  是 | 必须true           |
| `created_at`      | 系统        |                  是 | ISO 8601         |

#### Mock标识

Mock消息必须带`mock_only:true`，不得暗示真实微信/短信已发送。

#### 幂等规则

必须要求`X-Idempotency-Key`。重复请求返回同一Mock message_id。

#### failure_injection

消息失败通常不阻断主行程。可返回`BAD_REQUEST`或`INTERNAL_ERROR`，Executor按非关键动作标记`failed`或`skipped`。

#### TraceLog

| event_type     | module            | visible_to_user | payload摘要                                 |
| -------------- | ----------------- | --------------: | ----------------------------------------- |
| `tool_log`     | `MockAPIService`  |               是 | `tool_name:"send_message"`、channel、status |
| `executor_log` | `ExecutorService` |               是 | action_id、message_id摘要                    |
| `error_log`    | `MockAPIService`  |               否 | 参数错误、幂等冲突                                 |

#### 错误码

`BAD_REQUEST`、`IDEMPOTENCY_CONFLICT`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

Verifier检查消息动作完整性。Executor生成Mock message_id。消息失败一般不触发Recovery，除非该消息动作被标记为关键执行动作。

#### 示例

```http
POST /api/v1/mock/messages/send
Content-Type: application/json
X-Trace-Id: trace_20260520_0003
X-Idempotency-Key: idem_act_msg_0001
```

```json
{
  "plan_id": "plan_20260520_0003",
  "action_id": "act_msg_0001",
  "channel": "mock_wechat",
  "recipient_type": "spouse",
  "content": "我排了一版不夸张的纪念日安排，先散步看展，再去一家安静餐厅，晚上不会太晚。",
  "scheduled_time": "2026-05-20T13:20:00+08:00"
}
```

```json
{
  "success": true,
  "trace_id": "trace_20260520_0003",
  "data": {
    "message_id": "mock_msg_20260520_0001",
    "delivery_status": "mock_generated",
    "display_text": "模拟消息已生成",
    "mock_only": true,
    "created_at": "2026-05-20T13:20:00+08:00"
  },
  "error": null
}
```

#### 验收标准

1. 必须返回Mock message_id。
2. 必须包含`mock_only:true`。
3. 用户文案不得写“微信已真实发送”或“短信已真实发送”。
4. 消息发送失败不应默认阻断主行程。
5. 朋友局和纪念日都可复用该接口。

---

## 14.SocialSignalMock设计

### 14.1GET /api/v1/mock/social-signals/{poi_id}

#### 接口定位

返回POI的Mock口碑摘要，用于展示P1 SocialSignalRadar能力。P0可预留，不作为主流程强依赖。

#### 是否P0

否，P1；P0可预留。

#### 调用方

CandidateRetriever / Frontend Debug / SocialSignalMockService。

#### 是否允许前端直接调用

普通用户页可展示已聚合的口碑卡，但必须标注Mock；Debug/评委模式可直接调用。P0主流程不得依赖它通过。

#### Request Headers

| Header         | 是否必填 | 说明                 |
| -------------- | ---: | ------------------ |
| `Accept`       |    是 | `application/json` |
| `X-Trace-Id`   |   建议 | 复用上游trace          |
| `X-Debug-Mode` |    否 | 可返回mock_sources    |

#### Request Parameters

| 字段       | 类型          | 是否必填 | 来源         | 说明       |
| -------- | ----------- | ---: | ---------- | -------- |
| `poi_id` | path string |    是 | POI.poi_id | `poi_`前缀 |

#### Response Data

| 字段              | 来源                         | 是否进入03 Schema | 说明                     |
| --------------- | -------------------------- | ------------: | ---------------------- |
| `signal_id`     | MockAPI生成                  |             是 | `sig_`前缀建议             |
| `poi_id`        | path                       |             是 | POI                    |
| `summary`       | `mock_social_signals.json` |             是 | 口碑摘要                   |
| `positive_tags` | fixture                    |             是 | 正向标签                   |
| `negative_tags` | fixture                    |             是 | 负向标签                   |
| `source_type`   | 固定                         |             是 | 必须`mock_social_signal` |
| `confidence`    | fixture                    |             是 | 0-1                    |
| `is_mock`       | 固定                         |             是 | 必须true                 |
| `mock_sources`  | fixture                    |             是 | 模拟来源，不代表真实爬取           |
| `updated_at`    | fixture/系统                 |             是 | ISO 8601               |

#### Mock标识

SocialSignalMock必须带：

```json
{
  "is_mock": true,
  "source_type": "mock_social_signal"
}
```

#### 幂等规则

GET天然幂等。

#### failure_injection

可测试缺失口碑卡，返回`SOCIAL_SIGNAL_MISSING`。缺失不阻断主流程，只隐藏口碑卡。

#### TraceLog

| event_type  | module           | visible_to_user | payload摘要                                             |
| ----------- | ---------------- | --------------: | ----------------------------------------------------- |
| `tool_log`  | `MockAPIService` |            P1可见 | `tool_name:"get_social_signal_mock"`、poi_id           |
| `error_log` | `MockAPIService` |               否 | `SOCIAL_SIGNAL_MISSING`或`SOCIAL_SIGNAL_MOCK_REQUIRED` |

#### 错误码

`SOCIAL_SIGNAL_MISSING`、`SOCIAL_SIGNAL_MOCK_REQUIRED`、`PLAN_STEP_POI_NOT_FOUND`、`INTERNAL_ERROR`。

#### 与Verifier/Executor/Recovery关系

P0不得因SocialSignalMock缺失而失败。P1可用于风险解释或候选排序，但不能替代餐厅余位、票务、路线、天气等硬状态。

#### 示例

```http
GET /api/v1/mock/social-signals/poi_light_food_003
X-Trace-Id: trace_20260520_0001
```

```json
{
  "success": true,
  "trace_id": "trace_20260520_0001",
  "data": {
    "signal_id": "sig_20260520_0001",
    "poi_id": "poi_light_food_003",
    "summary": "Mock口碑显示环境安静、轻食选择较多，但晚高峰可能需要等位。",
    "positive_tags": ["安静", "低卡选择多", "适合家庭"],
    "negative_tags": ["晚高峰等位"],
    "source_type": "mock_social_signal",
    "confidence": 0.78,
    "is_mock": true,
    "mock_sources": ["mock_xiaohongshu", "mock_douyin", "mock_dianping"],
    "updated_at": "2026-05-20T12:00:00+08:00"
  },
  "error": null
}
```

#### 验收标准

1. 必须包含`is_mock:true`。
2. 必须包含`source_type:"mock_social_signal"`。
3. 不得承诺真实抓取小红书/抖音/点评。
4. 缺失时不阻断主流程。
5. 未标Mock时返回`SOCIAL_SIGNAL_MOCK_REQUIRED`或隐藏口碑卡。

---

## 15.failure_injection失败注入设计

### 15.1设计目标

failure_injection用于Demo、测试和评委Debug，验证LifePilot能处理动态失败，而不是只跑通成功路径。

### 15.2可注入错误

#### P0必须覆盖

| 场景      | 错误码                              | 触发接口                                             | 预期行为                         |
| ------- | -------------------------------- | ------------------------------------------------ | ---------------------------- |
| 餐厅满座    | `NO_TABLE_AVAILABLE`             | `POST /api/v1/mock/restaurants/{poi_id}/reserve` | Executor触发Recovery，替换备选餐厅    |
| 活动满员    | `ACTIVITY_FULL`                  | `POST /api/v1/mock/activities/{poi_id}/book`     | Executor触发Recovery，替换活动或调整时间 |
| 可执行窗口过期 | `PLAN_EXECUTABLE_WINDOW_EXPIRED` | 执行类接口或`refresh-window`前置检查                       | 重新状态查询和Verifier              |

#### P1/P2预留

| 场景     | 错误码                 | 预期行为         |
| ------ | ------------------- | ------------ |
| 路线延迟   | `ROUTE_DELAY`       | 换近POI或压缩活动时间 |
| 天气风险升高 | `WEATHER_RISK_HIGH` | 户外改室内        |
| 预算超限   | `BUDGET_EXCEEDED`   | 替换低价餐厅/活动    |

### 15.3触发方式

| 方式                                     | 说明                     |  普通用户可见 |
| -------------------------------------- | ---------------------- | ------: |
| 请求参数`failure_scenario_id`              | Debug/测试直接指定           |       否 |
| Header `X-Debug-Mode:true` + fixture规则 | 评委演示                   |       否 |
| `mock_failure_scenarios.json`预设        | 自动化测试                  |       否 |
| 时间推进导致窗口过期                             | 可作为真实Demo行为展示，但不展示注入细节 | 不展示注入字段 |

### 15.4可见性规则

1. 普通用户页只看到“原餐厅已满，正在切换备选”。
2. Debug/评委模式可展示`failure_scenario_id`和命中规则。
3. Trace中可记录脱敏failure摘要，但不得展示给普通用户。
4. failure_injection不得进入PlanContract领域Schema。

### 15.5Trace要求

| 事件    | event_type     | module                             | 说明                             |
| ----- | -------------- | ---------------------------------- | ------------------------------ |
| 注入命中  | `tool_log`     | `MockAPIService`                   | payload中记录tool_name和error_code |
| 业务失败  | `error_log`    | `MockAPIService`或`ExecutorService` | 记录错误码                          |
| 触发恢复  | `recovery_log` | `RecoveryPlanner`                  | 记录trigger和updated_plan_id      |
| 恢复后重验 | `verifier_log` | `VerifierService`                  | 记录新VerifierResult              |

### 15.6Recovery要求

执行失败后：

```text
Executor收到NO_TABLE_AVAILABLE/ACTIVITY_FULL
→ RecoveryPlanner读取原PlanContract和failed_action
→ 搜索/读取备选POI
→ 重新调用MockAPI状态查询、路线、天气
→ 重新Verifier
→ 生成RecoveryResult
→ 创建新的完整PlanContract
→ RecoveryResult.updated_plan_id指向新plan
→ Executor基于新ToolAction继续执行
```

禁止原地覆盖原PlanContract。

---

## 16.幂等、状态持久化与Mock凭证设计

### 16.1幂等键存储

建议使用`mock_idempotency_store.json`或SQLite表。

#### 结构示例

```json
{
  "items": [
    {
      "idempotency_key": "idem_act_reserve_0001",
      "plan_id": "plan_20260520_0001",
      "action_id": "act_reserve_0001",
      "tool_name": "reserve_restaurant",
      "request_hash": "hash_plan_action_payload_001",
      "response_ref": "mock_reservation_20260520_0001",
      "trace_id": "trace_20260520_0001",
      "created_at": "2026-05-20T13:06:00+08:00"
    }
  ]
}
```

### 16.2幂等判断规则

HTTP层幂等键只认Header `X-Idempotency-Key`。

| 来源 | 用途 | 是否权威 |
|---|---|---:|
| `X-Idempotency-Key` | HTTP层防重复提交 | 是 |
| `ToolAction.idempotency_key` | Agent内部动作追踪 | 是，但只限内部 |
| `body.idempotency_key` | 兼容旧示例，可忽略或校验一致 | 否 |

兼容规则：

| 情况 | 返回 |
|---|---|
| 无Header | `BAD_REQUEST` |
| 有Header无body.idempotency_key | 正常 |
| 有Header且body.idempotency_key一致 | 正常 |
| 有Header且body.idempotency_key不一致 | `BAD_REQUEST` |

| 情况                           | 返回                          |
| ---------------------------- | --------------------------- |
| 新key + 合法请求                  | 执行动作，生成Mock凭证，写入幂等记录        |
| 同key + 同plan/action/payload  | 返回同一Mock凭证                  |
| 同key + 不同plan/action/payload | `IDEMPOTENCY_CONFLICT`      |
| 缺少key                        | `BAD_REQUEST`               |
| key存在但凭证记录丢失                 | `INTERNAL_ERROR`或重建失败，测试应发现 |

### 16.3状态持久化

| 数据         | 存储位置                                                                                             | 写入时机                      |
| ---------- | ------------------------------------------------------------------------------------------------ | ------------------------- |
| 查询fixture  | `mock_pois.json`、`mock_status.json`、`mock_routes.json`、`mock_weather.json`，以及06内部`mock_inventory.json` | 预置或测试前加载                  |
| 执行记录       | `executions.json`                                                                                | Executor每个动作完成或失败         |
| 幂等记录       | `mock_idempotency_store.json`                                                                    | 执行类接口成功或可重复失败时            |
| Trace      | `traces.json`                                                                                    | 每次MockAPI调用               |
| Recovery结果 | plans存储或recovery结果表                                                                              | Recovery完成后               |
| 库存扣减       | `mock_inventory.json`或运行时状态表                                                                     | 预约/订座成功后，可按Demo需求决定是否持久扣减 |

### 16.4Mock凭证类型

| 凭证类型      | 生成接口                                             | 示例ID                             | 必须字段             |
| --------- | ------------------------------------------------ | -------------------------------- | ---------------- |
| 活动预约凭证    | `POST /api/v1/mock/activities/{poi_id}/book`     | `mock_booking_20260520_0001`     | `mock_only:true` |
| 餐厅订座/排号凭证 | `POST /api/v1/mock/restaurants/{poi_id}/reserve` | `mock_reservation_20260520_0001` | `mock_only:true` |
| Mock订单凭证  | `POST /api/v1/mock/orders/create`                | `mock_order_20260520_0001`       | `mock_only:true` |
| Mock消息凭证  | `POST /api/v1/mock/messages/send`                | `mock_msg_20260520_0001`         | `mock_only:true` |

所有凭证文案只能写：

```text
Mock预约号已生成
Mock订座号已生成
Mock订单号已生成
模拟消息已生成
```

不得写：

```text
餐厅已真实订座
票务已真实锁定
订单已真实支付
微信已发送
短信已发送
```

### 16.5Recovery后的关联

Recovery后：

| 对象                 | 规则                                                     |
| ------------------ | ------------------------------------------------------ |
| 原`plan_id`         | 状态进入`recovered`                                        |
| 新`updated_plan_id` | 指向新的完整PlanContract                                     |
| 原ToolAction        | 标记`failed`或`recovered`                                 |
| 新ToolAction        | 使用新的`action_id`和新的`idempotency_key`                    |
| 幂等键                | 不复用原失败动作的HTTP幂等键                                       |
| 凭证                 | 关联新`execution_id`、新`plan_id`、新`action_id`、同一`trace_id` |
| Trace              | 同一trace_id下串联失败、Recovery、重验、再执行                        |

---

## 17.MockAPI与Verifier联调协议

### 17.1Verifier调用MockAPI

Verifier必须使用MockAPI或规则状态，不允许LLM替代。

| Verifier检查项           | MockAPI输入                            | MockAPI输出                                               | 失败/Warning       |
| --------------------- | ------------------------------------ | ------------------------------------------------------- | ---------------- |
| `opening_hours`       | `poi_id`、`arrival_time`              | POIStatus/RestaurantStatus.open_status                  | closed时fail      |
| `restaurant_capacity` | `poi_id`、`arrival_time`、`party_size` | `available_tables`、`reservation_available`、`risk_level` | 0桌fail           |
| `queue_time`          | `poi_id`、`arrival_time`、`party_size` | `queue_minutes`                                         | 超过容忍warning/fail |
| `activity_ticket`     | `poi_id`、`arrival_time`、`party_size` | `remaining_tickets`、`booking_available`                 | 不足fail           |
| `distance_constraint` | 起终点、transport_mode、departure_time    | RouteEstimate.distance_km                               | 超出约束warning/fail |
| `time_feasibility`    | timeline、RouteEstimate               | duration_minutes                                        | 时间重叠或超窗fail      |
| `weather_risk`        | area/time_window                     | WeatherStatus                                           | 高风险warning/fail  |
| `executable_window`   | POIStatus/RestaurantStatus.expire_at     | 最小expire_at                                             | 过期fail           |

### 17.2ExecutableWindow计算

建议：

```text
status_expire_at = min(
  poi_status.expire_at for activity/service/walk status if exists,
  restaurant_status.expire_at for restaurant steps if exists
)

window_minutes = max(0, status_expire_at - now)

confidence = min(
  verifier_score,
  route_estimate.confidence,
  status_confidence
)
```

P0只直接使用03状态对象中明确存在的`expire_at`字段，即`POIStatus.expire_at`和`RestaurantStatus.expire_at`。`WeatherStatus`和`RouteEstimate`不直接贡献`expire_at`，除非未来03扩展对应字段。

天气风险和路线交通只进入`risk_factors`、`reasons`和`confidence`，不直接计算窗口过期时间。`route_ttl_minutes`可以作为`MockAPIService`内部配置，但不得进入03 Schema或HTTP响应。

### 17.3Verifier联调验收

1. Verifier不得读取LLM生成的“有位”文案作为状态。
2. 每个restaurant节点必须有RestaurantStatus输入。
3. 每个activity节点若booking_required=true，必须有POIStatus票务输入。
4. 每段transport必须有RouteEstimate。
5. 带户外walk节点时必须有WeatherStatus或明确降级warning。
6. `expire_at`过期必须触发`PLAN_EXECUTABLE_WINDOW_EXPIRED`或刷新窗口。
7. VerifierResult.status只能是`pass`、`warning`、`fail`。

---

## 18.MockAPI与Executor联调协议

### 18.1Executor调用MockAPI

Executor只执行ToolAction，不执行自然语言。

| ToolAction.type      | HTTP接口                                           | 是否执行类 | 幂等 |
| -------------------- | ------------------------------------------------ | ----: | -: |
| `book_activity`      | `POST /api/v1/mock/activities/{poi_id}/book`     |     是 | 必须 |
| `reserve_restaurant` | `POST /api/v1/mock/restaurants/{poi_id}/reserve` |     是 | 必须 |
| `order_item`         | `POST /api/v1/mock/orders/create`                |     是 | 必须 |
| `send_message`       | `POST /api/v1/mock/messages/send`                |     是 | 必须 |

查询类ToolAction仅用于Trace和Verifier上下文：

| ToolAction.type         | HTTP接口                                         |
| ----------------------- | ---------------------------------------------- |
| `get_poi_status`        | `GET /api/v1/mock/poi/{poi_id}/status`         |
| `get_restaurant_status` | `GET /api/v1/mock/restaurants/{poi_id}/status` |
| `estimate_route`        | `GET /api/v1/mock/routes/estimate`             |
| `get_weather`           | `GET /api/v1/mock/weather`                     |

### 18.2Executor执行前检查

Executor调用执行类Mock接口前必须检查：

1. PlanContract.status是否允许执行。
2. VerifierResult.status是否为`pass`或`warning`。
3. ExecutableWindow.expire_at是否未过期。
4. ToolAction.status是否为`pending`。
5. ToolAction.idempotency_key是否存在。
6. HTTP请求是否携带`X-Idempotency-Key`。
7. target_poi_id是否存在且为`poi_`前缀。

### 18.3Executor联调验收

1. 执行类接口无幂等键必须返回`BAD_REQUEST`。
2. `order_item`必须映射到`POST /api/v1/mock/orders/create`。
3. 执行成功必须生成Mock凭证。
4. Mock凭证必须写入ExecutionResult或action.result。
5. `NO_TABLE_AVAILABLE`和`ACTIVITY_FULL`必须触发Recovery。
6. 消息和订单失败不应默认阻断主行程，除非被配置为关键动作。
7. Executor不得声称真实平台执行成功。

---

## 19.MockAPI与Recovery联调协议

### 19.1Recovery触发源

| 触发源    | 错误码                              | Recovery策略                |
| ------ | -------------------------------- | ------------------------- |
| 餐厅订座失败 | `NO_TABLE_AVAILABLE`             | 搜索同区域、同预算、同饮食偏好的餐厅        |
| 活动预约失败 | `ACTIVITY_FULL`                  | 搜索同区域、同场景活动或调整场次          |
| 窗口过期   | `PLAN_EXECUTABLE_WINDOW_EXPIRED` | refresh-window或重新Verifier |
| 路线延迟   | `ROUTE_DELAY`                    | 换近POI、压缩活动、调整出发时间         |
| 天气风险   | `WEATHER_RISK_HIGH`              | 户外改室内                     |
| 预算超限   | `BUDGET_EXCEEDED`                | 替换低价节点                    |

### 19.2Recovery调用MockAPI步骤

```text
读取失败动作和原PlanContract
→ 识别替换类型
→ 调用search接口找备选
→ 调用status接口确认余位/票务
→ 调用routes/estimate确认转场时间
→ 调用weather确认户外风险
→ 生成PlanBuildCandidate
→ Verifier重新验证
→ PlanContractBuilder生成新完整PlanContract
→ Full SchemaValidator
→ 写RecoveryResult.updated_plan_id
```

### 19.3Recovery版本化要求

| 项              | 要求                                  |
| -------------- | ----------------------------------- |
| 原计划            | 不原地覆盖                               |
| 新计划            | 新`plan_id`，如`plan_20260520_0001_r1` |
| RecoveryResult | 必须包含`updated_plan_id`               |
| Trace          | 复用原`trace_id`                       |
| ToolAction     | 替换节点生成新action_id                    |
| 幂等             | 新动作使用新幂等键                           |
| Verifier       | Recovery后必须重新Verifier               |

### 19.4Recovery联调验收

1. `NO_TABLE_AVAILABLE`后必须能切换到备选餐厅并重新Verifier。
2. `ACTIVITY_FULL`后必须能切换活动或场次并重新Verifier。
3. RecoveryResult不得缺少`original`、`replacement`、`diff`、`verifier_result`。
4. `updated_plan_id`必须指向新的完整PlanContract。
5. 新计划通过Full SchemaValidator后才能返回。
6. 普通用户页展示替换说明，不展示failure_injection细节。

---

## 20.MockAPI与前端工具调用链展示

### 20.1普通用户页展示

普通用户页展示“工具调用摘要”，让用户理解系统不是凭空生成。

示例：

```text
已检查亲子场馆余票：余票充足
已检查轻食餐厅余位：4人位剩余2桌
已估算路线：约25分钟
已检查天气：户外风险低
```

### 20.2Debug/评委模式展示

Debug/评委模式可展示：

| 内容                  |    是否可展示 |
| ------------------- | -------: |
| Mock接口路径            |        是 |
| tool_name           |        是 |
| 请求参数摘要              |     是，脱敏 |
| 响应状态摘要              |        是 |
| error_code          |        是 |
| failure_scenario_id | 是，仅Debug |
| ToolAction payload  |     是，脱敏 |
| fixture命中规则         |   可展示简化版 |

### 20.3永不展示

| 内容                       |
| ------------------------ |
| API Key                  |
| 底层Prompt                 |
| LLM推理链                   |
| 高敏MemoryCandidate        |
| failure_injection细节给普通用户 |
| 真实平台已执行的误导表述             |

---

## 21.Trace、日志与Debug可见性

### 21.1MockAPI Trace要求

Trace归属规则：

| 事件 | module | event_type |
|---|---|---|
| 候选召回摘要 | `CandidateRetriever` | `poi_log` |
| POI搜索接口调用 | `MockAPIService` | `tool_log` |
| 餐厅搜索接口调用 | `MockAPIService` | `tool_log` |
| 状态查询 | `MockAPIService` | `tool_log` |
| 路线/天气查询 | `MockAPIService` | `tool_log` |
| Mock执行动作 | `MockAPIService` | `tool_log` |
| 错误 | `MockAPIService`/`ExecutorService` | `error_log` |

`MockAPIService`不得写`poi_log`。`poi_log`只表示CandidateRetriever层的候选召回摘要。

每次MockAPI调用必须写`tool_log`：

```json
{
  "event_type": "tool_log",
  "module": "MockAPIService",
  "payload": {
    "tool_name": "get_restaurant_status",
    "poi_id": "poi_light_food_003",
    "status": "success"
  }
}
```

错误必须写`error_log`：

```json
{
  "event_type": "error_log",
  "module": "MockAPIService",
  "payload": {
    "tool_name": "reserve_restaurant",
    "error_code": "NO_TABLE_AVAILABLE",
    "recoverable": true
  }
}
```

禁止新增：

```text
mock_call
mock_log
api_log
```

### 21.2Trace事件类型

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

### 21.3trace_id规则

| 场景               | trace_id来源              |
| ---------------- | ----------------------- |
| 主计划生成            | Backend创建或复用请求头         |
| MockAPI业务调用      | 复用PlanContract.trace_id |
| Executor执行       | 复用PlanContract.trace_id |
| Recovery         | 复用原trace_id             |
| Debug单独调用MockAPI | 可新建trace_id             |
| 缺失且无法创建          | 返回`TRACE_ID_MISSING`    |

### 21.4可见性

| Trace内容            |  普通用户页 | Debug/评委模式 |
| ------------------ | -----: | ---------: |
| 工具调用摘要             |      是 |          是 |
| tool_name          |  可简化展示 |          是 |
| 参数摘要               |      否 |       是，脱敏 |
| error_code         | 可转用户文案 |          是 |
| failure_injection  |      否 |          是 |
| Prompt/推理链/API Key |      否 |          否 |

---

## 22.P0三大场景Mock数据包

### 22.1家庭亲子Mock数据包

#### 目标

支持输入：

```text
今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。
```

#### 数据包表

| 数据项    | 示例ID                         | 类型                 | 作用                            |
| ------ | ---------------------------- | ------------------ | ----------------------------- |
| 家庭起点   | `poi_home_anchor_001`        | transport_anchor   | 出发/返程锚点                       |
| 亲子活动   | `poi_child_science_001`      | activity           | 主要亲子节点                        |
| 低卡轻食餐厅 | `poi_light_food_003`         | restaurant         | 主餐厅                           |
| 备选低卡餐厅 | `poi_light_food_007`         | restaurant         | `NO_TABLE_AVAILABLE`后Recovery |
| 散步点    | `poi_jinshahu_walk_001`      | walk_spot          | 饭后轻松散步                        |
| 室内备选   | `poi_kids_bookstore_001`     | walk_spot/activity | 天气风险时替换                       |
| 路线规则   | `route_home_child_001`等      | mock_routes        | 串联时间线                         |
| 天气规则   | `weather_jinshahu_pm_001`    | weather            | 户外风险                          |
| 餐厅状态规则 | `status_light_food_003_pm`   | RestaurantStatus来源 | 余位中等风险                        |
| 活动余票规则 | `inv_child_science_001_1400` | POIStatus来源        | 可预约                           |
| 失败注入   | `fail_no_table_family_001`   | failure            | 餐厅满座                          |
| 失败注入   | `fail_activity_full_001`     | failure            | 活动满员                          |

#### 最小POI样例

```json
[
  {
    "poi_id": "poi_home_anchor_001",
    "name": "下沙家庭出发点",
    "category": "transport_anchor",
    "mock_group": "transport_anchor",
    "area": "xiasha",
    "tags": ["home_anchor"],
    "mock_only": true,
    "updated_at": "2026-05-20T09:00:00+08:00"
  },
  {
    "poi_id": "poi_light_food_007",
    "name": "谷物星球轻食",
    "category": "restaurant",
    "mock_group": "restaurant",
    "area": "jinshahu",
    "tags": ["low_calorie", "light_food", "family_friendly", "backup"],
    "price_per_person": 58,
    "mock_only": true,
    "updated_at": "2026-05-20T09:00:00+08:00"
  }
]
```

#### 验收点

1. 能生成亲子活动+低卡餐厅+散步路线。
2. 餐厅状态能给出中等风险和`expire_at`。
3. `NO_TABLE_AVAILABLE`后能切到`poi_light_food_007`。
4. `ACTIVITY_FULL`后能切到同区域室内备选活动。
5. 老婆减脂约束体现为低卡/轻食，而不是高热量餐厅。

---

### 22.2朋友局共识Mock数据包

#### 目标

支持输入：

```text
下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。
```

#### 候选组合

| 组合    | POI组合                                                                 |        预算 | 步行 | 排队 | 适配偏好   |
| ----- | --------------------------------------------------------------------- | --------: | -: | -: | ------ |
| 拍照逛展版 | `poi_light_exhibit_001` + `poi_photo_spot_001` + `poi_quiet_food_002` |  人均90-120 | 中低 |  低 | 拍照、轻展览 |
| 好吃不累版 | `poi_local_food_001` + `poi_mall_walk_001`                            | 人均100-150 |  低 |  中 | 吃饭聊天   |
| 桌游聊天版 | `poi_boardgame_001` + `poi_budget_food_001`                           |  人均60-100 |  低 |  低 | 坐着聊天   |
| 低预算版  | `poi_jinshahu_walk_001` + `poi_budget_food_002`                       |   人均30-60 |  中 |  低 | 预算敏感   |

#### 状态要求

| 能力          | 要求                             |
| ----------- | ------------------------------ |
| finalize后重验 | 最终方案必须重新调用MockAPI状态查询和Verifier |
| 预算差异        | 每个组合必须能展示预算差异                  |
| 排队差异        | 餐厅状态必须支持不同queue_minutes        |
| 路线差异        | 每组必须有`mock_routes`规则          |
| 失败恢复        | 最终餐厅满座时能替换到同预算备选               |

#### 验收点

1. 至少3个候选方案可投票。
2. 支持预算、步行、排队差异。
3. finalize后的最终PlanContract不能直接使用旧候选状态，必须重新Verifier。
4. SocialSignalMock缺失不阻断朋友局主流程。
5. 群聊消息通过`POST /api/v1/mock/messages/send`模拟生成Mock message_id。

---

### 22.3纪念日情绪导航Mock数据包

#### 目标

支持输入：

```text
想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。
```

#### 数据包表

| 数据项      | 示例ID                                | 类型                 | 作用             |
| -------- | ----------------------------------- | ------------------ | -------------- |
| 安静餐厅     | `poi_anniversary_restaurant_001`    | restaurant         | 主餐厅            |
| 备选安静餐厅   | `poi_anniversary_restaurant_002`    | restaurant         | 满座Recovery     |
| 看展点      | `poi_light_exhibit_001`             | activity           | 降低直接吃饭突兀感      |
| 散步点      | `poi_jinshahu_walk_001`             | walk_spot          | 情绪节奏           |
| 合照点      | `poi_photo_spot_001`                | walk_spot          | 轻仪式感           |
| 蛋糕服务     | `poi_cake_service_001`              | service            | 可选`order_item` |
| 鲜花服务     | `poi_flower_service_001`            | service            | P1可选           |
| Mock消息模板 | `msg_anniversary_light_001`         | message            | 自然邀请话术         |
| 餐厅状态     | `status_anniversary_restaurant_001` | RestaurantStatus来源 | 安静、可订          |
| 消息凭证     | `mock_msg_...`                      | execution          | 只模拟生成          |

#### 消息模板要求

```text
不写“已真实发送”。
只写“模拟消息已生成”或“可复制消息已生成”。
```

#### 验收点

1. 流程体现“看展/散步→安静餐厅→合照/蛋糕→返程”。
2. 仪式感强度为轻，不夸张。
3. 订座成功返回Mock订座号。
4. 蛋糕/鲜花如生成ToolAction，使用`order_item`。
5. 消息使用Mock message凭证，不真实发送微信/短信。

---

## 23.P1/P2扩展预留

| 能力                | P1/P2接口/文件                                                            | P0处理    |
| ----------------- | --------------------------------------------------------------------- | ------- |
| SocialSignalRadar | `GET /api/v1/mock/social-signals/{poi_id}`、`mock_social_signals.json` | 缺失不阻断   |
| 天气高风险Recovery     | `WEATHER_RISK_HIGH`                                                   | P0可预留   |
| 路线延迟Recovery      | `ROUTE_DELAY`                                                         | P0可预留   |
| 预算超限Recovery      | `BUDGET_EXCEEDED`                                                     | P0可预留   |
| 更细库存系统            | SQLite/PostgreSQL库存表                                                  | P0可JSON |
| Bench自动评测         | benchmark fixtures                                                    | P1      |
| 多区域扩展             | area config                                                           | P2      |

扩展原则：

1. 只追加可选字段或内部fixture，不破坏03/04契约。
2. SocialSignal始终标Mock，直到接入真实授权数据前不得改表述。
3. P1/P2错误码只能使用04 reserved列表，不新增同义错误码。

---

## 24.错误处理与降级策略

### 24.1错误码使用表

#### P0 active

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
BAD_REQUEST
UNAUTHORIZED_DEMO_USER
RESOURCE_NOT_FOUND
IDEMPOTENCY_CONFLICT
RATE_LIMITED
INTERNAL_ERROR
```

#### P1/P2 reserved

```text
ROUTE_DELAY
WEATHER_RISK_HIGH
BUDGET_EXCEEDED
CONSENSUS_CONFLICT
SOCIAL_SIGNAL_MISSING
MEMORY_UNAVAILABLE
```

禁止新增：

```text
MOCK_API_FAILED
PLAN_CREATE_FAILED
RESTAURANT_FULL
TICKET_SOLD_OUT
UNKNOWN_STATUS
```

### 24.2降级策略

| 错误                               | 用户侧展示                | 系统处理                      |
| -------------------------------- | -------------------- | ------------------------- |
| `MOCK_STATUS_MISSING`            | 当前地点状态未知，已降低置信度或切换备选 | Verifier warning或Recovery |
| `NO_TABLE_AVAILABLE`             | 原餐厅已满，正在切换备选         | Executor触发Recovery        |
| `ACTIVITY_FULL`                  | 当前活动满员，正在找替代活动       | Executor触发Recovery        |
| `PLAN_EXECUTABLE_WINDOW_EXPIRED` | 当前窗口已过期，需要重新检查       | refresh-window或重新verify   |
| `SOCIAL_SIGNAL_MISSING`          | 不展示口碑卡               | 不阻断                       |
| `BAD_REQUEST`                    | 请求异常，请重试             | 前端修参或提示                   |
| `IDEMPOTENCY_CONFLICT`           | 请勿重复提交，刷新后再试         | 拒绝执行                      |
| `INTERNAL_ERROR`                 | 系统异常，请重试             | 记录error_log               |

---

## 25.测试验收标准

### 25.1Mock接口基础验收

| 类别     | 标准                                                       |
| ------ | -------------------------------------------------------- |
| 路径     | 所有Mock路径必须是`/api/v1/mock/...`                            |
| 响应格式   | 成功/失败都符合04标准响应                                           |
| 时间     | 所有时间字段为ISO 8601                                          |
| ID     | `poi_id`、`route_id`、`plan_id`、`action_id`、`trace_id`前缀正确 |
| Mock标识 | 按对象类型正确标识                                                |
| 错误码    | 只使用04定义错误码                                               |
| Trace  | MockAPI调用写`tool_log`，错误写`error_log`                      |

### 25.2状态对象验收

1. POIStatus/RestaurantStatus必须带`expire_at`。
2. RouteEstimate必须包含完整字段和`source:"mock_api"`。
3. WeatherStatus必须使用03完整结构，不由LLM生成。
4. SocialSignalMock必须带`is_mock:true`和`source_type:"mock_social_signal"`。
5. Mock状态缺失返回`MOCK_STATUS_MISSING`。
6. 状态查询不得生成执行凭证。

### 25.3幂等验收

1. 执行类接口缺少`X-Idempotency-Key`返回`BAD_REQUEST`。
2. 同一key同一动作重复请求返回同一凭证。
3. 同一key不同plan/action返回`IDEMPOTENCY_CONFLICT`。
4. 幂等记录能关联`execution_id`、`plan_id`、`action_id`、`trace_id`。
5. Recovery后的新ToolAction不得复用旧失败动作的HTTP幂等键。

### 25.4failure_injection验收

1. `NO_TABLE_AVAILABLE`能触发餐厅Recovery。
2. `ACTIVITY_FULL`能触发活动Recovery。
3. `PLAN_EXECUTABLE_WINDOW_EXPIRED`能触发refresh-window或重新verify。
4. 普通用户页不展示failure_injection。
5. Debug/评委模式可查看脱敏failure_scenario。
6. failure_injection命中写`tool_log`和必要`error_log`。

### 25.5端到端验收

#### 家庭亲子

1. 生成亲子活动+低卡餐厅+散步时间线。
2. 查询亲子活动状态、餐厅状态、路线、天气。
3. 展示ExecutableWindow。
4. 餐厅满座后切换备选餐厅。
5. Recovery后生成`updated_plan_id`并重新Verifier。

#### 朋友局共识

1. 生成3-4个候选组合。
2. 投票finalize后最终方案重新Verifier。
3. 最终方案执行餐厅订座和消息Mock。
4. SocialSignalMock缺失不阻断主流程。

#### 纪念日

1. 生成轻仪式感时间线。
2. 安静餐厅状态可查。
3. 蛋糕/鲜花如执行，使用`order_item`。
4. 消息只生成Mock message_id，不真实发送。

### 25.6禁止项验收

测试必须扫描以下问题：

| 禁止项                             | 检查方式                    |
| ------------------------------- | ----------------------- |
| `create_order`作为ToolAction.type | 全局grep，必须为0             |
| `/api/mock/...`旧路径              | 全局grep，必须为0，除非明确写“早期示意” |
| `MOCK_API_FAILED`等新增错误码         | 错误码白名单校验                |
| `mock_call` Trace事件             | TraceLog枚举校验            |
| 非ISO时间                          | 正则校验                    |
| 普通用户页展示failure_injection        | 前端快照测试                  |
| 真实支付/短信/微信/订座/票务表述              | 文案敏感词扫描                 |

---

## 26.不做什么与安全边界

1. 不做真实支付。
2. 不做真实短信/微信发送。
3. 不做真实订座。
4. 不做真实票务锁定。
5. 不做真实第三方爬取。
6. 不做全城覆盖。
7. 不让LLM决定余位、票务、路线、天气或执行成功。
8. 不把Mock能力包装成真实平台能力。
9. 不向普通用户展示failure_injection。
10. 不暴露Prompt、LLM推理链、API Key。
11. 不保存真实用户隐私数据到Mock fixture。
12. 不在06中新增03/04未定义的领域字段、状态名、API路径或错误码。
13. 不把SocialSignalMock写成P0强依赖。
14. 不把Recovery写成原地覆盖PlanContract。
15. 不把查询快照当作执行锁定结果。

---

## 27.附录：Mock接口、ToolAction、错误码、Fixture速查表

### 27.1Mock接口速查表

| HTTP接口                                           | 查询/执行 |   P0 | ToolAction.type         | 幂等                    |
| ------------------------------------------------ | ----- | ---: | ----------------------- | --------------------- |
| `GET /api/v1/mock/poi/search`                    | 查询    |    是 | -                       | GET天然幂等               |
| `GET /api/v1/mock/restaurants/search`            | 查询    |    是 | -                       | GET天然幂等               |
| `GET /api/v1/mock/poi/{poi_id}/status`           | 查询    |    是 | `get_poi_status`        | GET天然幂等               |
| `GET /api/v1/mock/restaurants/{poi_id}/status`   | 查询    |    是 | `get_restaurant_status` | GET天然幂等               |
| `GET /api/v1/mock/routes/estimate`               | 查询    |    是 | `estimate_route`        | GET天然幂等               |
| `GET /api/v1/mock/weather`                       | 查询    |    是 | `get_weather`           | GET天然幂等               |
| `POST /api/v1/mock/activities/{poi_id}/book`     | 执行    |    是 | `book_activity`         | 必须`X-Idempotency-Key` |
| `POST /api/v1/mock/restaurants/{poi_id}/reserve` | 执行    |    是 | `reserve_restaurant`    | 必须`X-Idempotency-Key` |
| `POST /api/v1/mock/orders/create`                | 执行    | P0可选 | `order_item`            | 必须`X-Idempotency-Key` |
| `POST /api/v1/mock/messages/send`                | 执行    |    是 | `send_message`          | 必须`X-Idempotency-Key` |
| `GET /api/v1/mock/social-signals/{poi_id}`       | 查询    |   P1 | -                       | GET天然幂等               |

### 27.2Mock标识速查表

| 对象               | 必须字段                                              |
| ---------------- | ------------------------------------------------- |
| Mock POI         | `mock_only:true`                                  |
| Mock状态           | `source:"mock_api"`或`mock_only:true`              |
| Mock凭证           | `mock_only:true`                                  |
| SocialSignalMock | `is_mock:true`、`source_type:"mock_social_signal"` |
| Mock消息           | `mock_only:true`，不得暗示真实微信/短信已发送                   |

### 27.3错误码速查表

| 场景             | 正确错误码                            | 禁止写法                   |
| -------------- | -------------------------------- | ---------------------- |
| 餐厅满座           | `NO_TABLE_AVAILABLE`             | `RESTAURANT_FULL`      |
| 活动满员           | `ACTIVITY_FULL`                  | `TICKET_SOLD_OUT`      |
| Mock状态缺失       | `MOCK_STATUS_MISSING`            | `UNKNOWN_STATUS`       |
| 执行窗口过期         | `PLAN_EXECUTABLE_WINDOW_EXPIRED` | `WINDOW_EXPIRED`       |
| 幂等冲突           | `IDEMPOTENCY_CONFLICT`           | `DUPLICATE_REQUEST`    |
| SocialSignal缺失 | `SOCIAL_SIGNAL_MISSING`          | `SOCIAL_SIGNAL_FAILED` |
| Mock未标识        | `SOCIAL_SIGNAL_MOCK_REQUIRED`    | `MOCK_API_FAILED`      |

### 27.4Fixture文件速查表

| 文件                            | P0 | 说明         |
| ----------------------------- | -: | ---------- |
| `mock_pois.json`              |  是 | POI和餐厅静态数据 |
| `mock_status.json`            |  是 | POI基础状态    |
| `mock_inventory.json`         |  是 | 餐厅桌位、活动余票  |
| `mock_routes.json`            |  是 | 路线规则       |
| `mock_weather.json`           |  是 | 天气规则       |
| `mock_failure_scenarios.json` |  是 | 失败注入       |
| `executions.json`             |  是 | 执行记录和凭证    |
| `mock_idempotency_store.json` |  是 | 幂等记录       |
| `mock_social_signals.json`    | P1 | Mock口碑     |
| `traces.json`                 |  是 | TraceLog   |

### 27.5 06契约修订决议表

| 冲突点 | 决议 | 修改位置 |
|---|---|---|
| 天气接口字段 | 使用04的`start_time/end_time`和03完整WeatherStatus | 第12章 |
| POI搜索响应 | 返回03完整POI，内部fixture字段不得直接外露 | 第7章、第9章 |
| POIStatus/RestaurantStatus | 必须包含`available`、`expire_at`、nullable字段、Mock标识 | 第10章 |
| 执行凭证 | HTTP响应使用`booking_id/reservation_id/order_id/message_id`，`voucher`仅用于ExecutionResult聚合 | 第13章、第16章 |
| Fixture结构 | 03文件结构优先，06新增文件仅为内部fixture | 第7章 |
| 幂等键 | HTTP层以`X-Idempotency-Key`为准 | 第13章、第16章 |
| Trace归属 | CandidateRetriever写`poi_log`，MockAPIService写`tool_log` | 第21章 |
| GET/POST错误边界 | GET返回状态快照，POST返回`NO_TABLE_AVAILABLE/ACTIVITY_FULL` | 第10章、第13章、第15章 |
| ExecutableWindow | 只用POIStatus/RestaurantStatus.expire_at；天气/路线只影响risk和confidence | 第17章 |

### 27.6上线前重点检查清单

| 检查项                                 | 必须通过 |
| ----------------------------------- | ---: |
| Mock路径全部为`/api/v1/mock/...`         |    是 |
| ToolAction订单动作为`order_item`         |    是 |
| 执行类接口都有`X-Idempotency-Key`校验        |    是 |
| Mock标识按对象类型区分                       |    是 |
| failure_injection只给Debug/测试         |    是 |
| 无真实支付/短信/微信/订座/票务/爬取承诺              |    是 |
| TraceLog使用`tool_log`，不使用`mock_call` |    是 |
| Recovery版本化，生成`updated_plan_id`     |    是 |
| 状态查询和执行动作分离                         |    是 |
| SocialSignalMock不是P0强依赖             |    是 |

```
```

## 28. 2026-05-23追加：Mock路线兜底引擎

当`mock_routes.json`未覆盖某两个POI之间的稀疏配对时，`MockAPIService`可以在不新增HTTP路径的前提下，基于`mock_pois.json`中的经纬度生成确定性Mock路线。

生成边界：

1. 仅支持既有交通模式：`walk`、`bike`、`drive`、`taxi`、`mixed`、`subway`。
2. 仍使用`GET /api/v1/mock/routes/estimate`，响应字段投影为既有`RouteEstimate`。
3. 响应必须包含`source:"mock_api"`，不得伪装真实高德或真实商家路线。
4. `route_id`使用`route_engine_`前缀，表示由Mock路线引擎按经纬度生成。
5. 不支持的交通模式仍返回`ROUTE_DELAY`，不得静默生成。
6. Verifier可接受`mock_routes.json`命中路线或`route_engine_`生成路线，但仍必须检查`source`、起终点、时长和距离约束。
## 29. 2026-05-24追加：Mock订座/预约执行结果细节

执行类Mock接口在成功响应中补充可解释资源快照，帮助Demo讲清楚“关键动作已模拟完成”。

### 29.1活动预约

`POST /api/v1/mock/activities/{poi_id}/book`成功时可返回：

| 字段 | 说明 |
| --- | --- |
| `booking_id` | Mock预约号 |
| `party_size` | 预约人数 |
| `booking_time` | 预约时间 |
| `remaining_tickets_before` | 执行前Mock余票 |
| `booking_expires_at` | 当前资源快照过期时间 |
| `display_text` | 用户可见模拟凭证文案 |

### 29.2餐厅订座

`POST /api/v1/mock/restaurants/{poi_id}/reserve`成功时可返回：

| 字段 | 说明 |
| --- | --- |
| `reservation_id` | Mock订座号 |
| `party_size` | 订座人数 |
| `arrival_time` | 到店时间 |
| `available_tables_before` | 执行前Mock余桌数 |
| `queue_minutes` | Mock预计等待时间 |
| `reservation_expires_at` | 当前桌位快照过期时间 |
| `display_text` | 用户可见模拟凭证文案 |

边界：

1. 上述字段仍是Mock，不代表真实商家锁座、真实支付或真实排号。
2. GET状态查询和POST执行动作仍分离；只有POST执行成功才生成Mock凭证。
3. 失败仍使用既有错误码：餐厅无桌为`NO_TABLE_AVAILABLE`，活动满员为`ACTIVITY_FULL`。

## 30. 2026-05-24追加：高德数据稀疏与餐厅库存仿真补充

本轮对高德数据生成工具做了一次Dry Run审计：

```bash
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --raw-input backend/data/gaode_lifepilot_raw.json \
  --target-pois 500 \
  --output reports/gaode_dryrun_20260524 \
  --skip-routes \
  --allow-unrated
```

审计结论：

1. 当前POI池以`activity`和`restaurant`为主，服务型节点和轻散步节点偏少，需要补充Mock-only节点支撑纪念日/长窗口故事。
2. 原路线矩阵生成默认`--route-neighbors 1`，每个POI平均只保留1条显式近邻边，不适合4-5节点行程。
3. 运行时已有Mock路线兜底引擎，但数据层仍应提高显式近邻覆盖，便于讲清楚“路线图”而不是只依赖兜底估算。

工具默认值调整：

| 参数 | 调整前 | 调整后 | 说明 |
| --- | ---: | ---: | --- |
| `--route-neighbors` | 1 | 4 | 每个POI保留更多近邻边，支撑多段路线。 |
| `--max-route-pairs` | 500 | 1600 | 避免候选POI增多后路线矩阵过早截断。 |

Mock库存补充规则：

1. `mock_inventory.json.restaurant_slots`可为核心Demo餐厅声明晚餐时段余桌和`queue_minutes`。
2. `MockAPIService.restaurant_status()`必须优先使用匹配时段slot；slot未命中时再使用确定性库存引擎。
3. `queue_minutes`来自Mock状态/库存，不由LLM生成。
4. 余桌和排队仍必须标记Mock，不代表真实商家锁座或真实排号。

## 31. 2026-05-26追加：Mock状态引擎与数据工具边界

当前MockAPI实现采用“fixture override优先，确定性引擎兜底”的策略：

| 数据 | fixture存在时 | fixture缺失时 | Mock边界 |
| --- | --- | --- | --- |
| POI状态 | 使用`mock_status.json` override | `StatusMockEngine`按POI、时间、人数、seed生成 | 必须返回Mock状态和过期时间 |
| 餐厅库存 | 使用`mock_inventory.json.restaurant_slots` | `InventoryMockEngine`生成余桌、排队和可预约状态 | 不代表真实商家锁座 |
| 活动库存 | 使用`mock_inventory.json.activity_slots` | `InventoryMockEngine`生成余票和可预约状态 | 不代表真实票务 |
| 天气 | 匹配`mock_weather.json` | `WeatherMockEngine`按区域和日期生成 | 不代表实时天气服务 |
| 路线 | 命中`mock_routes.json` | 基于经纬度生成`route_engine_`路线 | `source`仍为`mock_api` |
| 口碑 | 命中`mock_social_signals.json` | `SocialSignalMockEngine`生成摘要 | 必须标`is_mock:true` |

高德数据工具只负责采集真实地点、路线和sidecar字段，不负责生成真实余位、真实订座、真实票务、真实排队或真实口碑。进入`backend/data`后的数据仍是Demo数字孪生fixture，必须保留Mock语义。
