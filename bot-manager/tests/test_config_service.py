"""Tests for config_service module."""
import os
import tempfile
import pytest
import yaml

from services.config_service import (
    read_config,
    write_config,
    validate_config,
    ConfigError,
)


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    config_data = {
        "symbol": "BTC_JPY",
        "trade_amount": 0.001,
        "max_position": 0.01,
        "spread_threshold": 100,
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        yaml.dump(config_data, f)
        yield f.name
    os.unlink(f.name)


class TestReadConfig:
    """Tests for read_config function."""

    def test_reads_valid_yaml(self, temp_config_file):
        """Should read and parse valid YAML config file."""
        config = read_config(temp_config_file)

        assert config["symbol"] == "BTC_JPY"
        assert config["trade_amount"] == 0.001
        assert config["max_position"] == 0.01

    def test_raises_error_for_missing_file(self):
        """Should raise ConfigError when file doesn't exist."""
        with pytest.raises(ConfigError) as exc_info:
            read_config("/nonexistent/path/config.yaml")

        assert "not found" in str(exc_info.value).lower()

    def test_raises_error_for_invalid_yaml(self):
        """Should raise ConfigError for invalid YAML syntax."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("invalid: yaml: syntax: [")
            f.flush()

            with pytest.raises(ConfigError) as exc_info:
                read_config(f.name)

            assert "parse" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()

            os.unlink(f.name)


class TestWriteConfig:
    """Tests for write_config function."""

    def test_writes_valid_config(self, temp_config_file):
        """Should write config to file successfully."""
        new_config = {
            "symbol": "ETH_JPY",
            "trade_amount": 0.01,
            "max_position": 0.1,
            "spread_threshold": 50,
        }

        result = write_config(temp_config_file, new_config)

        assert result is True

        # Verify written content
        with open(temp_config_file, "r") as f:
            saved_config = yaml.safe_load(f)

        assert saved_config["symbol"] == "ETH_JPY"
        assert saved_config["trade_amount"] == 0.01

    def test_creates_backup_before_write(self, temp_config_file):
        """Should create backup file before writing."""
        new_config = {"symbol": "ETH_JPY", "trade_amount": 0.01}

        write_config(temp_config_file, new_config)

        backup_path = temp_config_file + ".bak"
        assert os.path.exists(backup_path)

        # Cleanup backup
        os.unlink(backup_path)

    def test_raises_error_for_invalid_path(self):
        """Should raise ConfigError for invalid file path."""
        with pytest.raises(ConfigError):
            write_config("/nonexistent/dir/config.yaml", {"test": "data"})


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_valid_config_returns_true(self):
        """Should return (True, '') for valid config."""
        config = {
            "symbol": "BTC_JPY",
            "trade_amount": 0.001,
            "max_position": 0.01,
        }

        is_valid, error = validate_config(config)

        assert is_valid is True
        assert error == ""

    def test_missing_required_field_returns_false(self):
        """Should return (False, error_message) for missing required field."""
        config = {
            "trade_amount": 0.001,
            # missing "symbol"
        }

        is_valid, error = validate_config(config)

        assert is_valid is False
        assert "symbol" in error.lower()

    def test_negative_trade_amount_returns_false(self):
        """Should return (False, error_message) for negative trade_amount."""
        config = {
            "symbol": "BTC_JPY",
            "trade_amount": -0.001,
        }

        is_valid, error = validate_config(config)

        assert is_valid is False
        assert "trade_amount" in error.lower() or "negative" in error.lower()

    def test_invalid_symbol_format_returns_false(self):
        """Should return (False, error_message) for invalid symbol format."""
        config = {
            "symbol": "INVALID",  # Should be XXX_YYY format
            "trade_amount": 0.001,
        }

        is_valid, error = validate_config(config)

        assert is_valid is False
        assert "symbol" in error.lower()
