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
    NoEpics
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
            "environment", "serval", "run_settings", 
            "hardware", "zabers", "epics_control", "log_level"
        }
        actual_fields = set(fields.keys())
        
        assert actual_fields == expected_fields

    def test_justserval_field_structure(self):
        """Test JustServal schema has expected fields."""
        fields = JustServal.model_fields
        
        expected_fields = {"environment", "serval", "run_settings", "log_level"}
        actual_fields = set(fields.keys())
        
        assert actual_fields == expected_fields

    def test_justcamera_field_structure(self):
        """Test JustCamera schema has expected fields."""
        fields = JustCamera.model_fields
        
        expected_fields = {"environment", "run_settings", "hardware", "log_level"}
        actual_fields = set(fields.keys())
        
        assert actual_fields == expected_fields

    def test_noepics_field_structure(self):
        """Test NoEpics schema has expected fields."""
        fields = NoEpics.model_fields
        
        expected_fields = {"environment", "serval", "run_settings", "hardware", "zabers", "log_level"}
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
        assert "Only serval acquisition schema" in JustServal.__doc__
        
        assert JustCamera.__doc__ is not None
        assert "Only camera acquisition schema" in JustCamera.__doc__
        
        assert NoEpics.__doc__ is not None
        assert "Acquisition schema combining all software and hardware configurations except EPICS" in NoEpics.__doc__

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
        common_fields = {"environment", "log_level"}
        
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