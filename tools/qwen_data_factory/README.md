# LifePilot Qwen Data Factory

`tools/qwen_data_factory` 是 LifePilot 的 Mock 数据生成流水线。它把本地 Qwen 当作 OpenAI-compatible 数据候选 API 使用：Qwen 只生成候选 JSON，代码负责解析、清洗、校验、跨文件引用检查和写入 `backend/data`。

本工具服务杭州下沙 / 金沙湖 / 高教园区 P0 Demo。数据契约仍兼容三类P0场景：

- 家庭亲子：孩子友好、低排队、低卡/轻食、路线不赶。
- 朋友局：多人共识、预算敏感、少走路、轻松聚会。
- 纪念日：轻仪式感、安静餐厅、合照点、自然节奏。

同时，POI 和口碑生成不能只围绕这三类场景。地点标签和摘要要面向更广的大众生活意图，例如喜欢小动物、爱干净、心情不好想散心、爱运动、压力大想放空、外地朋友来玩、独处办公/阅读、雨天避雨、夜间补给、怕吵怕晒怕排队等。

## 目录说明

```text
tools/qwen_data_factory/
├── config.yaml                  # Qwen API配置
├── qwen_client.py               # OpenAI-compatible非流式客户端
├── factory_server.py            # 本地数据审计页面服务
├── frontend/index.html          # 数据审计前端
├── prompts/                     # 每类文件的Qwen提示词模板
├── generators/                  # 数据生成脚本
├── validators/                  # 数据校验脚本
├── staging/                     # 本地debug原始prompt/response
└── reports/                     # 请求、生成、校验报告
```

输出目录：

```text
backend/data/
├── mock_pois.json
├── mock_status.json
├── mock_inventory.json
├── mock_routes.json
├── mock_weather.json
├── mock_failure_scenarios.json
├── mock_social_signals.json
└── benchmark_samples.json
```

## 每个数据文件的用途

| 文件 | 用途 | 好数据的特征 |
| --- | --- | --- |
| `mock_pois.json` | POI基础地点库。所有状态、库存、路线、口碑和Benchmark都引用这里的 `poi_id`。 | 至少10个POI；覆盖 `activity / restaurant / walk_spot / service / transport_anchor`；兼容三大P0场景，同时覆盖宠物、卫生、散心、运动、外地来访、独处办公、雨天避雨、夜间补给等大众意图；地点在下沙/金沙湖/高教园区；`mock_only=true`。 |
| `mock_status.json` | POI动态状态快照。Verifier 用它判断营业、排队、桌位、票务和窗口。 | 每个状态有 `query_status`；`source=mock_api`；有 `expire_at`；餐厅有桌位/排队字段；活动有余票/可预约字段。 |
| `mock_inventory.json` | 时段库存规则。用于模拟查询与执行之间的动态变化。 | 餐厅库存与活动库存分开；slot时间是ISO 8601；所有 `poi_id` 存在。 |
| `mock_routes.json` | 路线估计矩阵。避免LLM估算路线。 | 起终点都存在于POI库；`source=mock_api`；距离和耗时合理；覆盖常见串联路径。 |
| `mock_weather.json` | 区域天气风险快照。用于户外风险和PlanB判断。 | 覆盖下沙、金沙湖、高教园区；同一区域时段不重叠；风险等级合法；户外风险较高时有恢复建议。 |
| `mock_failure_scenarios.json` | Debug/测试失败脚本。用于验证执行失败后的Recovery能力。 | 覆盖餐厅满座、活动满员、窗口过期；`visible_to_user=false`；错误码来自契约。 |
| `mock_social_signals.json` | 口碑Mock信号。展示可扩展口碑雷达能力。 | `summary` 是段落式Mock归纳；`mock_sources` 只用 `link1` 这类占位符；`is_mock=true`；`source_type=mock_social_signal`；缺失不阻断主流程。 |
| `benchmark_samples.json` | LifePilot-Bench样例。用于评估意图、约束、Verifier、Recovery和Mock边界。 | `sample_id` 以 `bench_` 开头；覆盖三大P0场景；断言指向既有检查项。 |

## Qwen API配置

默认读取：

```bash
tools/qwen_data_factory/config.yaml
```

当前配置字段：

