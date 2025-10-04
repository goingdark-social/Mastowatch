from unittest.mock import patch

import pytest

from app.startup_validation import validate_mastodon_version


@patch("app.services.mastodon_service.mastodon_service.get_instance_info_sync")
def test_validate_mastodon_version_ok(mock_info):
    mock_info.return_value = {"version": "4.2.0"}
    validate_mastodon_version()


@patch("app.services.mastodon_service.mastodon_service.get_instance_info_sync")
def test_validate_mastodon_version_fail(mock_info):
    mock_info.return_value = {"version": "3.5.0"}
    with pytest.raises(SystemExit):
        validate_mastodon_version()
