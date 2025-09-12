from hermes.acquisition.configure import (
    create_default_config, 
    load_config_from_file,
    create_config_from_dict
)
from hermes.acquisition.models.schema import Default as HermesDefault
from hermes.acquisition.logger import setup_logger

# Setup logging to see what's happening
setup_logger(log_level="INFO")

print("=== Example 1: Default Configuration ===")
manager = create_default_config()
print(manager.summary())

print("\n=== Example 2: Custom Environment Setup ===")
manager.setup_environment(
    path_to_working_dir="/Users/alexlong/test_data",
    run_dir_name="test_run_001",
    clean_if_exists=True
)
print(f"Updated working dir: {manager.config.environment.path_to_working_dir}")
print(f"Updated run dir: {manager.config.environment.run_dir_name}")

print("\n=== Example 3: Add Hardware Configuration ===")
manager.setup_zabers(
    port="/dev/ttyUSB0",
    baud_rate=115200,
    debug=True
)
print(f"Zabers port: {manager.config.zabers.port}")
print(f"Zabers debug: {manager.config.zabers.debug}")

# Add a motor to the Zabers config
manager.config.zabers.add_motor(axis_id=1, name="sample_x", max_position=50.0)
print(f"Added motor: {manager.config.zabers.get_motor_by_name('sample_x').name}")

print("\n=== Example 4: Setup Serval Configuration ===")
manager.setup_serval(
    host="192.168.1.100",
    port=8080,
    timeout=10.0
)
print(f"Serval: {manager.config.serval.host}:{manager.config.serval.port}")

print("\n=== Example 5: Save Configuration to File ===")
manager.save_to_file("test_config.json")
manager.save_to_file("test_config.yaml")
print("Configuration saved to both JSON and YAML formats")

print("\n=== Example 6: Load Configuration from File ===")
new_manager = load_config_from_file("test_config.json")
print("Loaded configuration summary:")
print(new_manager.summary())

print("\n=== Example 7: Create from Dictionary ===")
config_dict = {
    "environment": {
        "path_to_working_dir": "/tmp/hermes_test",
        "run_dir_name": "dict_test",
        "create_if_missing": True
    },
    "serval": {
        "host": "localhost",
        "port": 9999
    },
    "log_level": "DEBUG"
}

dict_manager = create_config_from_dict(config_dict)
print("Configuration from dictionary:")
print(dict_manager.summary())

print("\n=== Example 8: Access Individual Components ===")
# Get the full configuration object
config = manager.get_config()
print(f"Config type: {type(config)}")
print(f"Environment type: {type(config.environment)}")

# Access individual fields
print(f"Image files directory: {config.environment.path_to_image_files}")
print(f"Log files directory: {config.environment.path_to_log_files}")

if config.zabers:
    print(f"Number of motors: {len(config.zabers.motors)}")

print("\n=== Example 9: Validation ===")
try:
    manager.validate_config()
    print("✅ Configuration is valid")
except Exception as e:
    print(f"❌ Configuration validation failed: {e}")

print("\n=== Example 10: Export to Dictionary ===")
config_dict = manager.to_dict()
print("Configuration keys:", list(config_dict.keys()))
print("Environment keys:", list(config_dict['environment'].keys()))

print("\n=== Tests completed successfully! ===")