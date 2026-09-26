from typing import Any

from pydantic import BaseModel, Field


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=128, examples=["user@demo"])
    password: str = Field(min_length=6, max_length=128, examples=["demo123"])


class ParamsIn(BaseModel):
    object_type: str = Field(examples=["warehouse"])
    values: dict[str, Any] = {}


class SelectionIn(BaseModel):
    profile_code: str = Field(examples=["pallet_transport"])
    params: dict[str, Any] = Field(default_factory=dict,
                                   description="значения параметров объекта по названию; "
                                               "пропущенные берутся из демо-датасета")


class EvaluateIn(SelectionIn):
    solution_id: str
    overrides: dict[str, float] = Field(default_factory=dict,
                                        description="изменённые допущения модели (ключ → значение)")
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="automation_share, throughput_override, route_length_m, fleet_mode "
                    "(auto|passport|manual), manual_fleet, price_factor, salary_factor, "
                    "volume_factor")


class CompareIn(SelectionIn):
    solution_ids: list[str] = Field(min_length=1, max_length=5)
    options: dict[str, Any] = Field(default_factory=dict)


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    object_type: str
    profile_code: str = ""
    parameters: dict[str, Any] = {}
    notes: str = ""


class ProjectPatch(BaseModel):
    title: str | None = None
    object_type: str | None = None
    profile_code: str | None = None
    parameters: dict[str, Any] | None = None
    notes: str | None = None


class ScenarioIn(EvaluateIn):
    title: str = "Сценарий"


class SolutionIn(BaseModel):
    external_id: str | None = None
    name: str
    vendor: str = ""
    subtype: str
    scenarios: list[str] = []
    object_types: list[str] = []
    status: str = "operation"
    trl: int | None = None
    price_rub: float | None = None
    price_note: str = ""
    description: str = ""
    cases: str = ""
    country: str = "Россия"
    industry: str = "Торговля и услуги"
    specs: dict[str, Any] = Field(default_factory=dict,
                                  description="ключ → {value, unit, source, confirmed}")
    data_source: str = "Добавлено администратором"
    source_url: str | None = None


class AssumptionIn(BaseModel):
    value: float
    source: str = Field(min_length=3)
