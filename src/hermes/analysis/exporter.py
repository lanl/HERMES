"""
Raw Signal Data Exporter

This module provides functionality to export raw signal binary files to pandas DataFrames.
The binary format is based on the signalData structure from the C++ HERMES code.

Requirements:
    pip install pandas numpy

Usage:
    from hermes.analysis.exporter import SignalDataExporter
    
    exporter = SignalDataExporter()
    df = exporter.read_raw_signals('path/to/raw_signals.bin')
    
Author: HERMES Team
"""

import struct
from typing import Optional, Dict, Any
import pandas as pd
import numpy as np
import os


class SignalDataExporter:
    """
    A class to export raw signal binary files to pandas DataFrames.
    
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
        """Initialize the SignalDataExporter."""
            
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


    def read_rawsignals_folder(self, directory: str, index_range: str = "") -> pd.DataFrame:
        """
        Load multiple .rawSignals files into a single DataFrame.
        
        Args:
            directory (str): Directory containing .rawSignals files
            index_range (str, optional): Index range for selecting files. Examples:
                                        - "5"       -> only file at index 5
                                        - "5:10"    -> files 5 through 9
                                        - "5:10:2"  -> files 5, 7, 9
        
        Returns:
            pd.DataFrame: Combined DataFrame of all selected files
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

            # Build selected files
            selected_files = [all_files[i] for i in range(start, stop, step) if 0 <= i < len(all_files)]

            # Validate index range (e.g., start > stop or invalid indices)
            if not selected_files:
                raise ValueError(
                    f"Invalid index_range '{index_range}'. "
                    f"Make sure it matches the available files (0–{len(all_files) - 1})."
                )
        else:
            selected_files = all_files

        if not selected_files:
            raise ValueError("No .rawSignals files found to load.")

        # Load all selected files
        df_list = []
        for fname in selected_files:
            idx = all_files.index(fname)
            print(f"[{idx}] Reading {fname} ...")
            filepath = os.path.join(directory, fname)
            df_list.append(self.read_rawsignals_file(filepath))

        df = pd.concat(df_list, ignore_index=True)
        print(f"\nSuccessfully loaded {len(df):,} signal records from {len(selected_files)} files")
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
    
    def get_summary_stats(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get summary statistics for the signal data.
        
        Args:
            df (pd.DataFrame): DataFrame containing signal data
            
        Returns:
            Dict[str, Any]: Dictionary containing summary statistics
        """
        stats = {
            'total_signals': len(df),
            'unique_buffers': df['bufferNumber'].nunique(),
            'signal_type_counts': df['signalTypeDescription'].value_counts().to_dict(),
            'toa_range': {
                'min': df['ToaFinal'].min(),
                'max': df['ToaFinal'].max(),
                'duration': df['ToaFinal'].max() - df['ToaFinal'].min()
            },
            'pixel_range': {
                'x_min': df['xPixel'].min(),
                'x_max': df['xPixel'].max(),
                'y_min': df['yPixel'].min(),
                'y_max': df['yPixel'].max()
            },
            'unique_groups': df['groupID'].nunique() if df['groupID'].sum() > 0 else 0
        }
        return stats
    
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
        """
        Filter DataFrame by time range.
        
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
    Example usage of the SignalDataExporter class.
    """
    # Initialize the exporter
    exporter = SignalDataExporter()
    
    # Example usage (uncomment and modify paths as needed)
    # try:
    #     # Read raw signal file
    #     df = exporter.read_raw_signals('/path/to/your/raw_signals.bin')
    #     
    #     # Print basic info
    #     print(f"Loaded {len(df)} signals")
    #     print(f"Columns: {list(df.columns)}")
    #     
    #     # Get summary statistics
    #     stats = exporter.get_summary_stats(df)
    #     print("Summary Statistics:")
    #     for key, value in stats.items():
    #         print(f"  {key}: {value}")
    #     
    #     # Filter by signal type
    #     pixel_signals = exporter.filter_by_signal_type(df, 'Pixel')
    #     print(f"Pixel signals: {len(pixel_signals)}")
    #     
    #     # Export to CSV
    #     exporter.export_to_csv(df, '/path/to/output/signals.csv')
    #     
    # except Exception as e:
    #     print(f"Error: {e}")
    
    print("SignalDataExporter class is ready to use!")


if __name__ == "__main__":
    main()

