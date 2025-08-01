from typing import Dict, Any
import pandas as pd

class SignalAnalyzer:
    def __init__(self):
        pass  # Reserved for future expansion (e.g., storing config or metadata)


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

        # Print summary
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
        with pd.option_context("display.max_columns", None, "display.width", 2000, "display.expand_frame_repr", False):
            print(df.head(rows).to_string(index=False))


    def filter_by_signal_type(self, df: pd.DataFrame, signal_type: str) -> pd.DataFrame:
        """Filter DataFrame by signal type (e.g., 'Pixel', 'TDC')."""
        return df[df['signalTypeDescription'] == signal_type].copy()


    def filter_by_time_range(self, df: pd.DataFrame, start_time: float, end_time: float) -> pd.DataFrame:
        """Filter DataFrame based on a time window (start_time ≤ ToaFinal ≤ end_time)."""
        return df[(df['ToaFinal'] >= start_time) & (df['ToaFinal'] <= end_time)].copy()
