"""Flask application configuration."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.absolute()
PROJECTS_DIR = BASE_DIR / 'projects'

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    PROJECTS_DIR = PROJECTS_DIR

    # Ensure projects directory exists
    PROJECTS_DIR.mkdir(exist_ok=True)

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
