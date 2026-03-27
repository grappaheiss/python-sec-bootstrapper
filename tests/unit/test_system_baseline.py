"""Unit tests for system_baseline module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sec_bootstrapper.core.base import ModuleStatus
from sec_bootstrapper.core.manifest import ManifestLogger
from sec_bootstrapper.modules.system_baseline import SystemBaselineModule


@pytest.fixture
def mock_config():
    """Create mock config."""
    config = MagicMock()
    return config


@pytest.fixture
def mock_rollback():
    """Create mock rollback manager."""
    rollback = MagicMock()
    rollback.get_backups_for_module.return_value = []
    return rollback


@pytest.fixture
def mock_logger():
    """Create mock logger."""
    from sec_bootstrapper.core.manifest import ManifestLogger
    logger = ManifestLogger(log_file=Path("/tmp/test_manifest.jsonl"), skip_ensure_dir=True)
    return logger


@pytest.fixture
def module(mock_config, mock_rollback, mock_logger):
    """Create SystemBaselineModule instance."""
    return SystemBaselineModule(
        config=mock_config,
        rollback_manager=mock_rollback,
        dry_run=True,
        logger=mock_logger,
    )


class TestSystemBaselineModule:
    """Test cases for SystemBaselineModule."""

    def test_module_attributes(self, module):
        """Test module has correct attributes."""
        assert module.name == "system_baseline"
        assert module.description == "Update package lists and upgrade installed packages"
        assert module.phase == "server"
        assert "updated_packages" in module.provides

    def test_check_always_returns_true(self, module):
        """Test that check() always returns True."""
        # System baseline should always run to ensure latest packages
        assert module.check() is True

    def test_dry_run_does_not_execute_commands(self, module):
        """Test that dry-run mode doesn't execute actual commands."""
        with patch("subprocess.run") as mock_run:
            result = module.run()
            
            # Should complete successfully without running subprocess
            assert result.status == ModuleStatus.SUCCESS
            assert "Dry run" in result.message
            mock_run.assert_not_called()

    def test_preview_changes_returns_expected_list(self, module):
        """Test that preview shows expected changes."""
        changes = module._preview_changes()
        
        assert len(changes) == 2
        assert "Update package lists" in changes[0]
        assert "Upgrade" in changes[1]

    def test_get_changes_returns_expected_list(self, module):
        """Test that get_changes returns expected list."""
        changes = module._get_changes()
        
        assert len(changes) == 2
        assert "Package lists updated" in changes
        assert "Installed packages upgraded" in changes

    @patch("sec_bootstrapper.modules.system_baseline.get_package_manager")
    def test_apply_updates_packages(self, mock_get_manager, mock_config, mock_rollback, mock_logger):
        """Test that apply() updates and upgrades packages."""
        # Create real module (not dry-run)
        module = SystemBaselineModule(
            config=mock_config,
            rollback_manager=mock_rollback,
            dry_run=False,
            logger=mock_logger,
        )
        
        # Mock package manager
        mock_manager = MagicMock()
        mock_manager.update.return_value = True
        mock_manager.upgrade.return_value = True
        mock_get_manager.return_value = mock_manager
        
        # Apply should call update and upgrade
        module.apply()
        
        mock_manager.update.assert_called_once()
        mock_manager.upgrade.assert_called_once()

    @patch("sec_bootstrapper.modules.system_baseline.get_package_manager")
    def test_apply_fails_on_update_error(self, mock_get_manager, mock_config, mock_rollback, mock_logger):
        """Test that apply() raises error when update fails."""
        from sec_bootstrapper.core.base import ModuleError
        
        module = SystemBaselineModule(
            config=mock_config,
            rollback_manager=mock_rollback,
            dry_run=False,
            logger=mock_logger,
        )
        
        # Mock package manager to fail update
        mock_manager = MagicMock()
        mock_manager.update.return_value = False
        mock_get_manager.return_value = mock_manager
        
        # Should raise ModuleError
        with pytest.raises(ModuleError) as exc_info:
            module.apply()
        
        assert "Failed to update" in str(exc_info.value)
        assert len(exc_info.value.recovery_steps) > 0

    @patch("sec_bootstrapper.modules.system_baseline.get_package_manager")
    def test_apply_includes_update_error_details(self, mock_get_manager, mock_config, mock_rollback, mock_logger):
        """Test that apply() includes package-manager diagnostics for update failures."""
        from sec_bootstrapper.core.base import ModuleError

        module = SystemBaselineModule(
            config=mock_config,
            rollback_manager=mock_rollback,
            dry_run=False,
            logger=mock_logger,
        )

        mock_manager = MagicMock()
        mock_manager.update.return_value = False
        mock_manager.last_error = "apt-get update exited with 100: lock held"
        mock_get_manager.return_value = mock_manager

        with pytest.raises(ModuleError) as exc_info:
            module.apply()

        assert "Failed to update package lists" in str(exc_info.value)
        assert "lock held" in str(exc_info.value)

    @patch("sec_bootstrapper.modules.system_baseline.get_package_manager")
    def test_apply_includes_upgrade_error_details(self, mock_get_manager, mock_config, mock_rollback, mock_logger):
        """Test that apply() includes package-manager diagnostics for upgrade failures."""
        from sec_bootstrapper.core.base import ModuleError

        module = SystemBaselineModule(
            config=mock_config,
            rollback_manager=mock_rollback,
            dry_run=False,
            logger=mock_logger,
        )

        mock_manager = MagicMock()
        mock_manager.update.return_value = True
        mock_manager.upgrade.return_value = False
        mock_manager.last_error = "apt-get full-upgrade -y exited with 100: broken packages"
        mock_get_manager.return_value = mock_manager

        with pytest.raises(ModuleError) as exc_info:
            module.apply()

        assert "Failed to upgrade packages" in str(exc_info.value)
        assert "broken packages" in str(exc_info.value)

    @patch("subprocess.run")
    def test_verify_checks_upgradable_packages(self, mock_run, module):
        """Test that verify() checks for upgradable packages."""
        # Mock no upgradable packages (success case)
        mock_run.return_value = MagicMock(
            stdout="Listing... Done\n",
            returncode=0,
        )
        
        result = module.verify()
        
        assert result is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "apt" in args
        assert "--upgradable" in args

    @patch("subprocess.run")
    def test_verify_fails_when_packages_upgradable(self, mock_run, module):
        """Test that verify() fails when packages are still upgradable."""
        # Mock some upgradable packages
        mock_run.return_value = MagicMock(
            stdout="Listing... Done\npackage1/oldstable 1.0.0 amd64 [upgradable from: 0.9.0]\n",
            returncode=0,
        )
        
        result = module.verify()
        
        assert result is False

    def test_run_full_lifecycle_dry_run(self, module):
        """Test full module lifecycle in dry-run mode."""
        result = module.run()
        
        assert result.module_name == "system_baseline"
        assert result.status == ModuleStatus.SUCCESS
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration is not None
        assert result.duration >= 0
