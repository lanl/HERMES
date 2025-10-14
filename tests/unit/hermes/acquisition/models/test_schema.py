"""
Simplified tests for the schema models in schema.py.
"""

import pytest
from pydantic import ValidationError
from unittest.mock import patch, MagicMock

from hermes.acquisition.models.schema import (
    Default,
    JustServal,
    JustCamera,
    NoEpics,
    CURRENT_SCHEMA_VERSION,
    get_current_schema_version,
    is_schema_compatible,
    needs_migration
)


class TestSchemaStructure:
    """Test the structure and basic functionality of schema classes."""

    def test_schema_inheritance(self):
        """Test that all schemas inherit from BaseModel."""
        from pydantic import BaseModel
        
        assert issubclass(Default, BaseModel)
        assert issubclass(JustServal, BaseModel)
        assert issubclass(JustCamera, BaseModel)
        assert issubclass(NoEpics, BaseModel)

    def test_default_field_structure(self):
        """Test Default schema has expected fields."""
        fields = Default.model_fields
        
        expected_fields = {
            "schema_version", "environment", "serval", "run_settings", 
            "hardware", "zabers", "epics_control", "log_level"
        }
        actual_fields = set(fields.keys())
        
        assert actual_fields == expected_fields

    def test_justserval_field_structure(self):
        """Test JustServal schema has expected fields."""
        fields = JustServal.model_fields
        
        expected_fields = {"schema_version", "environment", "serval", "run_settings", "log_level"}
        actual_fields = set(fields.keys())
        
        assert actual_fields == expected_fields

    def test_justcamera_field_structure(self):
        """Test JustCamera schema has expected fields."""
        fields = JustCamera.model_fields
        
        expected_fields = {"schema_version", "environment", "run_settings", "hardware", "log_level"}
        actual_fields = set(fields.keys())
        
        assert actual_fields == expected_fields

    def test_noepics_field_structure(self):
        """Test NoEpics schema has expected fields."""
        fields = NoEpics.model_fields
        
        expected_fields = {"schema_version", "environment", "serval", "run_settings", "hardware", "zabers", "log_level"}
        actual_fields = set(fields.keys())
        
        assert actual_fields == expected_fields

    def test_field_descriptions(self):
        """Test that optional fields have proper descriptions."""
        default_fields = Default.model_fields
        justcamera_fields = JustCamera.model_fields
        noepics_fields = NoEpics.model_fields
        
        # Check Default schema descriptions
        assert default_fields["hardware"].description == "Hardware configuration (optional)"
        assert default_fields["zabers"].description == "Zaber motor configuration (optional)"
        assert default_fields["epics_control"].description == "EPICS control settings (optional)"
        
        # Check JustCamera schema descriptions
        assert justcamera_fields["hardware"].description == "Hardware configuration (optional)"
        
        # Check NoEpics schema descriptions
        assert noepics_fields["hardware"].description == "Hardware configuration (optional)"
        assert noepics_fields["zabers"].description == "Zaber motor configuration (optional)"

    def test_schema_docstrings(self):
        """Test that all schema classes have proper docstrings."""
        assert Default.__doc__ is not None
        assert "Default acquisition schema" in Default.__doc__
        
        assert JustServal.__doc__ is not None
        assert "SERVAL-only acquisition schema" in JustServal.__doc__
        
        assert JustCamera.__doc__ is not None
        assert "Camera-only acquisition schema" in JustCamera.__doc__
        
        assert NoEpics.__doc__ is not None
        assert "Complete acquisition schema without EPICS" in NoEpics.__doc__

    def test_field_optionality(self):
        """Test which fields are optional in each schema."""
        default_fields = Default.model_fields
        justcamera_fields = JustCamera.model_fields
        noepics_fields = NoEpics.model_fields
        
        # Default schema optional fields
        assert default_fields["hardware"].default is None
        assert default_fields["zabers"].default is None
        assert default_fields["epics_control"].default is None
        
        # JustCamera schema optional fields
        assert justcamera_fields["hardware"].default is None
        
        # NoEpics schema optional fields  
        assert noepics_fields["hardware"].default is None
        assert noepics_fields["zabers"].default is None

    def test_default_values(self):
        """Test default values for log_level field."""
        default_fields = Default.model_fields
        justserval_fields = JustServal.model_fields
        justcamera_fields = JustCamera.model_fields
        noepics_fields = NoEpics.model_fields
        
        # All schemas should have "INFO" as default log level
        assert default_fields["log_level"].default == "INFO"
        assert justserval_fields["log_level"].default == "INFO"
        assert justcamera_fields["log_level"].default == "INFO"
        assert noepics_fields["log_level"].default == "INFO"


