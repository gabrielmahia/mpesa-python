# Contributing to mpesa-python

## What's welcome

- Bug fixes with regression tests
- New Daraja API endpoints (Transaction Status, Reversal, QR Code, Ratiba)
- Better error messages for known M-Pesa error codes
- Async client (`MpesaAsyncClient` using `aiohttp`)
- Documentation improvements

## What's not (yet)

- Framework-specific integrations (Django, FastAPI) — these belong in separate packages
- Webhook signature validation — working on it, Daraja doesn't publish the algorithm

## Workflow

1. Open an issue first for anything beyond a small bug fix
2. Fork, branch (`feature/your-feature-name`), commit
3. All PRs must have passing tests — `pytest tests/` must be green
4. Match the existing code style — `ruff check .` must pass
5. PRs without tests for new functionality will be closed with explanation

## Testing

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Integration tests require Daraja sandbox credentials — see README for setup.

## Commit style

```
type: short description

Longer explanation if needed.
```

Types: `fix`, `feat`, `test`, `docs`, `refactor`, `chore`

## Contact

Open an issue, or email contact@aikungfu.dev for anything sensitive.
