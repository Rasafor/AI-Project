"""Connects to the data-quality metrics source for a pipeline incident (REQ-004)."""

from __future__ import annotations

import json
from pathlib import Path


class DataQualitySourceUnavailableError(Exception):
    """The data-quality metrics source itself could not be reached or read."""


class DataQualityInfoMissingError(Exception):
    """The source was read but has no usable data-quality metrics to analyze."""


def load_incident_data_quality(path: str | Path) -> dict:
    """Load the data-quality metrics for an incident from its JSON source file."""
    path = Path(path)

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DataQualitySourceUnavailableError(f"No data-quality source found at {path}") from exc
    except OSError as exc:
        raise DataQualitySourceUnavailableError(
            f"Could not read data-quality source at {path}: {exc}"
        ) from exc

    try:
        incident = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataQualitySourceUnavailableError(
            f"Data-quality source at {path} is not valid JSON: {exc}"
        ) from exc

    metrics = incident.get("data_quality_checks")
    if not isinstance(metrics, dict) or not metrics:
        raise DataQualityInfoMissingError(
            f"Data-quality source at {path} has no usable data_quality_checks"
        )

    return {
        "incident_id": incident.get("incident_id"),
        "metrics": metrics,
    }
