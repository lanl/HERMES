"""
Raw Signal Data Reader

This module provides functionality to read raw signal binary files to pandas DataFrames.
The binary format is based on the signalData structure from the C++ HERMES code.

Requirements:
    pip install pandas numpy

Usage:
    from hermes.analysis.reader import SignalDataReader
    
    reader = SignalDataReader()
    df = reader.read_rawsignals_folder(path/to/rawsignal/directory, index_range="0:100")
    
Author: HERMES Team
"""

import struct
from typing import Optional, Dict, Any, Iterable
import pandas as pd
import numpy as np
import os


class SignalDataReader:
    """
    A class to read raw signal binary files to pandas DataFrames.
    
    The binary file format is based on the signalData structure from the C++ code:
    - bufferNumber: uint32_t (4 bytes)
    - signalType: uint8_t (1 byte)  
    - xPixel: uint8_t (1 byte)
    - yPixel: uint8_t (1 byte)
    - padding: 1 byte (for double alignment)
    - ToaFinal: double (8 bytes)
    - TotFinal: uint16_t (2 bytes)
    - padding: 2 bytes (for uint32_t alignment)
    - groupID: uint32_t (4 bytes)
    Total: 24 bytes per signal (with compiler padding)
    """
    
    # Signal type mappings based on the C++ code comments
    SIGNAL_TYPES = {
        0: 'Unknown/Padding',
        1: 'TDC',
        2: 'Pixel',
        3: 'GTS',
        4: 'SPIDR_Control',
        5: 'TPX3_Control'
    }
    
    def __init__(self):
        """Initialize the SignalDataReader."""
            
        # Account for compiler padding in C++ struct
        # Original: uint32_t(4) + uint8_t(1) + uint8_t(1) + uint8_t(1) + double(8) + uint16_t(2) + uint32_t(4) = 21 bytes
        # With padding: uint32_t(4) + uint8_t(1) + uint8_t(1) + uint8_t(1) + pad(1) + double(8) + uint16_t(2) + pad(2) + uint32_t(4) = 24 bytes
        self.struct_format = '<I B B B x d H xx I'  # Little-endian format with padding
        self.struct_size = struct.calcsize(self.struct_format)
    
        
    def read_rawsignals_file(self, filepath: str) -> pd.DataFrame:
        """
        Read raw signal binary file and convert to pandas DataFrame.
        
        Args:
            filepath (str): Path to the raw signal binary file
            
        Returns:
            pd.DataFrame: DataFrame containing the signal data
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file format is invalid
        """
        with open(filepath, 'rb') as f:
            data = f.read()

        # Check if file size is valid (should be multiple of struct_size)
        if len(data) % self.struct_size != 0:
            raise ValueError(f"Invalid file format: file size {len(data)} is not a multiple of expected struct size {self.struct_size}")

        # Vectorized parsing: np.frombuffer is much faster than struct.unpack loop
        dtype = np.dtype([
            ('bufferNumber', '<u4'),
            ('signalType', '<u1'),
            ('xPixel', '<u1'),
            ('yPixel', '<u1'),
            ('_pad1', '<u1'),  # padding
            ('ToaFinal', '<f8'),
            ('TotFinal', '<u2'),
            ('_pad2', '<u2'),  # padding
            ('groupID', '<u4')
        ])
        arr = np.frombuffer(data, dtype=dtype)

        # Create DataFrame
        df = pd.DataFrame(arr)
        df.drop(columns=['_pad1', '_pad2'], inplace=True)  # remove padding
        df['signalTypeDescription'] = df['signalType'].map(self.SIGNAL_TYPES)
        return df


    def read_rawsignals_folder(self, directory: str, index_range: str = "", *, time_adjust: bool = False, round_period_to: float = 0.5, file_duration: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Load multiple .rawSignals files into a single DataFrame, with optional constant
        time adjustment to make 'ToA' continuous across files.

        Args:
            directory: Directory containing .rawSignals files.
            index_range: Optional slice syntax to select files, e.g. "5", "5:10", "5:10:2".
            time_adjust: If True, shift 'ToA' so timelines are contiguous across files.
            round_period_to: When inferring the per-file span, round to the nearest multiple of this.
                    Set <= 0 to disable rounding. Default: 0.5 (e.g., 4.99 → 5.0).
            file_duration: If provided (e.g., 5.0), use this span for every file; no inference.

        Returns:
            pd.DataFrame
        """
        all_files = sorted([f for f in os.listdir(directory) if f.endswith('.rawSignals')])

        # Apply index_range filtering if provided
        if index_range:
            parts = index_range.split(":")
            if len(parts) == 1:
                start = int(parts[0]); stop = start + 1; step = 1
            elif len(parts) == 2:
                start, stop = int(parts[0]), int(parts[1]); step = 1
            elif len(parts) == 3:
                start, stop, step = int(parts[0]), int(parts[1]), int(parts[2])
            else:
                raise ValueError("Invalid index_range format. Use 'start:end:step'.")
            selected_files = [all_files[i] for i in range(start, stop, step) if 0 <= i < len(all_files)]
            if not selected_files:
                raise ValueError(
                    f"Invalid index_range '{index_range}'. "
                    f"Make sure it matches the available files (0–{len(all_files) - 1})."
                )
        else:
            selected_files = all_files

        if not selected_files:
            raise ValueError("No .rawSignals files found to load.")

        def infer_period(toa_values: np.ndarray, round_period_to: float) -> float:
            """Estimate per-file span robustly, with optional rounding."""
            arr = np.asarray(toa_values, dtype=float)
            if arr.size == 0:
                return 0.0
            lo = np.nanquantile(arr, 0.001)
            hi = np.nanquantile(arr, 0.999)
            est = max(0.0, float(hi - lo))
            if round_period_to and round_period_to > 0:
                return float(round(est / round_period_to) * round_period_to)
            return est

        df_list = []
        period = None  # set once and reused (constant mode)

        for i, fname in enumerate(selected_files):
            idx = all_files.index(fname)
            print(f"[{idx}] Reading {fname} ...")
            filepath = os.path.join(directory, fname)
            df_i = self.read_rawsignals_file(filepath)

            if time_adjust:
                if "ToaFinal" not in df_i.columns:
                    raise KeyError(f"Column 'ToaFinal' not found in {fname}.")
                if period is None:
                    period = file_duration if file_duration is not None else infer_period(df_i["ToaFinal"].to_numpy(), round_period_to)
                df_i = df_i.copy()
                df_i["ToaFinal"] = df_i["ToaFinal"].astype(float) + (i * period)

            df_list.append(df_i)

        df = pd.concat(df_list, ignore_index=True)
        print(f"\nSuccessfully loaded {len(df):,} signal records from {len(selected_files)} files")
        if time_adjust:
            print(f"Time adjustment: constant period = {period}")
        return df


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
    

    def get_summary_stats(self, df: pd.DataFrame, *, rows: int = 10) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "total_signals": len(df),
            "unique_buffers": df["bufferNumber"].nunique() if "bufferNumber" in df else None,
            "signal_type_counts": df["signalTypeDescription"].value_counts(dropna=False).to_dict()
                                    if "signalTypeDescription" in df else None,
            "toa_range": None,
            "pixel_range": None,
            "unique_groups": None,
        }

        if "ToaFinal" in df:
            tmin, tmax = df["ToaFinal"].min(), df["ToaFinal"].max()
            stats["toa_range"] = {"min": float(tmin), "max": float(tmax), "duration": float(tmax - tmin)}

        if {"xPixel", "yPixel"}.issubset(df.columns):
            stats["pixel_range"] = {
                "x_min": int(df["xPixel"].min()), "x_max": int(df["xPixel"].max()),
                "y_min": int(df["yPixel"].min()), "y_max": int(df["yPixel"].max())
            }

        if "groupID" in df:
            ug = int(df["groupID"].nunique())
            if pd.api.types.is_numeric_dtype(df["groupID"]) and df["groupID"].sum() <= 0:
                ug = 0
            stats["unique_groups"] = ug


        print(f"Successfully loaded {len(df):,} signal records")
        print(f"Columns: {list(df.columns)}")
        print("\nSignal type distribution:")
        print(df["signalTypeDescription"].value_counts(dropna=False) if stats["signal_type_counts"] is not None else "(missing)")
        if stats["toa_range"]:
            tr = stats["toa_range"]
            print(f"\nTime range: {tr['min']:.6f} to {tr['max']:.6f} s\nDuration: {tr['duration']:.6f} s")
        else:
            print("\nTime range: (missing)")
        if stats["pixel_range"]:
            pr = stats["pixel_range"]
            print(f"\nPixels: x({pr['x_min']}-{pr['x_max']}), y({pr['y_min']}-{pr['y_max']})")
        else:
            print("\nPixels: (missing)")
        print(f"\nUnique buffers: {stats['unique_buffers']} | Unique groups: {stats['unique_groups']}")
        print(f"\nFirst {min(rows, len(df))} rows:")
        
        with pd.option_context(
            "display.max_columns", None,        # show all columns
            "display.width", 2000,              # large line width; adjust if needed. Smaller number = less characters before wrap around
            "display.expand_frame_repr", False  # don't wrap across lines
        ):
            print(df.head(rows).to_string(index=False))

    
    def filter_by_signal_type(self, df: pd.DataFrame, signal_type: str) -> pd.DataFrame:
        """
        Filter DataFrame by signal type.
        
        Args:
            df (pd.DataFrame): DataFrame to filter
            signal_type (str): Signal type to filter by ('TDC', 'Pixel', 'GTS', etc.)
            
        Returns:
            pd.DataFrame: Filtered DataFrame
        """
        return df[df['signalTypeDescription'] == signal_type].copy()
    
    def filter_by_time_range(self, df: pd.DataFrame, start_time: float, end_time: float) -> pd.DataFrame:
        """        Filter DataFrame by time range.
        
        Args:
            df (pd.DataFrame): DataFrame to filter
            start_time (float): Start time in seconds
            end_time (float): End time in seconds
            
        Returns:
            pd.DataFrame: Filtered DataFrame
        """
        return df[(df['ToaFinal'] >= start_time) & (df['ToaFinal'] <= end_time)].copy()


def main():
    """
    Example usage of the SignalDataReader class.
    """
    # Initialize the reader
    exporter = SignalDataReader()
    
    # Example usage (uncomment and modify paths as needed)
    # try:
    #     # Read raw signal file
    #     df = reader.read_rawsignal_file('/path/to/your/raw_signals.rawSignals')
    #     
    #     # Print basic info
    #     print(f"Loaded {len(df)} signals")
    #     print(f"Columns: {list(df.columns)}")
    #     
    #     # Get summary statistics
    #     stats = reader.get_summary_stats(df)
    #     print("Summary Statistics:")
    #     for key, value in stats.items():
    #         print(f"  {key}: {value}")
    #     
    #     # Filter by signal type
    #     pixel_signals = reader.filter_by_signal_type(df, 'Pixel')
    #     print(f"Pixel signals: {len(pixel_signals)}")
    #     
    #     # Export to CSV
    #     reader.export_to_csv(df, '/path/to/output/signals.csv')
    #     
    # except Exception as e:
    #     print(f"Error: {e}")
    
    print("SignalDataReader class is ready to use!")


if __name__ == "__main__":
    main()

