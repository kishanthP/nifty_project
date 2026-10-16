import subprocess
import sys

from tests.conftest import BACKEND_DIR


def test_models_match_migrations(database_url: str) -> None:
    """Fails if a model changed without a matching Alembic migration."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={database_url}", "check"],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