class TestSchemaValidation:
    """Test schema validation behavior."""

    @pytest.mark.parametrize("schema_class", [Default, JustServal, JustCamera, NoEpics])
    def test_invalid_log_level_types(self, schema_class):
        """Test that all schemas reject invalid log_level types."""
        # Test with completely mocked dependencies
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'), \
             patch('hermes.acquisition.models.schema.EPICSConfig'), \
             patch('hermes.acquisition.models.schema.HardwareConfig'), \
             patch('hermes.acquisition.models.schema.ZaberConfig'):
            
            with pytest.raises(ValidationError):
                schema_class(log_level=123)
                
            with pytest.raises(ValidationError):
                schema_class(log_level={"level": "INFO"})
                
            with pytest.raises(ValidationError):
                schema_class(log_level=["INFO"])

    def test_schema_field_combinations(self):
        """Test unique field combinations for each schema."""
        default_fields = set(Default.model_fields.keys())
        justserval_fields = set(JustServal.model_fields.keys())
        justcamera_fields = set(JustCamera.model_fields.keys())
        noepics_fields = set(NoEpics.model_fields.keys())
        
        # Common fields that should exist in all schemas
        common_fields = {"schema_version", "environment", "log_level"}
        
        assert common_fields.issubset(default_fields)
        assert common_fields.issubset(justserval_fields)
        assert common_fields.issubset(justcamera_fields)
        assert common_fields.issubset(noepics_fields)
        
        # Default should have all possible fields
        assert "epics_control" in default_fields
        assert "zabers" in default_fields
        assert "hardware" in default_fields
        assert "serval" in default_fields
        assert "run_settings" in default_fields
        
        # JustServal should have serval but not hardware fields
        assert "serval" in justserval_fields
        assert "run_settings" in justserval_fields
        assert "hardware" not in justserval_fields
        assert "zabers" not in justserval_fields
        assert "epics_control" not in justserval_fields
        
        # JustCamera should have hardware but not serval
        assert "hardware" in justcamera_fields
        assert "run_settings" in justcamera_fields
        assert "serval" not in justcamera_fields
        assert "zabers" not in justcamera_fields
        assert "epics_control" not in justcamera_fields
        
        # NoEpics should have everything except epics_control
        assert "serval" in noepics_fields
        assert "run_settings" in noepics_fields
        assert "hardware" in noepics_fields
        assert "zabers" in noepics_fields
        assert "epics_control" not in noepics_fields

    @pytest.mark.parametrize("schema_class,expected_optional_fields", [
        (Default, ["hardware", "zabers", "epics_control"]),
        (JustServal, []),
        (JustCamera, ["hardware"]),
        (NoEpics, ["hardware", "zabers"]),
    ])
    def test_optional_fields_parameterized(self, schema_class, expected_optional_fields):
        """Test optional fields for each schema using parameterized testing."""
        fields = schema_class.model_fields
        
        for field_name in expected_optional_fields:
            assert field_name in fields
            assert fields[field_name].default is None


