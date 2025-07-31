import struct
from typing import Optional
import pandas as pd
import numpy as np
from pathlib import Path
from collections import Counter
import re


class SignalsIO:
    """
    A class to read various signal files and load their data into pandas DataFrames.
    """

    _EXT_TO_FORMAT = {
        ".rawsignals": "rawsignals",
        ".csv": "csv",
        ".pixelactivations": "pixelactivations",
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
    # PUBLIC ENTRY POINT
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
        p = Path(filepath)
        if not p.exists():
            raise FileNotFoundError(f"Path does not exist: {p}")

        if p.is_dir():
            fmt = (format or "auto").lower()
            if fmt in (None, "", "auto"):
                fmt = self._detect_extensions_in_folder(p)  # raises if mixed/none
            else:
                if fmt not in ("rawsignals", "csv", "pixelactivations"):
                    raise ValueError(
                        f"Unknown format option for folder: {fmt!r}. "
                        "Use 'rawsignals' | 'csv' | 'pixelactivations'."
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
            fmt = (format or "auto").lower()
            if fmt == "auto":
                suffix = p.suffix.lower()
                if   suffix == ".rawsignals":       fmt = "rawsignals"
                elif suffix == ".csv":              fmt = "csv"
                elif suffix == ".pixelactivations": fmt = "pixelactivations"
                else:
                    raise ValueError(f"Unsupported file extension: {p.suffix}")
            return self._read_file_by_format(fmt, p)

        else:
            raise OSError(f"Unsupported path type: {p}")



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
    # FOLDER LOADING (with time-adjust)
    # ----------------------------
    def _load_folder(
        self,
        *,
        directory: Path,
        fmt: str,
        index: str,
        time_adjust: bool,
        round_period_to: float,
        file_duration: Optional[float],
    ) -> pd.DataFrame:
        files = self._list_files(directory, fmt)
        files = self._apply_index(files, index) if index else files
        if not files:
            raise ValueError(f"No files selected to load in '{directory}' (format={fmt}).")

        dfs: list[pd.DataFrame] = []
        period: Optional[float] = None

        for i, f in enumerate(files):
            df_i = self._read_file_by_format(fmt, f)

            if time_adjust:
                if "ToaFinal" not in df_i.columns:
                    raise KeyError(f"'ToaFinal' column missing in {f.name}; cannot time-adjust.")
                if period is None:
                    if file_duration is not None:
                        period = float(file_duration)
                    else:
                        period = self._infer_period(df_i["ToaFinal"].to_numpy(), round_period_to)
                        if not np.isfinite(period) or period <= 0:
                            tmin, tmax = float(df_i["ToaFinal"].min()), float(df_i["ToaFinal"].max())
                            period = max(0.0, tmax - tmin)
                    if period is None or period <= 0:
                        raise ValueError(
                            "Could not infer a positive file period; consider specifying file_duration."
                        )
                df_i = df_i.copy()
                df_i["ToaFinal"] = df_i["ToaFinal"].astype(float) + (i * period)

            dfs.append(df_i)

        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    # ----------------------------
    # HELPERS
    # ----------------------------
    def _detect_extensions_in_folder(self, directory: Path) -> str:
        """Return the single detected format in a folder or raise if multiple/none."""
        counts = Counter()
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            fmt = self._EXT_TO_FORMAT.get(entry.suffix.lower())
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
                f"Please specify format='rawsignals' | 'csv' | 'pixelactivations'."
            )

        fmt_detected, _ = counts.most_common(1)[0]
        return fmt_detected

    def _pattern_for_format(self, fmt: str) -> str:
        return {
            "rawsignals": "*.rawSignals",
            "csv": "*.csv",
            "pixelactivations": "*.pixelActivations",
        }[fmt]

    def _natural_key(self, path: Path):
        """Natural sort key so '10.rawSignals' comes after '2.rawSignals'."""
        s = path.name
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]

    def _list_files(self, directory: Path, fmt: str) -> list[Path]:
        pattern = self._pattern_for_format(fmt)
        files = sorted(directory.glob(pattern), key=self._natural_key)
        if not files:
            raise ValueError(
                f"No files matching pattern {pattern!r} found in '{directory}' (format={fmt})."
            )
        return files

    def _apply_index(self, files: list[Path], index: str) -> list[Path]:
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
        if fmt == "rawsignals":
            return self._read_rawsignals_file(path)
        elif fmt == "csv":
            return self._read_csv_file(path)
        elif fmt == "pixelactivations":
            return self._read_pixelactivations_file(path)
        else:
            raise ValueError(f"Unknown format option: {fmt}")

    def _infer_period(self, toa_values: np.ndarray, round_to: float) -> float:
        """Estimate per-file span from toa via robust quantiles; optional rounding."""
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
    # READERS (IMPLEMENTED)
    # ----------------------------
    def _read_rawsignals_file(self, path: Path) -> pd.DataFrame:
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
        df = pd.DataFrame(arr)
        df.drop(columns=[c for c in ("_pad1", "_pad2") if c in df.columns], inplace=True, errors="ignore")
        df.rename(columns={"groupID": "groupId"}, inplace=True)

        # Dtypes (exact where we can)
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
        # Try header first; fallback to no-header
        try:
            df = pd.read_csv(path, sep=r"[,\s]+", engine="python", header=0)
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

        # Ensure all target columns exist (fill if missing)
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


    def _read_pixelactivations_file(self, path: Path) -> pd.DataFrame:
        cols = ["typeOfEvent", "ToA_final", "xpixel", "ypixel", "spaceGroup", "timeGroup"]
        df = pd.read_csv(path, sep=r"\s+|,", engine="python", header=None, names=cols)

        df.rename(columns={
            "typeOfEvent": "signalType",
            "ToA_final":   "ToaFinal",
            "xpixel":      "xPixel",
            "ypixel":      "yPixel",
        }, inplace=True)

        # Add required columns not present in this format
        if "bufferNumber" not in df: df["bufferNumber"] = np.nan
        if "TotFinal" not in df:     df["TotFinal"] = np.nan
        if "groupId" not in df:      df["groupId"] = np.nan

        # Cast safe ones
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
        # Ensure ordering and the description column
        required = ["bufferNumber","signalType","xPixel","yPixel","ToaFinal","TotFinal","groupId","signalTypeDescription"]
        for col in required:
            if col not in df.columns:
                df[col] = np.nan
        return df[required + [c for c in df.columns if c not in required]]

