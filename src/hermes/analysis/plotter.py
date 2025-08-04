import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import imageio
import os
import re

class BufferPlotter:
    """
    Class for visualizing signal data from a specific buffer.
    """

    def __init__(self, df: pd.DataFrame, buffer_number: int):
        """
        Initialize a BufferPlotter.

        Args:
            df (pd.DataFrame): Full signal DataFrame.
            buffer_number (int): Buffer number to filter and visualize.
        """
        self.df = df
        self.buffer_number = buffer_number
        self.filtered_df = df[df["bufferNumber"] == buffer_number]

    def plot_3d_pixels_vs_toa(self, ax=None):
        """
        Plot 3D scatter of (xPixel, yPixel, ToaFinal) for 'Pixel' signals and overlay TDCs.

        Args:
            ax (matplotlib.axes._subplots.Axes3DSubplot, optional): Optional pre-existing 3D axis.
        """
        pixels = self.filtered_df[self.filtered_df["signalTypeDescription"] == "Pixel"]
        tdcs = self.filtered_df[self.filtered_df["signalTypeDescription"] == "TDC"]

        color_map = {-1: [0, 0, 0]}
        unique_groups = pixels["groupId"].unique()
        for group in unique_groups:
            if group != -1:
                color_map[group] = np.random.rand(3,)
        color_values = np.array([color_map[g] for g in pixels["groupId"]])

        if ax is None:
            fig = plt.figure(figsize=(10, 7))
            ax = fig.add_subplot(111, projection="3d")

        ax.scatter(pixels["xPixel"], pixels["yPixel"], pixels["ToaFinal"], c=color_values, label="Pixels")
        ax.scatter(tdcs["xPixel"], tdcs["yPixel"], tdcs["ToaFinal"], color="black", label="TDC", s=10)

        ax.set_xlabel("X Pixel")
        ax.set_ylabel("Y Pixel")
        ax.set_zlabel("ToA")
        ax.set_title(f"3D Plot of Pixels vs. ToA for Buffer {self.buffer_number}")

    def plot_tot_image(self, log=False, ax=None):
        """
        Plot 2D image of integrated TOT for all pixel hits in the buffer.

        Args:
            log (bool): Whether to use logarithmic color scaling.
            ax (matplotlib.axes.Axes, optional): Optional pre-existing axis.
        """
        pixels = self.filtered_df[self.filtered_df["signalTypeDescription"] == "Pixel"]
        image = np.zeros((256, 256))

        for _, row in pixels.iterrows():
            x, y, tot = int(row["xPixel"]), int(row["yPixel"]), row["TotFinal"]
            image[y, x] += tot

        if ax is None:
            fig, ax = plt.subplots()

        if log and np.any(image > 0):
            norm = LogNorm(vmin=max(np.min(image[image > 0]), 1e-1), vmax=np.max(image), clip=True)
            label = "Integrated TOT (Log Scale)"
        else:
            norm = None
            label = "Integrated TOT"

        img = ax.imshow(image, cmap="viridis", norm=norm, aspect="equal")
        ax.set_title(f"Buffer {self.buffer_number} TOT Image")
        ax.set_xlabel("X Pixel")
        ax.set_ylabel("Y Pixel")
        ax.set_xticks([])
        ax.set_yticks([])
        plt.colorbar(img, ax=ax, label=label)


