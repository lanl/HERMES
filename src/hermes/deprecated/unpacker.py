import struct
import numpy as np
import mmap
import time
from numba import njit


#--------------------------------------------------------------------------------------------------------------------------------------------
# Defining the structure of the singleSignalData with numpy
#--------------------------------------------------------------------------------------------------------------------------------------------
singleSignalData = np.dtype([('signalType', np.int16), ('xPixel', np.uint16),('yPixel', np.uint16),('ToaFinal', np.float64),('TotFinal', np.float64)])
#--------------------------------------------------------------------------------------------------------------------------------------------

#--------------------------------------------------------------------------------------------------------------------------------------------
# Defining the structure of the singlePhotonData with numpy
#--------------------------------------------------------------------------------------------------------------------------------------------
singlePhotonData = np.dtype([('xPixel', np.double),('yPixel', np.double),('ToaFinal', np.double),('TofFinal', np.double)])
#--------------------------------------------------------------------------------------------------------------------------------------------

#------------------------------------------------------------------------------
@njit()
def sortArray(array):
    """Uses numpy argsort to sort array of singleEventData based on 'ToaFinal'

    Args:
        array (numpy dtype singleSignalData): array of dtype singleSignalData

    Returns:
        _type_: sorted array of singleSignalData
    """
    return array[np.argsort(array['ToaFinal'])]
#--------------------------------------------------------------------------

@njit()
def convertCoordinates(chipnr, x, y):
    """converts coordinates of pixels based on chip number

    Args:
        chipnr (int): Chip number of timepix3 chip. There should only be one right now. 
        x (int): x pixel number
        y (int): y pixel number

    Returns:
        int aray: new x and y coordinates base on there chip number.
        
    Notes: 
        Chip number reading seem to be wrong comming of the chip. 
    """
    if chipnr == 0:
        x += 260
    elif chipnr == 1:
        x = 255 - x + 260
        y = 255 - y + 260
    elif chipnr == 2:
        x = 255 - x
        y = 255 - y + 260
    
    return x, y
	#--------------------------------------------------------------------------

@njit()
def bytesToIntLE(bytes_data):
    result = 0
    for i in range(len(bytes_data)):
        result |= bytes_data[i] << (i * 8)
    return result

@njit()
def get_type_header(data):
    """Grabs last four bits of 

    Args:
        data (_type_): _description_

    Returns:
        _type_: _description_
    
    Notes: 
        - Python's default behavior for bit-wise operations on integers is to use signed integers! 
        - That means when you're isolating the bits 63-60, if bit 63 is 1, it is treated as the sign 
        bit for a signed integer, which will make your integer negative.  
        - To ensure that we keep the last 4 bits and interperet as an unsigned integer we need to
        mask it further. num & 0xF 
    
    """
    num = bytesToIntLE(data)
    # This directly defines the mask for bits 63-60
    mask = 0xF000000000000000  
    #This ensures that you're only keeping the last 4 bits of the result
    return (num & mask) >> 60 & 0xF  


#---------------------------------------------
# Bit manipulation functions for header packet
#---------------------------------------------
@njit()
def extract_buffer_size(packet):
    return (packet >> 48) & 0xFFFF

@njit()
def extract_mode(packet):
    return (packet >> 40) & 0xFF

@njit()
def extract_chip_number(packet):
    return (packet >> 32) & 0xFF
#---------------------------------------------

#---------------------------------------------
# Bit manipulation functions for TDC packets
#---------------------------------------------
@njit()
def extract_tdc_header(packet):
    return (packet >> 56) & 0xFF

@njit()
def extract_tdc_trigger_counter(packet):
    return (packet >> 44) & 0xFFF

@njit()
def extract_tdc_timestamp(packet):
    return (packet >> 9) & 0x1FFFFFFFFFF

@njit()
def extract_tdc_stamp(packet):
    return (packet >> 5) & 0xF

@njit()
def extract_tdc_reserved(packet):
    return packet & 0x1F

@njit()
def get_tdc_toa_final(timestamp,stamp):
    return timestamp*3.125E-9+stamp*0.260E-9
#---------------------------------------------

#---------------------------------------------
# Bit manipulation functions for Pixel packets
#---------------------------------------------
@njit()
def extract_pixel_header(packet):
    return (packet >> 60) & 0xF

