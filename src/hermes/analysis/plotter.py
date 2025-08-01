import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
import imageio
import os
import re

class BufferPlotter:
    def __init__(self, df: pd.DataFrame, buffer_number: int):
        self.df = df
        self.buffer_number = buffer_number
        self.filtered_df = df[df["bufferNumber"] == buffer_number]

    def plot_3d_pixels_vs_toa(self, ax=None):
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
    @staticmethod
    def plot_packets_per_buffer(df: pd.DataFrame, print_counts=False):
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

class ToAImageSequenceGenerator:
    def __init__(self, df: pd.DataFrame, buffer_number: int):
        self.df = df[df["bufferNumber"] == buffer_number]
        self.buffer_number = buffer_number

    def generate_images(self, time_bin_size: float, toa_start: float, toa_stop: float, output_path: str = "./", log=True):
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
        image_files = sorted([f for f in os.listdir(output_path) if f.endswith(".png")],
                             key=lambda x: int(re.search(r'\d+', x).group()))
        images = [imageio.imread(os.path.join(output_path, fname)) for fname in image_files]
        imageio.mimsave(os.path.join(output_path, output_name), images, format="GIF", duration=duration)
