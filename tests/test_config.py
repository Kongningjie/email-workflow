from pathlib import Path

import pytest
from pydantic import ValidationError

from email_workflow.core.catalogs import Catalog, validate_versioned_configs
from email_workflow.core.config import Settings


def test_versioned_configs_are_valid() -> None:
    validate_versioned_configs(Path("config").resolve())


def test_missing_versioned_config_fails_fast(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="缺少版本化配置"):
        validate_versioned_configs(tmp_path)


def test_settings_resolve_data_path(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data")
    assert settings.data_dir.is_absolute()


def test_catalog_rejects_duplicate_keys() -> None:
    item = {
        "key": "duplicate",
        "display_name": "重复项",
        "platform_value": "DUPLICATE",
        "aliases": [],
        "enabled": True,
    }
    with pytest.raises(ValidationError, match="key 不得重复"):
        Catalog.model_validate({"version": "1.0.0", "items": [item, item]})