@njit()
def extract_pixel_address(packet):
    dcol = (packet & 0x0FE0000000000000) >> 52
    spix = (packet & 0x001F800000000000) >> 45
    pix = (packet & 0x0000700000000000) >> 44
    xPixel = int(dcol + pix // 4)
    yPixel = int(spix + (pix & 0x3))

    return xPixel, yPixel

@njit()
def extract_pixel_coarse_toa(packet):
    return (packet >> 30) & 0x3FFF

@njit()
def extract_pixel_tot(packet):
    return ((packet >> 20) & 0x3FF) * 25

@njit()
def extract_pixel_fine_toa(packet):
    return (packet >> 16) & 0xF

@njit()
def extract_pixel_daq_time(packet):
    return (packet & 0xFFFF) * 25.0 * 16384.0

@njit()
def get_pixel_toa_final(pixelCoarseToA,pixelFineToA,pixelDaqTime):
    CTOA = (pixelCoarseToA << 4) | (~pixelFineToA & 0xF) 
    return pixelDaqTime + CTOA * (25.0 / 16)
#---------------------------------------------

#---------------------------------------------
# Bit manipulation functions for Global Time packets
#---------------------------------------------
@njit()
def extractGlobalTimeHeader(packet):
    return (packet >> 60) & 0xF

@njit()
def extract_global_time_high_low_flag(packet):
    return (packet >> 56) & 0xFF

@njit()
def extract_global_time_low_timestamp(packet):
    return (packet >> 16) & 0xFFFFFFFF

@njit()
def extract_global_time_high_timestamp(packet):
    return (packet >> 16) & 0xFFFF

@njit()
def extract_global_time_daq_time(packet):
    return (packet & 0xFFFF) * 25.0 * 16384.0

#---------------------------------------------

#---------------------------------------------

#---------------------------------------------
# Unpacking functions for each type of packet
#---------------------------------------------
def parse_header_packet(payload):
    """_summary_

    Args:
        payload (_type_): _description_

    Returns:
        _type_: _description_
    """
    
    # Unpack the payload according to the header packet structure
    packet = struct.unpack('<Q', payload)[0]

    # Extract fields using bit manipulation
    bufferSize = extract_buffer_size(packet)
    mode = extract_mode(packet)
    chipNumber = extract_chip_number(packet) 

    return bufferSize,mode,chipNumber

def parse_tdc_packet(payload,signal):

    # Unpack the payload into packet
    packet = struct.unpack('<Q', payload)[0]

    # Extract fields using tdc bit manipulation functions
    tdc_header = extract_tdc_header(packet)
    trigger_counter = extract_tdc_trigger_counter(packet)
    timestamp = extract_tdc_timestamp(packet)
    stamp = extract_tdc_stamp(packet)
    reserved = extract_tdc_reserved(packet)

    # Calculate final Time of Arrival for TDC signal.
    ToaFinal = get_tdc_toa_final(timestamp,stamp)

    # set TDC info in signal
    signal['signalType'] = 1
    signal['xPixel'] = 0
    signal['yPixel'] = 0
    signal['ToaFinal'] = ToaFinal
    signal['TotFinal'] = 0


def parse_pixel_packet(payload,signal):
    
    # Unpack the payload 
    packet = struct.unpack('<Q', payload)[0]

    # Extract fields using bit manipulation
    pixelHeader = extract_pixel_header(packet)
    xPixel, yPixel = extract_pixel_address(packet)
    pixelCoarseToA = extract_pixel_coarse_toa(packet)
    pixelToT = extract_pixel_tot(packet)
    pixelFineToA = extract_pixel_fine_toa(packet)
    pixelDaqTime = extract_pixel_daq_time(packet)

    # Calculate final Time of Arrival for Pixel signal.
    finalPixelToA = get_pixel_toa_final(pixelCoarseToA,pixelFineToA,pixelDaqTime)

    # set Pixel info in signal
    signal['signalType'] = 2
    signal['xPixel'] = xPixel
    signal['yPixel'] = yPixel
    signal['ToaFinal'] = finalPixelToA
    signal['TotFinal'] = pixelToT


def parse_global_time_packet(payload,signal):
    
    # Unpack the payload 
    packet = struct.unpack('<Q', payload)[0]

    # Extract fields using bit manipulation
    highLowTimeFlag = extract_global_time_high_low_flag(packet)
    if highLowTimeFlag == 68:
        globalTimeTimestamp = extract_global_time_low_timestamp(packet)

    if highLowTimeFlag == 69:
        globalTimeTimestamp = extract_global_time_high_timestamp(packet)
    
    globalTimeDaqTime = extract_global_time_daq_time(packet)
    
    # set Pixel info in signal
    signal['signalType'] = 3
    signal['xPixel'] = 0
    signal['yPixel'] = 0
    signal['ToaFinal'] = 0
    signal['TotFinal'] = 0


def read_binary_tpx3_file(file,timeSorted = False,verbose=False):
    # Start recording the time to measure how long the process takes
    start_time = time.time()
    
    # TPX3 flags to check in chunk header in little endian format
    expected_flag_3xpt = (ord('3') << 24) | (ord('X') << 16) | (ord('P') << 8) | ord('T')
    
    
    with open(file, 'rb') as file:
        
        rawSignals = np.empty(0, dtype=singleSignalData)    # creating raw signals array
        readBinaryFlag = True                               # read in binary flag
        numberOfTdcSignals = 0                              # TDC signal counter
        numberOfPixelSignals = 0                            # Pixel signal counter
        numberOfGlobalTimestampSignals = 0                   # Global Timestamp counter
        
        while readBinaryFlag:
                        
            # Read 64 bits (8 bytes) from the file
            binDataPacket = file.read(8)
            if len(binDataPacket) == 8:

                packet = struct.unpack('<Q', binDataPacket)[0]
                
                # Check for TPX3 flag that indicates a chunk header packet
                flag_3xpt = packet & 0xFFFFFFFF
                if flag_3xpt != expected_flag_3xpt:
                    raise ValueError("TPX3 flag not found!")
                    exit()
                
                else:
                    bufferSize,mode,chipNumber = parse_header_packet(binDataPacket)

                    # Set up an array of signals that is the size of "bufferSize"
                    signalBuffer = np.zeros(bufferSize // 8, dtype=singleSignalData)

                    
                    # Loop through all signals in buffer and modify corresponding element in signalBuffer
                    for i in range(bufferSize//8):
                        
                        # Grab next 8 byte packet and determine packet type
                        binDataPacket = file.read(8)                 
                        typeHeader = get_type_header(binDataPacket) 
                        if typeHeader <0:
                            print(typeHeader)
                        
                        # if a TDC packet then parse TDC info and set in signalBuffer[i]
                        if typeHeader == 6: 
                            parse_tdc_packet(binDataPacket,signalBuffer[i])
                            numberOfTdcSignals+=1

                        # if a Pixel packet then parse Pixel info and set in signalBuffer[i]
                        if typeHeader == 11: 
                            parse_pixel_packet(binDataPacket,signalBuffer[i])
                            numberOfPixelSignals+=1

                        # if a Pixel packet then parse Pixel info and set in signalBuffer[i]
                        if typeHeader == 4: 
                            parse_global_time_packet(binDataPacket,signalBuffer[i])
                            numberOfGlobalTimestampSignals+=1
                
                    if timeSorted == True:
                        #Sort events in buffer
                        signalBuffer = sortArray(signalBuffer)
                        
                    rawSignals = np.append(rawSignals,signalBuffer) 
                
            else:
                # Record the time at the end of the process
                end_time = time.time()  
                
                if verbose == True: 
                    print("=========================================")
                    print("End of file")
                    print("Number of Pixel Signals: {}".format(numberOfPixelSignals))
                    print("Number of Tdc Signals: {}".format(numberOfTdcSignals))
                    print("Number of GobalTimestamp Signals: {}".format(numberOfGlobalTimestampSignals))
                    print("Read {} signals in {:.6f} seconds".format(len(rawSignals),end_time-start_time))
                    print("=========================================")
                
                # Set read binary flag to False
                readBinaryFlag = False
        
        return rawSignals


def read_binary_list_file(binaryFile):
    """Read in a binary file that is an array of four doubles [xPosition][yPosition][Time-of-Arrival][Time-of-Flight]

    Args:
        binaryFile (binary file): array of four doubles [xPosition][yPosition][Time-of-Arrival][Time-of-Flight]

    Returns:
        data: numpy array of shape (num_structs, 4) with columns [xPosition][yPosition][Time-of-Arrival][Time-of-Flight]
    """

    # Start recording the time to measure how long the process takes
    start_time = time.time()

    # Open the binary file in read-only binary mode
    with open(binaryFile, "rb") as file:
        
        # Memory-map the file to allow efficient random-access reads
        mmapped_file = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        
        # Define the format of the data in the binary file: four doubles per structure
        struct_format = "dddd"
        # Calculate the size (in bytes) of each structure
        struct_size = struct.calcsize(struct_format)
        # Calculate the total number of structures in the file
        num_structs = len(mmapped_file) // struct_size

        # Preallocate a numpy array for the data for efficient memory usage
        data = np.zeros((num_structs, 4))

        # Loop through the memory-mapped file, unpack each structure, and store it in the numpy array
        for i in range(num_structs):
            # Extract the raw bytes corresponding to the current structure
            raw_data = mmapped_file[i * struct_size : (i + 1) * struct_size]
            # Unpack the raw bytes into four doubles and store them in the numpy array
            data[i] = struct.unpack(struct_format, raw_data)
        
        # Close the memory-mapped file after reading all the data
        mmapped_file.close()

    # Record the time at the end of the process
    end_time = time.time()
    
    # Print the number of structures read and the time taken
    print("Read {} structures in {:.6f} seconds".format(len(data),end_time-start_time))
    
    # Return the data as a numpy array
    return data