class TestSchemaFunctionality:
    """Test basic schema functionality that doesn't require real instantiation."""

    def test_model_fields_access(self):
        """Test accessing model fields for all schemas."""
        # These should work without instantiation
        assert hasattr(Default, 'model_fields')
        assert hasattr(JustServal, 'model_fields')
        assert hasattr(JustCamera, 'model_fields')
        assert hasattr(NoEpics, 'model_fields')
        
        # All should return dictionaries
        assert isinstance(Default.model_fields, dict)
        assert isinstance(JustServal.model_fields, dict)
        assert isinstance(JustCamera.model_fields, dict)
        assert isinstance(NoEpics.model_fields, dict)

    def test_field_types(self):
        """Test field type annotations."""
        from typing import get_type_hints, get_origin, get_args
        from hermes.acquisition.models.software.environment import WorkingDir
        from hermes.acquisition.models.software.serval import ServalConfig
        from hermes.acquisition.models.software.parameters import RunSettings
        from hermes.acquisition.models.software.epics import EPICSConfig
        from hermes.acquisition.models.hardware.tpx3Cam import HardwareConfig
        from hermes.acquisition.models.hardware.zabers import ZaberConfig
        
        # Test Default schema type hints
        default_hints = get_type_hints(Default)
        assert default_hints['environment'] == WorkingDir
        assert default_hints['serval'] == ServalConfig
        assert default_hints['run_settings'] == RunSettings
        assert default_hints['log_level'] == str
        
        # Test optional types - check that they contain the expected types
        hardware_args = get_args(default_hints['hardware'])
        assert HardwareConfig in hardware_args
        assert type(None) in hardware_args
        
        # Test JustServal schema type hints
        justserval_hints = get_type_hints(JustServal)
        assert justserval_hints['environment'] == WorkingDir
        assert justserval_hints['serval'] == ServalConfig
        assert justserval_hints['run_settings'] == RunSettings
        assert justserval_hints['log_level'] == str
        
        # Test JustCamera schema type hints
        justcamera_hints = get_type_hints(JustCamera)
        assert justcamera_hints['environment'] == WorkingDir
        assert justcamera_hints['run_settings'] == RunSettings
        assert justcamera_hints['log_level'] == str
        
        # Test NoEpics schema type hints
        noepics_hints = get_type_hints(NoEpics)
        assert noepics_hints['environment'] == WorkingDir
        assert noepics_hints['serval'] == ServalConfig
        assert noepics_hints['run_settings'] == RunSettings
        assert noepics_hints['log_level'] == str


class TestSchemaIntegration:
    """Integration tests that test minimal functionality."""

    def test_schema_model_validation_signatures(self):
        """Test that model_validate method exists on all schemas."""
        # These methods should exist without instantiation
        assert hasattr(Default, 'model_validate')
        assert hasattr(JustServal, 'model_validate')
        assert hasattr(JustCamera, 'model_validate')
        assert hasattr(NoEpics, 'model_validate')
        
        # They should be callable
        assert callable(Default.model_validate)
        assert callable(JustServal.model_validate)
        assert callable(JustCamera.model_validate)
        assert callable(NoEpics.model_validate)

    def test_schema_model_dump_signatures(self):
        """Test that model instances would have model_dump method."""
        # Check that the classes have the expected pydantic methods
        assert 'model_dump' in dir(Default)
        assert 'model_dump' in dir(JustServal)
        assert 'model_dump' in dir(JustCamera)
        assert 'model_dump' in dir(NoEpics)

    def test_pydantic_field_info(self):
        """Test pydantic field info structure."""
        from pydantic.fields import FieldInfo
        
        # Check that fields are properly configured FieldInfo objects
        default_fields = Default.model_fields
        for field_name, field_info in default_fields.items():
            assert isinstance(field_info, FieldInfo)
            
        # Check specific field configurations
        assert default_fields['hardware'].description == "Hardware configuration (optional)"
        assert default_fields['zabers'].description == "Zaber motor configuration (optional)"
        assert default_fields['epics_control'].description == "EPICS control settings (optional)"


