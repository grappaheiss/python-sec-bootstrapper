"""Integration test for all hardening modules."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sec_bootstrapper.core.base import ModuleStatus
from sec_bootstrapper.core.config import Config
from sec_bootstrapper.core.manifest import ManifestLogger
from sec_bootstrapper.core.rollback import RollbackManager
from sec_bootstrapper.modules.firewall import FirewallModule
from sec_bootstrapper.modules.ssh_hardening import SSHHardeningModule
from sec_bootstrapper.modules.system_baseline import SystemBaselineModule
from sec_bootstrapper.modules.user_setup import UserSetupModule


@pytest.fixture
def test_config():
    """Create test configuration."""
    config = Config()
    config.execution.dry_run = True
    config.security.ssh.port = 2222
    config.security.ssh.allowed_users = ["chad"]
    config.security.ssh.password_auth = False
    config.security.ssh.root_login = False
    config.security.firewall.ipv6 = False
    return config


@pytest.fixture
def test_rollback():
    """Create test rollback manager."""
    return RollbackManager(
        backup_dir=Path("/tmp/sec_backups"),
        state_file=Path("/tmp/sec_state.json"),
    )


@pytest.fixture
def test_logger():
    """Create test logger."""
    return ManifestLogger(
        log_file=Path("/tmp/test_manifest.jsonl"),
        skip_ensure_dir=True,
    )


class TestModulesDryRun:
    """Test all modules in dry-run mode."""

    def test_system_baseline_dry_run(self, test_config, test_rollback, test_logger):
        """Test system_baseline in dry-run."""
        module = SystemBaselineModule(
            config=test_config,
            rollback_manager=test_rollback,
            dry_run=True,
            logger=test_logger,
        )
        
        result = module.run()
        
        assert result.status == ModuleStatus.SUCCESS
        assert "Dry run" in result.message
        assert len(result.changes) == 2
        assert "Update package lists" in result.changes[0]

    def test_user_setup_dry_run(self, test_config, test_rollback, test_logger):
        """Test user_setup in dry-run."""
        module = UserSetupModule(
            config=test_config,
            rollback_manager=test_rollback,
            dry_run=True,
            logger=test_logger,
        )
        
        result = module.run()
        
        # Should succeed or skip (depending on if user exists)
        assert result.status in [ModuleStatus.SUCCESS, ModuleStatus.SKIPPED]

    def test_ssh_hardening_dry_run(self, test_config, test_rollback, test_logger):
        """Test ssh_hardening in dry-run."""
        module = SSHHardeningModule(
            config=test_config,
            rollback_manager=test_rollback,
            dry_run=True,
            logger=test_logger,
        )
        
        result = module.run()
        
        assert result.status in [ModuleStatus.SUCCESS, ModuleStatus.SKIPPED]
        if result.status == ModuleStatus.SUCCESS:
            assert len(result.changes) > 0
            assert any("port" in c.lower() for c in result.changes)

    def test_firewall_dry_run(self, test_config, test_rollback, test_logger):
        """Test firewall in dry-run."""
        module = FirewallModule(
            config=test_config,
            rollback_manager=test_rollback,
            dry_run=True,
            logger=test_logger,
        )
        
        result = module.run()
        
        assert result.status in [ModuleStatus.SUCCESS, ModuleStatus.SKIPPED]


class TestModuleAttributes:
    """Test module metadata and attributes."""

    def test_all_modules_registered(self):
        """Test that all modules are registered."""
        from sec_bootstrapper.core.base import ModuleRegistry
        
        expected_modules = [
            "system_baseline",
            "user_setup",
            "ssh_hardening",
            "firewall",
        ]
        
        registered = ModuleRegistry.list_all()
        
        for mod in expected_modules:
            assert mod in registered, f"Module {mod} not registered"

    def test_system_baseline_attributes(self):
        """Test system_baseline module attributes."""
        from sec_bootstrapper.modules.system_baseline import SystemBaselineModule
        
        assert SystemBaselineModule.name == "system_baseline"
        assert SystemBaselineModule.phase == "server"
        assert "updated_packages" in SystemBaselineModule.provides
        assert SystemBaselineModule.dependencies == []

    def test_user_setup_dependencies(self):
        """Test user_setup depends on system_baseline."""
        from sec_bootstrapper.modules.user_setup import UserSetupModule
        
        assert "system_baseline" in UserSetupModule.dependencies
        assert "nonroot_user" in UserSetupModule.provides

    def test_ssh_hardening_dependencies(self):
        """Test ssh_hardening depends on user_setup."""
        from sec_bootstrapper.modules.ssh_hardening import SSHHardeningModule
        
        assert "user_setup" in SSHHardeningModule.dependencies
        assert "ssh_hardened" in SSHHardeningModule.provides

    def test_firewall_dependencies(self):
        """Test firewall depends on ssh_hardening."""
        from sec_bootstrapper.modules.firewall import FirewallModule
        
        assert "ssh_hardening" in FirewallModule.dependencies
        assert "firewall_configured" in FirewallModule.provides


class TestModuleExecutionOrder:
    """Test module dependency resolution."""

    def test_dependency_chain(self):
        """Test that dependencies form a valid chain."""
        from sec_bootstrapper.core.base import ModuleRegistry
        
        # Check all dependencies exist
        for mod_name in ModuleRegistry.list_all():
            mod_class = ModuleRegistry.get(mod_name)
            for dep in mod_class.dependencies:
                assert dep in ModuleRegistry.list_all(), \
                    f"{mod_name} depends on unknown module: {dep}"

    def test_no_circular_dependencies(self):
        """Test there are no circular dependencies."""
        from sec_bootstrapper.core.base import ModuleRegistry
        
        def has_circular_deps(mod_name, visited=None, stack=None):
            if visited is None:
                visited = set()
            if stack is None:
                stack = set()
            
            visited.add(mod_name)
            stack.add(mod_name)
            
            mod_class = ModuleRegistry.get(mod_name)
            if mod_class:
                for dep in mod_class.dependencies:
                    if dep not in visited:
                        if has_circular_deps(dep, visited, stack):
                            return True
                    elif dep in stack:
                        return True
            
            stack.remove(mod_name)
            return False
        
        for mod_name in ModuleRegistry.list_all():
            assert not has_circular_deps(mod_name), \
                f"Circular dependency detected for {mod_name}"


class TestDryRunPreview:
    """Test dry-run preview functionality."""

    def test_system_baseline_preview(self, test_config, test_rollback, test_logger):
        """Test system_baseline shows correct preview."""
        module = SystemBaselineModule(
            config=test_config,
            rollback_manager=test_rollback,
            dry_run=True,
            logger=test_logger,
        )
        
        preview = module._preview_changes()
        
        assert len(preview) == 2
        assert "Update package lists" in preview[0]
        assert "Upgrade all installed packages" in preview[1]

    def test_user_setup_preview(self, test_config, test_rollback, test_logger):
        """Test user_setup shows correct preview."""
        module = UserSetupModule(
            config=test_config,
            rollback_manager=test_rollback,
            dry_run=True,
            logger=test_logger,
        )
        
        preview = module._preview_changes()
        
        assert len(preview) == 4
        assert any("chad" in p for p in preview)
        assert any("sudo" in p for p in preview)

    def test_ssh_hardening_preview(self, test_config, test_rollback, test_logger):
        """Test ssh_hardening shows correct preview."""
        module = SSHHardeningModule(
            config=test_config,
            rollback_manager=test_rollback,
            dry_run=True,
            logger=test_logger,
        )
        
        preview = module._preview_changes()
        
        assert len(preview) >= 6
        assert any("2222" in p for p in preview)
        assert any("root" in p.lower() for p in preview)

    def test_firewall_preview(self, test_config, test_rollback, test_logger):
        """Test firewall shows correct preview."""
        module = FirewallModule(
            config=test_config,
            rollback_manager=test_rollback,
            dry_run=True,
            logger=test_logger,
        )
        
        preview = module._preview_changes()
        
        assert len(preview) == 6
        assert any("UFW" in p for p in preview)
        assert any("2222" in p for p in preview)
