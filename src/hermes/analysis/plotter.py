import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm
import matplotlib.animation as animation
import imageio
import os, re
import struct


class DataLoader:
    def __init__(self, filepath):
        self.filepath = filepath

    def load_data(self):
        if self.filepath.endswith('.csv'):
            return self.load_from_csv()
        elif self.filepath.endswith('.rawSignals'):
            return self.load_from_binary()
        elif self.filepath.endswith('.pixelActivations'):
            return self.load_from_empir()
        else:
            raise ValueError("Unsupported file type. Please use either a .csv or .rawSignals file.")

    def load_from_csv(self):
        column_names = ['buffer_number', 'signal_type', 'x_pixel', 'y_pixel', 'toa', 'tot', 'group_ID']
        df = pd.read_csv(self.filepath, sep='\s+', header=None, names=column_names)
        print("Pixel data loaded from CSV!")
        return df

    def load_from_binary(self):
        signal_data_format = 'IBBBdHI'
        signal_data_size = struct.calcsize(signal_data_format)
        data = []
        with open(self.filepath, 'rb') as file:
            while True:
                bytes_read = file.read(signal_data_size)
                if not bytes_read:
                    break
                data.append(struct.unpack(signal_data_format, bytes_read))
        signals = np.array(data, dtype=[
            ('buffer_number', 'u4'),
            ('signal_type', 'u1'),
            ('x_pixel', 'u1'),
            ('y_pixel', 'u1'),
            ('toa', 'f8'),
            ('tot', 'u2'),
            ('group_ID', 'u4')
        ])
        print(f"{len(signals)} packets loaded from binary file!")
        df = pd.DataFrame(signals)
        return df
    
    def load_from_empir(self):
        """
            The information of each event is contained in 5 consecutive doubles: 
            - x coordinate in pixels on the imaging chip
            - y coordinate in pixels on the imaging chip
            - absolute time in seconds
            - time over threshold in arbitrary units
            - time relative to the last trigger (nan if the event occured before the first trigger)

        Returns:
            dataframe: pandas dataframe containing the pixel data
        """
        
        
        column_names = ['typeOfEvent', 'ToA_final', 'xpixel', 'ypixel', 'spaceGroup', 'timeGroup']
        df = pd.read_csv(self.filepath, sep='\s+', header=None, names=column_names)
        print("Pixel data loaded from empir file!")
        return df

class PlotDiagnostics:
    """
    Class PlotDiagnostics
    Description:
        A class for performing diagnostic plotting of data related to signal processing or data analysis tasks.
        This class uses the DataLoader class to load data from a specified filepath. It provides functionalities 
        for visualizing the diagnostics of the loaded data, such as plotting the distribution of data packets 
        across different buffers.

    Attributes:
        df (pandas.DataFrame): The loaded dataset as a pandas DataFrame, obtained through the DataLoader class.

    Methods:
        plot_packets_per_buffer_histogram():
            Plots a histogram of the number of data packets per buffer in the loaded dataset.
    """
    def __init__(self, filepath):
        """
        Initializes the PlotDiagnostics object by loading data using the DataLoader class.

        Parameters:
            filepath (str): The file path to the dataset. Supported formats depend on DataLoader's capabilities.
        """
        self.df = DataLoader(filepath).load_data()

    def print_signal_data(self):
        """
        Prints the details of each signal in the dataset.

        This method iterates over each row in the DataFrame and prints out the signal's details,
        including buffer number, signal type, pixel coordinates, time of arrival, time over threshold, and group ID.
        """
        # Ensure that df is a DataFrame and not None
        if self.df is not None and not self.df.empty:
            for index, row in self.df.iterrows():
                print(f"Signal {index}: Buffer Number={row['buffer_number']}, "
                      f"Signal Type={row['signal_type']}, X Pixel={row['x_pixel']}, "
                      f"Y Pixel={row['y_pixel']}, ToA={row['toa']}, ToT={row['tot']}, "
                      f"Group ID={row['group_ID']}")
        else:
            print("No data to display. DataFrame is empty or not loaded.")

    def plot_packets_per_buffer_histogram(self, print_counts=False):
        """
        Plots a bar chart of the number of data packets per buffer.

        This method counts the occurrences of each buffer number in the dataset and plots these counts as a bar chart,
        providing insights into the distribution and volume of data packets across buffers.

        Parameters:
            print_counts (bool): If True, prints the counts of data packets per buffer before plotting.
        """

        # Count the occurrences of each buffer_number
        buffer_counts = self.df['buffer_number'].value_counts().sort_index()

        if print_counts:
            print("Buffer \t Counts")
            # Iterate through buffer_counts Series and print each buffer number and its count
            for buffer_number, count in buffer_counts.items():
                print(f"{buffer_number}\t{count}")

        plt.figure(figsize=(14, 8))
        plt.bar(buffer_counts.index, buffer_counts.values, width=1.0, edgecolor=None)
        plt.title('Data Packets per Buffer')
        plt.xlabel('Buffer Number')
        plt.ylabel('Count of Data Packets')
        plt.xticks(rotation=90)  # Rotate x labels if they overlap or for better readability
        plt.grid(axis='y')  # Add horizontal grid lines for readability
        plt.tight_layout()  # Adjust layout to make room for the rotated x-axis labels
        plt.show()



