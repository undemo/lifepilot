# T05_24 周末闲时活动规划优化记录

## 目标

本轮修复“当前模拟时间被误当成出发时间”的问题，并把比赛 Demo 的叙事能力补齐到一个可演示闭环：自然语言时间理解、类脑 POI 推荐、分享投票动态调参、MockAPI 仿真订座/预约、风险分支与 Recovery。

## 关键问题

首页原来把 Demo 当前时间通过 `preferred_start_time` 传给后端，后端因此认为用户显式指定了出发时间。典型场景是：

```text
当前模拟时间：2026-05-23 18:00
用户输入：周末下午我想去一个人散散心，顺便喝杯酒。
```

旧逻辑会从 `18:00` 开始排计划，但这句话里的“周末下午”是自然语言时间意图，不是“现在立刻出发”。当前时间应该只作为解析锚点，用来判断“周末下午”还剩不剩；如果当天周六下午已过，应落到周日 15:00-19:00 这样的可执行窗口。

## 本次实现

1. `PlanCreateRequest` 增加 `current_time` 和 `preferred_duration_hours`。
   - `current_time` 只表示 Demo/用户当前时间锚点。
   - `preferred_start_time` / `preferred_end_time` 继续只表示用户显式指定的执行窗口。
   - 前端首页已改为发送 `current_time`，避免把“现在几点”误传成“几点开始玩”。

2. `ConstraintExtractor` 增加 TimeAnchorResolver 规则。
   - 支持 `current_time` / `demo_now` / `now` 作为解析锚点。
   - “周末下午”会根据锚点判断目标日期：周六下午已过则顺延到周日，周日已过则顺延到下周六。
   - “下午 + 喝酒/小酌”默认规划为 4 小时窗口，示例为 `15:00-19:00`。
   - 约束中新增 `planning_anchor_time` 与 `time_intent`，用于解释本次时间解析，但不暴露内部 DraftPlan。

3. 首页增加“周末独处”快捷场景。
   - 默认当前时间锚点回到比赛题设的 `2026-05-23T09:00`。
   - 独处散心场景默认不生成多人投票候选，朋友/家庭场景仍可进入候选共识链路。

4. 类脑 POI 推荐叙事增强。
   - 计划页把“推荐匹配优先级”调整为“类脑推荐优先级”。
   - 候选 POI 的展示标签优先突出用户显式锚点，例如烤羊排、烧烤、日料、轻食，再展示泛化群体标签。
   - 这样 Demo 讲述时可以解释为：先理解任务意图和人群约束，再用 POI 特征向量、路程、价格、风险和库存做加权排序。

5. 分享投票页增加动态调整预览。
   - Vote API 返回更完整的 `PlanSummary`，包括目标摘要、时间线摘要、预算、人均、可执行窗口和分享链接。
   - 前端投票页展示预算、步行容忍、排队容忍和自由意见对计划的影响预览。
   - 投票 token 写入本地存储，便于同一浏览器体验重复访问和防重复提交。

6. MockAPI 执行动作更像真实数字孪生。
   - 餐厅订座动作返回 `party_size`、`arrival_time`、`available_tables_before`、`queue_minutes`、`reservation_expires_at`。
   - 活动预约动作返回 `party_size`、`booking_time`、`remaining_tickets_before`、`booking_expires_at`。
   - 执行页会显示“订座前 Mock 余桌 / 预计等位”和“预约前 Mock 余票”，让评委看到不是简单生成文本，而是在模拟可落地资源状态。

7. 风险分支故事保持在 PlanContract / Recovery 边界内。
   - 普通用户页不展示 `failure_injection`、Prompt、API Key、模型推理链等底层调试信息。
   - 出现余位不足、排队过长、路线不可达等风险时，Recovery 继续采用版本化策略，保留 `original`、`replacement`、`diff`、`updated_plan_id`。

## 验证结果

已通过：

```bash
PYTHONPATH=backend python -m py_compile backend/app/services/constraint_extractor.py backend/app/schemas/requests.py backend/app/services/mock_api_service.py backend/app/services/consensus_service.py scripts/run_backend_p0_tests.py tests/test_p0_plan_create.py
PYTHONPATH=backend python scripts/run_backend_p0_tests.py
PYTHONPATH=backend python scripts/contract_scan.py
PYTHONPATH=backend python scripts/validate_mock_data.py
cd frontend && npx tsc --noEmit
cd frontend && npx next lint
```

新增回归覆盖：

```text
current_time = 2026-05-23T18:00:00+08:00
input = 周末下午我想去一个人散散心，顺便喝杯酒。
expected window = 2026-05-24T15:00:00+08:00 -> 2026-05-24T19:00:00+08:00
```

