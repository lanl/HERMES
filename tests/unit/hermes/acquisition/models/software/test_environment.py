"""
Tests for the WorkingDir pydantic model.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from pydantic import ValidationError
from unittest.mock import patch, MagicMock
import os

from hermes.acquisition.models.software.environment import WorkingDir


@pytest.fixture
def temp_working_dir():
    """
    Fixture that creates a temporary working directory for testing.
    
    Returns:
        str: Path to the temporary working directory
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir


@pytest.fixture
def mock_logger():
    """
    Fixture that mocks the logger to avoid log output during tests.
    """
    with patch('hermes.acquisition.models.software.environment.logger') as mock_log:
        yield mock_log


@pytest.fixture
def mock_user_input():
    """
    Fixture that mocks user input for interactive prompts.
    """
    with patch('builtins.input') as mock_input:
        yield mock_input


class TestWorkingDir:
    """Test cases for WorkingDir pydantic model."""

    def test_default_values(self, temp_working_dir, mock_logger):
        """Test that default values are set correctly."""
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            create_if_missing=False  # Disable directory creation for this test
        )
        
        assert working_dir.path_to_working_dir == str(Path(temp_working_dir).resolve())
        assert working_dir.run_dir_name == "dummy_run/"  # Default keeps trailing slash from default value
        assert working_dir.path_to_status_files == "statusFiles/"  # Default keeps trailing slash from default value
        assert working_dir.path_to_log_files == "logFiles/"  # Default keeps trailing slash from default value
        assert working_dir.path_to_image_files == "imageFiles/"  # Default keeps trailing slash from default value
        assert working_dir.path_to_preview_files == "previewFiles/"  # Default keeps trailing slash from default value
        assert working_dir.path_to_tpx3_files == "tpx3Files/"  # Default keeps trailing slash from default value
        assert working_dir.path_to_init_files == "initFiles/"  # Default keeps trailing slash from default value
        assert working_dir.create_if_missing == False  # We set this explicitly
        assert working_dir.clean_if_exists == False

    def test_custom_values(self, temp_working_dir, mock_logger):
        """Test creating WorkingDir with custom values."""
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name="custom_run",
            path_to_status_files="custom_status/",
            path_to_log_files="custom_logs/",
            create_if_missing=False,
            clean_if_exists=True
        )
        
        assert working_dir.run_dir_name == "custom_run"
        assert working_dir.path_to_status_files == "custom_status"  # Normalized (no trailing slash)
        assert working_dir.path_to_log_files == "custom_logs"  # Normalized
        assert working_dir.create_if_missing == False
        assert working_dir.clean_if_exists == True

    def test_normalize_working_dir_expansion(self, mock_logger):
        """Test that working directory path is normalized and expanded."""
        # Test with relative path
        working_dir = WorkingDir(
            path_to_working_dir="./test_dir",
            create_if_missing=False
        )
        # Should be converted to absolute path
        assert Path(working_dir.path_to_working_dir).is_absolute()
        
        # Test with home directory expansion
        with patch('pathlib.Path.expanduser') as mock_expand:
            mock_expand.return_value = Path("/Users/test/expanded")
            working_dir = WorkingDir(
                path_to_working_dir="~/test_dir",
                create_if_missing=False
            )
            mock_expand.assert_called()

    def test_sanitize_run_dir_name_valid(self, temp_working_dir, mock_logger):
        """Test run directory name sanitization with valid names."""
        test_cases = [
            ("valid_run", "valid_run"),
            ("run_with_spaces ", "run_with_spaces"),
            (" leading_space", "leading_space"),
            ("trailing_slash/", "trailing_slash"),
            ("/leading_slash", "leading_slash"),
        ]
        
        for input_name, expected in test_cases:
            working_dir = WorkingDir(
                path_to_working_dir=temp_working_dir,
                run_dir_name=input_name,
                create_if_missing=False
            )
            assert working_dir.run_dir_name == expected

    def test_sanitize_run_dir_name_invalid(self, temp_working_dir, mock_logger):
        """Test run directory name sanitization with invalid names."""
        invalid_names = [None, "", "   ", "/", "///"]
        
        for invalid_name in invalid_names:
            working_dir = WorkingDir(
                path_to_working_dir=temp_working_dir,
                run_dir_name=invalid_name,
                create_if_missing=False
            )
            assert working_dir.run_dir_name == "run"

    def test_ensure_relative_path_absolute_conversion(self, temp_working_dir, mock_logger):
        """Test that absolute paths are converted to relative paths."""
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            path_to_status_files="/etc/passwd",  # Absolute path
            path_to_log_files="/var/log/",       # Another absolute path
            create_if_missing=False
        )
        
        # Should be converted to relative paths
        assert working_dir.path_to_status_files == "etc/passwd"
        assert working_dir.path_to_log_files == "var/log"

    def test_ensure_relative_path_relative_unchanged(self, temp_working_dir, mock_logger):
        """Test that relative paths remain unchanged."""
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            path_to_status_files="relative/path/",
            path_to_log_files="another_relative",
            create_if_missing=False
        )
        
        # Should remain as relative paths
        assert working_dir.path_to_status_files == "relative/path"
        assert working_dir.path_to_log_files == "another_relative"

    def test_ensure_relative_path_empty_strings(self, temp_working_dir, mock_logger):
        """Test that empty string values are handled properly."""
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            path_to_status_files="",
            create_if_missing=False
        )
        
        # Empty string gets converted to "." by pathlib
        assert working_dir.path_to_status_files == "."

    def test_directory_creation_enabled(self, temp_working_dir, mock_logger):
        """Test directory creation when create_if_missing=True."""
        run_dir_name = "test_run"
        
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name=run_dir_name,
            create_if_missing=True
        )
        
        # Check that directories were created
        base_run_dir = Path(temp_working_dir) / run_dir_name
        assert base_run_dir.exists()
        assert (base_run_dir / "statusFiles").exists()
        assert (base_run_dir / "logFiles").exists()
        assert (base_run_dir / "imageFiles").exists()
        assert (base_run_dir / "previewFiles").exists()
        assert (base_run_dir / "tpx3Files").exists()
        assert (base_run_dir / "initFiles").exists()

    def test_directory_creation_disabled(self, temp_working_dir, mock_logger):
        """Test that directories are not created when create_if_missing=False."""
        run_dir_name = "test_run"
        
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name=run_dir_name,
            create_if_missing=False
        )
        
        # Check that directories were NOT created
        base_run_dir = Path(temp_working_dir) / run_dir_name
        assert not base_run_dir.exists()

    def test_root_directory_protection(self, mock_logger):
        """Test that operating on root directory is blocked."""
        with pytest.raises(RuntimeError) as exc_info:
            WorkingDir(
                path_to_working_dir="/",
                run_dir_name="",  # This would result in root
                create_if_missing=True
            )
        
        # The error could be either the root protection or file system error
        error_msg = str(exc_info.value)
        assert ("Refusing to operate on root directory" in error_msg or 
                "Failed to create" in error_msg)

    def test_clean_existing_directory_user_confirms_yes(self, temp_working_dir, mock_logger, mock_user_input):
        """Test cleaning existing directory when user confirms."""
        # Create existing directory with some content
        run_dir = Path(temp_working_dir) / "existing_run"
        run_dir.mkdir()
        (run_dir / "existing_file.txt").write_text("test content")
        
        # Mock user input to confirm deletion
        mock_user_input.return_value = "y"
        
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name="existing_run",
            create_if_missing=True,
            clean_if_exists=True
        )
        
        # Directory should exist (recreated) but old content should be gone
        assert run_dir.exists()
        assert not (run_dir / "existing_file.txt").exists()
        # New subdirectories should be created
        assert (run_dir / "statusFiles").exists()

    def test_clean_existing_directory_user_confirms_no(self, temp_working_dir, mock_logger, mock_user_input):
        """Test keeping existing directory when user declines."""
        # Create existing directory with some content
        run_dir = Path(temp_working_dir) / "existing_run"
        run_dir.mkdir()
        existing_file = run_dir / "existing_file.txt"
        existing_file.write_text("test content")
        
        # Mock user input to decline deletion
        mock_user_input.return_value = "n"
        
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name="existing_run",
            create_if_missing=True,
            clean_if_exists=True
        )
        
        # Directory should exist and old content should be preserved
        assert run_dir.exists()
        assert existing_file.exists()
        assert existing_file.read_text() == "test content"
        # New subdirectories should still be created
        assert (run_dir / "statusFiles").exists()

    def test_clean_existing_empty_directory(self, temp_working_dir, mock_logger):
        """Test handling of existing empty directory."""
        # Create existing empty directory
        run_dir = Path(temp_working_dir) / "empty_run"
        run_dir.mkdir()
        
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name="empty_run",
            create_if_missing=True,
            clean_if_exists=True
        )
        
        # Directory should exist and subdirectories should be created
        assert run_dir.exists()
        assert (run_dir / "statusFiles").exists()

    def test_user_input_invalid_then_valid(self, temp_working_dir, mock_logger, mock_user_input):
        """Test user input validation with invalid then valid responses."""
        # Create existing directory with content
        run_dir = Path(temp_working_dir) / "existing_run"
        run_dir.mkdir()
        (run_dir / "existing_file.txt").write_text("test content")
        
        # Mock user input: invalid responses then valid 'y'
        mock_user_input.side_effect = ["maybe", "sure", "y"]
        
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name="existing_run",
            create_if_missing=True,
            clean_if_exists=True
        )
        
        # Should eventually accept 'y' and clean directory
        assert run_dir.exists()
        assert not (run_dir / "existing_file.txt").exists()
        assert mock_user_input.call_count == 3

    def test_directory_creation_failure(self, temp_working_dir, mock_logger):
        """Test handling of directory creation failures."""
        # Create a file with the same name as the intended directory
        conflicting_file = Path(temp_working_dir) / "conflict_run"
        conflicting_file.write_text("I'm a file, not a directory!")
        
        with pytest.raises(RuntimeError) as exc_info:
            WorkingDir(
                path_to_working_dir=temp_working_dir,
                run_dir_name="conflict_run",
                create_if_missing=True
            )
        
        assert "Failed to create" in str(exc_info.value)

    def test_directory_check_permission_error(self, temp_working_dir, mock_logger, mock_user_input):
        """Test handling of permission errors when checking directory contents."""
        # Create existing directory
        run_dir = Path(temp_working_dir) / "permission_test"
        run_dir.mkdir()
        
        # Mock iterdir to raise PermissionError
        with patch.object(Path, 'iterdir', side_effect=PermissionError("Access denied")):
            # Should handle the exception gracefully
            working_dir = WorkingDir(
                path_to_working_dir=temp_working_dir,
                run_dir_name="permission_test",
                create_if_missing=True,
                clean_if_exists=True
            )
            
            # Should still complete successfully
            assert working_dir.run_dir_name == "permission_test"

    def test_complex_directory_structure(self, temp_working_dir, mock_logger):
        """Test creation of complex nested directory structure."""
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name="complex_run",
            path_to_status_files="deeply/nested/status/",
            path_to_log_files="another/deep/path/logs/",
            path_to_image_files="images/subfolder/",
            create_if_missing=True
        )
        
        base_run_dir = Path(temp_working_dir) / "complex_run"
        assert (base_run_dir / "deeply/nested/status").exists()
        assert (base_run_dir / "another/deep/path/logs").exists()
        assert (base_run_dir / "images/subfolder").exists()

    @pytest.mark.parametrize("run_dir_input,expected", [
        ("simple_run", "simple_run"),
        ("run-with-dashes", "run-with-dashes"),
        ("run_with_underscores", "run_with_underscores"),
        ("run123", "run123"),
        ("RUN_MIXED_Case", "RUN_MIXED_Case"),
    ])
    def test_run_dir_name_variations(self, temp_working_dir, mock_logger, run_dir_input, expected):
        """Test various valid run directory name formats."""
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name=run_dir_input,
            create_if_missing=False
        )
        assert working_dir.run_dir_name == expected

    def test_working_dir_none_default(self, mock_logger):
        """Test that None working directory defaults to current directory."""
        working_dir = WorkingDir(
            path_to_working_dir=None,
            create_if_missing=False
        )
        # Should default to current directory (absolute path)
        assert Path(working_dir.path_to_working_dir).is_absolute()

    def test_large_directory_content_display(self, temp_working_dir, mock_logger, mock_user_input):
        """Test display of directory contents when many files exist."""
        # Create directory with many files
        run_dir = Path(temp_working_dir) / "large_dir"
        run_dir.mkdir()
        
        # Create 10 files
        for i in range(10):
            (run_dir / f"file_{i:02d}.txt").write_text(f"content {i}")
        
        mock_user_input.return_value = "n"
        
        working_dir = WorkingDir(
            path_to_working_dir=temp_working_dir,
            run_dir_name="large_dir",
            create_if_missing=True,
            clean_if_exists=True
        )
        
        # Should handle display of many files gracefully
        assert working_dir.run_dir_name == "large_dir"
        # All original files should still exist since user said 'n'
        assert len(list(run_dir.glob("file_*.txt"))) == 10
