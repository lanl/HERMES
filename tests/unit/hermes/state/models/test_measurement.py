from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes.state.models.measurement import MeasurementInfo


def test_measurement_info_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MeasurementInfo(
            measurement_id="LC-20231023",
            run="testing",
            unsupported_field=True,
        )


def test_measurement_info_requires_run_label() -> None:
    with pytest.raises(ValidationError, match="run"):
        MeasurementInfo(measurement_id="LC-20231023")


def test_measurement_info_rejects_blank_run_label() -> None:
    with pytest.raises(ValidationError, match="run must not be blank"):
        MeasurementInfo(measurement_id="LC-20231023", run="   ")


def test_measurement_info_run_number_is_optional() -> None:
    info = MeasurementInfo(measurement_id="LC-20231023", run="testing")
    assert info.run_number is None


def test_measurement_info_run_number_must_be_non_negative() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        MeasurementInfo(
            measurement_id="LC-20231023", run="testing", run_number=-1
        )
