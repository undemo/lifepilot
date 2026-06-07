# LifePilot Backend

FastAPI backend for LifePilot. Business APIs use `/api/v1`; mock/debug APIs are clearly marked as Mock/模拟.

Run locally:

```bash
cd backend
python3 -m pip install -r requirements.txt
PYTHONPATH=. DEEPSEEK_ENABLED=false QWEN_ENABLED=false \
  python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Useful checks:

```bash
cd ..
PYTHONPATH=backend python3 scripts/run_backend_p0_tests.py
PYTHONPATH=backend python3 scripts/contract_scan.py
PYTHONPATH=backend python3 scripts/validate_mock_data.py
```
