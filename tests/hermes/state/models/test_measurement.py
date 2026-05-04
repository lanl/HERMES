from __future__ import annotations

import pytest
from pydantic import ValidationError

from hermes.state.models.measurement import MeasurementInfo


def test_measurement_info_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MeasurementInfo(
            measurement_id="LC-20231023",
            run_number=1,
            unsupported_field=True,
        )
