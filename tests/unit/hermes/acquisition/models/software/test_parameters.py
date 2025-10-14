"""
Tests for the RunSettings pydantic model.

This module contains comprehensive test cases for the RunSettings model
that defines acquisition run parameters and data recording settings.
"""

import pytest
from pydantic import ValidationError

from hermes.acquisition.models.software.parameters import RunSettings


class TestRunSettings:
    """Test cases for RunSettings pydantic model."""

    def test_default_creation(self):
        """Test creating RunSettings with all default values."""
        run_settings = RunSettings()
        
        # Check all default values
        assert run_settings.run_name == "you_forgot_to_name_the_runs"
        assert run_settings.run_number == 0
        assert run_settings.trigger_period_in_seconds == 1.0
        assert run_settings.exposure_time_in_seconds == 0.5
        assert run_settings.trigger_delay_in_seconds == 0.0
        assert run_settings.number_of_triggers == 0
        assert run_settings.number_of_runs == 0
        assert run_settings.global_timestamp_interval_in_seconds == 0.0
        assert run_settings.record_logs is True
        assert run_settings.record_tpx_data is True
        assert run_settings.record_preview is True
        assert run_settings.record_status is True

    def test_custom_creation(self):
        """Test creating RunSettings with custom values."""
        run_settings = RunSettings(
            run_name="test_measurement_001",
            run_number=5,
            trigger_period_in_seconds=2.5,
            exposure_time_in_seconds=1.2,
            trigger_delay_in_seconds=0.1,
            number_of_triggers=100,
            number_of_runs=3,
            global_timestamp_interval_in_seconds=0.05,
            record_logs=False,
            record_tpx_data=True,
            record_preview=False,
            record_status=True
        )
        
        assert run_settings.run_name == "test_measurement_001"
        assert run_settings.run_number == 5
        assert run_settings.trigger_period_in_seconds == 2.5
        assert run_settings.exposure_time_in_seconds == 1.2
        assert run_settings.trigger_delay_in_seconds == 0.1
        assert run_settings.number_of_triggers == 100
        assert run_settings.number_of_runs == 3
        assert run_settings.global_timestamp_interval_in_seconds == 0.05
        assert run_settings.record_logs is False
        assert run_settings.record_tpx_data is True
        assert run_settings.record_preview is False
        assert run_settings.record_status is True

    def test_partial_creation(self):
        """Test creating RunSettings with only some custom values."""
        run_settings = RunSettings(
            run_name="partial_test",
            exposure_time_in_seconds=0.8,
            number_of_triggers=50
        )
        
        # Custom values
        assert run_settings.run_name == "partial_test"
        assert run_settings.exposure_time_in_seconds == 0.8
        assert run_settings.number_of_triggers == 50
        
        # Default values for unspecified fields
        assert run_settings.run_number == 0
        assert run_settings.trigger_period_in_seconds == 1.0
        assert run_settings.trigger_delay_in_seconds == 0.0
        assert run_settings.number_of_runs == 0
        assert run_settings.global_timestamp_interval_in_seconds == 0.0
        assert run_settings.record_logs is True
        assert run_settings.record_tpx_data is True
        assert run_settings.record_preview is True
        assert run_settings.record_status is True

    def test_string_fields_validation(self):
        """Test validation of string fields."""
        # Valid string
        run_settings = RunSettings(run_name="valid_run_name_123")
        assert run_settings.run_name == "valid_run_name_123"
        
        # Empty string should be allowed
        run_settings = RunSettings(run_name="")
        assert run_settings.run_name == ""
        
        # String representation of numbers
        run_settings = RunSettings(run_name="12345")
        assert run_settings.run_name == "12345"

    def test_integer_fields_validation(self):
        """Test validation of integer fields."""
        # Valid integers
        run_settings = RunSettings(
            run_number=10,
            number_of_triggers=1000,
            number_of_runs=5
        )
        assert run_settings.run_number == 10
        assert run_settings.number_of_triggers == 1000
        assert run_settings.number_of_runs == 5
        
        # Integer from float without fractional part
        run_settings = RunSettings(run_number=10.0)
        assert run_settings.run_number == 10
        
        # Negative values should be allowed (could be meaningful in some contexts)
        run_settings = RunSettings(run_number=-1)
        assert run_settings.run_number == -1
        
        # Test that floats with fractional parts are rejected
        with pytest.raises(ValidationError):
            RunSettings(run_number=10.7)

    def test_float_fields_validation(self):
        """Test validation of float fields."""
        # Valid floats
        run_settings = RunSettings(
            trigger_period_in_seconds=2.5,
            exposure_time_in_seconds=0.001,
            trigger_delay_in_seconds=0.1,
            global_timestamp_interval_in_seconds=0.05
        )
        assert run_settings.trigger_period_in_seconds == 2.5
        assert run_settings.exposure_time_in_seconds == 0.001
        assert run_settings.trigger_delay_in_seconds == 0.1
        assert run_settings.global_timestamp_interval_in_seconds == 0.05
        
        # Integers converted to float
        run_settings = RunSettings(trigger_period_in_seconds=2)
        assert run_settings.trigger_period_in_seconds == 2.0
        
        # Zero values
        run_settings = RunSettings(
            trigger_period_in_seconds=0.0,
            exposure_time_in_seconds=0.0
        )
        assert run_settings.trigger_period_in_seconds == 0.0
        assert run_settings.exposure_time_in_seconds == 0.0
        
        # Very small values
        run_settings = RunSettings(exposure_time_in_seconds=1e-6)
        assert run_settings.exposure_time_in_seconds == 1e-6

    def test_boolean_fields_validation(self):
        """Test validation of boolean fields."""
        # Explicit boolean values
        run_settings = RunSettings(
            record_logs=True,
            record_tpx_data=False,
            record_preview=True,
            record_status=False
        )
        assert run_settings.record_logs is True
        assert run_settings.record_tpx_data is False
        assert run_settings.record_preview is True
        assert run_settings.record_status is False
        
        # Some truthy/falsy values that Pydantic v2 accepts
        run_settings = RunSettings(
            record_logs=1,
            record_tpx_data=0,
            record_preview="true",
            record_status="false"
        )
        assert run_settings.record_logs is True
        assert run_settings.record_tpx_data is False
        assert run_settings.record_preview is True
        assert run_settings.record_status is False
        
        # Test some values that should be rejected
        with pytest.raises(ValidationError):
            RunSettings(record_logs="")  # Empty string not valid boolean

    def test_invalid_type_validation(self):
        """Test that invalid types raise ValidationError."""
        # Invalid string conversion
        with pytest.raises(ValidationError):
            RunSettings(run_name=None)
        
        # Invalid number types that can't be converted
        with pytest.raises(ValidationError):
            RunSettings(run_number="not_a_number")
        
        with pytest.raises(ValidationError):
            RunSettings(trigger_period_in_seconds="invalid_float")
        
        # Complex objects that can't be converted to boolean
        with pytest.raises(ValidationError):
            RunSettings(record_logs=object())

    def test_serialization(self):
        """Test model serialization to dict and JSON."""
        run_settings = RunSettings(
            run_name="test_run",
            run_number=1,
            trigger_period_in_seconds=1.5,
            exposure_time_in_seconds=0.8,
            number_of_triggers=50,
            record_logs=False
        )
        
        # Test dict serialization
        data_dict = run_settings.model_dump()
        expected_dict = {
            'run_name': 'test_run',
            'run_number': 1,
            'trigger_period_in_seconds': 1.5,
            'exposure_time_in_seconds': 0.8,
            'trigger_delay_in_seconds': 0.0,  # default
            'number_of_triggers': 50,
            'number_of_runs': 0,  # default
            'global_timestamp_interval_in_seconds': 0.0,  # default
            'record_logs': False,
            'record_tpx_data': True,  # default
            'record_preview': True,  # default
            'record_status': True  # default
        }
        assert data_dict == expected_dict
        
        # Test JSON serialization
        json_str = run_settings.model_dump_json()
        assert isinstance(json_str, str)
        assert '"run_name":"test_run"' in json_str
        assert '"record_logs":false' in json_str

    def test_deserialization(self):
        """Test model creation from dict and JSON."""
        # Test from dict
        data_dict = {
            'run_name': 'deserialization_test',
            'run_number': 42,
            'exposure_time_in_seconds': 2.0,
            'number_of_triggers': 75,
            'record_tpx_data': False
        }
        
        run_settings = RunSettings(**data_dict)
        assert run_settings.run_name == 'deserialization_test'
        assert run_settings.run_number == 42
        assert run_settings.exposure_time_in_seconds == 2.0
        assert run_settings.number_of_triggers == 75
        assert run_settings.record_tpx_data is False
        # Check that defaults are applied for missing fields
        assert run_settings.trigger_period_in_seconds == 1.0

    def test_model_validation_comprehensive(self):
        """Test comprehensive model validation with edge cases."""
        # Very large numbers
        run_settings = RunSettings(
            run_number=999999,
            number_of_triggers=1000000,
            trigger_period_in_seconds=3600.0  # 1 hour
        )
        assert run_settings.run_number == 999999
        assert run_settings.number_of_triggers == 1000000
        assert run_settings.trigger_period_in_seconds == 3600.0
        
        # Very small positive numbers
        run_settings = RunSettings(
            exposure_time_in_seconds=1e-9,
            trigger_delay_in_seconds=1e-12
        )
        assert run_settings.exposure_time_in_seconds == 1e-9
        assert run_settings.trigger_delay_in_seconds == 1e-12

    def test_field_assignment_after_creation(self):
        """Test that fields can be modified after model creation."""
        run_settings = RunSettings()
        
        # Modify fields
        run_settings.run_name = "modified_run"
        run_settings.run_number = 100
        run_settings.exposure_time_in_seconds = 5.0
        run_settings.record_logs = False
        
        # Verify changes
        assert run_settings.run_name == "modified_run"
        assert run_settings.run_number == 100
        assert run_settings.exposure_time_in_seconds == 5.0
        assert run_settings.record_logs is False

    def test_model_equality(self):
        """Test model equality comparison."""
        run_settings1 = RunSettings(
            run_name="test",
            run_number=1,
            exposure_time_in_seconds=1.0
        )
        
        run_settings2 = RunSettings(
            run_name="test",
            run_number=1,
            exposure_time_in_seconds=1.0
        )
        
        run_settings3 = RunSettings(
            run_name="different",
            run_number=1,
            exposure_time_in_seconds=1.0
        )
        
        # Same values should be equal
        assert run_settings1 == run_settings2
        
        # Different values should not be equal
        assert run_settings1 != run_settings3

    def test_realistic_acquisition_scenarios(self):
        """Test realistic acquisition parameter scenarios."""
        # Fast acquisition scenario
        fast_acquisition = RunSettings(
            run_name="fast_neutron_imaging",
            run_number=1,
            trigger_period_in_seconds=0.1,  # 10 Hz
            exposure_time_in_seconds=0.05,  # 50ms exposure
            number_of_triggers=1000,
            number_of_runs=1,
            record_tpx_data=True,
            record_preview=True
        )
        
        assert fast_acquisition.trigger_period_in_seconds == 0.1
        assert fast_acquisition.exposure_time_in_seconds == 0.05
        assert fast_acquisition.number_of_triggers == 1000
        
        # Long exposure scenario
        long_exposure = RunSettings(
            run_name="long_exposure_crystallography",
            run_number=1,
            trigger_period_in_seconds=300.0,  # 5 minutes between triggers
            exposure_time_in_seconds=250.0,   # 4+ minute exposure
            trigger_delay_in_seconds=10.0,    # 10 second delay
            number_of_triggers=50,
            number_of_runs=3,
            global_timestamp_interval_in_seconds=1.0,
            record_logs=True,
            record_tpx_data=True,
            record_preview=False,  # Might skip preview for long exposures
            record_status=True
        )
        
        assert long_exposure.trigger_period_in_seconds == 300.0
        assert long_exposure.exposure_time_in_seconds == 250.0
        assert long_exposure.trigger_delay_in_seconds == 10.0
        assert long_exposure.number_of_triggers == 50
        assert long_exposure.number_of_runs == 3
        assert long_exposure.record_preview is False

    def test_data_recording_combinations(self):
        """Test various combinations of data recording flags."""
        # Record everything
        record_all = RunSettings(
            record_logs=True,
            record_tpx_data=True,
            record_preview=True,
            record_status=True
        )
        assert all([
            record_all.record_logs,
            record_all.record_tpx_data,
            record_all.record_preview,
            record_all.record_status
        ])
        
        # Record nothing (testing scenario)
        record_nothing = RunSettings(
            record_logs=False,
            record_tpx_data=False,
            record_preview=False,
            record_status=False
        )
        assert not any([
            record_nothing.record_logs,
            record_nothing.record_tpx_data,
            record_nothing.record_preview,
            record_nothing.record_status
        ])
        
        # Record only essential data
        record_essential = RunSettings(
            record_logs=True,
            record_tpx_data=True,
            record_preview=False,
            record_status=True
        )
        assert record_essential.record_logs
        assert record_essential.record_tpx_data
        assert not record_essential.record_preview
        assert record_essential.record_status