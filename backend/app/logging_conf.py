"""Structured JSON logging configuration for the application."""
import logging
import sys

from pythonjsonlogger import jsonlogger


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "file": "%(filename)s", "line": %(lineno)d, "message": "%(message)s"}'
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [handler]
