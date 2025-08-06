import argparse
import analysis.plotter as ph_plotter   # pyhermes plotter class.

# Parse command line arguments
parser = argparse.ArgumentParser(description='Plot diagnostics for a given data file.')
parser.add_argument('file_path', type=str, help='The path to the data file you want to analyze')
args = parser.parse_args()

# Use the file path passed from command line
file_path = args.file_path

# Initiate the PlotDiagnostics class with the specified file path
diagnostics = ph_plotter.PlotDiagnostics(file_path)
#diagnostics.print_signal_data()
diagnostics.plot_packets_per_buffer_histogram()