class PlotPixelsInSingeBuffer_3D:
    """
    Class PlotPixelsInBuffer_3D
    Description:
        This class is designed to visualize pixel data from a given dataset for a 
        specific buffer number within the dataset.
        
    Attributes:
        filepath (str): The file path to the dataset.
        buffer_number (int): The specific buffer number to visualize.
        df (DataFrame): The loaded dataset as a pandas DataFrame.
        
    Methods:
        load_data: Loads the dataset from the specified file path.
        plot_pixels_vs_toa: Plots pixels in a 3D space based on their ToA.
        generate_buffer_image: Generates an image representation of pixels based on ToT values.
    """
    def __init__(self, filepath, buffer_number):
        self.filepath = filepath
        self.buffer_number = buffer_number
        self.df = DataLoader(filepath).load_data()  # Use the instance to call its method

    def plot_pixels_vs_toa(self, ax=None):
        # Filter the dataset for the specific buffer number and separate pixels and TDCs.
        filtered_df = self.df[self.df['buffer_number'] == self.buffer_number]
        pixels_df = filtered_df[filtered_df['signal_type'] == 'Pixel']
        tdcs_df = filtered_df[filtered_df['signal_type'] == 'TDC'].copy()

        # Prepare a color map for pixels, with a special case for group_ID = -1 (black).
        color_map = {-1: [0, 0, 0]}  # Black in RGB for TDCs and group_ID = -1 pixels.
        unique_groups = np.unique(pixels_df['group_ID'])
        for group in unique_groups:
            if group != -1:
                color_map[group] = np.random.rand(3,)  # Assign a random color for each group_ID.
        color_values = np.array([color_map[group] for group in pixels_df['group_ID']])
        
        # Create a 3D plot for pixels and TDCs.
        if ax is None:
            fig = plt.figure(figsize=(10, 7))
            ax = fig.add_subplot(111, projection='3d')
        ax.scatter(pixels_df['x_pixel'], pixels_df['y_pixel'], pixels_df['toa'], c=color_values, label='Pixels')
        ax.scatter(tdcs_df['x_pixel'], tdcs_df['y_pixel'], tdcs_df['toa'], color='black', label='TDC', s=10)
        ax.set_xlabel('X Pixel')
        ax.set_ylabel('Y Pixel')
        ax.set_zlabel('TOA')
        ax.set_title(f'3D Plot of Pixels vs. ToA for Buffer Number {self.buffer_number}')

    def generate_buffer_image(self, log=False, ax=None):
        # Filter the dataset for the specific buffer number to visualize pixel intensities based on ToT.
        filtered_df = self.df[self.df['buffer_number'] == self.buffer_number]
        pixels_df = filtered_df[filtered_df['signal_type'] == 'Pixel']
        
        # Initialize a 256x256 array with zeros for ToT integration.
        image_array = np.zeros((256, 256))
        for index, row in pixels_df.iterrows():
            x, y, tot = int(row['x_pixel']), int(row['y_pixel']), row['tot']
            image_array[y, x] += tot  # Accumulate 'tot' values for each pixel position.
        
        if ax is None:
            fig, ax = plt.subplots()
        
        # Choose logarithmic or linear scale based on 'log' parameter.
        if log:
            if np.any(image_array > 0):
                log_norm = LogNorm(vmin=np.min(image_array[image_array > 0]), vmax=np.max(image_array), clip=True)
                img = ax.imshow(image_array, cmap='viridis', norm=log_norm, aspect='equal')
                label = 'Integrated TOT (Log Scale)'
            else:
                print("No non-zero TOT values found. Displaying in linear scale.")
                img = ax.imshow(image_array, cmap='viridis', aspect='equal')
                label = 'Integrated TOT'
        else:
            img = ax.imshow(image_array, cmap='viridis', aspect='equal')
            label = 'Integrated TOT'
        
        # Configure the plot appearance.
        ax.set_title(f'Integrated TOT as Image for Buffer Number {self.buffer_number}')
        ax.set_xlabel('X Pixel')
        ax.set_ylabel('Y Pixel')
        plt.colorbar(img, label=label)
        ax.set_xticks([])
        ax.set_yticks([])  # Hide axis ticks for a cleaner image presentation.


    def generate_toa_image(self, data, start_toa, end_toa, log=False,):
        """
        Generates and saves an image visualizing the Time of Arrival (ToA) for pixels within a specific time bin.

        This function uses the filtered `bin_data` containing pixels for a specific time bin to create a visualization
        based on their ToA values. The function assumes the existence of `self.data` containing 'x', 'y', and 'ToA'
        columns to plot.

        @param bin_data: Filtered DataFrame containing data for the current time bin.
        @return: None. The function directly plots and saves the generated image.
        """
        # Assuming bin_data contains columns 'x', 'y', and 'ToA'

        # Initialize a 256x256 array with zeros for ToT integration.
        image_array = np.zeros((256, 256))
        for index, row in data.iterrows():
            x, y, tot = int(row['x_pixel']), int(row['y_pixel']), row['tot']
            image_array[y, x] += tot  # Accumulate 'tot' values for each pixel position.
        
        fig, ax = plt.subplots()  # Create figure and axes directly without checking ax
        
        # Choose logarithmic or linear scale based on 'log' parameter.
        if log:
            if np.any(image_array > 0):
                log_norm = LogNorm(vmin=1E-1, vmax=500, clip=True)
                img = ax.imshow(image_array, cmap='viridis', norm=log_norm, aspect='equal')
                label = 'Integrated TOT (Log Scale)'
            else:
                image_array[image_array == 0] = 1e-1  # Set all zero values to 1E-1
                log_norm = LogNorm(vmin=1E-1, vmax=500, clip=True)
                img = ax.imshow(image_array, cmap='viridis', norm=log_norm, aspect='equal')
                label = 'Integrated TOT (Log Scale)'
        else:
            img = ax.imshow(image_array, cmap='viridis', aspect='equal')
            label = 'Integrated TOT'

        
        # Configure the plot appearance.
        start_toa_formatted = '{:.6e}'.format(start_toa)
        end_toa_formatted = '{:.6e}'.format(end_toa)
        ax.set_title(f'{self.buffer_number}, ToA: {start_toa_formatted} to {end_toa_formatted}')
        ax.set_xlabel('X Pixel')
        ax.set_ylabel('Y Pixel')
        plt.colorbar(img, label=label)
        ax.set_xticks([])
        ax.set_yticks([])  # Hide axis ticks for a cleaner image presentation.
        

    def compile_images_to_movie(self, output_path, movie_filename):
        """
        Compiles the saved images into a movie file.

        This function searches for image files in the specified output directory, reads them in order,
        and compiles them into a movie file saved with the specified filename.

        @param output_path: The directory path where the images are saved.
        @param movie_filename: The name of the movie file to be created, including its path.
        """
        images = []
        # Use regular expression to extract numbers from filenames and sort them numerically
        sorted_files = sorted(os.listdir(output_path), key=lambda x: int(re.findall(r'\d+', x)[0]))
        for file_name in sorted_files:
            if file_name.endswith('.png'):
                file_path = os.path.join(output_path, file_name)
                images.append(imageio.imread(file_path))
        imageio.mimsave(movie_filename, images, format='GIF', duration=5)



    def generate_ToA_Image_Sequence(self, time_bin_size, toa_start, toa_stop, output_path='./'):
        """
        Plots pixels in a given time bin for a range of time bins within the buffer and saves the images to a user-defined path.

        @param time_bin_size: The size of each time bin in the same units as the ToA data.
        @param output_path: The directory path where the images will be saved.
        @param toa_start: The start Time of Arrival for clipping the dataset.
        @param toa_stop: The stop Time of Arrival for clipping the dataset.
        @return: None. The function saves plot images for each time bin in the specified output path and assumes an external method compiles these into a movie.
        """
        # Filter the dataset for the specific buffer number to visualize pixel intensities based on ToT.
        filtered_df = self.df[(self.df['buffer_number'] == self.buffer_number) & (self.df['toa'] >= toa_start) & (self.df['toa'] <= toa_stop)]
        pixels_df = filtered_df[filtered_df['signal_type'] == 'Pixel']

        # Calculate min and max ToA to define time bins
        min_toa = pixels_df['toa'].min()
        max_toa = pixels_df['toa'].max()
        total_toa_range = max_toa - min_toa
        initial_num_toas = total_toa_range / time_bin_size
        
        # Adjust time_bin_size if num_toas exceeds 1000
        if initial_num_toas > 1000:
            print(f"Number of images to generate is {initial_num_toas}! Recalculating bin size to limit total number of images to 1000")
            time_bin_size = total_toa_range / 1000  # Recalculate time_bin_size to ensure 1000 bins
            num_toas = 1000
        else:
            num_toas = initial_num_toas
        
        # Iterate over time bins using the (possibly adjusted) time_bin_size
        for i in range(int(num_toas)):
            start_toa_bin = min_toa + i * time_bin_size
            end_toa_bin = start_toa_bin + time_bin_size
            bin_data = pixels_df[(pixels_df['toa'] >= start_toa_bin) & (pixels_df['toa'] < end_toa_bin)]
            # Now pass start_toa and end_toa to the function
            self.generate_toa_image(data=bin_data, start_toa=start_toa_bin, end_toa=end_toa_bin,log=True)
            plt.savefig(f'{output_path}/bin_{i}.png')
            plt.clf()
            plt.close()


        # After all bins are plotted and saved, compile them into a movie
        self.compile_images_to_movie(output_path=output_path,movie_filename='rawTPX3.tiff')


        