| 字段 | 含义 | 示例 |
| --- | --- | --- |
| `base_url` | Qwen OpenAI-compatible服务地址。可以写root地址，客户端会优先拼 `/v1/chat/completions`。 | `http://10.31.112.238:58080` |
| `api_key` | Qwen服务密钥。不会写入普通日志和前端页面。 | 见本地配置 |
| `model` | `/v1/models` 返回的模型ID。 | `Qwen3.5-35B-A3B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf` |
| `temperature` | 生成多样性。POI建议 `0.3-0.6`。 | `0.35` |
| `max_tokens` | 单次最大输出长度。POI批量建议 `4096` 或更高。 | `4096` |
| `timeout` | 单次请求超时秒数。大模型生成POI可能较慢。 | `60` |
| `retry` | 失败重试次数。 | `2` |
| `backoff` | 重试退避基数。 | `1.5` |
| `enable_thinking` | 是否启用模型思考输出。必须保持 `false`，否则可用JSON可能不在 content 字段。 | `false` |

也可以用环境变量覆盖：

```bash
export QWEN_BASE_URL=http://10.31.112.238:58080
export QWEN_API_KEY="..."
export QWEN_MODEL="Qwen3.5-35B-A3B-Uncensored-HauhauCS-Aggressive-Q8_0.gguf"
export QWEN_TIMEOUT=60
export QWEN_RETRY=2
export QWEN_ENABLE_THINKING=false
```

Smoke test：

```bash
python tools/qwen_data_factory/qwen_client.py \
  --task-type smoke \
  --prompt 'You must output only this valid JSON object and no prose: {"ok": true, "source": "mock_api"}'
```

## 推荐执行顺序

### 1. 生成POI

```bash
python tools/qwen_data_factory/generators/generate_pois.py --target 120 --batch-size 15
```

参数：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `--target` | `120` | 目标POI数量。P0至少10个，Demo建议100以上。 |
| `--batch-size` | `15` | 每次Qwen请求生成多少候选。太大会增加JSON失败概率，太小会增加请求次数。 |
| `--output` | `backend/data` | 输出目录。 |
| `--allow-template-fallback` | 关闭 | Qwen不可用时用本地模板兜底。正式造数建议关闭，除非只是联调页面。 |

脚本会显示 `qwen_pois` 进度条。每批请求成功后，只有通过解析、字段白名单、ID和Mock边界清洗的数据才会进入 accepted。

### 2. 生成全量派生数据

```bash
python tools/qwen_data_factory/generators/generate_all.py
```

默认行为：

- 默认会调用Qwen重新生成 `mock_pois.json`。这是为了避免你以为生成了新数据，实际却复用了旧文件。
- 然后生成其它7个文件：`mock_routes.json` 仍由规则生成，避免路线矩阵被LLM臆造；status、inventory、weather、failure scenarios、social signals、benchmark samples 默认先走Qwen候选，再由代码校准字段、枚举、时间、引用和Mock边界。
- 最后自动运行 validator。

如果你明确只想复用现有POI并重建其它文件，使用：

```bash
python tools/qwen_data_factory/generators/generate_all.py --target-pois 10 --reuse-existing
```

如果你只想跑规则派生，不调用Qwen生成非POI候选，使用：

```bash
python tools/qwen_data_factory/generators/generate_all.py --target-pois 10 --no-qwen-derived
```

Qwen派生的安全策略是：每个非路线文件先由Qwen生成候选JSON，代码只吸收可用语义，再写入临时目录做整包validator校验；通过才落盘，不通过会自动回退到规则派生版本。想让任何一个Qwen派生失败都直接失败，可以加 `--strict-qwen-derived`。

参数：

| 参数 | 默认值 | 说明 |
| --- | ---: | --- |
| `--target-pois` | `120` | 需要的POI数量。已有POI不足时会先生成POI。 |
| `--batch-size` | `15` | POI生成批大小。 |
| `--output` | `backend/data` | 输出目录。 |
| `--reuse-existing` | 关闭 | 复用现有 `mock_pois.json`，只重建其它文件。 |
| `--force-pois` | 关闭 | 兼容旧用法；默认已经会重新生成POI。 |
| `--qwen-derived` | 开启 | 非路线文件也先尝试Qwen候选生成；代码校准后校验，通过才落盘。 |
| `--no-qwen-derived` | 关闭 | 禁用非POI Qwen候选，只用规则生成派生文件。 |
| `--strict-qwen-derived` | 关闭 | 非POI文件的Qwen候选只要有一个校验失败，整次生成失败。 |
| `--allow-template-fallback` | 关闭 | Qwen不可用时用本地模板兜底。 |
| `--skip-validate` | 关闭 | 跳过最后的校验。一般不要跳过。 |

