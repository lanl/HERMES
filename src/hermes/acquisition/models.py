
from pydantic import BaseModel, Field, validator
import tempfile
from typing import Optional
import os

from serval.models import ServalConfig

class WorkingDir(BaseModel):
    path_to_working_dir: str = Field(default="./", description="Path to the working directory where all files will be stored.")
    run_dir_name: str = Field(default="dummy/", description="Name of the run directory where all run-specific files will be stored.")
    path_to_status_files: str = Field(default="statusFiles/", description="Path to the directory where status files will be stored.")
    path_to_log_files: str = Field(default="tpx3Logs/", description="Path to the directory where log files will be stored.")
    path_to_image_files: str = Field(default="imageFiles/", description="Path to the directory where image files will be stored.")
    path_to_rawSignal_files: str = Field(default="rawSignalFiles/", description="Path to the directory where raw signal files will be stored.")
    path_to_preview_files: str = Field(default="previewFiles/", description="Path to the directory where preview files will be stored.")
    path_to_raw_files: str = Field(default="tpx3Files/", description="Path to the directory where raw files are stored.")
    path_to_init_files: str = Field(default="initFiles/", description="Path to the initialization files.")

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
    record_images: bool = Field(default=True)
    record_raw_data: bool = Field(default=True)
    record_preview: bool = Field(default=True)
    record_status: bool = Field(default=True)

class Settings(BaseModel):
    WorkingDir: WorkingDir
    ServalConfig: ServalConfig
    RunSettings: RunSettings
    
    
