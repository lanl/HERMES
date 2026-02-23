import pymepix
from pymepix.processing import MessageType
import numpy as np

#Connect to SPIDR
timepix = pymepix.pymepix_connection.PymepixConnection(
    spidr_address=('192.168.100.10', 50000),  # SPIDR IP and port
    udp_ip_port=('192.168.100.1', 8192),      # Local IP and UDP port
    pc_ip='192.168.100.1'                     # Local IP
)

#Set bias voltage
timepix.biasVoltage = 50

#Set pixel masks
timepix[0].pixelThreshold = np.zeros(shape=(256,256),dtype=np.uint8)
timepix[0].pixelMask = np.zeros(shape=(256,256),dtype=np.uint8)
timepix[0].uploadPixels()

#Start acquisition
timepix.start()

while True:
    try:
        #Poll
        data_type,data = timepix.poll()
    except pymepix.PollBufferEmpty:
        #If empty then just loop
        continue

    #Handle Raw
    if data_type is MessageType.RawData:

        print('UDP PACKET')

        packets,longtime = data

        print('Packet ',packets)
        print('Time', longtime)

    #Handle Pixels
    elif data_type is MessageType.PixelData:

        print('I GOT PIXELS!!!!')

        x,y,toa,tot = data

        print('x',x)
        print('y', y)
        print('toa', toa)
        print('tot',tot)

#Stop
timepix.stop()