残留环境问题：

```bash
PYTHONPATH=backend python -m pytest tests/test_p0_plan_create.py -q
```

在当前 Python 3.13 环境下仍然以 `-1` 退出且无输出；同一批断言已放进 `scripts/run_backend_p0_tests.py` 并通过。该问题更像本地 pytest/capture 运行环境问题，不是本次业务回归失败。

## Demo 讲法

评委看到的主线可以这样讲：

1. 用户只说一句话，Agent 先做时间语义解析，区分“当前几点”和“想什么时候去”。
2. 类脑 POI 推荐引擎把自然语言拆成意图、人群、情绪、预算、路程、库存和风险多个维度，生成可执行路线。
3. 计划不是静态推荐，分享给家人或朋友后，投票页会把预算、步行、排队、偏好变化实时汇总成调参预览。
4. 用户确认后，MockAPI 会像数字孪生一样读取餐厅余桌、活动余票和排队时间，模拟订座/预约/锁库存。
5. 如果执行中发现资源变化或风险升高，Recovery 会生成带版本 diff 的替代方案，让计划继续可落地。

## 追加记录二：多节点纪念日长窗口修复

### 新问题

用户输入：

```text
今晚想给纪念日安排一段轻松一点的约会，不夸张，预算适中，路线别太折腾。安排4-5个活动。下午一点出发，晚上十点钟回来
```

旧效果无法稳定满足三件事：

1. “4-5个活动”没有进入结构化约束，计划仍按固定三段生成。
2. “下午一点出发、晚上十点回来”没有被识别为显式起止窗口。
3. 高德路线矩阵默认`route_neighbors=1`，显式路线图太稀疏，多节点行程容易只围绕一两个近邻点打转。

### 本次修复

1. `ConstraintExtractor`新增显式文本时间窗解析。
   - 支持“出发/开始/集合”和“回来/回家/结束/之前”等关键词附近的时间提及。
   - 示例会得到`2026-05-23T13:00:00+08:00 -> 2026-05-23T22:00:00+08:00`。
   - 新增`target_stop_count`和`target_stop_count_range`，示例为`[4,5]`。

2. `CandidateRetriever`新增多节点候选补充。
   - 主链仍选活动、餐厅、收尾。
   - 当目标节点数大于等于4时，从活动、服务、轻停留节点里补充`extra_pois`。
   - 内部生成`itinerary_nodes`后按相邻节点估算路线，避免只查两段转场。

3. `PlanGenerator`新增多节点timeline生成。
   - 真实POI节点数量按用户目标控制。
   - 纪念日长窗口默认排成低压力活动、轻仪式节点、晚餐。
   - 多节点候选不足时回退原短链，不返回空timeline。

4. Mock数据补齐长窗口故事。
   - 新增湖畔慢行、日落观景、香薰手作、轻写真、鲜花蛋糕站等Mock-only节点。
   - `mock_inventory.json`为核心晚餐餐厅补充晚餐slot和低排队分钟。
   - `MockAPIService.restaurant_status()`读取slot中的`queue_minutes`并据此产出风险等级。

5. 高德数据生成工具默认值调整。
   - `--route-neighbors`从1调整为4。
   - `--max-route-pairs`从500调整为1600。
   - README补充说明：neighbor=1只适合快速试跑，不适合多节点短时行程。

### 高德工具审计

已调用Dry Run：

```bash
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --raw-input backend/data/gaode_lifepilot_raw.json \
  --target-pois 500 \
  --output reports/gaode_dryrun_20260524 \
  --skip-routes \
  --allow-unrated
```

结果摘要：

```text
POI: 500
activity: 196
restaurant: 304
service/walk_spot: 0
```

这说明当前高德原始数据偏“活动+餐饮”，服务型节点、轻散步节点和仪式节点需要通过Mock数字孪生补齐，才能讲好“纪念日/家庭/朋友局”的完整短时活动故事。

### 复验样例

当前输出：

```text
time_window: 2026-05-23 13:00 -> 22:00
target_stop_count_range: [4, 5]
真实POI节点: 5
晚餐开始: 18:21
人均预算: 370.5 <= 400
verifier_result.status: pass
```

示例节点：

```text
13:00 湖畔手作香薰工坊
14:29 金沙湖轻写真自助影棚
15:59 蕉个朋友DIY手工
17:28 一朵纪念日鲜花蛋糕站
18:21 三川茶空间(和达湖畔中心店)
```

### 验证结果

已通过：

