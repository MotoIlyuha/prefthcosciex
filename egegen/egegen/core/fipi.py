"""FIPI-2027 format configuration (design doc 7.6).

Tasks 10, 13, 23 and the answer layout of 27 are parametric: the demo version
approved in November may change the answer transform or the input structure. Those
knobs live in ``egegen/config/fipi_2027.yaml`` and are validated here, so switching
a format never requires a code change or a client release.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from egegen.core.errors import ConfigError

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "fipi_2027.yaml"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Task10Config(_Strict):
    """Task 10 — subnet masks (moved here from 13 in 2027)."""

    answer_transform: Literal["octet_sum", "address_no_dots", "number"] = "octet_sum"
    """2027 draft: the answer is the sum of the four octets (100.20.3.4 -> 127)."""
    min_prefix: int = Field(default=16, ge=8, le=30)
    max_prefix: int = Field(default=30, ge=8, le=31)

    @model_validator(mode="after")
    def _prefix_order(self) -> Task10Config:
        if self.min_prefix > self.max_prefix:
            raise ValueError("t10.min_prefix must not exceed t10.max_prefix")
        return self


class Task13Config(_Strict):
    """Task 13 — counting an executor's programs (former task 23).

    "Формулировка и формат ответа — прежние" (doc 2.1), so only the command set and
    the value ranges are configurable.
    """

    answer_transform: Literal["number"] = "number"
    commands: list[str] = Field(default_factory=lambda: ["add1", "mul2"])
    """Command ids resolved by :mod:`egegen.solvers.executor`."""
    min_a: int = Field(default=1, ge=1, le=100)
    max_b: int = Field(default=120, ge=10, le=100_000)
    answer_min: int = Field(default=3, ge=1)
    answer_max: int = Field(default=5000, ge=10)

    @model_validator(mode="after")
    def _commands_ok(self) -> Task13Config:
        if len(self.commands) < 2:
            raise ValueError("task 13 needs at least two commands")
        if len(set(self.commands)) != len(self.commands):
            raise ValueError("task 13 commands must be distinct")
        return self


class Task23Config(_Strict):
    """Task 23 — graphs: optimal path and path counting (new in 2027)."""

    graph_input_format: Literal["matrix_ods", "edges_txt", "figure"] = "matrix_ods"
    """How the graph reaches the student. Switchable without touching the solvers."""
    weighted_min_nodes: int = Field(default=7, ge=4, le=26)
    weighted_max_nodes: int = Field(default=14, ge=4, le=26)
    dag_min_nodes: int = Field(default=8, ge=4, le=26)
    dag_max_nodes: int = Field(default=20, ge=4, le=26)
    dag_answer_min: int = Field(default=5, ge=1)
    dag_answer_max: int = Field(default=5000, ge=10)
    max_weight: int = Field(default=30, ge=2, le=99)

    @model_validator(mode="after")
    def _sizes_ok(self) -> Task23Config:
        if self.weighted_min_nodes > self.weighted_max_nodes:
            raise ValueError("t23 weighted node range is inverted")
        if self.dag_min_nodes > self.dag_max_nodes:
            raise ValueError("t23 DAG node range is inverted")
        return self


class Task27Config(_Strict):
    """Task 27 — two files, efficient algorithm."""

    answer_layout: Literal["one_line_pair", "two_lines"] = "one_line_pair"
    """2027 draft: both numbers on one line, space separated."""
    separator: str = " "
    file_a_size: int = Field(default=10_000, ge=100, le=100_000)
    file_b_size: int = Field(default=1_000_000, ge=1000, le=10_000_000)
    mini_b_size: int = Field(default=100_000, ge=1000, le=200_000)
    """Phone-friendly subset of file B; the full file is produced by the worker."""


class FipiConfig(_Strict):
    version: str
    source_note: str
    banner_ru: str
    """Shown in the app until the approved FIPI demo version lands in November."""
    approved: bool = False
    """Flip to true once the November demo version has been cross-checked."""
    t10: Task10Config = Task10Config()
    t13: Task13Config = Task13Config()
    t23: Task23Config = Task23Config()
    t27: Task27Config = Task27Config()


_OVERRIDE: FipiConfig | None = None


def set_fipi_config(cfg: FipiConfig | None) -> None:
    """Install a process-wide override.

    Used by the parametricity tests and by the admin panel on stage to switch the
    answer shape of 10/13/23/27 without a code change or a restart.
    """
    global _OVERRIDE
    _OVERRIDE = cfg


def load_fipi_config(path: Path | None = None) -> FipiConfig:
    if _OVERRIDE is not None and path is None:
        return _OVERRIDE
    return _load_fipi_config(path)


@lru_cache(maxsize=4)
def _load_fipi_config(path: Path | None = None) -> FipiConfig:
    target = path or CONFIG_PATH
    if not target.exists():
        raise ConfigError(f"missing FIPI config {target}")
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    try:
        return FipiConfig.model_validate(raw)
    except Exception as exc:  # pragma: no cover - surfaced verbatim at startup
        raise ConfigError(f"{target}: {exc}") from exc


def reload_fipi_config() -> FipiConfig:
    """Drop the cache and any override, re-reading the YAML from disk."""
    set_fipi_config(None)
    _load_fipi_config.cache_clear()
    return load_fipi_config()
