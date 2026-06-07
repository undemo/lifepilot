# backend/data

`fixtures/` 是稳定 mock source，用于 MockAPI、Verifier、Retriever、测试基准。

`runtime/` 是本地运行时写入数据，包括 plans、consensus、feedback、traces、executions、idempotency、runtime_activity_pois。提交包不带本机 runtime 快照；服务运行时会按需初始化该目录。

不要在业务服务中硬编码 data 路径。新增数据文件时，先在 `backend/app/core/data_paths.py` 增加路径常量。

测试应优先使用临时目录或 fixture copy，避免污染 `runtime/`。