```bash
PYTHONPATH=backend python -m py_compile backend/app/services/constraint_extractor.py backend/app/services/intent_parser.py backend/app/services/candidate_retriever.py backend/app/services/plan_generator.py backend/app/services/plan_contract_builder.py backend/app/services/mock_api_service.py scripts/run_backend_p0_tests.py tests/test_p0_plan_create.py tools/gaode_data_factory/generate_lifepilot_dataset.py
PYTHONPATH=backend python scripts/validate_mock_data.py
PYTHONPATH=backend python scripts/contract_scan.py
PYTHONPATH=backend python scripts/run_backend_p0_tests.py
cd frontend && npm run typecheck
```

`pytest`在当前Python 3.13环境下仍以`-1`无输出退出；同一核心断言已纳入`run_backend_p0_tests.py`并通过。

## 追加记录三：浏览器端到端按钮巡检与流程体验修复

### 本轮目标

用浏览器自动化和现有Smoke脚本验证当前前后端是否能跑通，覆盖首页、计划页、执行页、投票页、共识页、反馈页、记忆页、设置页和Debug入口；发现断点后直接修复，并把结果记录到本文档。

### 发现的问题

1. 亲子快捷场景会生成不可直接执行的计划。
   - “手作酸奶铺”“手工粉”这类餐饮名称被活动语义误召回，可能作为`activity`进入时间线。
   - 部分活动候选没有按`party_size`过滤余票，Verifier会在`activity_ticket`阶段阻断。
   - 家庭默认预算被“轻食/减脂”预算提示压到人均约110-120元，4小时多节点亲子路线容易被误判为预算失败。

2. 朋友投票共识最终方案偶发失败。
   - 咖啡/轻聊天餐饮节点作为`activity`停靠时，前端/后端会生成“活动预约”动作，Verifier按活动票务检查后阻断。

3. 部分按钮体验不够闭环。
   - 计划失败态底部按钮原来只显示“存在阻断风险”，用户不能直接刷新状态。
   - 底部操作条只有一个按钮时没有占满宽度。
   - 首页快捷场景点击后缺少选中态反馈。
   - 反馈页提交后如果出现候选记忆，原页面不能直接确认/忽略，需要跳转到记忆页。

### 本次修复

1. `CandidateRetriever`收紧家庭活动候选。
   - 家庭亲子主活动只接受真实`activity`类POI，不再把餐饮店名里的“手作/手工”当活动。
   - 候选状态评分会检查`ticket_available`、`booking_available`和`remaining_tickets >= party_size`，避免把余票不足的活动排进主方案。

2. `ConstraintExtractor`调整家庭默认预算。
   - 对无明确低预算诉求的家庭亲子场景，提高默认人均预算上限，避免把4小时亲子活动+正餐错误打成预算阻断。
   - “别太贵/不贵”等明确低预算表达仍保留更紧的人均100元规则。

3. `PlanGenerator`修正轻停靠动作。
   - 非`activity`类POI如果作为轻聊天/咖啡等`activity`停靠，不再生成`book_activity`动作。
   - 这样朋友局共识最终方案不会把咖啡聊天误当成票务预约。

4. 前端交互优化。
   - 计划失败态主按钮改为可点击的“刷新可执行窗口”。
   - 单按钮底部操作条自动占满宽度。
   - 首页快捷场景增加选中态，默认家庭亲子卡已选中。
   - 反馈页候选记忆卡支持直接“确认/忽略”。

### 浏览器手动验证

已用Codex in-app browser覆盖：

```text
首页：4个快捷场景按钮、生成计划、设置入口
设置页：读取设置、保存设置
家庭链路：首页 -> 计划页 -> Debug Trace -> 返回计划 -> 确认模拟执行 -> 执行页 -> 反馈页 -> 记忆页
朋友链路：首页 -> 计划页 -> 发起投票 -> 投票页喜欢/提交 -> 共识页生成共识方案 -> 最终计划页
```

关键截图已保存：

```text
reports/screenshots/browser-home.png
reports/screenshots/browser-family-plan.png
reports/screenshots/browser-execution.png
reports/screenshots/browser-feedback.png
reports/screenshots/browser-memory.png
```

### 验证结果

已通过：

```bash
PYTHONPATH=backend python -m py_compile backend/app/services/constraint_extractor.py backend/app/services/candidate_retriever.py backend/app/services/plan_generator.py
PYTHONPATH=backend python scripts/run_backend_p0_tests.py
PYTHONPATH=backend python scripts/run_p0_frontend_smoke.py
cd frontend && npm run typecheck
cd frontend && npm run lint
```

最终Smoke结果：

```text
backend_ready: True
frontend_ready: True
backend_p0_tests: PASS
contract_scan: PASS
validate_mock_data: PASS
Playwright E2E: 9 passed
```

