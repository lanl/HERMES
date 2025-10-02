"""
Tests for the ServalConfig pydantic model.
"""

import pytest
import tempfile
from pathlib import Path
from pydantic import ValidationError

from hermes.acquisition.models.software.serval import ServalConfig


@pytest.fixture
def mock_serval_environment():
    """
    Fixture that creates a temporary serval environment with all required directories and files.
    
    Returns:
        dict: Contains 'serval_dir' and 'config_dir' paths as strings
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        serval_dir = Path(temp_dir) / "serval"
        config_dir = Path(temp_dir) / "servalConfigFiles"
        serval_dir.mkdir()
        config_dir.mkdir()
        
        # Create all required files
        (config_dir / "initial_serval_destinations.json").touch()
        (config_dir / "initial_serval_detector_config.json").touch()
        (config_dir / "settings.bpc").touch()
        (config_dir / "settings.bpc.dac").touch()
        
        yield {
            'serval_dir': str(serval_dir),
            'config_dir': str(config_dir)
        }


@pytest.fixture
def mock_serval_directories_only():
    """
    Fixture that creates only the serval and config directories without files.
    Useful for testing missing file scenarios.
    
    Returns:
        dict: Contains 'serval_dir' and 'config_dir' paths as strings
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        serval_dir = Path(temp_dir) / "serval"
        config_dir = Path(temp_dir) / "config"
        serval_dir.mkdir()
        config_dir.mkdir()
        
        yield {
            'serval_dir': str(serval_dir),
            'config_dir': str(config_dir)
        }


