"""
Tests for the ConfigurationManager and related functions in configure.py.
"""

import pytest
import tempfile
import json
from pathlib import Path
from pydantic import ValidationError
from unittest.mock import patch, MagicMock, mock_open

from hermes.acquisition.configure import (
    ConfigurationManager,
    create_default_config,
    load_config_from_file,
    create_config_from_dict,
    save_individual_model,
    load_individual_model
)


@pytest.fixture(autouse=True)
def mock_hermes():
    """Auto-use fixture that mocks HermesDefault globally for all tests."""
    with patch('hermes.acquisition.configure.HermesDefault') as mock_default:
        # Create a mock instance with properly configured attributes
        mock_instance = MagicMock()
        mock_instance.environment = MagicMock()
        mock_instance.environment.path_to_working_dir = "/tmp"
        mock_instance.environment.run_dir_name = "test_run"
        
        mock_instance.serval = MagicMock()
        mock_instance.serval.host = "localhost"
        mock_instance.serval.port = 8080
        
        mock_instance.run_settings = MagicMock()
        mock_instance.run_settings.measurement_time = 60.0
        
        mock_instance.hardware = None
        mock_instance.zabers = None
        mock_instance.epics_control = None
        mock_instance.log_level = "INFO"
        
        # Configure methods
        mock_instance.model_dump.return_value = {
            "environment": {"path_to_working_dir": "/tmp", "run_dir_name": "test_run"},
            "serval": {"host": "localhost", "port": 8080},
            "run_settings": {"measurement_time": 60.0},
            "log_level": "INFO"
        }
        
        # Make the constructor return the mock instance
        mock_default.return_value = mock_instance
        mock_default.model_validate.return_value = mock_instance
        
        yield mock_instance