`npm run lint`返回0；当前仍有既有`react-hooks/exhaustive-deps` warning，未在本轮扩大修改范围。

## 追加记录四：Stitch美团风格前端集成与真实链路回归

### 本轮目标

将Stitch生成的“生活导航首页、计划总览、好友投票、生活记忆、生活时间轴”视觉样例吸收到现有系统中，但不把静态HTML当成产品页面。所有核心功能仍然走真实`/api/v1`接口、`PlanContract`、Verifier、Executor、Consensus和Memory链路。

### 产品回答

它是一个本地生活时间导航Agent。

它解决的问题不是“推荐几个地点”，而是把用户一句生活目标变成一段可验证、可协同、可恢复的生活时间线：今天何时出发、去哪几个点、路上怎么转场、预算是否可控、余位是否可执行、失败时怎么改道。

包含的主要板块：

1. 首页自然语言入口：快捷场景、当前时间锚点、可规划时长、本地实时状态。
2. 计划页：目标理解、时间线、路线转场、预算、风险、PlanB和工具调用摘要。
3. 好友投票与共识：候选方案投票、预算/步行/排队偏好收集、共识PlanContract生成。
4. 执行页：用户确认后执行Mock订座、预约、消息和订单动作。
5. 生活记忆页：反馈沉淀为可确认/可忽略的长期偏好。
6. 设置与Debug：普通用户页不展示底层敏感调试信息，Debug入口保留给演示和排障。

希望用户看到网站时感受到：

```text
这不是一个冷冰冰的AI聊天框，而是一个懂时间、懂约束、懂同伴、也懂失败改道的生活导航员。
```

### 本次集成

1. 前端Shell统一为美团风格移动端应用壳。
   - 顶部保留LifePilot品牌和设置入口。
   - 底部导航固定为“首页、计划、同步、我的”。
   - 最近计划和最近投票只作为导航缓存，不作为业务真相。

2. 首页重构为Stitch样例风格。
   - 保留真实`POST /api/v1/plans/create`。
   - 保留`textarea`和“生成计划”按钮，兼容现有E2E。
   - 增加本地实时、快捷场景、今日灵感和“LifePilot 当前优势”。
   - 页面明确标注Demo使用模拟状态与Mock凭证。

3. 计划页增强路线表达。
   - 在“路线与转场”中加入轻量模拟路线轨迹。
   - 仍然只展示后端返回的路线与转场数据，不由前端编造路线。

4. 投票页和候选卡重构。
   - 增加好友同步状态。
   - 候选方案卡升级为带图片区域、评分、预算、时间窗和真实投票按钮的地点卡。
   - 投票提交仍调用`POST /api/v1/votes/{vote_page_id}`。

5. 记忆页重构。
   - 增加个人资料和生活记忆语境展示。
   - 候选记忆仍从后端读取，确认/忽略仍调用真实Memory接口。
   - 页面只展示中文用户可见投影，不展示底层枚举。

### 功能补丁

集成后Smoke发现家庭亲子链路偶发不能执行。根因不是前端按钮，而是后端候选链选择有两个口径不一致：

1. 活动类收尾节点按泛化角色时间检查，真实时间线落点可能进入Mock无票时段。
2. 家庭场景候选选择允许默认预算松弛，但Verifier按硬预算校验。

修复：

1. 对活动类收尾节点按候选链预计到达时间做Mock余票/预约硬校验。
2. 为该校验增加缓存，避免组合搜索中重复打状态查询导致E2E超时。
3. 家庭亲子场景没有明确餐饮诉求时，不使用预算松弛，候选选择和Verifier预算口径保持一致。

### 文档追加

已追加：

```text
docs/07_frontend_design.md
docs/09_demo_script.md
```

追加内容覆盖Stitch视觉集成边界、真实接口映射、底部导航规则、Demo讲法和用户感受目标。

### 验证结果

已通过：

```bash
PYTHONPATH=backend python -m py_compile backend/app/services/candidate_retriever.py
cd frontend && npm run typecheck
cd frontend && npm run lint
PYTHONPATH=backend python scripts/run_p0_frontend_smoke.py
```

Smoke最终结果：

```text
backend_ready: True
frontend_ready: True
backend_p0_tests: PASS
contract_scan: PASS
validate_mock_data: PASS
Playwright E2E: 9 passed
```

浏览器检查：

```text
http://127.0.0.1:3040/
首页Hero、本地实时、LifePilot优势、Mock边界、生成按钮、底部导航均可见。
```

当前唯一运行服务：

```text
backend:  http://127.0.0.1:8040
frontend: http://127.0.0.1:3040
```