class TestServalConfig:
    """Test cases for ServalConfig pydantic model."""

    def test_default_values(self, mock_serval_environment):
        """Test that default values are set correctly."""
        config = ServalConfig(
            path_to_serval=mock_serval_environment['serval_dir'],
            path_to_serval_config_files=mock_serval_environment['config_dir']
        )
            
        assert config.host == "localhost"
        assert config.port == 8080
        assert config.path_to_serval == mock_serval_environment['serval_dir']
        assert config.version == "2.1.6"
        assert config.path_to_serval_config_files == mock_serval_environment['config_dir']
        assert config.destinations_file_name == "initial_serval_destinations.json"
        assert config.detector_config_file_name == "initial_serval_detector_config.json"
        assert config.bpc_file_name == "settings.bpc"
        assert config.dac_file_name == "settings.bpc.dac"

    def test_custom_values(self, mock_serval_environment):
        """Test creating config with custom values."""
        config = ServalConfig(
            host="192.168.1.100",
            port=9090,
            version="3.0.0",
            path_to_serval=mock_serval_environment['serval_dir'],
            path_to_serval_config_files=mock_serval_environment['config_dir']
        )
        
        assert config.host == "192.168.1.100"
        assert config.port == 9090
        assert config.version == "3.0.0"
        # Other values should use the provided paths
        assert config.path_to_serval == mock_serval_environment['serval_dir']

    def test_port_validation_valid_range(self, mock_serval_environment):
        """Test that valid port numbers are accepted."""
        # Test edge cases and common ports
        valid_ports = [1, 80, 443, 8080, 65535]
        
        for port in valid_ports:
            config = ServalConfig(
                port=port,
                path_to_serval=mock_serval_environment['serval_dir'],
                path_to_serval_config_files=mock_serval_environment['config_dir']
            )
            assert config.port == port

    def test_port_validation_invalid_range(self):
        """Test that invalid port numbers raise ValidationError."""
        invalid_ports = [0, -1, 65536, 100000]
        
        for port in invalid_ports:
            with pytest.raises(ValidationError) as exc_info:
                ServalConfig(port=port)
            
            assert "Port must be between 1 and 65535" in str(exc_info.value)

    def test_serval_path_validation_nonexistent_directory(self):
        """Test that non-existent serval directory raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ServalConfig(path_to_serval="/nonexistent/path/")
        
        assert "Serval directory does not exist" in str(exc_info.value)

    def test_serval_path_validation_file_instead_of_directory(self):
        """Test that providing a file path instead of directory raises ValidationError."""
        with tempfile.NamedTemporaryFile() as temp_file:
            with pytest.raises(ValidationError) as exc_info:
                ServalConfig(path_to_serval=temp_file.name)
            
            assert "Serval path is not a directory" in str(exc_info.value)

    def test_config_files_path_validation_nonexistent_directory(self):
        """Test that non-existent config files directory raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ServalConfig(path_to_serval_config_files="/nonexistent/config/path/")
        
        assert "Serval config files directory does not exist" in str(exc_info.value)

    def test_config_files_path_validation_file_instead_of_directory(self):
        """Test that providing a file path instead of config directory raises ValidationError."""
        with tempfile.NamedTemporaryFile() as temp_file:
            with pytest.raises(ValidationError) as exc_info:
                ServalConfig(path_to_serval_config_files=temp_file.name)
            
            assert "Serval config files path is not a directory" in str(exc_info.value)

    def test_missing_destinations_file(self, mock_serval_directories_only):
        """Test that missing destinations file raises ValidationError."""
        config_dir = Path(mock_serval_directories_only['config_dir'])
        
        # Create all files except destinations file
        (config_dir / "initial_serval_detector_config.json").touch()
        (config_dir / "settings.bpc").touch()
        (config_dir / "settings.bpc.dac").touch()
        
        with pytest.raises(ValidationError) as exc_info:
            ServalConfig(
                path_to_serval=mock_serval_directories_only['serval_dir'],
                path_to_serval_config_files=mock_serval_directories_only['config_dir']
            )
        
        assert "Destinations file does not exist" in str(exc_info.value)

    def test_missing_detector_config_file(self, mock_serval_directories_only):
        """Test that missing detector config file raises ValidationError."""
        config_dir = Path(mock_serval_directories_only['config_dir'])
        
        # Create all files except detector config file
        (config_dir / "initial_serval_destinations.json").touch()
        (config_dir / "settings.bpc").touch()
        (config_dir / "settings.bpc.dac").touch()
        
        with pytest.raises(ValidationError) as exc_info:
            ServalConfig(
                path_to_serval=mock_serval_directories_only['serval_dir'],
                path_to_serval_config_files=mock_serval_directories_only['config_dir']
            )
        
        assert "Detector config file does not exist" in str(exc_info.value)

    def test_missing_bpc_file(self, mock_serval_directories_only):
        """Test that missing BPC file raises ValidationError."""
        config_dir = Path(mock_serval_directories_only['config_dir'])
        
        # Create all files except BPC file
        (config_dir / "initial_serval_destinations.json").touch()
        (config_dir / "initial_serval_detector_config.json").touch()
        (config_dir / "settings.bpc.dac").touch()
        
        with pytest.raises(ValidationError) as exc_info:
            ServalConfig(
                path_to_serval=mock_serval_directories_only['serval_dir'],
                path_to_serval_config_files=mock_serval_directories_only['config_dir']
            )
        
        assert "BPC file does not exist" in str(exc_info.value)

    def test_missing_dac_file(self, mock_serval_directories_only):
        """Test that missing DAC file raises ValidationError."""
        config_dir = Path(mock_serval_directories_only['config_dir'])
        
        # Create all files except DAC file
        (config_dir / "initial_serval_destinations.json").touch()
        (config_dir / "initial_serval_detector_config.json").touch()
        (config_dir / "settings.bpc").touch()
        
        with pytest.raises(ValidationError) as exc_info:
            ServalConfig(
                path_to_serval=mock_serval_directories_only['serval_dir'],
                path_to_serval_config_files=mock_serval_directories_only['config_dir']
            )
        
        assert "DAC file does not exist" in str(exc_info.value)

    def test_valid_configuration_with_all_files(self, mock_serval_environment):
        """Test that a valid configuration with all required files works."""
        # This should not raise any exceptions
        config = ServalConfig(
            host="example.com",
            port=9000,
            path_to_serval=mock_serval_environment['serval_dir'],
            path_to_serval_config_files=mock_serval_environment['config_dir'],
            version="2.2.0"
        )
        
        assert config.host == "example.com"
        assert config.port == 9000
        assert config.path_to_serval == mock_serval_environment['serval_dir']
        assert config.path_to_serval_config_files == mock_serval_environment['config_dir']
        assert config.version == "2.2.0"

    def test_custom_file_names(self, mock_serval_directories_only):
        """Test that custom config file names work correctly."""
        config_dir = Path(mock_serval_directories_only['config_dir'])
        
        # Create files with custom names
        (config_dir / "custom_destinations.json").touch()
        (config_dir / "custom_detector.json").touch()
        (config_dir / "custom.bpc").touch()
        (config_dir / "custom.dac").touch()
        
        config = ServalConfig(
            path_to_serval=mock_serval_directories_only['serval_dir'],
            path_to_serval_config_files=mock_serval_directories_only['config_dir'],
            destinations_file_name="custom_destinations.json",
            detector_config_file_name="custom_detector.json",
            bpc_file_name="custom.bpc",
            dac_file_name="custom.dac"
        )
        
        assert config.destinations_file_name == "custom_destinations.json"
        assert config.detector_config_file_name == "custom_detector.json"
        assert config.bpc_file_name == "custom.bpc"
        assert config.dac_file_name == "custom.dac"

    def test_validation_order(self):
        """Test that field validation happens before model validation."""
        # This should fail on field validation before reaching model validation
        with pytest.raises(ValidationError) as exc_info:
            ServalConfig(
                port=70000,  # Invalid port
                path_to_serval="/nonexistent/"  # Invalid path
            )
        
        # Should contain port validation error
        error_str = str(exc_info.value)
        assert "Port must be between 1 and 65535" in error_str

    @pytest.mark.parametrize("host", [
        "localhost",
        "127.0.0.1",
        "192.168.1.100",
        "example.com",
        "subdomain.example.com"
    ])
    def test_various_host_formats(self, host, mock_serval_environment):
        """Test that various host formats are accepted."""
        config = ServalConfig(
            host=host,
            path_to_serval=mock_serval_environment['serval_dir'],
            path_to_serval_config_files=mock_serval_environment['config_dir']
        )
        assert config.host == host