class TestSchemaVersioning:
    """Test schema versioning functionality and validation."""

    def test_current_schema_version_constant(self):
        """Test that CURRENT_SCHEMA_VERSION is properly defined."""
        assert CURRENT_SCHEMA_VERSION == "1.0.0"
        assert isinstance(CURRENT_SCHEMA_VERSION, str)

    def test_get_current_schema_version(self):
        """Test get_current_schema_version utility function."""
        version = get_current_schema_version()
        assert version == "1.0.0"
        assert version == CURRENT_SCHEMA_VERSION

    @pytest.mark.parametrize("schema_class", [Default, JustServal, JustCamera, NoEpics])
    def test_schema_version_field_exists(self, schema_class):
        """Test that all schemas have schema_version field."""
        fields = schema_class.model_fields
        assert "schema_version" in fields
        
        # Test default value
        field_info = fields["schema_version"]
        assert field_info.default == CURRENT_SCHEMA_VERSION

    @pytest.mark.parametrize("schema_class", [Default, JustServal, JustCamera, NoEpics])
    def test_schema_version_field_description(self, schema_class):
        """Test that schema_version field has proper description."""
        fields = schema_class.model_fields
        field_info = fields["schema_version"]
        assert "Schema version" in field_info.description
        assert "backward compatibility" in field_info.description

    @pytest.mark.parametrize("schema_class", [Default, JustServal, JustCamera, NoEpics])
    @pytest.mark.parametrize("valid_version", [
        "1.0.0",        # Current version - should work
    ])
    def test_valid_schema_versions(self, schema_class, valid_version):
        """Test that valid semantic versions are accepted."""
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'), \
             patch('hermes.acquisition.models.schema.EPICSConfig'), \
             patch('hermes.acquisition.models.schema.HardwareConfig'), \
             patch('hermes.acquisition.models.schema.ZaberConfig'):
            
            # This should not raise an exception
            instance = schema_class(schema_version=valid_version)
            assert instance.schema_version == valid_version

    @pytest.mark.parametrize("schema_class", [Default, JustServal, JustCamera, NoEpics])
    @pytest.mark.parametrize("invalid_version", [
        "1.0",          # Missing patch version
        "v1.0.0",       # Has 'v' prefix
        "1.0.0-beta",   # Has pre-release suffix
        "1.0.0.0",      # Too many version parts
        "1",            # Only major version
        "invalid",      # Not a version at all
        "",             # Empty string
        "1.0.a",        # Non-numeric patch
    ])
    def test_invalid_schema_version_format(self, schema_class, invalid_version):
        """Test that invalid version formats are rejected."""
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'), \
             patch('hermes.acquisition.models.schema.EPICSConfig'), \
             patch('hermes.acquisition.models.schema.HardwareConfig'), \
             patch('hermes.acquisition.models.schema.ZaberConfig'):
            
            with pytest.raises(ValidationError) as exc_info:
                schema_class(schema_version=invalid_version)
            
            error_msg = str(exc_info.value)
            assert "Schema version must follow semantic versioning" in error_msg

    @pytest.mark.parametrize("schema_class", [Default, JustServal, JustCamera, NoEpics])
    @pytest.mark.parametrize("future_version", [
        "2.0.0",    # Next major version
        "1.1.0",    # Next minor version (currently we're on 1.0.0)
        "1.0.1",    # Next patch version (currently we're on 1.0.0)
        "10.5.3",   # Far future version
    ])
    def test_future_schema_versions_rejected(self, schema_class, future_version):
        """Test that future schema versions are rejected."""
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'), \
             patch('hermes.acquisition.models.schema.EPICSConfig'), \
             patch('hermes.acquisition.models.schema.HardwareConfig'), \
             patch('hermes.acquisition.models.schema.ZaberConfig'):
            
            with pytest.raises(ValidationError) as exc_info:
                schema_class(schema_version=future_version)
            
            error_msg = str(exc_info.value)
            assert "newer than supported version" in error_msg

    @pytest.mark.parametrize("schema_class", [Default, JustServal, JustCamera, NoEpics])
    @pytest.mark.parametrize("old_version", [
        "0.1.0",
        "0.9.9",
        "0.0.1",
    ])
    def test_unsupported_old_versions_rejected(self, schema_class, old_version):
        """Test that unsupported old versions (< 1.0.0) are rejected."""
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'), \
             patch('hermes.acquisition.models.schema.EPICSConfig'), \
             patch('hermes.acquisition.models.schema.HardwareConfig'), \
             patch('hermes.acquisition.models.schema.ZaberConfig'):
            
            with pytest.raises(ValidationError) as exc_info:
                schema_class(schema_version=old_version)
            
            error_msg = str(exc_info.value)
            assert "too old and no longer supported" in error_msg

    def test_default_schema_version_on_instantiation(self):
        """Test that schemas get current version by default."""
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'):
            
            # Test Default schema
            default_instance = Default()
            assert default_instance.schema_version == CURRENT_SCHEMA_VERSION
            
            # Test JustServal schema
            serval_instance = JustServal()
            assert serval_instance.schema_version == CURRENT_SCHEMA_VERSION


