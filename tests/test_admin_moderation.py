"""Tests for admin moderation API calls."""

import unittest
from unittest.mock import MagicMock, patch

from app.services.enforcement_service import EnforcementService
from app.services.mastodon_service import MastodonService


class TestAdminModeration(unittest.TestCase):
    """Test admin moderation API calls use correct parameters."""

    def test_admin_suspend_uses_id_kwarg(self):
        """Verify admin_suspend_account uses id= keyword argument."""
        service = MastodonService()
        
        with patch.object(service, 'get_admin_client') as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.admin_account_moderate.return_value = {"id": "123", "suspended": True}
            
            result = service.admin_suspend_account("123")
            
            # Verify the call used keyword arguments
            mock_client.admin_account_moderate.assert_called_once_with(
                id="123",
                action="suspend"
            )
            self.assertEqual(result["suspended"], True)

    def test_admin_account_action_sync_uses_id_kwarg(self):
        """Verify admin_account_action_sync uses id= keyword argument."""
        service = MastodonService()
        
        with patch.object(service, 'get_admin_client') as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.admin_account_moderate.return_value = {"id": "456", "silenced": True}
            
            result = service.admin_account_action_sync(
                account_id="456",
                action_type="silence",
                text="Violates rules",
                warning_preset_id=None
            )
            
            # Verify the call used keyword arguments
            mock_client.admin_account_moderate.assert_called_once_with(
                id="456",
                action="silence",
                text="Violates rules",
                warning_preset_id=None
            )
            self.assertEqual(result["silenced"], True)

    def test_enforcement_service_uses_id_kwarg(self):
        """Verify EnforcementService uses id= keyword argument."""
        mock_client = MagicMock()
        mock_client.admin_account_moderate.return_value = {"id": "789"}
        
        service = EnforcementService(client=mock_client)
        
        # Mock the database session to avoid needing actual database
        with patch('app.services.enforcement_service.SessionLocal') as mock_session_local:
            mock_session = MagicMock()
            mock_session_local.return_value.__enter__.return_value = mock_session
            
            # Temporarily disable DRY_RUN for this test
            with patch('app.services.enforcement_service.settings.DRY_RUN', False):
                service.suspend_account("789", text="Spam", rule_id=1)
                
                # Verify the call used keyword arguments
                mock_client.admin_account_moderate.assert_called_once_with(
                    id="789",
                    action="suspend",
                    text="Spam",
                    warning_preset_id=None
                )

    def test_warn_action_uses_none_for_action(self):
        """Verify warning actions use action=None."""
        service = MastodonService()
        
        with patch.object(service, 'get_admin_client') as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client
            mock_client.admin_account_moderate.return_value = {"id": "999"}
            
            result = service.admin_account_action_sync(
                account_id="999",
                action_type="warn",
                text="First warning"
            )
            
            # Verify warn uses action=None
            mock_client.admin_account_moderate.assert_called_once_with(
                id="999",
                action=None,  # Should be None for warnings
                text="First warning",
                warning_preset_id=None
            )


if __name__ == "__main__":
    unittest.main()