脚本会显示 `generate_all`、`mock_status`、`mock_inventory`、`mock_routes`、`mock_weather`、`mock_failures`、`mock_social`、`benchmark_samples` 等进度条。

### 3. 单独重生成某个文件

```bash
python tools/qwen_data_factory/generators/generate_status.py
python tools/qwen_data_factory/generators/generate_inventory.py
python tools/qwen_data_factory/generators/generate_routes.py --max-routes 260
python tools/qwen_data_factory/generators/generate_weather.py
python tools/qwen_data_factory/generators/generate_failure_scenarios.py
python tools/qwen_data_factory/generators/generate_social_signals.py
python tools/qwen_data_factory/generators/generate_benchmark_samples.py
```

常用参数：

| 参数 | 适用脚本 | 说明 |
| --- | --- | --- |
| `--input` | 依赖POI的脚本 | 读取 `mock_pois.json` 的目录。 |
| `--output` | 全部 | 写出目录。 |
| `--max-routes` | `generate_routes.py` | 路线矩阵最大数量。 |

### 4. 校验数据

```bash
python tools/qwen_data_factory/validators/validate_mock_data.py --input backend/data
```

校验内容：

- 所有必需文件存在。
- JSON可解析，顶层结构正确。
- 字段白名单检查。
- ID前缀检查。
- ISO 8601时间检查。
- 下沙、金沙湖、高教园区经纬度边界检查。
- 同一区域天气时段不重叠检查。
- 口碑Mock段落长度、占位链接和Mock来源检查。
- POI类别、区域、衣食住行娱乐停车等生活场景覆盖审计。
- Mock标识检查。
- 禁止外部平台完成类文案。
- POI、状态、库存、路线、口碑之间的跨文件引用检查。
- 三大P0场景覆盖检查。

## Prompt组合器

查看某个文件本次会喂给Qwen的上下文：

```bash
python tools/qwen_data_factory/generators/prompt_composer.py --file mock_pois.json --seed 9
python tools/qwen_data_factory/generators/prompt_composer.py --file mock_routes.json --seed 7
```

组合维度包括：

- 情绪/风格：朴素、轻松、安静、热闹、高效、疗愈、运动感、烟火气、干净清爽、适合外地人。
- 价位：免费、10-30、30-50、50-100、100-150、150以上。
- 区域：下沙、金沙湖、高教园区。
- 时间段：清晨运动前后、工作日午休、周六下午、雨天临时改计划、深夜前补给、外地朋友到达后、情绪低落想散心。
- 天气：多云可散步、小雨偏室内、天气热需少走路、湖边风大需备选、雨后地面湿滑、晴天适合运动。
- 同行人：一个人、两个人、三五人、同事临时聚、外地朋友来访、带宠物、带老人、带孩子、骑行或跑步后。
- 动线：少走路、可步行串联、地铁口集合、打车优先、开车停车优先、骑行友好、轮椅或推车友好、室内连廊动线。
- 生活需求：正餐、咖啡茶饮、散步放空、运动后补给、宠物友好、卫生间/更衣/洗手、临时买药/便利补给、安静工作、雨天室内备选、情绪缓冲。

`generate_pois.py` 每一批都会用不同seed组合提示词，避免Qwen只沿着一套上下文生成。

## 前端审计

启动：

```bash
python tools/qwen_data_factory/factory_server.py --data backend/data --port 8765
```

打开：

```text
http://127.0.0.1:8765/factory
```

页面能力：

- 文件筛选：选择某个JSON文件后，顶部会显示中文用途、读取模块、关键校验点。
- 场景筛选：家庭亲子、朋友局、纪念日。
- 类别筛选：activity、restaurant、walk_spot、service、transport_anchor。
- 区域筛选：下沙、金沙湖、高教园区。
- 搜索：按名称、ID、标签或JSON片段搜索。
- 刷新状态：点击“刷新状态”会重新从 `backend/data` 读取文件，不需要重载页面。
- 运行校验：调用 validator，并把报告写入 `reports/validate_mock_data_report.json`。
- 删除：删除单条数据。删除POI时会级联清理状态、库存、路线和口碑引用，避免悬空引用。