class TestSchemaVersioningUtilities:
    """Test schema versioning utility functions."""

    @pytest.mark.parametrize("version,expected", [
        ("1.0.0", True),   # Current version
        ("1.0.1", True),   # Same major.minor, newer patch (utility is more permissive)
        ("1.1.0", True),   # Same major, newer minor (utility is more permissive)
        ("1.2.3", True),   # Same major, much newer minor.patch (utility is more permissive)
        ("2.0.0", False),  # Newer major version
        ("0.9.9", False),  # Older major (version 0.x.x not supported)
        ("0.1.0", False),  # Older major (version 0.x.x not supported)
        ("10.0.0", False), # Much newer major
    ])
    def test_is_schema_compatible(self, version, expected):
        """Test is_schema_compatible function with various versions."""
        result = is_schema_compatible(version)
        assert result == expected

    @pytest.mark.parametrize("invalid_version", [
        "1.0",
        "v1.0.0", 
        "invalid",
        "",
        "1.0.0.0",
    ])
    def test_is_schema_compatible_invalid_formats(self, invalid_version):
        """Test is_schema_compatible with invalid version formats."""
        result = is_schema_compatible(invalid_version)
        assert result is False

    @pytest.mark.parametrize("version,expected", [
        ("1.0.0", False),  # Same version, no migration needed
        ("1.0.0", False),  # Identical to current
        ("0.9.9", False),  # Incompatible version, can't migrate
        ("2.0.0", False),  # Future version, can't migrate
        ("invalid", False), # Invalid format, can't migrate
    ])
    def test_needs_migration(self, version, expected):
        """Test needs_migration function."""
        result = needs_migration(version)
        assert result == expected

    def test_needs_migration_with_mock_future_version(self):
        """Test needs_migration when current version is higher."""
        # This test simulates what would happen if CURRENT_SCHEMA_VERSION was "1.1.0"
        with patch('hermes.acquisition.models.schema.CURRENT_SCHEMA_VERSION', "1.1.0"):
            # Older patch version should need migration
            assert needs_migration("1.0.0") is True
            assert needs_migration("1.0.5") is True
            # Same version should not need migration
            assert needs_migration("1.1.0") is False
            # Future versions should not need migration (incompatible)
            assert needs_migration("1.2.0") is False
            assert needs_migration("2.0.0") is False

    def test_schema_version_validation_error_messages(self):
        """Test that validation error messages are informative."""
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'):
            
            # Test format error
            with pytest.raises(ValidationError) as exc_info:
                Default(schema_version="invalid")
            assert "semantic versioning" in str(exc_info.value)
            
            # Test future version error
            with pytest.raises(ValidationError) as exc_info:
                Default(schema_version="2.0.0")
            assert "newer than supported" in str(exc_info.value)
            
            # Test old version error
            with pytest.raises(ValidationError) as exc_info:
                Default(schema_version="0.1.0")
            assert "too old" in str(exc_info.value)

    def test_schema_version_field_validator_reuse(self):
        """Test that all schemas use the same validation logic."""
        # Verify that all schemas reference the same validator function
        default_validator = Default.model_fields['schema_version'].metadata
        justserval_validator = JustServal.model_fields['schema_version'].metadata  
        justcamera_validator = JustCamera.model_fields['schema_version'].metadata
        noepics_validator = NoEpics.model_fields['schema_version'].metadata
        
        # All should have the same metadata structure (indicating same validation)
        assert isinstance(default_validator, list)
        assert isinstance(justserval_validator, list)
        assert isinstance(justcamera_validator, list)
        assert isinstance(noepics_validator, list)


