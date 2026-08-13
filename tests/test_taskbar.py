"""The taskbar identity a player's windows are grouped under."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from player_core import taskbar


class TestSetAppUserModelId:
    def test_it_claims_the_identity_it_is_given(self):
        """Which identity is the launcher's to decide — a player run on its own is
        its own application, one run by an orchestrator belongs to that."""
        with patch.object(taskbar, "_shell32") as shell32:
            shell32.SetCurrentProcessExplicitAppUserModelID.return_value = 0
            taskbar.set_app_user_model_id("Example.App")

        shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with("Example.App")

    def test_a_refusal_is_raised_rather_than_swallowed(self):
        """The callers decide that an icon is not worth failing to start over;
        this one only reports what happened."""
        with patch.object(taskbar, "_shell32") as shell32:
            shell32.SetCurrentProcessExplicitAppUserModelID.return_value = -2147024809
            with pytest.raises(OSError):
                taskbar.set_app_user_model_id("Example.App")

    def test_a_zero_result_is_success(self):
        with patch.object(taskbar, "_shell32") as shell32:
            shell32.SetCurrentProcessExplicitAppUserModelID.return_value = 0
            taskbar.set_app_user_model_id("Example.App")  # does not raise
