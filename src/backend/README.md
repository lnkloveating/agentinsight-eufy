# Backend

FastAPI application skeleton. Business endpoints intentionally return `501 Not Implemented` until their application services are built. Swagger remains available for contract-driven frontend development.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m app.main
```
