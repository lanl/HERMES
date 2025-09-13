import os
import json

def create_camera_info_directory(base_path: str):
    """Create the camera info directory structure inside CameraConfig."""
    camera_config_path = os.path.join(base_path, "CameraConfig")
    directories = [
        os.path.join(camera_config_path, "acquisition_configs"),
        os.path.join(camera_config_path, "serval"),
        os.path.join(camera_config_path, "calibration_files"),
        os.path.join(camera_config_path, "logs"),
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    print(f"Camera info directory structure created at: {camera_config_path}")


def initial_setup(base_path: str):
    """Perform the initial setup for HERMES."""
    # Create the camera info directory structure
    create_camera_info_directory(base_path)

    # Ensure server_config.ini exists
    setup_ini_path = os.path.join(base_path, "CameraConfig", "server_config.ini")
    if not os.path.exists(setup_ini_path):
        with open(setup_ini_path, "w") as f:
            f.write(
                "[ServerConfig]\n"
                "serverurl = http://localhost:8080\n"
                "path_to_server = [PATH/TO/TPX3/SERVAL]\n"
                "path_to_server_config_files = [/PATH/TO/CAMERASETTINGS/FROM/SERVAL/DIR]\n"
                "bpc_file_name = settings.bpc\n"
                "dac_file_name = settings.bpc.dacs\n"
                "destinations_file_name = initial_server_destinations.json\n"
                "detector_config_file_name = initial_detector_config.json\n"
            )
        print(f"Default server_config.ini created at: {setup_ini_path}")
    else:
        print(f"server_config.ini already exists at: {setup_ini_path}")

    print(f"Initial setup completed. Camera info directory created at: {os.path.join(base_path, 'CameraConfig')}")
 