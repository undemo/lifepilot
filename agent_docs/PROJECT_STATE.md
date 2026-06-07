# 当前项目状态摘要

1. 当前实现已经是可运行的 P0 Demo，不只是空骨架。
2. 原本缺少 `AGENTS.md`，现在已补上最小协作说明。
3. 权威文档在 `docs/` 下；仓库实际使用 `docs/03_schema.md` 对应用户提到的 `03_data_schema.md`。
4. 前端是 Next.js App Router，主要代码在 `frontend/app`。
5. 后端是 FastAPI，主要代码在 `backend/app`。
6. Demo 存储使用 `backend/data` 下的 JSON 文件。
7. 主链路已存在：输入 -> 意图解析 -> 约束抽取 -> Mock 候选 -> 草案 -> Builder -> Verifier -> PlanContract。
8. 三个 P0 场景已实现：家庭亲子、朋友局、纪念日情绪导航。
9. 额外实现了单人散心的兜底场景。
10. 计划页通过 ViewModel 映射渲染完整 `PlanContract`。
11. 前端没有直接消费内部 `DraftPlan`。
12. 生成中页面展示规划服务事件流和补充偏好状态。
13. 计划执行通过 `ExecutorService` 实现。
14. Mock 执行只返回模拟凭证。
15. 餐厅满座和活动满员支持自动 Recovery。
16. 窗口过期和替换触发支持手动 Recovery。
17. 朋友局投票可用，并会 finalize 成新的已校验 PlanContract。
18. 反馈接口可生成低敏 `MemoryCandidate`。
19. 独立的 LifeMemory 后端服务已实现。
20. 记忆 API 已实现列表、候选确认/忽略、编辑、删除和个性化开关。
21. Memory 页面已接入后端 API，普通页过滤高敏候选。
22. 通用追踪 API 缺失。
23. 计划维度的追踪 API 已实现。
24. 按 `execution_id` 读取执行记录的 API 缺失。
25. 执行结果页依赖 `sessionStorage` 和计划 payload。
26. MockAPI 已实现 06 文档里的 11 个 Mock 端点。
27. Mock POI 有 500 个，覆盖下沙、金沙湖、高教园区。
28. Mock 数据包含 POI、状态、库存、路线、天气、失败场景和口碑信号层。
29. Mock 数据有区域感，但场景标签过宽：500 个 POI 都标了三个 P0 场景。
30. 路线图有 261 条路线，足够支撑 Demo 链路，但不是完整区域路网。
31. `SchemaValidator` 只是最小校验，不是完整 03 JSON Schema 校验器。
32. 运行时代码里没有发现 `ToolAction.type=create_order`。
33. 当前生成的运行时动作主要是 `book_activity` 和 `reserve_restaurant`；Executor 也支持 `order_item` 和 `send_message`。
34. 本次 X-Ray 实时运行的契约扫描通过。
35. 本次 X-Ray 实时运行的 Mock 数据校验通过。
36. 本次 X-Ray 实时运行的后端 P0 测试脚本 8/8 通过。
37. 当前环境直接运行 `pytest` 会 139 崩溃且没有标准输出。
38. 历史前端冒烟报告显示完整冒烟测试通过。
39. Playwright E2E 用例在 `frontend/e2e` 下。
40. 基准评测样例存在，但只有 3 个基础 P0 case。
41. 没有基准评测器，也没有基准评测 API。
42. 普通前端页面已收敛工程词，底层调试字段不进入主体验路径。
43. 常见机器标签已经通过映射或隐藏处理，并有 E2E 扫描覆盖。
44. 提交版不携带运行时 JSON 快照，服务按需初始化 `backend/data/runtime/`。
45. 下一步最值得加固：完整 Schema 校验、通用追踪/执行记录 API、基准评测扩展。
