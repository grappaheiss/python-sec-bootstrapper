# T-022 Module Inventory

## Core Modules (Critical)

- `local_key_prep` (Stage 1, `local_prep`): local SSH key bootstrap and handoff guidance
- `system_baseline` (Stage 1): package metadata refresh + upgrade
- `system_packages` (Stage 1): curl/wget/ufw/fail2ban/ca-certificates/gnupg
- `user_setup` (Stage 1): non-root sudo user + SSH directory workflow
- `ssh_hardening` (Stage 1): secure `sshd_config` baseline (port 2222, key auth)
- `firewall` (Stage 1): UFW defaults + SSH allow + IPv6 toggle
- `fail2ban` (Stage 1): jail.local sshd controls
- `unattended_upgrades` (Stage 1): apt unattended-upgrades or dnf-automatic
- `system_hardening` (Stage 1): timezone + entropy daemon
- `tailscale` (Stage 1): tailscale client installation path
- `dev_runtime_tools` (Stage 1): python/pip/venv, npm, git
- `docker_prereq` (Stage 1): Docker runtime package prerequisites and CLI availability check
- `firejail` (Stage 1): firejail installation

## Secondary Modules

- `clamav` (Stage 1)
- `rkhunter` (Stage 1)
- `lynis` (Stage 1)
- `docker_baseline` (Stage 2): hardened `/etc/docker/daemon.json`

## Stage 3 / Validation Modules

- `docker_ai_validation` (Stage 3): secure compose validation and evidence handoff

## AI Framework Modules

- `openclaw` (Stage 3)
- `opencode` (Stage 3)
- `claude` (Stage 3)
- `vscode` (Stage 3)

## Wiring Status

All modules are decorator-registered and discoverable through `list-modules`.
