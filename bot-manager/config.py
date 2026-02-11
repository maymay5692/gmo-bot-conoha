"""Bot Manager application configuration."""
import os
import secrets


class Config:
    """Application configuration."""

    # Bot service settings
    BOT_SERVICE_NAME: str = "gmo-bot"

    # Config file path (can be overridden by environment variable)
    CONFIG_PATH: str = os.environ.get(
        "BOT_CONFIG_PATH",
        "/home/ubuntu/gmo-bot/trade-config.yaml"
    )

    # Server settings (0.0.0.0 for external access, protected by Basic Auth)
    HOST: str = os.environ.get("BOT_MANAGER_HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("BOT_MANAGER_PORT", "80"))
    DEBUG: bool = False

    # Log settings
    LOG_LINES_DEFAULT: int = 100
    LOG_LINES_MAX: int = 1000

    # Security settings
    SECRET_KEY: str = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    WTF_CSRF_ENABLED: bool = True

    # Basic Auth (set via environment variables)
    BASIC_AUTH_USERNAME: str = os.environ.get("ADMIN_USER", "admin")
    BASIC_AUTH_PASSWORD: str = os.environ.get("ADMIN_PASS", "")

    # P&L data directory
    PNL_DATA_DIR: str = os.environ.get(
        "PNL_DATA_DIR",
        r"C:\gmo-bot\data" if os.name == "nt" else "/home/ubuntu/gmo-bot/data"
    )


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG: bool = True
    CONFIG_PATH: str = os.environ.get(
        "BOT_CONFIG_PATH",
        os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "src",
            "trade-config.yaml"
        )
    )
    PNL_DATA_DIR: str = os.environ.get(
        "PNL_DATA_DIR",
        os.path.join(os.path.dirname(__file__), "data")
    )


class TestConfig(Config):
    """Test configuration."""

    TESTING: bool = True
    HOST: str = "127.0.0.1"
    CONFIG_PATH: str = "/tmp/test-config.yaml"
    PNL_DATA_DIR: str = "/tmp/test-pnl-data"


def get_config() -> Config:
    """Get configuration based on environment."""
    env = os.environ.get("FLASK_ENV", "production")

    if env == "development":
        return DevelopmentConfig()
    if env == "testing":
        return TestConfig()
    return Config()
