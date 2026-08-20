# Dev setup — AI_algo API

```bash
cd "/Users/kreckeroff/Fintech (startup)/AI_algo"
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
uvicorn ai_algo.app:app --reload --port 8090
```

- Health: `GET http://127.0.0.1:8090/v1/health`
- OpenAPI UI: `http://127.0.0.1:8090/docs`
