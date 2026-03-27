# T-022 Distro Support Matrix

| Distro | Minimum Target | Family Mapping | Package Manager | Status |
|---|---|---|---|---|
| Ubuntu | 22.04+ | Debian family | apt | Implemented (code path), not runtime-validated in this workspace |
| Debian | 12+ | Debian family | apt | Implemented; local environment is Debian 13 (forward-compatible path) |
| Fedora | 38+ | RedHat family | dnf | Implemented (dnf path), not runtime-validated in this workspace |
| Parrot | Current (Debian-based) | Debian family | apt | Implemented via Debian-family logic, not runtime-validated |

## Notes

- Current workspace OS is Debian 13 (`/etc/os-release`), not one of the explicit target minimums; logic is compatible with Debian-family flow.
- Remote second-distro validation evidence is still required for full acceptance.
