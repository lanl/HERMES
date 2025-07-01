# filepath: /home/l280162/Programs/hermes/src/pyhermes/utils/logger.py
import logging
import os

# Create a custom logger
logger = logging.getLogger('pyhermes_logger')

# Set the default log level
logger.setLevel(logging.DEBUG)

# Create stream handler
c_handler = logging.StreamHandler() 

# Create file handler in the current working directory
log_file_path = os.path.join(os.getcwd(), 'hermes.log')
f_handler = logging.FileHandler(log_file_path)

# Set log level for handlers
c_handler.setLevel(logging.WARNING)
f_handler.setLevel(logging.DEBUG)

# Create formatters and add them to handlers
c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
c_handler.setFormatter(c_format)
f_handler.setFormatter(f_format)

# Add handlers to the logger
logger.addHandler(c_handler)
logger.addHandler(f_handler)