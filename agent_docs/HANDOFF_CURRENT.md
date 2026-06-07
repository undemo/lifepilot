# 当前交接说明

## 本次已完成

- 已读取 `docs/00_project_vision.md` 到 `docs/08_evaluation_design.md`。
- 已确认当前仓库用 `docs/03_schema.md` 对应文档里提到的 `03_data_schema.md`。
- 原仓库缺少 `AGENTS.md`，已补一个最小版协作说明。
- 已扫描前端、后端、Mock 数据、测试、脚本和已有报告。
- 已把 X-Ray 文档写入 `agent_docs/`。
- 未修改业务逻辑、Schema、API，也未改 00-08 权威文档。

## 本次验证结果

```text
python scripts/contract_scan.py
  -> 通过

python scripts/validate_mock_data.py
  -> 通过

QWEN_ENABLED=false python scripts/run_backend_p0_tests.py
  -> 8/8 通过

PYTHONPATH=backend QWEN_ENABLED=false pytest -q tests -ra
python -m pytest --version
  -> 当前环境 139 崩溃，没有标准输出
```

## 当前心智模型

LifePilot 现在是一个可运行的 P0 Demo，核心对象是 `PlanContract`。主链路大致是：

```text
用户输入
-> 规则/受控 Qwen 意图理解
-> 约束抽取
-> MockAPI 候选、状态、路线、天气
-> 计划草案
-> PlanContractBuilder
-> Verifier
-> 保存 PlanContract
-> 前端计划页
-> 执行
-> Mock 凭证
-> 可选 Recovery
-> 反馈
```

当前最大缺口不是“计划能不能生成”，而是 LifeMemory 和契约严谨度还不够完整。

## 下个 Agent 优先读这些

1. `AGENTS.md`
2. `agent_docs/PROJECT_STATE.md`
3. `agent_docs/CONTRACT_GAP_REPORT.md`
4. `agent_docs/API_IMPLEMENTATION_MAP.md`
5. `backend/app/services/agent_orchestrator.py`
6. `backend/app/services/plan_service.py`
7. `frontend/lib/api.ts`
8. `frontend/app/plans/[planId]/page.tsx`

## 不要误判的点

- `/api/v1/memory/*` 已经存在；记忆候选确认/忽略走 `LifeMemoryService`。
- 不要以为 `/api/v1/traces/*` 已经存在。
- 不要以为执行页只靠 `execution_id` 就能恢复完整状态。
- 不要以为 `SchemaValidator` 已经完整实现 03 Schema。
- 不要把 `backend/data/runtime/` 当成提交内容；运行态目录由服务本地生成。
- 不要默认当前环境能直接跑 `pytest`；这次测试入口本身会崩溃。

## 后续最值得做的事

1. 补通用追踪 API 和执行记录读取 API，让调试页/执行页可刷新、可深链。
2. 用真实 JSON Schema 校验或生成模型替换最小 `SchemaValidator`。
3. 扩展基准评测器和报告汇总。
4. 把不可变固定数据和运行时状态拆开，或者加一个重置命令。
5. 把基准评测样例从 3 个扩到 08 设计里的 15 类。
6. 如果从评委演示转向产品演示，减少普通页面上的技术词。
