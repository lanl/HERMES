''' 
Module for defining the run settings pydantic model needed for setting up a data acquisition run.
'''

from pydantic import BaseModel, Field
from typing import Optional

class RunSettings(BaseModel):
    run_name: str = Field(default="you_forgot_to_name_the_runs")
    run_number: int = Field(default=0)
    trigger_period_in_seconds: float = Field(default=1.0)
    exposure_time_in_seconds: float = Field(default=0.5)
    trigger_delay_in_seconds: float = Field(default=0.0)
    number_of_triggers: int = Field(default=0)
    number_of_runs: int = Field(default=0)
    global_timestamp_interval_in_seconds: float = Field(default=0.0)
    record_logs: bool = Field(default=True)
    record_tpx_data: bool = Field(default=True)
    record_preview: bool = Field(default=True)
    record_status: bool = Field(default=True)