#------------------------------------------------------------------------------
#  	plotFianlResults:	Plots events after they are sorted into both timeGroups
#						and spaceGroups
#
#	args: 		array of type signleEventData,
# 	returns: 	nothing. timeGroup types are updated in event array
#------------------------------------------------------------------------------
def plotFinalResults(data):
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    
    # Get unique timeGroup values
    unique_timeGroups = np.unique(data['timeGroup'])
    
    # Create a scatter plot for each timeGroup
    for timeGroup in unique_timeGroups:	
        
        # filter data based on timeGroups
        filteredTimeData = data[data['timeGroup'] == timeGroup]

        # Get unique spaceGroup values
        unique_spaceGroups = np.unique(filteredTimeData['spaceGroup'])
        
        for spaceGroup in unique_spaceGroups:
            # filter data based on timeGroups
            filteredSpaceData = data[data['spaceGroup'] == spaceGroup]

            ax.scatter(filteredSpaceData['ToA_final'],filteredSpaceData['xpixel'],filteredSpaceData['ypixel'])

    plt.show()


def plotHistOneD(data, signalType, dataType,NumOfBins):
    signalsOfType = data[data['typeOfEvent'] == signalType]
    print(np.min(signalsOfType[dataType]))

    plt.hist(signalsOfType[dataType], bins=NumOfBins)
    plt.xlabel(dataType)
    plt.show()

