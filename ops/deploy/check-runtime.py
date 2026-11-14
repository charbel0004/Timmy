"""Validate the effective production settings under the actual systemd environment."""
import os
from pathlib import Path

from sqlalchemy.engine import make_url

from timmy.config import settings

config = settings()
url = make_url(config.database_url)
if (
    url.get_backend_name() != "sqlite"
    or not url.database
    or not Path(url.database).is_absolute()
    or Path(url.database).resolve() != Path(os.environ["TIMMY_EXPECTED_DATABASE"]).resolve()
    or not Path(url.database).is_file()
    or config.frontend_origin != os.environ["TIMMY_EXPECTED_ORIGIN"]
    or not config.document_root.is_absolute()
    or not config.document_root.is_dir()
    or not os.access(config.document_root, os.W_OK | os.X_OK)
    or config.weekly_enabled
):
    raise SystemExit("Production settings mismatch or singleton scheduler enabled")
