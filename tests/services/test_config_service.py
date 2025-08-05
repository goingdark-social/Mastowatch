"""Tests for configuration service layer."""

import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.services.config_service import ConfigService


class TestConfigService(unittest.TestCase):
    """Validate ConfigService behavior."""

    def setUp(self):
        """Configure test database."""
        self.db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        engine = create_engine(f"sqlite:///{self.db_file.name}")
        Base.metadata.create_all(engine)
        self.SessionLocal = sessionmaker(bind=engine)
        self.service = ConfigService()
        self.patcher = patch("app.services.config_service.SessionLocal", self.SessionLocal)
        self.patcher.start()

    def tearDown(self):
        """Cleanup test database."""
        self.patcher.stop()
        os.unlink(self.db_file.name)

    def test_set_and_get_flag(self):
        """Store and retrieve flag value."""
        self.service.set_flag("panic_stop", True, updated_by="tester")
        value = self.service.get_config("panic_stop")
        self.assertEqual(value["enabled"], True)

    def test_set_threshold(self):
        """Store and retrieve numeric threshold."""
        self.service.set_threshold("report_threshold", 2.5, updated_by="tester")
        value = self.service.get_config("report_threshold")
        self.assertEqual(value["threshold"], 2.5)


if __name__ == "__main__":
    unittest.main()