#------------------------------------------------------------------------------
#  	animateData:	Creates an animation of the data by plotting x and y pixels
#					while stepping through ToA. 
#
#	args: 		array of type signleEventData,
# 	returns: 	Nothing. An animation gif is saved to file.
#------------------------------------------------------------------------------
def animateData(data,startTime=None,stopTime=None,numOfFrames=100):

    pixelData = data[data['typeOfEvent'] == 2] #grab only pixel signals

    if startTime == None:
        startTime = np.min(pixelData['ToA_final'])
        print("Start time:{}".format(startTime))

    if stopTime == None:
        stopTime = np.max(pixelData['ToA_final'])
        print("Stop time:{}".format(stopTime))

    frameBin = (stopTime-startTime)/numOfFrames
    print("Each frame bin is {} seconds".format(frameBin))

    # Create an array to store unique group IDs based on space-time combos
    group_IDs = np.zeros((len(pixelData),), dtype=np.int32)
    for i,signal in enumerate(pixelData):
        group_IDs[i] = int(str(signal['timeGroup']) + str(signal['spaceGroup']))

    # create frame spacing based on 
    frames=np.arange(startTime, stopTime, frameBin)

    # Initialize figure and axes
    fig, ax = plt.subplots()

    # Initial plot
    scatterPlot = ax.scatter([], [], c=[])

    # Set tolerance for each frame
    eps = frameBin*2

    def init():
        ax.set_xlim(0, 255)
        ax.set_ylim(0, 255)
        ax.set_title('ToA_final: 0.0')  # initial title
        
        return scatterPlot,

    def update(frame):

        # Only take events where 'ToA_final' falls within the frame +/- eps
        frame_indices = np.where((pixelData['ToA_final'] >= frame - eps) & (pixelData['ToA_final'] < frame + eps)) 
        currentEvents = pixelData[frame_indices]

        currentGroup_IDs = group_IDs[frame_indices]
        
        scatterPlot.set_offsets(np.c_[currentEvents['xpixel'], currentEvents['ypixel']])
        scatterPlot.set_array(currentGroup_IDs)  # Update colors based on group_ID
        ax.set_title(f'ToA_final: {frame:.6f} seconds')  # update title with current ToaFinal
        
        return scatterPlot,

    ani = animation.FuncAnimation(fig, update, frames, init_func=init, blit=True)

    # Save the animation as a gif
    ani.save("animation.gif", writer='pillow', fps=10)
    

























