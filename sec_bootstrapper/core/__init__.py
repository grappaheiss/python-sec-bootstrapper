"""Core infrastructure for sec-bootstrapper."""

from sec_bootstrapper.core.base import BaseModule, ModuleError, ModuleRegistry, module
from sec_bootstrapper.core.config import Config
from sec_bootstrapper.core.distro import DistroDetector, get_package_manager
from sec_bootstrapper.core.manifest import ManifestLogger
from sec_bootstrapper.core.rollback import RollbackManager

__all__ = [
    "BaseModule",
    "Config", 
    "DistroDetector",
    "get_package_manager",
    "ManifestLogger",
    "ModuleError",
    "ModuleRegistry",
    "module",
    "RollbackManager",
]
