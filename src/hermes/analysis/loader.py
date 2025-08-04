import struct
from typing import Optional
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter
import re


class SignalsIO:
    """
    A class for reading, processing, and exporting signal data from various file formats 
    into pandas DataFrames. Supports `.rawSignals`, `.csv`, and `.pixelActivations` formats.
    """


    _EXT_TO_FORMAT = {
        ".rawSignals": "rawSignals",
        ".csv": "csv",
        ".pixelActivations": "pixelActivations",
    }

    # Mapping from numeric signal types to descriptions
    SIGNAL_TYPES = {
        0: "Unknown/Padding",
        1: "TDC",
        2: "Pixel",
        3: "GTS",
        4: "SPIDR_Control",
        5: "TPX3_Control",
    }

    # ----------------------------
    # PUBLIC FUNCTIONS
    # ----------------------------
    def load_data(
        self,
        filepath: str,
        *,
        format: Optional[str] = None,
        index: str = "",
        time_adjust: bool = False,
        round_period_to: float = 0.5,
        file_duration: Optional[float] = None,
    ) -> pd.DataFrame:
    """
    Load signal data from a file or folder into a DataFrame.

    Args:
        filepath (str): Path to the input file or directory.
        format (Optional[str]): Explicit format to use ('rawSignals', 'csv', 'pixelActivations'). 
            If None or 'auto', it is inferred from the extension or folder contents.
        index (str): Index string to select a file slice (e.g., '0:3').
        time_adjust (bool): Whether to time-adjust signals across files using ToA.
        round_period_to (float): Rounding factor for estimated period during time adjustment.
        file_duration (Optional[float]): Explicit file duration to use for time adjustment.

    Returns:
        pd.DataFrame: Combined signal data.
    """
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {p}")

        if p.is_dir():
            fmt = (format or "auto")
            if fmt in (None, "", "auto"):
                fmt = self._detect_extensions_in_folder(p)  # raises if mixed/none
            else:
                if fmt not in ("rawSignals", "csv", "pixelActivations"):
                    raise ValueError(
                        f"Unknown format option for folder: {fmt!r}. "
                        "Use 'rawSignals' | 'csv' | 'pixelActivations'."
                    )
            return self._load_folder(
                directory=p,
                fmt=fmt,
                index=index,
                time_adjust=time_adjust,
                round_period_to=round_period_to,
                file_duration=file_duration,
            )

        elif p.is_file():
            fmt = (format or "auto")
            if fmt == "auto":
                suffix = p.suffix
                if   suffix == ".rawSignals":       fmt = "rawSignals"
                elif suffix == ".csv":              fmt = "csv"
                elif suffix == ".pixelActivations": fmt = "pixelActivations"
                else:
                    raise ValueError(
                        f"Unsupported file extension: {p.suffix} - "
                        f"Supported extensions are: {', '.join(sorted(self._EXT_TO_FORMAT.keys()))}"
                        )
            print(f"Loading {fmt} file: {p.name} ...")
            return self._read_file_by_format(fmt, p)

        else:
            raise OSError(f"Unsupported path type: {p}. Double check capitalization in file (.rawsignal is invalid, use .rawSignal)")



    def export_to_csv(self, df: pd.DataFrame, output_path: str) -> None:
        """
        Export DataFrame to CSV file.
        
        Args:
            df (pd.DataFrame): DataFrame to export
            output_path (str): Path for output CSV file
        """
        df.to_csv(output_path, index=False)
        print(f"Data exported to CSV: {output_path}")
        

    def export_to_parquet(self, df: pd.DataFrame, output_path: str) -> None:
        """
        Export DataFrame to Parquet file.
        
        Args:
            df (pd.DataFrame): DataFrame to export
            output_path (str): Path for output Parquet file
        """
        df.to_parquet(output_path, index=False)
        print(f"Data exported to Parquet: {output_path}")

    # ----------------------------
    # FOLDER LOADING (with time-adjustment based on ToA in files)
    # ----------------------------
    def _load_folder(
        self,
        directory: Path,
        fmt: str,
        index: str = "",
        time_adjust: bool = False,
        round_period_to: float = 0.5,
        file_duration: Optional[float] = None,
    ) -> pd.DataFrame:
    """
    Load and concatenate signal files from a folder.

    Args:
        directory (Path): Path to the folder.
        fmt (str): Format of files in the folder ('rawSignals', 'csv', or 'pixelActivations').
        index (str): Index string for file slicing.
        time_adjust (bool): Whether to apply time adjustments using ToA.
        round_period_to (float): Rounding value for estimated period.
        file_duration (Optional[float]): Manually specified file duration.

    Returns:
        pd.DataFrame: Concatenated and optionally time-adjusted signal data.
    """
        pattern = self._pattern_for_format(fmt)
        files = self._list_files(directory, fmt)

        # Apply index slicing if requested
        full_range_count = len(files)
        if index:
            parts = index.split(":")
            try:
                if len(parts) == 1:
                    start = int(parts[0]); stop = start + 1; step = 1
                elif len(parts) == 2:
                    start, stop = int(parts[0]), int(parts[1]); step = 1
                elif len(parts) == 3:
                    start, stop, step = int(parts[0]), int(parts[1]), int(parts[2])
                else:
                    raise ValueError
            except ValueError:
                raise ValueError(
                    f"Invalid index format: {index!r}. Use 'start', 'start:stop', or 'start:stop:step'."
                )

            full_range_count = stop - start  # used later for time adjustment
            files = [files[i] for i in range(start, stop, step) if 0 <= i < len(files)]
            if not files:
                raise ValueError(
                    f"index {index!r} selected no files "
                    f"(valid indices: 0–{len(sorted(directory.glob(pattern))) - 1})."
                )

        dfs = []
        file_indices = [f.name for f in sorted(directory.glob(self._pattern_for_format(fmt)))]
        period = None
        total_duration = None

        for i, path in enumerate(files):
            idx = file_indices.index(path.name)
            print(f"[{idx}] Loading {fmt} file: {path.name} ...")

            df = self._read_file_by_format(fmt, path)

            if time_adjust:
                if "ToaFinal" not in df.columns:
                    raise KeyError(f"Column 'ToaFinal' not found in {path.name}.")
                if period is None:
                    period = (
                        file_duration if file_duration is not None
                        else self._infer_period(df["ToaFinal"].to_numpy(), round_period_to)
                    )
                    total_duration = full_range_count * period

                df = df.copy()
                adjusted_t0 = i * (total_duration / len(files))
                df["ToaFinal"] = df["ToaFinal"].astype(float) + adjusted_t0

            dfs.append(df)

        result = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        print(f"\nSuccessfully loaded {len(result):,} signal records from {len(files)} file(s).")
        if time_adjust and period is not None:
            print(f"Time adjustment: constant period = {period}, total adjusted window = {total_duration} s")
        return result



    # ----------------------------
    # HELPERS
    # ----------------------------
    def _detect_extensions_in_folder(self, directory: Path) -> str:
        """
        Detect the signal file format in a folder.

        Args:
            directory (Path): Directory to scan.

        Returns:
            str: Detected format ('rawSignals', 'csv', or 'pixelActivations').

        Raises:
            ValueError: If no supported files or multiple formats are found.
        """
        counts = Counter()
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            fmt = self._EXT_TO_FORMAT.get(entry.suffix)
            if fmt:
                counts[fmt] += 1

        if not counts:
            supported = ", ".join(sorted(set(self._EXT_TO_FORMAT.keys())))
            raise ValueError(
                f"No supported files found in folder '{directory}'. "
                f"Supported extensions: {supported}"
            )

        if len(counts) > 1:
            details = ", ".join(f"{k}={counts[k]}" for k in sorted(counts))
            raise ValueError(
                f"Multiple supported file types found in folder '{directory}': {details}. "
                f"Please specify format='rawSignals' | 'csv' | 'pixelActivations'."
            )

        fmt_detected, _ = counts.most_common(1)[0]
        return fmt_detected


    def _pattern_for_format(self, fmt: str) -> str:
        """
        Get the filename glob pattern for a given format.

        Args:
            fmt (str): File format ('rawSignals', 'csv', or 'pixelActivations').

        Returns:
            str: Glob pattern for file matching.
        """
        return {
            "rawSignals": "*.rawSignals",
            "csv": "*.csv",
            "pixelActivations": "*.pixelActivations",
        }[fmt]


    def _natural_key(self, path: Path):
        """
        Generate a sorting key for natural sorting of file names.

        Args:
            path (Path): File path.

        Returns:
            list: Sorting key with numeric components handled naturally.
        """
        s = path.name
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


    def _list_files(self, directory: Path, fmt: str) -> list[Path]:
        """
        List and sort files in a directory that match the given format.

        Args:
            directory (Path): Directory to search.
            fmt (str): File format ('rawSignals', 'csv', 'pixelActivations').

        Returns:
            list[Path]: List of matching files.

        Raises:
            ValueError: If no files matching the pattern are found.
        """
        pattern = self._pattern_for_format(fmt)
        files = sorted(
            [f for f in directory.glob(pattern) if not f.name.startswith("._")], # Remove macOS helper files '._'
            key=self._natural_key,
        )
        if not files:
            raise ValueError(
                f"No files matching pattern {pattern!r} found in '{directory}' (format={fmt})."
            )
        return files


    def _apply_index(self, files: list[Path], index: str) -> list[Path]:
        """
        Apply index slicing to a list of files.

        Args:
            files (list[Path]): List of files.
            index (str): Index string (e.g., '2', '1:4', '0:10:2').

        Returns:
            list[Path]: Sliced file list.

        Raises:
            ValueError: If the index is invalid or selects no files.
        """
        if isinstance(index, int):
            start, stop, step = index, index + 1, 1
        else:
            parts = [p.strip() for p in str(index).split(":")]
            try:
                if len(parts) == 1:
                    start = int(parts[0]); stop = start + 1; step = 1
                elif len(parts) == 2:
                    start, stop = int(parts[0]), int(parts[1]); step = 1
                elif len(parts) == 3:
                    start, stop, step = int(parts[0]), int(parts[1]), int(parts[2])
                else:
                    raise ValueError
            except ValueError:
                raise ValueError(
                    f"Invalid index format: {index!r}. "
                    "Use 'start', 'start:stop', or 'start:stop:step'."
                )
        sel = [files[i] for i in range(start, stop, step) if 0 <= i < len(files)]
        if not sel:
            raise ValueError(
                f"index {index!r} selected no files (valid indices: 0–{len(files) - 1})."
            )
        return sel


    def _read_file_by_format(self, fmt: str, path: Path) -> pd.DataFrame:
        """
        Read a single file based on its format.

        Args:
            fmt (str): Format type ('rawSignals', 'csv', or 'pixelActivations').
            path (Path): Path to the file.

        Returns:
            pd.DataFrame: Parsed DataFrame.

        Raises:
            ValueError: If an unknown format is provided.
        """
        if fmt == "rawSignals":
            return self._read_rawSignals_file(path)
        elif fmt == "csv":
            return self._read_csv_file(path)
        elif fmt == "pixelActivations":
            return self._read_pixelActivations_file(path)
        else:
            raise ValueError(f"Unknown format option: {fmt}")


    def _infer_period(self, toa_values: np.ndarray, round_to: float) -> float:
        """
        Estimate period between signals using robust quantiles.

        Args:
            toa_values (np.ndarray): Array of ToA values.
            round_to (float): Round estimated period to nearest multiple of this value.

        Returns:
            float: Estimated period.
        """
        arr = np.asarray(toa_values, dtype=float)
        if arr.size == 0 or not np.isfinite(arr).any():
            return 0.0
        lo = float(np.nanquantile(arr, 0.001))
        hi = float(np.nanquantile(arr, 0.999))
        est = max(0.0, hi - lo)
        if round_to and round_to > 0:
            return float(round(est / round_to) * round_to)
        return est


    # ----------------------------
    # READERS
    # ----------------------------
    def _read_rawSignals_file(self, path: Path) -> pd.DataFrame:
        """
        Read a .rawSignals binary file into a DataFrame.

        Args:
            path (Path): Path to the .rawSignals file.

        Returns:
            pd.DataFrame: Parsed signal data.
        """
        data = path.read_bytes()
        record_size = 24
        if len(data) % record_size != 0:
            raise ValueError(
                f"Invalid .rawSignals file '{path.name}': size {len(data)} not multiple of {record_size}."
            )

        dtype = np.dtype([
            ("bufferNumber", "<u4"),
            ("signalType",   "<u1"),
            ("xPixel",       "<u1"),
            ("yPixel",       "<u1"),
            ("_pad1",        "<u1"),
            ("ToaFinal",     "<f8"),
            ("TotFinal",     "<u2"),
            ("_pad2",        "<u2"),
            ("groupID",      "<u4"),
        ])

        arr = np.frombuffer(data, dtype=dtype)
        print(f"  -> {len(arr):,} packets loaded from {path.name}")
        df = pd.DataFrame(arr)
        df.drop(columns=[c for c in ("_pad1", "_pad2") if c in df.columns], inplace=True, errors="ignore")
        df.rename(columns={"groupID": "groupId"}, inplace=True)


        try:
            df = df.astype({
                "bufferNumber": "uint32",
                "signalType":   "uint8",
                "xPixel":       "uint8",
                "yPixel":       "uint8",
                "ToaFinal":     "float64",
                "TotFinal":     "uint16",
                "groupId":      "uint32",
            })
        except Exception:
            pass

        df["signalTypeDescription"] = df["signalType"].map(self.SIGNAL_TYPES)
        return df


    def _read_csv_file(self, path: Path) -> pd.DataFrame:
        """
        Read a CSV file into a DataFrame with flexible header handling.

        Args:
            path (Path): Path to the CSV file.

        Returns:
            pd.DataFrame: Parsed signal data with normalized column names.
        """
        # Try header first; fallback to no-header
        try:
            df = pd.read_csv(path, sep=r"[,\s]+", engine="python", header=0)
            print(f"  -> {len(df):,} rows loaded from {path.name}")
        except Exception:
            df = pd.read_csv(path, sep=r"[,\s]+", engine="python", header=None)

        # If it looks like plotter-style (7 cols, no known headers), set names
        if df.shape[1] == 7 and not set(df.columns).intersection(
            {"bufferNumber","buffer_number","signalType","signal_type","xPixel","x_pixel"}
        ):
            df.columns = ["bufferNumber","signalType","xPixel","yPixel","ToaFinal","TotFinal","groupId"]

        # Normalize common variants -> camelCase target
        rename = {
            # snake_case variants
            "buffer_number": "bufferNumber",
            "signal_type":   "signalType",
            "x_pixel":       "xPixel",
            "y_pixel":       "yPixel",
            "toa":           "ToaFinal",
            "tot":           "TotFinal",
            "group_ID":      "groupId",
            "group_id":      "groupId",
            "groupID":       "groupId",
            # mixed-case variants seen before
            "ToaFinal":      "ToaFinal",   # no-op if already
            "TotFinal":      "TotFinal",
        }
        df.rename(columns=rename, inplace=True)

        # Ensure all target columns exist
        required = ["bufferNumber","signalType","xPixel","yPixel","ToaFinal","TotFinal","groupId"]
        for col in required:
            if col not in df.columns:
                df[col] = np.nan

        # Dtypes: enforce where safe (note: NaN forces float; we keep those as float)
        for col, dt in {
            "bufferNumber": "uint32",
            "signalType":   "uint8",
            "xPixel":       "uint8",
            "yPixel":       "uint8",
            "ToaFinal":     "float64",
            # TotFinal / groupId may be NaN for CSV sources → leave as float64
        }.items():
            if col in df.columns:
                try:
                    df[col] = df[col].astype(dt)
                except Exception:
                    pass

        # Description if numeric
        if pd.api.types.is_integer_dtype(df["signalType"]):
            df["signalTypeDescription"] = df["signalType"].map(self.SIGNAL_TYPES)
        else:
            df["signalTypeDescription"] = np.nan

        # Order columns (targets first)
        ordered = required + ["signalTypeDescription"]
        df = df[ordered + [c for c in df.columns if c not in ordered]]
        return df


    def _read_pixelActivations_file(self, path: Path) -> pd.DataFrame:
        """
        Read a .pixelActivations file into a DataFrame.

        Args:
            path (Path): Path to the .pixelActivations file.

        Returns:
            pd.DataFrame: Parsed signal data with standardized columns.
        """
        cols = ["typeOfEvent", "ToA_final", "xpixel", "ypixel", "spaceGroup", "timeGroup"]
        df = pd.read_csv(path, sep=r"\s+|,", engine="python", header=None, names=cols)
        print(f"  -> {len(df):,} rows loaded from {path.name}")

        df.rename(columns={
            "typeOfEvent": "signalType",
            "ToA_final":   "ToaFinal",
            "xpixel":      "xPixel",
            "ypixel":      "yPixel",
        }, inplace=True)

        if "bufferNumber" not in df: df["bufferNumber"] = np.nan
        if "TotFinal" not in df:     df["TotFinal"] = np.nan
        if "groupId" not in df:      df["groupId"] = np.nan

        for col, dt in {
            "signalType":   "uint8",
            "xPixel":       "uint8",
            "yPixel":       "uint8",
            "ToaFinal":     "float64",
        }.items():
            try:
                df[col] = df[col].astype(dt)
            except Exception:
                pass

        df["signalTypeDescription"] = df["signalType"].map(self.SIGNAL_TYPES)
        # Final ordering
        required = ["bufferNumber","signalType","xPixel","yPixel","ToaFinal","TotFinal","groupId","signalTypeDescription"]
        extras = [c for c in df.columns if c not in required]
        return df[required + extras]


    # ----------------------------
    # NORMALIZATION - Currently not required for anything, keeping it around just in case. 
    # ----------------------------
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize column presence and order in a DataFrame.

        Args:
            df (pd.DataFrame): Input DataFrame.

        Returns:
            pd.DataFrame: Normalized DataFrame with required columns.
        """
        # Ensure ordering and the description column
        required = ["bufferNumber","signalType","xPixel","yPixel","ToaFinal","TotFinal","groupId","signalTypeDescription"]
        for col in required:
            if col not in df.columns:
                df[col] = np.nan
        return df[required + [c for c in df.columns if c not in required]]

