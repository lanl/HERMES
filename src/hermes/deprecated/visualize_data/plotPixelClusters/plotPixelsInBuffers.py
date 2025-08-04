import argparse
import analysis.plotter as ph_plotter   # pyhermes plotter class.
import matplotlib.pyplot as plt

# Parse command line arguments
parser = argparse.ArgumentParser(description='Plot pixels in buffer from a file.')
parser.add_argument('file_path', type=str, help='Path to the data file')
parser.add_argument('buffer_number', type=int, help='Specify the buffer number you\'re interested in')
args = parser.parse_args()

# Use the file path and buffer number passed from command line
file_path = args.file_path
buffer_number = args.buffer_number

# Initiate a pyHERMES plotter class
plotter = ph_plotter.PlotPixelsInSingeBuffer_3D(file_path, buffer_number)

# For plotting single plots
#plotter.plot_pixels_vs_toa()
#plt.show()
#plotter.generate_buffer_image(log=True)
#plt.show()

# For combined plotting you need to first set up the figure and axes.
fig3 = plt.figure(figsize=(14, 7))              # Setup figure with layout (side-by-side)
ax1 = fig3.add_subplot(121, projection='3d')    # Define the first axes (for 3D plots)
ax2 = fig3.add_subplot(122)                     # Define the second axes (for 2D plots).
plotter.plot_pixels_vs_toa(ax=ax1)              # Plot on the first subplot
plotter.generate_buffer_image(log=True, ax=ax2) # Plot on the second subplot with log scale
plt.tight_layout()                              # Make a tight layout
plt.show()                                      # Show plot