import argparse
import analysis.plotter as ph_plotter

# Parse command line arguments
parser = argparse.ArgumentParser(description='Creates images from pixels in a given buffer.')
parser.add_argument('buffer_number', type=int, help='Specify the buffer number you\'re interested in')
parser.add_argument('--movie_start_in_seconds', type=float, default=0, help='Start time in seconds for the movie.')
parser.add_argument('--movie_stop_in_seconds', type=float, default=0, help='Stop time in seconds for the movie.')
parser.add_argument('--time_bin_in_seconds', type=float, default=0, help='Time bin size in seconds.')
args = parser.parse_args()

file_path = '../pixelID.example'
buffer_number = args.buffer_number

# Convert seconds to the unit your data uses, if necessary
start = args.movie_start_in_seconds
stop = args.movie_stop_in_seconds
time_bins = args.time_bin_in_seconds

# Initiate a pyHERMES plotter class
plotter = ph_plotter.PlotPixelsInSingeBuffer_3D(file_path, buffer_number)
plotter.generate_ToA_Image_Sequence(toa_start=start, toa_stop=stop, time_bin_size=time_bins)