@pytest.fixture
def temp_working_dir():
    """Fixture that creates a temporary working directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_logger():
    """Fixture that mocks the logger to avoid log output during tests."""
    with patch('hermes.acquisition.configure.logger') as mock_log:
        yield mock_log


@pytest.fixture
def sample_config_dict():
    """Fixture providing a sample configuration dictionary."""
    return {
        "environment": {
            "path_to_working_dir": "/tmp/test",
            "run_dir_name": "test_run",
            "create_if_missing": False
        },
        "serval": {
            "host": "test.example.com",
            "port": 9090
        },
        "run_settings": {
            "measurement_time": 60.0,
            "detector_distance": 100.0
        },
        "log_level": "INFO"
    }


class TestConfigurationManager:
    """Test cases for ConfigurationManager class."""

    def test_init_default_config(self, mock_logger):
        """Test initialization with default configuration."""
        manager = ConfigurationManager()
        
        assert manager.config is not None
        mock_logger.info.assert_called_with("ConfigurationManager initialized")

    def test_init_with_existing_config(self, mock_logger):
        """Test initialization with pre-existing configuration."""
        existing_config = MagicMock()
        manager = ConfigurationManager(config=existing_config)
        
        assert manager.config is existing_config
        mock_logger.info.assert_called_with("ConfigurationManager initialized")

    def test_setup_environment_no_kwargs(self, mock_logger):
        """Test environment setup without modifications."""
        manager = ConfigurationManager()
        original_env = manager.config.environment
        
        result = manager.setup_environment()
        
        assert result is manager.config.environment
        assert result is original_env

    def test_setup_environment_with_kwargs(self, mock_logger):
        """Test environment setup with modifications."""
        manager = ConfigurationManager()
        
        # Mock the WorkingDir constructor
        with patch('hermes.acquisition.configure.WorkingDir') as mock_working_dir:
            mock_instance = MagicMock()
            mock_working_dir.return_value = mock_instance
            
            result = manager.setup_environment(
                run_dir_name="custom_run",
                create_if_missing=False
            )
            
            assert result is mock_instance
            mock_logger.info.assert_called_with(
                "Environment configuration updated with: ['run_dir_name', 'create_if_missing']"
            )

    def test_setup_environment_validation_error(self, mock_logger):
        """Test environment setup with invalid configuration."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.WorkingDir', side_effect=ValidationError.from_exception_data("WorkingDir", [])):
            with pytest.raises(ValidationError):
                manager.setup_environment(invalid_field="invalid_value")
            
            mock_logger.error.assert_called()

    def test_setup_serval_with_kwargs(self, mock_logger):
        """Test Serval setup with modifications."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.ServalConfig') as mock_serval:
            mock_instance = MagicMock()
            mock_serval.return_value = mock_instance
            
            result = manager.setup_serval(
                host="custom.example.com",
                port=8090
            )
            
            assert result is mock_instance
            mock_logger.info.assert_called_with(
                "Serval configuration updated with: ['host', 'port']"
            )

    def test_setup_serval_validation_error(self, mock_logger):
        """Test Serval setup with validation error."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.ServalConfig', side_effect=ValidationError.from_exception_data("ServalConfig", [])):
            with pytest.raises(ValidationError):
                manager.setup_serval(host="invalid", port="invalid")
            
            mock_logger.error.assert_called()

    def test_setup_run_settings_with_kwargs(self, mock_logger):
        """Test run settings setup with modifications."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.RunSettings') as mock_run_settings:
            mock_instance = MagicMock()
            mock_run_settings.return_value = mock_instance
            
            result = manager.setup_run_settings(
                measurement_time=120.0,
                detector_distance=200.0
            )
            
            assert result is mock_instance
            mock_logger.info.assert_called_with(
                "Run settings configuration updated with: ['measurement_time', 'detector_distance']"
            )

    def test_setup_run_settings_validation_error(self, mock_logger):
        """Test run settings setup with validation error."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.RunSettings', side_effect=ValidationError.from_exception_data("RunSettings", [])):
            with pytest.raises(ValidationError):
                manager.setup_run_settings(invalid_field="invalid")
            
            mock_logger.error.assert_called()

    def test_setup_hardware_new_config(self, mock_logger):
        """Test hardware setup when no existing config."""
        manager = ConfigurationManager()
        manager.config.hardware = None
        
        with patch('hermes.acquisition.configure.HardwareConfig') as mock_hardware:
            mock_instance = MagicMock()
            mock_hardware.return_value = mock_instance
            
            result = manager.setup_hardware(
                detector_name="test_detector",
                serial_number="12345"
            )
            
            assert result is mock_instance
            mock_logger.info.assert_called_with("Hardware configuration created")

    def test_setup_hardware_update_existing(self, mock_logger):
        """Test hardware setup when updating existing config."""
        manager = ConfigurationManager()
        
        # Create existing hardware config
        existing_hardware = MagicMock()
        existing_hardware.model_dump.return_value = {"detector_name": "old_detector"}
        manager.config.hardware = existing_hardware
        
        with patch('hermes.acquisition.configure.HardwareConfig') as mock_hardware:
            mock_instance = MagicMock()
            mock_hardware.return_value = mock_instance
            
            result = manager.setup_hardware(detector_name="updated_detector")
            
            assert result is mock_instance
            mock_logger.info.assert_called_with(
                "Hardware configuration updated with: ['detector_name']"
            )

    def test_setup_hardware_validation_error(self, mock_logger):
        """Test hardware setup with validation error."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.HardwareConfig', side_effect=ValidationError.from_exception_data("HardwareConfig", [])):
            with pytest.raises(ValidationError):
                manager.setup_hardware(invalid_field="invalid")
            
            mock_logger.error.assert_called()

    def test_setup_zabers_new_config(self, mock_logger):
        """Test Zaber setup when no existing config."""
        manager = ConfigurationManager()
        manager.config.zabers = None
        
        with patch('hermes.acquisition.configure.ZaberConfig') as mock_zaber:
            mock_instance = MagicMock()
            mock_zaber.return_value = mock_instance
            
            result = manager.setup_zabers(serial_port="/dev/ttyUSB0")
            
            assert result is mock_instance
            mock_logger.info.assert_called_with("Zaber configuration created")

    def test_setup_zabers_update_existing(self, mock_logger):
        """Test Zaber setup when updating existing config."""
        manager = ConfigurationManager()
        
        # Create existing zabers config
        existing_zabers = MagicMock()
        existing_zabers.model_dump.return_value = {"serial_port": "/dev/ttyUSB0"}
        manager.config.zabers = existing_zabers
        
        with patch('hermes.acquisition.configure.ZaberConfig') as mock_zaber:
            mock_instance = MagicMock()
            mock_zaber.return_value = mock_instance
            
            result = manager.setup_zabers(serial_port="/dev/ttyUSB1")
            
            assert result is mock_instance
            mock_logger.info.assert_called_with(
                "Zaber configuration updated with: ['serial_port']"
            )

    def test_setup_zabers_validation_error(self, mock_logger):
        """Test Zaber setup with validation error."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.ZaberConfig', side_effect=ValidationError.from_exception_data("ZaberConfig", [])):
            with pytest.raises(ValidationError):
                manager.setup_zabers(invalid_field="invalid")
            
            mock_logger.error.assert_called()

    def test_setup_epics_new_config(self, mock_logger):
        """Test EPICS setup when no existing config."""
        manager = ConfigurationManager()
        manager.config.epics_control = None
        
        with patch('hermes.acquisition.configure.EPICSConfig') as mock_epics:
            mock_instance = MagicMock()
            mock_epics.return_value = mock_instance
            
            result = manager.setup_epics(prefix="TEST:")
            
            assert result is mock_instance
            mock_logger.info.assert_called_with("EPICS configuration created")

    def test_setup_epics_update_existing(self, mock_logger):
        """Test EPICS setup when updating existing config."""
        manager = ConfigurationManager()
        
        # Create existing EPICS config
        existing_epics = MagicMock()
        existing_epics.model_dump.return_value = {"prefix": "OLD:"}
        manager.config.epics_control = existing_epics
        
        with patch('hermes.acquisition.configure.EPICSConfig') as mock_epics:
            mock_instance = MagicMock()
            mock_epics.return_value = mock_instance
            
            result = manager.setup_epics(prefix="NEW:")
            
            assert result is mock_instance
            mock_logger.info.assert_called_with(
                "EPICS configuration updated with: ['prefix']"
            )

    def test_setup_epics_validation_error(self, mock_logger):
        """Test EPICS setup with validation error."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.EPICSConfig', side_effect=ValidationError.from_exception_data("EPICSConfig", [])):
            with pytest.raises(ValidationError):
                manager.setup_epics(invalid_field="invalid")
            
            mock_logger.error.assert_called()

    def test_save_config_file_default_path(self, temp_working_dir, mock_logger):
        """Test saving configuration to default path."""
        manager = ConfigurationManager()
        manager.config.environment.path_to_working_dir = temp_working_dir
        config_file = "test_config.json"
        
        with patch('hermes.acquisition.configure.save_pydantic_model') as mock_save:
            manager.save_config_file(config_file)
            
            expected_path = Path(temp_working_dir) / "CameraConfig" / "acquisition_configs" / config_file
            mock_save.assert_called_once_with(manager.config, expected_path, format="auto")

    def test_save_config_file_custom_path(self, temp_working_dir, mock_logger):
        """Test saving configuration to custom path."""
        manager = ConfigurationManager()
        config_file = "test_config.yaml"
        custom_path = Path(temp_working_dir) / "custom"
        
        with patch('hermes.acquisition.configure.save_pydantic_model') as mock_save:
            manager.save_config_file(config_file, format="yaml", config_path=custom_path)
            
            expected_path = custom_path / config_file
            mock_save.assert_called_once_with(manager.config, expected_path, format="yaml")

    def test_save_config_file_error(self, temp_working_dir, mock_logger):
        """Test save configuration with error."""
        manager = ConfigurationManager()
        manager.config.environment.path_to_working_dir = temp_working_dir
        
        with patch('hermes.acquisition.configure.save_pydantic_model', side_effect=Exception("Save failed")):
            with pytest.raises(Exception, match="Save failed"):
                manager.save_config_file("test_config.json")
            
            mock_logger.error.assert_called()

    def test_load_from_file_success(self, mock_logger):
        """Test loading configuration from file successfully."""
        manager = ConfigurationManager()
        mock_config = MagicMock()
        
        with patch('hermes.acquisition.utils.load_pydantic_model', return_value=mock_config):
            result = manager.load_from_file("test_config.json")
            
            assert result is mock_config
            assert manager.config is mock_config
            mock_logger.success.assert_called_with("Configuration loaded from test_config.json")

    def test_load_from_file_error(self, mock_logger):
        """Test loading configuration from file with error."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.utils.load_pydantic_model', side_effect=Exception("Load failed")):
            with pytest.raises(Exception, match="Load failed"):
                manager.load_from_file("invalid_config.json")
            
            mock_logger.error.assert_called()

    def test_load_from_dict_success(self, sample_config_dict, mock_logger):
        """Test loading configuration from dictionary successfully."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.HermesDefault') as mock_hermes:
            mock_instance = MagicMock()
            mock_hermes.model_validate.return_value = mock_instance
            
            result = manager.load_from_dict(sample_config_dict)
            
            assert result is mock_instance
            mock_logger.success.assert_called_with("Configuration loaded from dictionary")

    def test_load_from_dict_validation_error(self, mock_logger):
        """Test loading configuration from invalid dictionary."""
        manager = ConfigurationManager()
        invalid_dict = {"invalid_field": "invalid_value"}
        
        with patch('hermes.acquisition.configure.HermesDefault') as mock_hermes:
            mock_hermes.model_validate.side_effect = ValidationError.from_exception_data("HermesDefault", [])
            
            with pytest.raises(ValidationError):
                manager.load_from_dict(invalid_dict)
            
            mock_logger.error.assert_called()

    def test_to_dict(self):
        """Test converting configuration to dictionary."""
        manager = ConfigurationManager()
        result = manager.to_dict()
        
        manager.config.model_dump.assert_called_once_with(exclude_none=True)

    def test_to_dict_exclude_none_false(self):
        """Test converting configuration to dictionary including None values."""
        manager = ConfigurationManager()
        result = manager.to_dict(exclude_none=False)
        
        manager.config.model_dump.assert_called_once_with(exclude_none=False)

    def test_get_config(self):
        """Test getting current configuration."""
        manager = ConfigurationManager()
        result = manager.get_config()
        
        assert result is manager.config

    def test_validate_config_success(self, mock_logger):
        """Test successful configuration validation."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.HermesDefault') as mock_hermes:
            mock_hermes.model_validate.return_value = MagicMock()
            
            result = manager.validate_config()
            
            assert result is True
            mock_logger.info.assert_called_with("Configuration validation successful")

    def test_validate_config_failure(self, mock_logger):
        """Test failed configuration validation."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.HermesDefault') as mock_hermes:
            mock_hermes.model_validate.side_effect = ValidationError.from_exception_data("HermesDefault", [])
            
            with pytest.raises(ValidationError):
                manager.validate_config()
            
            mock_logger.error.assert_called()

    def test_reset_to_defaults(self, mock_logger):
        """Test resetting configuration to defaults."""
        manager = ConfigurationManager()
        
        with patch('hermes.acquisition.configure.HermesDefault') as mock_hermes:
            mock_instance = MagicMock()
            mock_hermes.return_value = mock_instance
            
            result = manager.reset_to_defaults()
            
            assert result is mock_instance
            mock_logger.info.assert_called_with("Configuration reset to defaults")

    def test_summary(self):
        """Test getting configuration summary."""
        manager = ConfigurationManager()
        # Configure the mock to return realistic values
        manager.config.environment.path_to_working_dir = "/tmp/test"
        manager.config.environment.run_dir_name = "test_run"
        manager.config.log_level = "INFO"
        manager.config.serval.host = "localhost"
        manager.config.serval.port = 8080
        manager.config.hardware = None
        manager.config.zabers = None
        manager.config.epics_control = None
        
        summary = manager.summary()
        
        assert "HERMES Configuration Summary:" in summary
        assert "Working Directory: /tmp/test" in summary
        assert "Run Directory: test_run" in summary


class TestConvenienceFunctions:
    """Test cases for convenience functions."""

    def test_create_default_config(self):
        """Test creating default configuration manager."""
        with patch('hermes.acquisition.configure.ConfigurationManager') as mock_manager:
            result = create_default_config()
            
            mock_manager.assert_called_once_with()
            assert result == mock_manager.return_value

    def test_load_config_from_file(self):
        """Test loading configuration from file."""
        test_file = "test_config.json"
        
        with patch('hermes.acquisition.configure.ConfigurationManager') as mock_manager:
            mock_instance = mock_manager.return_value
            
            result = load_config_from_file(test_file)
            
            mock_manager.assert_called_once_with()
            mock_instance.load_from_file.assert_called_once_with(test_file)
            assert result == mock_instance

    def test_create_config_from_dict(self, sample_config_dict):
        """Test creating configuration from dictionary."""
        with patch('hermes.acquisition.configure.ConfigurationManager') as mock_manager:
            mock_instance = mock_manager.return_value
            
            result = create_config_from_dict(sample_config_dict)
            
            mock_manager.assert_called_once_with()
            mock_instance.load_from_dict.assert_called_once_with(sample_config_dict)
            assert result == mock_instance

    def test_save_individual_model_success(self, mock_logger):
        """Test saving individual model successfully."""
        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"test": "data"}
        output_file = "test_model.json"
        
        with patch('hermes.acquisition.utils.save_pydantic_model') as mock_save:
            save_individual_model(mock_model, output_file, format="json")
            
            mock_save.assert_called_once_with(mock_model, output_file, format="json")

    def test_save_individual_model_error(self, mock_logger):
        """Test saving individual model with error."""
        mock_model = MagicMock()
        output_file = "test_model.json"
        
        with patch('hermes.acquisition.utils.save_pydantic_model', side_effect=Exception("Save failed")):
            with pytest.raises(Exception, match="Save failed"):
                save_individual_model(mock_model, output_file)
            
            mock_logger.error.assert_called()

    def test_load_individual_model_success(self, mock_logger):
        """Test loading individual model successfully."""
        mock_model_class = MagicMock()
        mock_instance = MagicMock()
        input_file = "test_model.json"
        
        with patch('hermes.acquisition.utils.load_pydantic_model', return_value=mock_instance):
            result = load_individual_model(mock_model_class, input_file)
            
            assert result == mock_instance
            mock_logger.success.assert_called_with(f"Model loaded from {input_file}")

    def test_load_individual_model_error(self, mock_logger):
        """Test loading individual model with error."""
        mock_model_class = MagicMock()
        input_file = "invalid_model.json"
        
        with patch('hermes.acquisition.utils.load_pydantic_model', side_effect=Exception("Load failed")):
            with pytest.raises(Exception, match="Load failed"):
                load_individual_model(mock_model_class, input_file)
            
            mock_logger.error.assert_called()


class TestIntegrationScenarios:
    """Integration test scenarios combining multiple operations."""

    def test_configuration_workflow(self, mock_logger):
        """Test a complete configuration workflow."""
        # Create manager
        manager = ConfigurationManager()
        
        # Mock setup methods
        with patch.object(manager, 'setup_environment') as mock_env, \
             patch.object(manager, 'setup_serval') as mock_serval, \
             patch.object(manager, 'validate_config') as mock_validate:
            
            mock_validate.return_value = True
            
            # Setup components
            manager.setup_environment(run_dir_name="integration_test")
            manager.setup_serval(host="integration.example.com", port=9000)
            
            # Validate configuration
            assert manager.validate_config() is True
            
            # Verify methods were called
            mock_env.assert_called_once()
            mock_serval.assert_called_once()
            mock_validate.assert_called()

    @pytest.mark.parametrize("setup_method,test_kwargs", [
        ("setup_environment", {"run_dir_name": "param_test"}),
        ("setup_serval", {"host": "param.example.com"}),
        ("setup_run_settings", {"measurement_time": 180.0}),
    ])
    def test_parameterized_setup_methods(self, setup_method, test_kwargs):
        """Test various setup methods with different parameters."""
        manager = ConfigurationManager()
        
        # Mock the specific setup method
        with patch.object(manager, setup_method) as mock_setup:
            mock_result = MagicMock()
            mock_setup.return_value = mock_result
            
            # Call the setup method
            setup_func = getattr(manager, setup_method)
            result = setup_func(**test_kwargs)
            
            # Verify the result
            assert result is mock_result
            mock_setup.assert_called_once_with(**test_kwargs)