class TestSchemaVersioningIntegration:
    """Integration tests for schema versioning with realistic scenarios."""

    def test_schema_version_in_model_dump(self):
        """Test that schema_version appears in model serialization."""
        with patch('hermes.acquisition.models.schema.WorkingDir') as mock_workingdir, \
             patch('hermes.acquisition.models.schema.ServalConfig') as mock_serval, \
             patch('hermes.acquisition.models.schema.RunSettings') as mock_run:
            
            # Configure mocks to return valid instances
            mock_workingdir.return_value = MagicMock()
            mock_serval.return_value = MagicMock()
            mock_run.return_value = MagicMock()
            
            instance = Default()
            model_dict = instance.model_dump()
            
            assert "schema_version" in model_dict
            assert model_dict["schema_version"] == CURRENT_SCHEMA_VERSION

    def test_schema_version_in_model_validate(self):
        """Test that schema_version is validated during model_validate."""
        valid_data = {
            "schema_version": "1.0.0",
            "log_level": "INFO"
        }
        
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'):
            
            # Should work with valid version
            instance = Default.model_validate(valid_data)
            assert instance.schema_version == "1.0.0"
            
            # Should fail with invalid version
            invalid_data = valid_data.copy()
            invalid_data["schema_version"] = "invalid"
            
            with pytest.raises(ValidationError):
                Default.model_validate(invalid_data)

    def test_configuration_migration_scenario(self):
        """Test a realistic configuration migration scenario."""
        # Simulate loading an older configuration
        older_config_data = {
            "schema_version": "1.0.0",
            "log_level": "DEBUG",
            # ... other fields would be here in real scenario
        }
        
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'):
            
            # Should successfully load
            config = Default.model_validate(older_config_data)
            assert config.schema_version == "1.0.0"
            
            # Check if migration is needed (currently false since we're on 1.0.0)
            assert needs_migration(config.schema_version) is False
            
            # Verify compatibility
            assert is_schema_compatible(config.schema_version) is True

    @pytest.mark.parametrize("schema_class", [Default, JustServal, JustCamera, NoEpics])
    def test_schema_version_consistency_across_schemas(self, schema_class):
        """Test that all schemas use consistent versioning."""
        with patch('hermes.acquisition.models.schema.WorkingDir'), \
             patch('hermes.acquisition.models.schema.ServalConfig'), \
             patch('hermes.acquisition.models.schema.RunSettings'), \
             patch('hermes.acquisition.models.schema.EPICSConfig'), \
             patch('hermes.acquisition.models.schema.HardwareConfig'), \
             patch('hermes.acquisition.models.schema.ZaberConfig'):
            
            instance = schema_class()
            assert instance.schema_version == CURRENT_SCHEMA_VERSION
            
            # Test that all schemas reject the same invalid versions
            with pytest.raises(ValidationError):
                schema_class(schema_version="invalid")
                
            with pytest.raises(ValidationError):
                schema_class(schema_version="0.1.0")
                
            with pytest.raises(ValidationError):
                schema_class(schema_version="2.0.0")