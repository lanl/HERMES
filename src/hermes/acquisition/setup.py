import os
import json
import configparser

def create_camera_info_directory(base_path: str):
    """Create the camera info directory structure."""
    directories = [
        os.path.join(base_path, "acquisition_configs"),
        os.path.join(base_path, "serval"),
        os.path.join(base_path, "camera_files"),
        os.path.join(base_path, "logs"),
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
    print(f"Camera info directory structure created at: {base_path}")


def save_config_file(config: dict, base_path: str, file_name: str):
    """Save a configuration file to the acquisition_configs/ folder."""
    configs_path = os.path.join(base_path, "acquisition_configs")
    os.makedirs(configs_path, exist_ok=True)
    file_path = os.path.join(configs_path, file_name)
    with open(file_path, "w") as f:
        json.dump(config, f, indent=4)
    print(f"Configuration saved to {file_path}")


def load_config_file(base_path: str, file_name: str) -> dict:
    """Load a configuration file from the acquisition_configs/ folder."""
    file_path = os.path.join(base_path, "acquisition_configs", file_name)
    with open(file_path, "r") as f:
        return json.load(f)


def load_config_with_setup(acquisition_config_path: str, setup_config_path: str) -> dict:
    """Load acquisition and setup configurations and merge them."""
    acquisition_config = configparser.ConfigParser()
    acquisition_config.read(acquisition_config_path)

    setup_config = configparser.ConfigParser()
    setup_config.read(setup_config_path)

    # Merge ServerConfig from setup.ini into the acquisition config
    if 'ServerConfig' in setup_config:
        acquisition_config['ServerConfig'] = setup_config['ServerConfig']

    return acquisition_config
