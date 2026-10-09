import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

DATASET_DIR = Path(__file__).resolve().parent / "datasets"


class CaseDataset(BaseModel):
    schema_version: int = Field(ge=1)
    dataset_version: str = Field(min_length=1)
    description: str = Field(min_length=1)
    labeling_method: str | None = None
    policy_scope: str | None = None
    cases: list[dict[str, Any]]


def load_case_dataset(filename: str) -> CaseDataset:
    path = DATASET_DIR / filename
    payload = json.loads(path.read_text(encoding="utf-8"))
    dataset = CaseDataset.model_validate(payload)
    case_ids = [str(case.get("id") or case.get("case_id") or "") for case in dataset.cases]
    if any(not case_id for case_id in case_ids):
        raise ValueError(f"평가 case ID가 비어 있습니다: {path}")
    if len(case_ids) != len(set(case_ids)):
        raise ValueError(f"평가 case ID가 중복됩니다: {path}")
    return dataset
