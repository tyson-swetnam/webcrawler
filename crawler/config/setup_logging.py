"""
Logging setup utility for AI News Crawler

This module configures logging for the entire application based on
the logging.yaml configuration file.
"""

import logging
import logging.config
import os
import sys
from pathlib import Path
import yaml


def setup_logging(
    config_path: str = "crawler/config/logging.yaml",
    default_level: int = logging.INFO,
    log_dir: str = "logs"
):
    """
    Setup logging configuration from YAML file

    Args:
        config_path: Path to logging configuration YAML file
        default_level: Default logging level if config file not found
        log_dir: Directory for log files (will be created if not exists)
    """
    # Ensure log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Get project root directory
    project_root = Path(__file__).parent.parent.parent
    config_file = project_root / config_path

    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            # Update file paths to be relative to project root
            for handler in config.get('handlers', {}).values():
                if 'filename' in handler:
                    # Make path absolute relative to project root
                    handler['filename'] = str(project_root / handler['filename'])

            logging.config.dictConfig(config)
            logging.info(f"Logging configured from {config_file}")

        except Exception as e:
            # Fallback to basic config if YAML loading fails
            logging.basicConfig(
                level=default_level,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.StreamHandler(sys.stdout),
                    logging.FileHandler(log_path / 'crawler.log')
                ]
            )
            logging.error(f"Failed to load logging config from {config_file}: {e}")
            logging.info("Using basic logging configuration")
    else:
        # Config file not found, use basic configuration
        logging.basicConfig(
            level=default_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout),
                logging.FileHandler(log_path / 'crawler.log')
            ]
        )
        logging.warning(f"Logging config file not found: {config_file}")
        logging.info("Using basic logging configuration")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name

    Args:
        name: Logger name (usually __name__ of the calling module)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)


if __name__ == "__main__":
    # Test logging setup
    setup_logging()

    logger = get_logger(__name__)

    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    print("\nLogging setup test complete!")
    print("Check the logs/ directory for output files:")
    print("  - logs/crawler.log (all messages)")
    print("  - logs/error.log (errors only)")
    print("  - logs/crawler.json.log (JSON format)")
    print("  - logs/stdout.log (stdout redirect)")
