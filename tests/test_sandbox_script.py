"""The sandbox script must never make a live call by accident: without credentials it refuses (exit 2) before importing anything networked."""
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sandbox_buy_goods_check.py"


def _run(env_extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("DARAJA_")}
    env.update(env_extra)
    return subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, env=env, timeout=30)


def test_refuses_without_credentials():
    r = _run({})
    assert r.returncode == 2 and "missing environment variables" in r.stderr


def test_refuses_a_non_https_callback():
    r = _run({"DARAJA_CONSUMER_KEY": "k", "DARAJA_CONSUMER_SECRET": "s", "DARAJA_CALLBACK_URL": "http://localhost:5000/cb"})
    assert r.returncode == 2 and "https" in r.stderr


def test_script_is_sandbox_only():
    assert "sandbox=True" in SCRIPT.read_text() and "api.safaricom.co.ke" not in SCRIPT.read_text()
