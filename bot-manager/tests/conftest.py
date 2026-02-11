"""Shared test configuration."""
import os

# Set FLASK_ENV before any app imports to prevent module-level create_app()
os.environ["FLASK_ENV"] = "testing"