class HistogramPlotter:
    """
    Utility class for plotting histograms from signal data.
    """

    @staticmethod
    def plot_packets_per_buffer(df: pd.DataFrame, print_counts=False):
        """
        Plot a histogram showing number of packets per buffer.

        Args:
            df (pd.DataFrame): Input signal DataFrame.
            print_counts (bool): Whether to print buffer counts to console.
        """
        counts = df["bufferNumber"].value_counts().sort_index()

        if print_counts:
            print("Buffer\tCount")
            for b, c in counts.items():
                print(f"{b}\t{c}")

        plt.figure(figsize=(14, 6))
        plt.bar(counts.index, counts.values, width=1.0)
        plt.title("Data Packets per Buffer")
        plt.xlabel("Buffer Number")
        plt.ylabel("Count")
        plt.grid(axis="y")
        plt.tight_layout()
        plt.show()

    @staticmethod
    def plot_2D_histogram(data, title="", x_axis_index=2, y_axis_index=3, vmin=None, vmax=None):
        """
        Display a 256x256 2D histogram of pixel (x, y) hit counts.

        Args:
            data (pd.DataFrame or array-like): Input data containing pixel coordinates.
            title (str): Plot title.
            x_axis_index (int): Column index for x-coordinate.
            y_axis_index (int): Column index for y-coordinate.
            vmin (float, optional): Minimum value for color scaling.
            vmax (float, optional): Maximum value for color scaling.

        Raises:
            ValueError: If input is not 2D.
        """
        if isinstance(data, pd.DataFrame):
            x = data.iloc[:, x_axis_index].astype(int)
            y = data.iloc[:, y_axis_index].astype(int)
        else:
            data = np.asarray(data)
            if data.ndim != 2:
                raise ValueError("Input must be 2D")
            x = data[:, x_axis_index].astype(int)
            y = data[:, y_axis_index].astype(int)

        heatmap = np.zeros((256, 256), dtype=int)
        for xi, yi in zip(x, y):
            if 0 <= xi < 256 and 0 <= yi < 256:
                heatmap[yi, xi] += 1

        plt.figure(figsize=(10, 8))
        plt.imshow(heatmap, cmap="viridis", origin="lower", vmin=vmin, vmax=vmax)
        plt.colorbar(label="Counts")
        plt.xlabel("x-axis")
        plt.ylabel("y-axis")
        plt.title(title)
        plt.tight_layout()
        plt.show()


class ToAImageSequenceGenerator:
    """
    Generates a sequence of TOT images across time bins for a specific buffer.
    """

    def __init__(self, df: pd.DataFrame, buffer_number: int):
        """
        Initialize the sequence generator for a specific buffer.

        Args:
            df (pd.DataFrame): Input signal DataFrame.
            buffer_number (int): Buffer number to visualize.
        """
        self.df = df[df["bufferNumber"] == buffer_number]
        self.buffer_number = buffer_number

    def generate_images(self, time_bin_size: float, toa_start: float, toa_stop: float, output_path: str = "./", log=True):
        """
        Generate and save TOT images for time-binned intervals.

        Args:
            time_bin_size (float): Duration of each time bin.
            toa_start (float): Start time for image generation.
            toa_stop (float): Stop time for image generation.
            output_path (str): Directory to save images.
            log (bool): Use logarithmic scaling for TOT values.
        """
        pixels = self.df[(self.df["signalTypeDescription"] == "Pixel") & 
                         (self.df["ToaFinal"] >= toa_start) & 
                         (self.df["ToaFinal"] <= toa_stop)]

        min_toa = pixels["ToaFinal"].min()
        max_toa = pixels["ToaFinal"].max()
        total_range = max_toa - min_toa
        n_bins = int(np.ceil(total_range / time_bin_size))

        if n_bins > 1000:
            print(f"Too many frames ({n_bins}), reducing to 1000.")
            time_bin_size = total_range / 1000
            n_bins = 1000

        for i in range(n_bins):
            start = min_toa + i * time_bin_size
            end = start + time_bin_size
            frame = pixels[(pixels["ToaFinal"] >= start) & (pixels["ToaFinal"] < end)]

            image = np.zeros((256, 256))
            for _, row in frame.iterrows():
                x, y, tot = int(row["xPixel"]), int(row["yPixel"]), row["TotFinal"]
                image[y, x] += tot

            fig, ax = plt.subplots()
            if log and np.any(image > 0):
                norm = LogNorm(vmin=1e-1, vmax=np.max(image), clip=True)
            else:
                norm = None

            img = ax.imshow(image, cmap="viridis", norm=norm, aspect="equal")
            ax.set_title(f"Buffer {self.buffer_number}, ToA: {start:.6e} – {end:.6e}")
            ax.set_xlabel("X Pixel")
            ax.set_ylabel("Y Pixel")
            ax.set_xticks([])
            ax.set_yticks([])
            plt.colorbar(img, ax=ax, label="Integrated TOT")
            plt.savefig(f"{output_path}/frame_{i:04d}.png")
            plt.close()

    @staticmethod
    def compile_images_to_gif(output_path: str, output_name: str = "output.gif", duration: float = 0.2):
        """
        Compile a sequence of saved PNG images into an animated GIF.

        Args:
            output_path (str): Directory containing PNG frames.
            output_name (str): Filename for the output GIF.
            duration (float): Duration per frame in seconds.
        """
        image_files = sorted([f for f in os.listdir(output_path) if f.endswith(".png")],
                             key=lambda x: int(re.search(r'\d+', x).group()))
        images = [imageio.imread(os.path.join(output_path, fname)) for fname in image_files]
        imageio.mimsave(os.path.join(output_path, output_name), images, format="GIF", duration=duration)
