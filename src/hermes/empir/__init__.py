"""
pyhermes.empir package

This package contains modules and functions related to analysis with the EMPIR commercial code.
"""

# Import models
from .models import (
    PixelToPhotonParams,
    PhotonToEventParams,
    EventToImageParams,
    DirectoryStructure,
    PixelActivations,
    Photons
)

# Import core functions for EMPIR analysis
from .core import (
    empirConfig,
    zip_file,
    check_for_files,
    process_pixels_to_photons,
    process_photons_to_events,
    process_event_files_to_image_stack
)

# Import export functions for EMPIR analysis
from .export import (
    export_pixel_activations,
    export_photons,
    read_exported_pixel_activations
)

# Define package-level variables or functions if needed
__all__ = [
    'empirConfig',
    'zip_file',
    'check_for_files',
    'process_pixels_to_photons',
    'process_photons_to_events',
    'process_event_files_to_image_stack',
    'export_pixel_activations',
    'export_photons',
    'read_exported_pixel_activations',
    'PixelToPhotonParams',
    'PhotonToEventParams',
    'EventToImageParams',
    'DirectoryStructure',
    'PixelActivations',
    'Photons'
]

# Initialize package-level settings or configurations if needed
def initialize():
    pass

# Any other package-level code can go here