浏览器自身刷新页面也会重新加载数据；“刷新状态”按钮用于你在后台重跑生成脚本后，保持当前筛选条件并立即审计新数据。

## 怎么判断一批数据好不好

一批数据至少要通过三层判断。

### 1. 自动校验通过

必须看到：

```json
{
  "success": true,
  "error_count": 0
}
```

如果失败，先看：

```bash
tools/qwen_data_factory/reports/validate_mock_data_report.json
```

常见坏数据：

- POI引用不存在。
- 时间不是ISO 8601。
- 缺少 `mock_only`、`source=mock_api`、`is_mock=true` 等Mock标识。
- 文件结构不符合顶层约定。
- 三个P0场景没有覆盖全。

### 2. 前端抽样审计通过

在页面逐个选中8个文件，看顶部说明和数据内容是否一致。

建议抽样：

- `mock_pois.json`：每个场景至少看5条，确认地点不是重复换名。
- `mock_status.json`：看餐厅是否有桌位和排队字段，活动是否有余票字段。
- `mock_inventory.json`：看slot时间是否覆盖下午/傍晚。
- `mock_routes.json`：看起点终点是否能串成生活时间线，而不是随机点对。
- `mock_weather.json`：看户外风险能否解释PlanB。
- `mock_failure_scenarios.json`：看失败脚本是否只用于Debug/测试。
- `mock_social_signals.json`：确认口碑文案明确是Mock。
- `benchmark_samples.json`：确认样例覆盖三大场景和主要失败路径。

### 3. 合同红线扫描通过

```bash
PYTHONPATH=backend python scripts/contract_scan.py
```

这会检查旧路径、旧字段、错误动作类型、普通源代码中的Debug字段泄露风险、以及外部平台完成类误导文案。

## 报告和debug文件

| 文件 | 内容 |
| --- | --- |
| `reports/qwen_requests.jsonl` | 每次Qwen请求的 `request_id`、任务类型、状态、耗时、错误摘要。没有API Key。 |
| `reports/generate_pois_report.json` | POI生成数量、accepted/rejected、请求ID、是否兜底。 |
| `reports/generate_all_report.json` | 全量生成结果、校验摘要。 |
| `reports/prompt_preview_report.json` | 每个文件的prompt预览，便于审查上下文是否足够多样。 |
| `reports/validate_mock_data_report.json` | validator完整报告。 |
| `staging/*_debug.json` | 本地debug用原始prompt和原始response。只供开发者查看，不进入普通用户页面。 |

## 失败重试策略

### Qwen请求超时

先增大超时：

```bash
QWEN_TIMEOUT=120 python tools/qwen_data_factory/generators/generate_pois.py --target 120 --batch-size 10
```

如果JSON不稳定，降低批大小：

```bash
python tools/qwen_data_factory/generators/generate_pois.py --target 120 --batch-size 8
```

### Qwen暂时不可用

只做页面联调时：

```bash
python tools/qwen_data_factory/generators/generate_all.py --allow-template-fallback
```

正式造数建议等Qwen恢复后重新跑：

```bash
python tools/qwen_data_factory/generators/generate_all.py
```

如果只想复用当前POI并让其它文件重新走一遍Qwen候选：

```bash
python tools/qwen_data_factory/generators/generate_all.py --reuse-existing
```

### 校验失败

修复顺序：

1. 打开 `validate_mock_data_report.json` 看第一个 error。
2. 如果是POI本身问题，重跑 `generate_pois.py`。
3. 如果是派生文件引用问题，先确认 `mock_pois.json` 合格，再重跑 `generate_all.py`。
4. 如果前端删除过POI，点击“运行校验”；必要时重跑派生文件。

## 安全边界

- Qwen只生成候选JSON。
- Qwen输出不得直接写成PlanContract。
- 写入 `backend/data` 前必须经过解析、白名单、ID、ISO时间、Mock边界和跨文件引用校验。
- 可执行状态只来自Mock数据或规则，不由Qwen确认。
- 普通用户页面不展示底层prompt、API Key、模型推理内容或Debug失败细节。
- 所有对外部平台能力的表达必须是Mock或模拟，不承诺外部平台动作已经完成。
