# LifePilot Gaode Data Factory

`tools/gaode_data_factory` 用高德 Web 服务 POI 搜索接口拉取真实 POI，再转换成当前 `tools/qwen_data_factory` 生产的 `mock_pois.json` 同形结构。

基础 POI 生成：

```bash
export AMAP_KEY="你的高德 Web 服务 Key"
python tools/gaode_data_factory/generate_pois.py --target 60
```

生成 500 条精品 POI 候选池和高德路线矩阵：

```bash
export AMAP_KEY="你的高德 Web 服务 Key"
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --target-pois 500 \
  --route-neighbors 4 \
  --max-route-pairs 1600
```

该脚本默认使用高德 `v3/place/around` 周边搜索，不使用关键词枚举地点。POI 机器筛选后输出给人工复核；路线默认对每个入选 POI 的 4 个近邻 pair 调用步行、驾车、公交/地铁换乘三类高德路径接口，并把换乘结果映射为 LifePilot `transport_mode=subway`。`--route-neighbors 1` 只适合快速试跑，会让多节点行程的显式路线矩阵过稀。

如只想先生成/复核 POI，不调用路线接口：

```bash
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --target-pois 500 \
  --skip-routes
```

如只想用已有 raw 归档 dry run：

```bash
python tools/gaode_data_factory/generate_lifepilot_dataset.py \
  --raw-input tools/gaode_data_factory/output/gaode_capability_probe_raw.json \
  --target-pois 20 \
  --output /tmp/lifepilot_gaode_dryrun \
  --skip-routes \
  --allow-unrated
```

比较关键词搜索和坐标周边搜索：

```bash
python tools/gaode_data_factory/compare_poi_strategies.py \
  --target 60 \
  --radius 1800
```

验证高德 API 对 LifePilot 各 Mock JSON 的字段还原能力：

```bash
python tools/gaode_data_factory/gaode_api_capability_probe.py \
  --sample-details 3
```

默认输出：

```text
tools/gaode_data_factory/output/mock_pois.json
tools/gaode_data_factory/output/gaode_raw_poi_responses.json
tools/gaode_data_factory/output/around_mock_pois.json
tools/gaode_data_factory/output/gaode_around_raw_poi_responses.json
tools/gaode_data_factory/output/combined_deduped_mock_pois.json
tools/gaode_data_factory/output/poi_strategy_evaluation.json
tools/gaode_data_factory/output/gaode_capability_probe_report.json
tools/gaode_data_factory/output/gaode_capability_probe_raw.json
tools/gaode_data_factory/output/gaode_lifepilot_raw.json
tools/gaode_data_factory/output/gaode_poi_enrichment.json
tools/gaode_data_factory/output/gaode_poi_review_candidates.json
tools/gaode_data_factory/output/gaode_route_raw_responses.json
tools/gaode_data_factory/reports/generate_pois_report.json
tools/gaode_data_factory/reports/generate_around_pois_report.json
tools/gaode_data_factory/reports/gaode_capability_probe_summary.json
tools/gaode_data_factory/reports/generate_lifepilot_dataset_report.json
```

如需直接写入后端数据目录：

```bash
python tools/gaode_data_factory/generate_pois.py \
  --target 60 \
  --output backend/data
```

## 设计约束

- 输出顶层结构保持 `{"version":"v0.1","area":"杭州下沙/金沙湖/高教园区","pois":[]}`。
- 高德原始响应另存为 `gaode_raw_poi_responses.json`，保留 `type`、`typecode`、`location`、`biz_ext.rating`、`biz_ext.cost`、`biz_ext.open_time` 等原始字段。
- POI 字段保持与 `docs/03_schema.md` 和 qwen data factory 一致，不额外写入 `source`、`gaode_id` 等字段，避免破坏现有 validator 的字段白名单。
- `generate_lifepilot_dataset.py` 会把图片、电话、高德 id、type/typecode、business_area、原始营业时间、质量分等有用字段写入 `gaode_poi_enrichment.json` 和 `gaode_poi_review_candidates.json`，不塞进 `mock_pois.json`。
- POI 来自高德真实地点，但当前 LifePilot Demo 契约仍要求 `mock_only=true`。这表示该对象作为 Demo 数字孪生 fixture 使用，不表示状态、订座、票务来自真实商家。
- API key 只从 `AMAP_KEY` 或 `--key` 读取，不写入输出数据和报告。

## 转换规则

- 使用高德 `v3/place/text`，固定 `city=杭州`、`citylimit=true`、`extensions=all`。
- 按餐饮、活动、步道、服务、交通锚点配置多组关键词和类型码。
- 只保留经纬度落在下沙、金沙湖、高教园区边界内的 POI。
- `rating` 和 `price_per_person` 优先读取高德 `biz_ext.rating`、`biz_ext.cost`，缺失时按类别给默认值。
- `opening_hours` 优先解析高德 `biz_ext.open_time`，缺失时按类别给默认营业时间。
- `suitable_scenarios` 和 `risk_tags` 由类别/搜索规格规则补齐，保证兼容 P0 Demo。

## 500 候选池生成规则

- 使用高德 `v3/place/around`，围绕金沙湖、下沙、高教园区多个商业/生活中心坐标做周边搜索。
- type 覆盖餐饮、咖啡甜品、购物商场、休闲娱乐、电影剧场、健身运动、景区公园、书店文化。
- 不主动覆盖大学、学院、学校、校区、教学楼、宿舍等 POI；机器过滤也会剔除公司、产业园、写字楼、汽修、建材、银行、营业厅等噪声。
- 有评分且低于 `--min-rating` 的 POI 默认剔除；缺评分 POI 默认剔除，可用 `--allow-unrated` 放开。
- `mock_pois.json` 只保留 Schema 安全字段；图片地址、电话、高德原始类型等进入 enrichment/review sidecar，供前端展示实验或人工筛选参考。
- `mock_routes.json` 只写入 `RouteEstimate` 契约字段，`source` 仍为 `mock_api`；高德路线步骤、polyline、换乘摘要等保存在 `gaode_route_raw_responses.json`。
- `mock_status.json`、`mock_inventory.json`、`mock_failure_scenarios.json`、`benchmark_samples.json` 不由该脚本生成，避免伪装真实库存、排队、订座、测试失败注入和评测样例。
- 脚本会在安装了 `tqdm` 时显示 `gaode_poi_around`、`load_raw_archive`、`curate_pois`、`route_pairs`、`gaode_routes` 等进度条；未安装 `tqdm` 时自动退化为无进度条运行。

## 临时可视化

```bash
cd tools/gaode_data_factory
python -m http.server 8876 --bind 127.0.0.1
```

打开：

```text
http://127.0.0.1:8876/viewer.html
```

页面会读取 `output/*.json`，展示 raw 结构、转换后 POI、关键词/周边搜索评估指标，并支持在本地输入高德 Web 服务 Key 后通过 `/v3/staticmap` 加载真实地图图片。Key 不会写入仓库文件。
“API 能力”tab 会展示 `gaode_capability_probe_report.json`，用于判断 `mock_pois/routes/weather/status/inventory/social/failure/benchmark` 中哪些字段可由高德真实还原，哪些仍需 Mock/规则/AI。
