import pathlib
import re

import mpesa

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_the_module_version_equals_the_package_version():
    """0.1.2 shipped reporting mpesa.__version__ == '0.1.1': the string was a second copy that nobody bumped."""
    declared = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    assert mpesa.__version__ == declared
