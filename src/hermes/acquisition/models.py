
from pydantic import BaseModel, Field
from typing import Optional

class WorkingDir(BaseModel):
    path_to_working_dir: str = Field(default="./")
    path_to_init_files: str = Field(default="initFiles/")
    run_dir_name: str = Field(default="dummy/")
    path_to_status_files: str = Field(default="statusFiles/")
    path_to_log_files: str = Field(default="tpx3Logs/")
    path_to_image_files: str = Field(default="imageFiles/")
    path_to_preview_files: str = Field(default="previewFiles/")
    path_to_raw_files: str = Field(default="tpx3Files/")

class ServerConfig(BaseModel):
    serverurl: Optional[str] = None
    path_to_server: Optional[str] = None
    path_to_server_config_files: Optional[str] = None
    destinations_file_name: Optional[str] = None
    detector_config_file_name: Optional[str] = None
    bpc_file_name: Optional[str] = None
    dac_file_name: Optional[str] = None

class RunSettings(BaseModel):
    run_name: str = Field(default="you_forgot_to_name_the_runs")
    run_number: int = Field(default=0)
    trigger_period_in_seconds: float = Field(default=1.0)
    exposure_time_in_seconds: float = Field(default=0.5)
    trigger_delay_in_seconds: float = Field(default=0.0)
    number_of_triggers: int = Field(default=0)
    global_timestamp_interval_in_seconds: float = Field(default=0.0)
    record_logs: bool = Field(default=True)
    record_images: bool = Field(default=True)
    record_raw_data: bool = Field(default=True)
    record_preview: bool = Field(default=True)
    record_status: bool = Field(default=True)

class Settings(BaseModel):
    WorkingDir: WorkingDir
    ServerConfig: ServerConfig
    RunSettings: RunSettings
