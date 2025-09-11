'''
Module for defining pydantic configuration models needed for setting up a working directory structure.
'''

from pydantic import BaseModel, Field
from typing import Optional

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
    
    # Controls for side-effects
    create_if_missing: bool = Field(default=True, description="Create the directory tree if missing.")
    clean_if_exists: bool = Field(default=True, description="If the run directory exists, remove it before creating.")

    @model_validator(mode="after")
    def verify_and_prepare_dirs(cls, values):
        # Normalize base path
        working_dir = values.get("path_to_working_dir") or "./"
        working_dir = str(Path(working_dir).expanduser().resolve())
        values["path_to_working_dir"] = working_dir

        # Sanitize run_dir_name
        run_dir_name = (values.get("run_dir_name") or "run").strip().strip("/")
        if not run_dir_name or run_dir_name == "/":
            run_dir_name = "run"
        values["run_dir_name"] = run_dir_name

        # Force subpaths to be relative (no leading '/')
        rel_keys = (
            "path_to_status_files",
            "path_to_log_files",
            "path_to_image_files",
            "path_to_rawSignal_files",
            "path_to_preview_files",
            "path_to_raw_files",
            "path_to_init_files",
        )
        for k in rel_keys:
            v = values.get(k, "")
            if v is None:
                continue
            values[k] = str(v).lstrip("/")

        # Compute tree
        run_dir              = _safe_join(working_dir, run_dir_name)
        raw_file_dir         = _safe_join(run_dir, values["path_to_raw_files"])
        image_file_dir       = _safe_join(run_dir, values["path_to_image_files"])
        raw_signals_file_dir = _safe_join(run_dir, values["path_to_rawSignal_files"])
        preview_file_dir     = _safe_join(run_dir, values["path_to_preview_files"])
        tpx3_log_files_dir   = _safe_join(run_dir, values["path_to_log_files"])
        status_files_dir     = _safe_join(run_dir, values["path_to_status_files"])
        init_files_dir       = _safe_join(run_dir, values["path_to_init_files"])

        # Safety check
        if run_dir in ("", "/"):
            raise RuntimeError("Refusing to operate on root directory")

        # Side effects (optional)
        if values.get("create_if_missing", True):
            if os.path.exists(run_dir) and values.get("clean_if_exists", True):
                shutil.rmtree(run_dir)

            directories = [
                run_dir,
                raw_file_dir,
                image_file_dir,
                preview_file_dir,
                raw_signals_file_dir,
                tpx3_log_files_dir,
                status_files_dir,
                init_files_dir,
            ]
            for d in directories:
                os.makedirs(d, exist_ok=True)

        return values