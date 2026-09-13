from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    display_name: str
    platform_value: str
    aliases: list[str] = Field(default_factory=list)
    enabled: bool = True
    owner_name: str | None = None
    owner_employee_id: str | None = None


class Catalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    items: list[CatalogItem]

    @model_validator(mode="after")
    def keys_are_unique(self) -> Catalog:
        keys = [item.key for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("配置项 key 不得重复")
        return self


class RuleMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    version: str
    severity: Literal["blocking", "warning", "info"]
    enabled: bool
    message: str


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    rules: list[RuleMetadata]

    @model_validator(mode="after")
    def rule_ids_are_unique(self) -> RuleSet:
        ids = [rule.id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("规则 ID 不得重复")
        return self


class PromptLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_domains: int = Field(gt=0)
    max_cases_per_domain: int = Field(gt=0)
    max_cases_total: int = Field(gt=0)
    max_steps_per_case: int = Field(gt=0)


class PromptDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    model: str
    temperature: float
    thinking: bool
    system_prompt: str
    limits: PromptLimits


class MappingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    contract_version: str
    fixed_values: dict[str, str]
    fields: dict[str, str]
    forbidden_fields: list[str]
    limits: dict[str, int]
    near_limit_ratio: float = Field(gt=0, lt=1)

    @model_validator(mode="after")
    def required_contract_keys_exist(self) -> MappingDocument:
        required_fields = {
            "plan_name",
            "project_name",
            "project_code",
            "requirement_ids",
            "test_type",
            "test_stage",
            "test_round",
            "priority",
            "test_version",
            "planned_start_date",
            "planned_end_date",
            "objective",
            "scope",
            "environment",
            "risks",
            "dependencies",
            "details",
        }
        required_limits = {
            "plan_name",
            "project_name",
            "project_code",
            "test_round",
            "test_version",
            "objective",
            "scope",
            "environment",
            "domain_scope",
            "requirement",
            "case_title",
            "case_objective",
            "case_step",
            "case_expected_result",
            "max_domains",
            "max_cases_per_domain",
            "max_cases_total",
            "max_steps_per_case",
        }
        if "source_system" not in self.fixed_values:
            raise ValueError("平台映射缺少 source_system 固定值")
        if not required_fields <= set(self.fields):
            raise ValueError("平台映射缺少必需字段")
        if not required_limits <= set(self.limits) or any(
            value <= 0 for value in self.limits.values()
        ):
            raise ValueError("平台映射缺少有效字段上限")
        return self


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        payload = yaml.safe_load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"配置文件必须是 YAML 对象: {path.name}")
    return payload


def load_catalog(path: Path) -> Catalog:
    return Catalog.model_validate(_read_yaml(path))


def load_prompt_document(path: Path) -> PromptDocument:
    return PromptDocument.model_validate(_read_yaml(path))


def load_rule_set(path: Path) -> RuleSet:
    return RuleSet.model_validate(_read_yaml(path))


def load_mapping_document(path: Path) -> MappingDocument:
    return MappingDocument.model_validate(_read_yaml(path))


def validate_versioned_configs(config_dir: Path) -> None:
    required: list[
        tuple[
            str,
            type[Catalog] | type[RuleSet] | type[PromptDocument] | type[MappingDocument],
        ]
    ] = [
        ("domains/v1.yaml", Catalog),
        ("values/test-types-v1.yaml", Catalog),
        ("values/test-stages-v1.yaml", Catalog),
        ("values/priorities-v1.yaml", Catalog),
        ("rules/v1.yaml", RuleSet),
        ("prompts/extraction-v1.yaml", PromptDocument),
        ("mappings/mock-platform-v1.yaml", MappingDocument),
    ]
    for relative_path, schema in required:
        path = config_dir / relative_path
        if not path.is_file():
            raise ValueError(f"缺少版本化配置: {relative_path}")
        schema.model_validate(_read_yaml(path))
