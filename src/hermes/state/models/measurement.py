from __future__ import annotations

from pydantic import Field, field_validator

from hermes.state.models.shared_models import JsonObject, StrictBaseModel


class MeasurementInfo(StrictBaseModel):
    """Human and facility metadata needed to identify a measurement."""

    measurement_id: str = Field(min_length=1)
    run_number: int = Field(ge=0)
    beamline: str | None = None
    proposal_id: str | None = None
    image_intensifier_sn: str | None = None
    scintillator_sn: str | None = None
    sample_name: str | None = None
    operator_name: str | None = None
    log_notes: str | None = None
    additional_metadata: JsonObject = Field(default_factory=dict)

    @field_validator("measurement_id")
    @classmethod
    def strip_measurement_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "measurement_id must not be blank"
            raise ValueError(msg)
        return stripped
