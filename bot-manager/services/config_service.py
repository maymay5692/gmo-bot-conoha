"""Configuration file service for bot settings."""
import os
import re
import shutil
from typing import Any, Dict, Tuple

import yaml


class ConfigError(Exception):
    """Configuration related error."""


# Required fields in config
REQUIRED_FIELDS = ["symbol"]

# Valid symbol pattern (e.g., BTC_JPY, ETH_JPY)
SYMBOL_PATTERN = re.compile(r"^[A-Z]+_[A-Z]+$")


def read_config(config_path: str) -> Dict[str, Any]:
    """Read configuration from YAML file.

    Args:
        config_path: Path to the YAML configuration file.

    Returns:
        Dict containing configuration values.

    Raises:
        ConfigError: If file not found or invalid YAML.
    """
    if not os.path.exists(config_path):
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Failed to parse YAML: {e}") from e


def write_config(config_path: str, config: Dict[str, Any]) -> bool:
    """Write configuration to YAML file.

    Creates a backup of the existing file before writing.

    Args:
        config_path: Path to the YAML configuration file.
        config: Configuration dictionary to write.

    Returns:
        True if successful.

    Raises:
        ConfigError: If write fails.
    """
    # Ensure directory exists
    dir_path = os.path.dirname(config_path)
    if dir_path and not os.path.exists(dir_path):
        raise ConfigError(f"Directory does not exist: {dir_path}")

    # Create backup if file exists
    if os.path.exists(config_path):
        backup_path = config_path + ".bak"
        shutil.copy2(config_path, backup_path)

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        return True
    except (IOError, OSError) as e:
        raise ConfigError(f"Failed to write config: {e}") from e


def validate_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate configuration values.

    Args:
        config: Configuration dictionary to validate.

    Returns:
        Tuple of (is_valid, error_message).
        If valid, error_message is empty string.
    """
    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in config:
            return False, f"Missing required field: {field}"

    # Validate symbol format
    symbol = config.get("symbol", "")
    if not SYMBOL_PATTERN.match(str(symbol)):
        return False, f"Invalid symbol format: {symbol}. Expected format: XXX_YYY"

    # Validate trade_amount if present
    trade_amount = config.get("trade_amount")
    if trade_amount is not None:
        try:
            amount = float(trade_amount)
            if amount < 0:
                return False, f"trade_amount must be non-negative, got: {amount}"
        except (ValueError, TypeError):
            return False, f"trade_amount must be a number, got: {trade_amount}"

    # Validate max_position if present
    max_position = config.get("max_position")
    if max_position is not None:
        try:
            pos = float(max_position)
            if pos < 0:
                return False, f"max_position must be non-negative, got: {pos}"
        except (ValueError, TypeError):
            return False, f"max_position must be a number, got: {max_position}"

    return True, ""
