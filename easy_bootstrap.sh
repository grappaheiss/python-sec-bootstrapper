#!/usr/bin/env bash
set -euo pipefail

# One-shot bootstrap for non-technical operators:
# - installs core tools (including Docker)
# - creates 4 SSH bootstrap keys
# - writes ~/.ssh/config host block
# - optionally pins host key + copies all pubkeys to remote
#
# Example:
#   ./easy_bootstrap.sh --host 100.122.106.19 --user gigachad --port 22 --alias chadd

HOST=""
USER_NAME=""
PORT="22"
ALIAS_NAME=""
NON_INTERACTIVE="0"
SKIP_REMOTE="0"
RUN_DEBLOAT="ask"
RUN_STAGE1="ask"
RUN_STAGE2="ask"
RUN_STAGE3="ask"
STAGE_CONFIG="${STAGE_CONFIG:-config/config.local.yaml}"
GENERATE_KEYS="ask"
USER_SETUP_USER=""
KEY_NAMES_CSV=""
USE_GUI="0"
RUN_DOCKER_SCRIPT="ask"
INSTALL_AI_IMAGES="ask"
AI_IMAGES_CSV=""
GUI_EVIDENCE_ROOT="${GUI_EVIDENCE_ROOT:-}"
GUI_EVIDENCE_RUN_ID=""
DOCKER_SCRIPT_PATH=""
COMPOSE_FILE_PATH=""
COMPOSE_ENV_FILE_PATH=""
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
EFFECTIVE_STAGE_CONFIG=""
PY_RUNTIME_READY="0"
PY_REQUIREMENTS_FILE="requirements.txt"

# Tool cache defaults (aligned with sec_bootstrapper ToolCacheManager)
TOOLS_CACHE_ROOT="${TOOLS_CACHE_ROOT:-/tools}"
TOOLS_FALLBACK_ROOT="${TOOLS_FALLBACK_ROOT:-$HOME/.cache/sec_bootstrapper/tools}"
TOOLS_MANIFEST="${TOOLS_MANIFEST:-$SCRIPT_DIR/config/tools_manifest.yaml}"

KEY_NAMES=(
  "id_ed25519_bootstrap_1"
  "id_ed25519_bootstrap_2"
  "id_rsa_bootstrap_1"
  "id_rsa_bootstrap_2"
)

usage() {
  cat <<'EOF'
Usage: easy_bootstrap.sh [options]

Required (unless --skip-remote):
  --host <hostname_or_ip>     Remote server address
  --user <remote_user>        Remote SSH user

Optional:
  --port <port>               SSH port (default: 22)
  --alias <ssh_alias>         Alias for ~/.ssh/config (prompted if omitted)
  --user-setup-user <name>    Non-root user to configure in stage config (default prompt value: chad)
  --key-names <csv>           Override local bootstrap key names (4 comma-separated names)
  --debloat                   Run debloat recommendation scan
  --no-debloat                Skip debloat recommendation scan
  --run-stage1                Execute sec-bootstrapper Stage 1 after baseline
  --run-docker-hardening      Execute sec-bootstrapper Stage 2 (docker hardening)
  --run-stage3                Execute sec-bootstrapper Stage 3 (dockerized AI validation)
  --run-pipeline              Execute Stage 1 -> Stage 2 -> Stage 3 sequence
  --run-docker-script         Execute follow-on Docker hardening script bridge
  --install-ai-images         Pull required Stage-3 docker images via secure bridge
  --ai-images <csv>           Optional image list; mandatory defaults ollama,opencode,claude,openclaw,openvscode,grype are always included
  --docker-script <path>      Follow-on Docker hardening script path
  --compose-file <path>       Compose file used for image pull bridge
  --compose-env-file <path>   Optional env-file used with compose bridge
  --stage-config <path>       Config file for stage execution (default: config/config.local.yaml)
  --gui                       Show GUI checklist (zenity/whiptail) for bridge actions
  --no-gui                    Disable GUI checklist mode
  --gen-keys                  Generate local SSH bootstrap keys even with --skip-remote
  --no-gen-keys               Never generate local SSH bootstrap keys
  --skip-remote               Do not run ssh-keyscan/ssh-copy-id steps
  --yes                       Non-interactive mode (auto-continue prompts)
  -h, --help                  Show this help
EOF
}

log() { printf '[INFO] %s\n' "$*"; }
ok() { printf '[OK] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*"; }
die() { printf '[ERR] %s\n' "$*" >&2; exit 1; }
ui_banner() {
  printf '\n'
  printf '============================================\n'
  printf ' T-022 Easy Bootstrap Wizard\n'
  printf '============================================\n'
}
ui_step() { printf '\n[STEP] %s\n' "$*"; }

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --host) HOST="${2:-}"; shift 2 ;;
      --user) USER_NAME="${2:-}"; shift 2 ;;
      --port) PORT="${2:-}"; shift 2 ;;
      --alias) ALIAS_NAME="${2:-}"; shift 2 ;;
      --user-setup-user) USER_SETUP_USER="${2:-}"; shift 2 ;;
      --key-names) KEY_NAMES_CSV="${2:-}"; shift 2 ;;
      --debloat) RUN_DEBLOAT="yes"; shift ;;
      --no-debloat) RUN_DEBLOAT="no"; shift ;;
      --run-stage1) RUN_STAGE1="yes"; shift ;;
      --run-docker-hardening) RUN_STAGE2="yes"; shift ;;
      --run-stage3) RUN_STAGE3="yes"; shift ;;
      --run-pipeline) RUN_STAGE1="yes"; RUN_STAGE2="yes"; RUN_STAGE3="yes"; shift ;;
      --run-docker-script) RUN_DOCKER_SCRIPT="yes"; shift ;;
      --install-ai-images) INSTALL_AI_IMAGES="yes"; shift ;;
      --ai-images) AI_IMAGES_CSV="${2:-}"; shift 2 ;;
      --docker-script) DOCKER_SCRIPT_PATH="${2:-}"; shift 2 ;;
      --compose-file) COMPOSE_FILE_PATH="${2:-}"; shift 2 ;;
      --compose-env-file) COMPOSE_ENV_FILE_PATH="${2:-}"; shift 2 ;;
      --stage-config) STAGE_CONFIG="${2:-}"; shift 2 ;;
      --gui) USE_GUI="1"; shift ;;
      --no-gui) USE_GUI="0"; shift ;;
      --gen-keys) GENERATE_KEYS="yes"; shift ;;
      --no-gen-keys) GENERATE_KEYS="no"; shift ;;
      --yes) NON_INTERACTIVE="1"; shift ;;
      --skip-remote) SKIP_REMOTE="1"; shift ;;
      -h|--help) usage; exit 0 ;;
      *) die "Unknown argument: $1" ;;
    esac
  done

}

parse_key_names_csv() {
  local csv="$1"
  local parsed=()
  local part=""
  IFS=',' read -r -a parsed <<<"$csv"
  KEY_NAMES=()
  for part in "${parsed[@]}"; do
    part="$(printf '%s' "$part" | xargs)"
    [[ -n "$part" ]] && KEY_NAMES+=("$part")
  done
  if [[ "${#KEY_NAMES[@]}" -ne 4 ]]; then
    die "--key-names requires exactly 4 comma-separated values"
  fi
}

normalize_bool_for_gui() {
  local value="${1:-}"
  if [[ "$value" == "yes" ]]; then
    printf '%s' "TRUE"
  else
    printf '%s' "FALSE"
  fi
}

stage_status_triplet() {
  local python_cmd=""
  local cfg_path="${EFFECTIVE_STAGE_CONFIG:-$STAGE_CONFIG}"
  local stage1="pending"
  local stage2="pending"
  local stage3="pending"

  if [[ -f "$SCRIPT_DIR/$cfg_path" ]]; then
    cfg_path="$SCRIPT_DIR/$cfg_path"
  fi

  if ! python_cmd="$(resolve_python_cmd 2>/dev/null)"; then
    printf '%s|%s|%s\n' "$stage1" "$stage2" "$stage3"
    return 0
  fi

  local status_line
  status_line="$("$python_cmd" - "$cfg_path" <<'PY' 2>/dev/null
import sys
from pathlib import Path

cfg = Path(sys.argv[1])
try:
    from sec_bootstrapper.core.config import Config
    from sec_bootstrapper.core.stage_gate import StageGateManager
except Exception:
    print("pending|pending|pending")
    raise SystemExit(0)

try:
    config = Config.from_yaml(cfg)
    gate = StageGateManager(config.stage_gate.state_file)
    stages = gate.state.stages
    print(f"{stages['stage1'].status}|{stages['stage2'].status}|{stages['stage3'].status}")
except Exception:
    print("pending|pending|pending")
PY
)"
  if [[ -z "$status_line" ]]; then
    status_line="pending|pending|pending"
  fi
  printf '%s\n' "$status_line"
}

stage_is_complete() {
  local status="${1:-pending}"
  [[ "$status" == "accepted" || "$status" == "completed" ]]
}

apply_gui_bridge_selection() {
  local selected="$1"
  [[ "$selected" == *"debloat"* ]] && RUN_DEBLOAT="yes" || RUN_DEBLOAT="no"
  [[ "$selected" == *"stage1"* ]] && RUN_STAGE1="yes" || RUN_STAGE1="${RUN_STAGE1:-no}"
  [[ "$selected" == *"stage2"* ]] && RUN_STAGE2="yes" || RUN_STAGE2="${RUN_STAGE2:-no}"
  [[ "$selected" == *"stage3"* ]] && RUN_STAGE3="yes" || RUN_STAGE3="${RUN_STAGE3:-no}"
  [[ "$selected" == *"docker_script"* ]] && RUN_DOCKER_SCRIPT="yes" || RUN_DOCKER_SCRIPT="${RUN_DOCKER_SCRIPT:-no}"
  [[ "$selected" == *"ai_images"* ]] && INSTALL_AI_IMAGES="yes" || INSTALL_AI_IMAGES="${INSTALL_AI_IMAGES:-no}"
}

init_gui_evidence() {
  [[ "$USE_GUI" == "1" ]] || return 0
  if [[ -z "$GUI_EVIDENCE_ROOT" ]]; then
    GUI_EVIDENCE_ROOT="$SCRIPT_DIR/artifacts/gui_runs"
  fi
  GUI_EVIDENCE_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$GUI_EVIDENCE_ROOT/$GUI_EVIDENCE_RUN_ID"
}

append_gui_evidence() {
  local name="$1"
  shift
  [[ "$USE_GUI" == "1" ]] || return 0
  [[ -n "$GUI_EVIDENCE_RUN_ID" ]] || init_gui_evidence
  printf '%s\n' "$*" >> "$GUI_EVIDENCE_ROOT/$GUI_EVIDENCE_RUN_ID/$name"
}

wizard_gui_bridge() {
  local selected=""
  local stage_statuses=""
  local stage1_status="pending"
  local stage2_status="pending"
  local stage3_status="pending"
  local stage1_default="no"
  local stage2_default="no"
  local stage3_default="no"
  local stage1_zenity="FALSE"
  local stage2_zenity="FALSE"
  local stage3_zenity="FALSE"

  stage_statuses="$(stage_status_triplet)"
  IFS='|' read -r stage1_status stage2_status stage3_status <<<"$stage_statuses"

  if ! stage_is_complete "$stage1_status"; then
    stage1_default="yes"
  elif ! stage_is_complete "$stage2_status"; then
    stage2_default="yes"
  elif ! stage_is_complete "$stage3_status"; then
    stage3_default="yes"
  fi

  stage1_zenity="$(normalize_bool_for_gui "$stage1_default")"
  stage2_zenity="$(normalize_bool_for_gui "$stage2_default")"
  stage3_zenity="$(normalize_bool_for_gui "$stage3_default")"

  if command -v zenity >/dev/null 2>&1; then
    selected="$(
      zenity --list --checklist \
        --title="T-022 Bridge Actions" \
        --text="Select bridge actions to run after baseline bootstrap. Stage3 image defaults include ollama + opencode + claude + openclaw + openvscode + grype." \
        --separator="|" \
        --column="Pick" --column="Action" \
        TRUE "debloat" \
        "$stage1_zenity" "stage1" \
        "$stage2_zenity" "stage2" \
        "$stage3_zenity" "stage3" \
        FALSE "docker_script" \
        FALSE "ai_images"
    )" || die "GUI selection canceled"
    apply_gui_bridge_selection "$selected"
    append_gui_evidence "bridge_backend.txt" "zenity"
    append_gui_evidence "bridge_selection.txt" "$selected"
    return 0
  fi

  if command -v whiptail >/dev/null 2>&1; then
    selected="$(
      whiptail --title "T-022 Bridge Actions" --checklist \
        "Select bridge actions to run after baseline bootstrap. Stage3 image defaults include ollama + opencode + claude + openclaw + openvscode + grype." 20 90 8 \
        "debloat" "Run debloat scan" ON \
        "stage1" "Run sec-bootstrapper stage1" "$([[ "$stage1_default" == "yes" ]] && echo ON || echo OFF)" \
        "stage2" "Run sec-bootstrapper stage2" "$([[ "$stage2_default" == "yes" ]] && echo ON || echo OFF)" \
        "stage3" "Run sec-bootstrapper stage3" "$([[ "$stage3_default" == "yes" ]] && echo ON || echo OFF)" \
        "docker_script" "Run follow-on docker hardening script bridge" OFF \
        "ai_images" "Pull mandatory Ollama + Opencode + Claude + OpenClaw + OpenVSCode + Grype images bridge" OFF \
        3>&1 1>&2 2>&3
    )" || die "GUI selection canceled"
    selected="$(printf '%s' "$selected" | tr -d '"')"
    apply_gui_bridge_selection "$selected"
    append_gui_evidence "bridge_backend.txt" "whiptail"
    append_gui_evidence "bridge_selection.txt" "$selected"
    return 0
  fi

  warn "--gui requested but zenity/whiptail is not available; continuing with terminal prompts"
}

wizard_prompt_inputs() {
  if [[ -n "$KEY_NAMES_CSV" ]]; then
    parse_key_names_csv "$KEY_NAMES_CSV"
  elif [[ "$NON_INTERACTIVE" != "1" ]]; then
    local default_keys
    default_keys="$(IFS=,; echo "${KEY_NAMES[*]}")"
    read -r -p "Bootstrap key names CSV [${default_keys}]: " KEY_NAMES_CSV
    KEY_NAMES_CSV="${KEY_NAMES_CSV:-$default_keys}"
    parse_key_names_csv "$KEY_NAMES_CSV"
  fi

  if [[ -z "$USER_SETUP_USER" ]]; then
    if [[ "$NON_INTERACTIVE" == "1" ]]; then
      USER_SETUP_USER="chad"
    else
      read -r -p "Stage user_setup target non-root user [chad]: " USER_SETUP_USER
      USER_SETUP_USER="${USER_SETUP_USER:-chad}"
    fi
  fi

  if [[ "$USE_GUI" == "1" ]]; then
    init_gui_evidence
    wizard_gui_bridge
  fi
}

build_effective_stage_config() {
  EFFECTIVE_STAGE_CONFIG="$STAGE_CONFIG"
  [[ -f "$SCRIPT_DIR/$STAGE_CONFIG" ]] && EFFECTIVE_STAGE_CONFIG="$SCRIPT_DIR/$STAGE_CONFIG"
  [[ -f "$EFFECTIVE_STAGE_CONFIG" ]] || die "Stage config not found: $STAGE_CONFIG"

  local pycmd=""
  if pycmd="$(resolve_python_cmd 2>/dev/null)"; then
    local tmp_cfg="/tmp/t022_stage_config.$$.yaml"
    if "$pycmd" - "$EFFECTIVE_STAGE_CONFIG" "$tmp_cfg" "$USER_SETUP_USER" <<'PY'; then
import sys
try:
    import yaml
except Exception:
    raise SystemExit(2)
src, dst, user = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src) as f:
    data = yaml.safe_load(f) or {}
data.setdefault("security", {}).setdefault("ssh", {})["allowed_users"] = [user]
with open(dst, "w") as f:
    yaml.safe_dump(data, f, sort_keys=False)
print(dst)
PY
      :
    else
      warn "Could not generate stage config override; using original config"
      return 0
    fi
    EFFECTIVE_STAGE_CONFIG="$tmp_cfg"
    ok "Prepared effective stage config with user_setup user: ${USER_SETUP_USER}"
  else
    warn "Python not available to patch stage config dynamically; using original config"
  fi
}

run_debloat_scan() {
  local python_cmd=""
  local debloat_args=(debloat --only-recommended)

  ensure_python_runtime_ready
  if [[ -x ".venv/bin/python" ]]; then
    python_cmd=".venv/bin/python"
  elif [[ -x "venv/bin/python" ]]; then
    python_cmd="venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    python_cmd="python3"
  else
    warn "Skipping debloat scan: Python runtime not found"
    return 0
  fi

  log "Running debloat recommendation scan..."
  if ! "$python_cmd" -m sec_bootstrapper.cli.main "${debloat_args[@]}"; then
    warn "Debloat scan did not complete successfully; continuing bootstrap flow"
    return 0
  fi
  ok "Debloat recommendation scan complete"
}

debloat_gui_export() {
  local python_cmd=""
  ensure_python_runtime_ready
  if ! python_cmd="$(resolve_python_cmd)"; then
    return 1
  fi

  "$python_cmd" - <<'PY'
from sec_bootstrapper.core.debloat import DebloatScanner

report = DebloatScanner().scan()
for finding in report.recommended_findings:
    packages = ",".join(finding.installed_packages)
    services = ",".join(sorted(set(finding.enabled_services + finding.active_services)))
    print(f"{finding.rule.key}\t{finding.rule.title}\t{packages}\t{services}")
PY
}

run_debloat_gui_review() {
  local scan_output=""
  local key=""
  local title=""
  local packages=""
  local services=""
  local selected=""
  local purge_cmd=""
  local disable_cmd=""
  local full_cmd=""
  local idx=0
  local p=""
  local s=""
  local -a row_keys=()
  local -a row_packages=()
  local -a row_services=()
  local -a zenity_args=()
  local -a picked=()
  local -A chosen_map=()
  local -A pkg_set=()
  local -A svc_set=()

  scan_output="$(debloat_gui_export || true)"
  if [[ -z "$scan_output" ]]; then
    ok "Debloat scan found no recommended candidates"
    return 0
  fi

  while IFS=$'\t' read -r key title packages services; do
    [[ -z "$key" ]] && continue
    row_keys+=("$key")
    row_packages+=("$packages")
    row_services+=("$services")
    zenity_args+=(TRUE "$key" "$title" "${packages:--}" "${services:--}")
  done <<<"$scan_output"
  append_gui_evidence "debloat_scan.tsv" "$scan_output"

  if [[ "${#row_keys[@]}" -eq 0 ]]; then
    ok "Debloat scan found no recommended candidates"
    return 0
  fi

  if command -v zenity >/dev/null 2>&1; then
    selected="$(
      zenity --list --checklist \
        --title="Debloat Recommendations" \
        --text="Recommended candidates are preselected. Review and continue to generate removal command." \
        --separator="|" \
        --column="Pick" --column="Key" --column="Component" --column="Packages" --column="Services" \
        "${zenity_args[@]}"
    )" || {
      warn "Debloat GUI review canceled"
      return 0
    }
  elif command -v whiptail >/dev/null 2>&1; then
    local -a whiptail_args=()
    local desc=""
    for ((idx = 0; idx < ${#row_keys[@]}; idx++)); do
      desc="pkgs:${row_packages[$idx]:--none} svcs:${row_services[$idx]:--none}"
      whiptail_args+=("${row_keys[$idx]}" "$desc" ON)
    done
    selected="$(
      whiptail --title "Debloat Recommendations" --checklist \
        "Recommended candidates are preselected. Review and continue to generate removal command." 22 110 12 \
        "${whiptail_args[@]}" \
        3>&1 1>&2 2>&3
    )" || {
      warn "Debloat GUI review canceled"
      return 0
    }
    selected="$(printf '%s' "$selected" | tr -d '"')"
    selected="$(printf '%s' "$selected" | tr ' ' '|')"
  else
    warn "No GUI backend available for debloat review; using CLI report"
    run_debloat_scan
    return 0
  fi

  if [[ -z "$selected" ]]; then
    warn "No debloat candidates selected; skipping removal command generation"
    append_gui_evidence "debloat_selected.txt" "<none>"
    return 0
  fi

  append_gui_evidence "debloat_selected.txt" "$selected"

  IFS='|' read -r -a picked <<<"$selected"
  for key in "${picked[@]}"; do
    chosen_map["$key"]=1
  done

  for ((idx = 0; idx < ${#row_keys[@]}; idx++)); do
    key="${row_keys[$idx]}"
    if [[ -z "${chosen_map[$key]:-}" ]]; then
      continue
    fi
    IFS=',' read -r -a pkgs <<<"${row_packages[$idx]}"
    for p in "${pkgs[@]}"; do
      p="$(printf '%s' "$p" | xargs)"
      [[ -n "$p" ]] && pkg_set["$p"]=1
    done
    IFS=',' read -r -a svcs <<<"${row_services[$idx]}"
    for s in "${svcs[@]}"; do
      s="$(printf '%s' "$s" | xargs)"
      [[ -n "$s" ]] && svc_set["$s"]=1
    done
  done

  if [[ "${#pkg_set[@]}" -gt 0 ]]; then
    purge_cmd="sudo apt-get purge -y"
    for p in "${!pkg_set[@]}"; do
      purge_cmd+=" $p"
    done
    purge_cmd+=" && sudo apt-get autoremove -y"
  fi

  if [[ "${#svc_set[@]}" -gt 0 ]]; then
    disable_cmd="sudo systemctl disable --now"
    for s in "${!svc_set[@]}"; do
      disable_cmd+=" $s"
    done
  fi

  if [[ -n "$purge_cmd" && -n "$disable_cmd" ]]; then
    full_cmd="$purge_cmd"$'\n'"$disable_cmd"
  elif [[ -n "$purge_cmd" ]]; then
    full_cmd="$purge_cmd"
  else
    full_cmd="$disable_cmd"
  fi

  if [[ -z "$full_cmd" ]]; then
    warn "Selected candidates produced no executable command"
    append_gui_evidence "debloat_command.txt" "<none>"
    return 0
  fi
  append_gui_evidence "debloat_command.txt" "$full_cmd"

  if command -v zenity >/dev/null 2>&1; then
    if ! zenity --question --width=900 --title="Confirm Debloat Command" \
      --text="Generated removal command:\n\n$full_cmd\n\nExecute now with sudo?"; then
      warn "Debloat command not executed by operator choice"
      append_gui_evidence "debloat_execute_decision.txt" "declined"
      return 0
    fi
  elif command -v whiptail >/dev/null 2>&1; then
    if ! whiptail --yesno "Generated removal command:\n\n$full_cmd\n\nExecute now with sudo?" 22 110; then
      warn "Debloat command not executed by operator choice"
      append_gui_evidence "debloat_execute_decision.txt" "declined"
      return 0
    fi
  fi

  append_gui_evidence "debloat_execute_decision.txt" "approved"
  log "Executing operator-confirmed debloat command(s)..."
  if [[ -n "$purge_cmd" ]]; then
    eval "$purge_cmd"
  fi
  if [[ -n "$disable_cmd" ]]; then
    eval "$disable_cmd"
  fi
  ok "Debloat GUI command execution complete"
}

resolve_python_cmd() {
  cd "$SCRIPT_DIR"
  if [[ -x ".venv/bin/python" ]]; then
    printf '%s' ".venv/bin/python"
    return 0
  fi
  if [[ -x "venv/bin/python" ]]; then
    printf '%s' "venv/bin/python"
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "python3"
    return 0
  fi
  return 1
}

python_runtime_import_check() {
  local python_cmd="$1"
  "$python_cmd" - <<'PY' >/dev/null 2>&1
import packaging
import pydantic
import rich
import typer
import yaml
PY
}

ensure_python_runtime_ready() {
  local requirements_path="$SCRIPT_DIR/$PY_REQUIREMENTS_FILE"
  local python_cmd=""
  local host_python=""

  [[ "$PY_RUNTIME_READY" == "1" ]] && return 0
  [[ -f "$requirements_path" ]] || die "Python requirements file missing: $requirements_path"

  cd "$SCRIPT_DIR"

  if [[ -x ".venv/bin/python" ]]; then
    python_cmd=".venv/bin/python"
  else
    host_python="$(command -v python3 || true)"
    [[ -n "$host_python" ]] || die "python3 is required to bootstrap sec_bootstrapper runtime"
    log "Creating local virtual environment: $SCRIPT_DIR/.venv"
    "$host_python" -m venv .venv
    python_cmd=".venv/bin/python"
  fi

  if python_runtime_import_check "$python_cmd"; then
    PY_RUNTIME_READY="1"
    return 0
  fi

  log "Installing Python dependencies from ${PY_REQUIREMENTS_FILE}..."
  "$python_cmd" -m ensurepip --upgrade >/dev/null 2>&1 || true
  "$python_cmd" -m pip install --upgrade pip >/dev/null
  "$python_cmd" -m pip install -r "$requirements_path"

  if ! python_runtime_import_check "$python_cmd"; then
    die "Python dependency bootstrap failed; verify pip network/index access and ${PY_REQUIREMENTS_FILE}"
  fi

  PY_RUNTIME_READY="1"
  ok "Python runtime dependencies ready (.venv)"
}

run_stage_bridge() {
  local stage="$1"
  local accept_flag="${2:-no}"
  local python_cmd=""

  ensure_python_runtime_ready
  if ! python_cmd="$(resolve_python_cmd)"; then
    warn "Skipping stage ${stage}: Python runtime not found"
    return 0
  fi

  log "Executing sec-bootstrapper ${stage} using ${EFFECTIVE_STAGE_CONFIG}..."
  if [[ "$accept_flag" == "yes" ]]; then
    sudo "$python_cmd" -m sec_bootstrapper.cli.main run --stage "$stage" --phase server --config "$EFFECTIVE_STAGE_CONFIG" --accept-stage || {
      warn "Stage ${stage} failed in bridge flow"
      return 1
    }
  else
    sudo "$python_cmd" -m sec_bootstrapper.cli.main run --stage "$stage" --phase server --config "$EFFECTIVE_STAGE_CONFIG" || {
      warn "Stage ${stage} failed in bridge flow"
      return 1
    }
  fi

  ok "Stage ${stage} completed"
}

run_requested_stages() {
  local requested="ask"
  local progression_selected="no"
  local python_cmd=""
  local stage_statuses=""
  local stage1_status="pending"
  local stage2_status="pending"
  local stage3_status="pending"
  if [[ "$RUN_STAGE1" == "yes" || "$RUN_STAGE2" == "yes" || "$RUN_STAGE3" == "yes" ]]; then
    requested="yes"
  elif [[ "$RUN_STAGE1" == "no" && "$RUN_STAGE2" == "no" && "$RUN_STAGE3" == "no" ]]; then
    requested="no"
  fi

  if [[ "$requested" == "ask" ]]; then
    stage_statuses="$(stage_status_triplet)"
    IFS='|' read -r stage1_status stage2_status stage3_status <<<"$stage_statuses"

    if stage_is_complete "$stage2_status" && ! stage_is_complete "$stage3_status"; then
      if confirm_or_continue "Stage 2 is complete. Run Stage 3 validation now?"; then
        RUN_STAGE1="no"
        RUN_STAGE2="no"
        RUN_STAGE3="yes"
        progression_selected="yes"
      else
        return 0
      fi
    elif stage_is_complete "$stage1_status" && ! stage_is_complete "$stage2_status"; then
      if confirm_or_continue "Baseline complete. Run Stage 2 Docker hardening now?"; then
        RUN_STAGE1="no"
        RUN_STAGE2="yes"
        RUN_STAGE3="no"
        progression_selected="yes"
      else
        return 0
      fi
    elif stage_is_complete "$stage3_status"; then
      ok "Stage gate already shows Stage 3 complete; skipping stage bridge prompt"
      return 0
    fi

    if [[ "$progression_selected" != "yes" ]]; then
      if [[ "$NON_INTERACTIVE" == "1" ]]; then
        return 0
      fi
      if confirm_or_continue "Baseline complete. Run stage bridge now (stage1->stage2->stage3)?"; then
        RUN_STAGE1="yes"
        RUN_STAGE2="yes"
        RUN_STAGE3="yes"
      else
        return 0
      fi
    fi
  elif [[ "$requested" == "no" ]]; then
    return 0
  fi

  if [[ "$RUN_STAGE1" == "yes" ]]; then
    run_stage_bridge stage1 yes || return 1
  fi
  if [[ "$RUN_STAGE2" == "yes" ]]; then
    run_stage_bridge stage2 yes || return 1
  fi
  if [[ "$RUN_STAGE3" == "yes" ]]; then
    run_stage_bridge stage3 no || return 1
  fi

  if ! python_cmd="$(resolve_python_cmd)"; then
    warn "Skipping stage-status summary: Python runtime not found"
    return 0
  fi

  cd "$SCRIPT_DIR"
  log "Final gate status:"
  sudo "$python_cmd" -m sec_bootstrapper.cli.main stage-status --config "$EFFECTIVE_STAGE_CONFIG" || true
}

resolve_docker_bridge_script() {
  if [[ -n "$DOCKER_SCRIPT_PATH" ]]; then
    printf '%s' "$DOCKER_SCRIPT_PATH"
    return 0
  fi
  if [[ -f "$SCRIPT_DIR/artifacts/docker/bootstrap_docker_plus.sh" ]]; then
    printf '%s' "$SCRIPT_DIR/artifacts/docker/bootstrap_docker_plus.sh"
    return 0
  fi
  if [[ -f "$SCRIPT_DIR/bootstrap_docker_plus.sh" ]]; then
    printf '%s' "$SCRIPT_DIR/bootstrap_docker_plus.sh"
    return 0
  fi
  return 1
}

run_docker_script_bridge() {
  local bridge_script=""
  local bridge_output=""
  local bridge_status=0
  if ! bridge_script="$(resolve_docker_bridge_script)"; then
    warn "Docker script bridge requested but no script was found"
    return 1
  fi
  log "Running Docker hardening script bridge: $bridge_script"

  set +e
  bridge_output="$(sudo bash "$bridge_script" 2>&1)"
  bridge_status=$?
  set -e
  printf '%s\n' "$bridge_output"

  if [[ "$bridge_status" -ne 0 ]]; then
    warn "Docker hardening script bridge failed (exit=$bridge_status)"
    return 1
  fi

  if printf '%s\n' "$bridge_output" | grep -Eqi 'jq:\s*parse error|error:'; then
    warn "Docker hardening script bridge reported parse/error output; treating as failed"
    return 1
  fi

  if sudo test -f /etc/docker/daemon.json; then
    if command -v jq >/dev/null 2>&1; then
      if ! sudo jq empty /etc/docker/daemon.json >/dev/null 2>&1; then
        warn "Docker daemon.json is not valid JSON after bridge run"
        return 1
      fi
    elif command -v python3 >/dev/null 2>&1; then
      if ! sudo python3 - <<'PY' >/dev/null 2>&1
import json
from pathlib import Path
json.loads(Path("/etc/docker/daemon.json").read_text())
PY
      then
        warn "Docker daemon.json failed JSON validation after bridge run"
        return 1
      fi
    fi
  fi

  ok "Docker hardening script bridge complete"
}

run_ai_image_bridge() {
  local compose_file="$COMPOSE_FILE_PATH"
  local compat_compose_file="$SCRIPT_DIR/artifacts/docker/compose.secure-ollama-opencode.v1.yml"
  local env_file="$COMPOSE_ENV_FILE_PATH"
  local images_csv="${AI_IMAGES_CSV:-ollama,opencode,claude,openclaw,openvscode,grype}"
  local default_opencode_image="ghcr.io/pilinux/opencode:1.2.15"
  local default_ollama_image="ollama/ollama:latest"
  local default_claude_image="ghcr.io/anthropic-ai/claude-code:latest"
  local default_openclaw_image="ghcr.io/openclaw/openclaw:latest"
  local default_openvscode_image="gitpod/openvscode-server:latest"
  local default_grype_image="anchore/grype:latest"
  local default_grype_fallback="ghcr.io/anchore/grype:latest"
  local default_claude_fallbacks="docker.io/anthropic-ai/claude-code:latest,ghcr.io/anthropic/claude-code:latest"
  local default_openclaw_fallbacks="docker.io/openclaw/openclaw:latest"
  local default_openvscode_fallbacks="ghcr.io/gitpod-io/openvscode-server:latest"
  local default_opencode_fallbacks="ghcr.io/opencode-ai/opencode:latest,docker.io/opencode-ai/opencode:latest,docker.io/opencodeai/opencode:latest"
  local token=""
  local image_key=""
  local local_env_opencode=""
  local local_env_ollama=""
  local local_env_claude=""
  local local_env_openclaw=""
  local local_env_openvscode=""
  local local_env_opencode_fallbacks=""
  local local_env_ollama_fallbacks=""
  local local_env_claude_fallbacks=""
  local local_env_openclaw_fallbacks=""
  local local_env_openvscode_fallbacks=""
  local local_env_grype=""
  local local_env_grype_fallbacks=""
  local opencode_primary=""
  local ollama_primary=""
  local claude_primary=""
  local openclaw_primary=""
  local openvscode_primary=""
  local grype_primary=""
  local opencode_fallbacks_csv=""
  local ollama_fallbacks_csv=""
  local claude_fallbacks_csv=""
  local openclaw_fallbacks_csv=""
  local openvscode_fallbacks_csv=""
  local grype_fallbacks_csv=""
  local compose_mode=""
  local compose_pull_output=""
  local compose_pull_status=0
  local docker_pull_output=""
  local docker_pull_status=0
  local LAST_IMAGE_SOURCE=""
  local selected_source=""
  local selected_ollama_source=""
  local selected_opencode_source=""
  local selected_claude_source=""
  local selected_openclaw_source=""
  local selected_openvscode_source=""
  local selected_grype_source=""
  local required_ref=""
  local pull_failures=0
  local candidate=""
  local -a opencode_candidates=()
  local -a ollama_candidates=()
  local -a claude_candidates=()
  local -a openclaw_candidates=()
  local -a openvscode_candidates=()
  local -a grype_candidates=()
  local compose_args=()
  local -a parsed_images=()
  local -a compose_targets=()
  local -a requested_optional=()
  local -a source_tokens=()
  local -a mandatory_keys=(ollama opencode claude openclaw openvscode grype)
  local -A source_seen=()
  local -A requested_map=()

  normalize_image_key() {
    local raw="$1"
    local lower=""
    lower="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
    case "$lower" in
      ollama) printf '%s' "ollama" ;;
      opencode) printf '%s' "opencode" ;;
      claude) printf '%s' "claude" ;;
      openclaw) printf '%s' "openclaw" ;;
      openvscode|vscode|gitpod/openvscode-server) printf '%s' "openvscode" ;;
      grype) printf '%s' "grype" ;;
      *) printf '%s' "" ;;
    esac
  }

  join_csv() {
    local -a values=("$@")
    local item=""
    local output=""
    for item in "${values[@]}"; do
      if [[ -z "$output" ]]; then
        output="$item"
      else
        output="${output},${item}"
      fi
    done
    printf '%s' "$output"
  }

  read_env_value() {
    local key="$1"
    local file_path="$2"
    [[ -n "$file_path" && -f "$file_path" ]] || return 1
    awk -F= -v key="$key" '
      BEGIN { found=0 }
      /^[[:space:]]*#/ { next }
      index($0, "=") == 0 { next }
      {
        k=$1
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
        if (k == key) {
          v=substr($0, index($0, "=") + 1)
          gsub(/^[[:space:]]+|[[:space:]]+$/, "", v)
          gsub(/^"|"$/, "", v)
          print v
          found=1
          exit
        }
      }
      END { if (!found) exit 1 }
    ' "$file_path"
  }

  append_source_list() {
    local csv="$1"
    local item=""
    [[ -z "$csv" ]] && return 0
    IFS=',' read -r -a source_tokens <<<"$csv"
    for item in "${source_tokens[@]}"; do
      item="$(printf '%s' "$item" | xargs)"
      [[ -z "$item" ]] && continue
      if [[ -z "${source_seen[$item]:-}" ]]; then
        source_seen["$item"]=1
        printf '%s\n' "$item"
      fi
    done
  }

  compose_pull_service_with_image() {
    local service="$1"
    local image_var="$2"
    local image_ref="$3"

    set +e
    if [[ "$compose_mode" == "v2" ]]; then
      compose_pull_output="$(sudo env "${image_var}=${image_ref}" docker compose "${compose_args[@]}" -f "$compose_file" pull "$service" 2>&1)"
    else
      compose_pull_output="$(sudo env "${image_var}=${image_ref}" docker-compose "${compose_args[@]}" -f "$compose_file" pull "$service" 2>&1)"
    fi
    compose_pull_status=$?
    set -e
    printf '%s\n' "$compose_pull_output"
    return "$compose_pull_status"
  }

  compose_pull_with_fallback_chain() {
    local service="$1"
    local image_var="$2"
    shift 2
    local -a candidates=("$@")
    local src=""

    for src in "${candidates[@]}"; do
      log "Pulling ${service} candidate: ${src}"
      if compose_pull_service_with_image "$service" "$image_var" "$src"; then
        LAST_IMAGE_SOURCE="$src"
        return 0
      fi
      warn "${service} pull failed for ${src}"
    done
    return 1
  }

  docker_pull_with_fallback_chain() {
    local label="$1"
    shift
    local -a candidates=("$@")
    local src=""
    local inspect_status=1
    local preloaded_status=1

    for src in "${candidates[@]}"; do
      # Local-first path: if image is already staged in local daemon, use it.
      set +e
      sudo docker image inspect "$src" >/dev/null 2>&1
      preloaded_status=$?
      set -e
      if [[ "$preloaded_status" -eq 0 ]]; then
        ok "${label} source already present locally: ${src}"
        LAST_IMAGE_SOURCE="$src"
        return 0
      fi

      log "Pulling ${label} candidate: ${src}"
      set +e
      docker_pull_output="$(sudo docker pull "$src" 2>&1)"
      docker_pull_status=$?
      set -e
      printf '%s\n' "$docker_pull_output"
      # Some registries can deny pull while a preloaded image is already present.
      # Treat local presence as sufficient for runtime continuity.
      set +e
      sudo docker image inspect "$src" >/dev/null 2>&1
      inspect_status=$?
      set -e
      if [[ "$inspect_status" -eq 0 ]]; then
        if [[ "$docker_pull_status" -ne 0 ]]; then
          warn "${label} pull denied but local image is present: ${src}"
        fi
        LAST_IMAGE_SOURCE="$src"
        return 0
      fi
      warn "${label} direct pull failed for ${src}"
    done
    return 1
  }

  if [[ -z "$compose_file" ]]; then
    compose_file="$SCRIPT_DIR/artifacts/docker/compose.secure-ollama-opencode.yml"
  fi
  [[ -f "$compose_file" ]] || {
    warn "AI image bridge compose file not found: $compose_file"
    return 1
  }

  if [[ -z "$env_file" && -f "$SCRIPT_DIR/artifacts/docker/.env" ]]; then
    env_file="$SCRIPT_DIR/artifacts/docker/.env"
  fi

  if sudo docker compose version >/dev/null 2>&1; then
    compose_mode="v2"
  elif command -v docker-compose >/dev/null 2>&1; then
    compose_mode="v1"
  else
    warn "AI image bridge requires docker compose or docker-compose"
    return 1
  fi

  # docker-compose v1 cannot parse the top-level `name:` key used by modern compose files.
  if [[ "$compose_mode" == "v1" && -f "$compat_compose_file" ]]; then
    if [[ "$compose_file" == "$SCRIPT_DIR/artifacts/docker/compose.secure-ollama-opencode.yml" ]]; then
      warn "Using v1-compatible compose file for docker-compose: $compat_compose_file"
      compose_file="$compat_compose_file"
    fi
  fi

  if [[ -n "$env_file" ]]; then
    if [[ "$compose_mode" == "v2" ]]; then
      if sudo docker compose --help 2>/dev/null | grep -q -- '--env-file'; then
        compose_args+=(--env-file "$env_file")
      else
        warn "Compose CLI does not support --env-file; continuing without env file: $env_file"
      fi
    elif docker-compose --help 2>/dev/null | grep -q -- '--env-file'; then
      compose_args+=(--env-file "$env_file")
    else
      warn "Compose CLI does not support --env-file; continuing without env file: $env_file"
    fi
  fi

  local_env_ollama="${OLLAMA_IMAGE:-}"
  local_env_opencode="${OPENCODE_IMAGE:-}"
  local_env_claude="${CLAUDE_IMAGE:-}"
  local_env_openclaw="${OPENCLAW_IMAGE:-}"
  local_env_openvscode="${OPENVSCODE_IMAGE:-}"
  local_env_grype="${GRYPE_IMAGE:-}"
  local_env_ollama_fallbacks="${OLLAMA_IMAGE_FALLBACKS:-}"
  local_env_opencode_fallbacks="${OPENCODE_IMAGE_FALLBACKS:-}"
  local_env_claude_fallbacks="${CLAUDE_IMAGE_FALLBACKS:-}"
  local_env_openclaw_fallbacks="${OPENCLAW_IMAGE_FALLBACKS:-}"
  local_env_openvscode_fallbacks="${OPENVSCODE_IMAGE_FALLBACKS:-}"
  local_env_grype_fallbacks="${GRYPE_IMAGE_FALLBACKS:-}"

  if [[ -z "$local_env_ollama" ]]; then
    local_env_ollama="$(read_env_value "OLLAMA_IMAGE" "$env_file" || true)"
  fi
  if [[ -z "$local_env_opencode" ]]; then
    local_env_opencode="$(read_env_value "OPENCODE_IMAGE" "$env_file" || true)"
  fi
  if [[ -z "$local_env_claude" ]]; then
    local_env_claude="$(read_env_value "CLAUDE_IMAGE" "$env_file" || true)"
  fi
  if [[ -z "$local_env_openclaw" ]]; then
    local_env_openclaw="$(read_env_value "OPENCLAW_IMAGE" "$env_file" || true)"
  fi
  if [[ -z "$local_env_openvscode" ]]; then
    local_env_openvscode="$(read_env_value "OPENVSCODE_IMAGE" "$env_file" || true)"
  fi
  if [[ -z "$local_env_grype" ]]; then
    local_env_grype="$(read_env_value "GRYPE_IMAGE" "$env_file" || true)"
  fi
  if [[ -z "$local_env_ollama_fallbacks" ]]; then
    local_env_ollama_fallbacks="$(read_env_value "OLLAMA_IMAGE_FALLBACKS" "$env_file" || true)"
  fi
  if [[ -z "$local_env_opencode_fallbacks" ]]; then
    local_env_opencode_fallbacks="$(read_env_value "OPENCODE_IMAGE_FALLBACKS" "$env_file" || true)"
  fi
  if [[ -z "$local_env_claude_fallbacks" ]]; then
    local_env_claude_fallbacks="$(read_env_value "CLAUDE_IMAGE_FALLBACKS" "$env_file" || true)"
  fi
  if [[ -z "$local_env_openclaw_fallbacks" ]]; then
    local_env_openclaw_fallbacks="$(read_env_value "OPENCLAW_IMAGE_FALLBACKS" "$env_file" || true)"
  fi
  if [[ -z "$local_env_openvscode_fallbacks" ]]; then
    local_env_openvscode_fallbacks="$(read_env_value "OPENVSCODE_IMAGE_FALLBACKS" "$env_file" || true)"
  fi
  if [[ -z "$local_env_grype_fallbacks" ]]; then
    local_env_grype_fallbacks="$(read_env_value "GRYPE_IMAGE_FALLBACKS" "$env_file" || true)"
  fi

  ollama_primary="${local_env_ollama:-$default_ollama_image}"
  opencode_primary="${local_env_opencode:-$default_opencode_image}"
  claude_primary="${local_env_claude:-$default_claude_image}"
  openclaw_primary="${local_env_openclaw:-$default_openclaw_image}"
  openvscode_primary="${local_env_openvscode:-$default_openvscode_image}"
  grype_primary="${local_env_grype:-$default_grype_image}"
  ollama_fallbacks_csv="$local_env_ollama_fallbacks"
  opencode_fallbacks_csv="${local_env_opencode_fallbacks:-$default_opencode_fallbacks}"
  claude_fallbacks_csv="${local_env_claude_fallbacks:-$default_claude_fallbacks}"
  openclaw_fallbacks_csv="${local_env_openclaw_fallbacks:-$default_openclaw_fallbacks}"
  openvscode_fallbacks_csv="${local_env_openvscode_fallbacks:-$default_openvscode_fallbacks}"
  grype_fallbacks_csv="${local_env_grype_fallbacks:-$default_grype_fallback}"

  IFS=',' read -r -a parsed_images <<<"$images_csv"
  for token in "${parsed_images[@]}"; do
    token="$(printf '%s' "$token" | xargs)"
    [[ -z "$token" ]] && continue
    image_key="$(normalize_image_key "$token")"
    if [[ -n "$image_key" ]]; then
      requested_map["$image_key"]=1
    else
      requested_optional+=("$token")
    fi
  done

  # Required defaults are always enforced, regardless of optional CSV.
  for image_key in "${mandatory_keys[@]}"; do
    requested_map["$image_key"]=1
  done

  for token in "${requested_optional[@]}"; do
    compose_targets+=("$token")
  done

  log "Pulling AI images from compose bridge: $compose_file"
  if [[ "${#compose_targets[@]}" -gt 0 ]]; then
    if [[ "$compose_mode" == "v2" ]]; then
      if ! sudo docker compose "${compose_args[@]}" -f "$compose_file" pull "${compose_targets[@]}"; then
        warn "AI image bridge pull failed"
        return 1
      fi
    elif ! sudo docker-compose "${compose_args[@]}" -f "$compose_file" pull "${compose_targets[@]}"; then
      warn "AI image bridge pull failed"
      return 1
    fi
  fi

  if [[ -n "${requested_map[ollama]:-}" ]]; then
    source_seen=()
    mapfile -t ollama_candidates < <(
      append_source_list "$ollama_primary"
      append_source_list "$ollama_fallbacks_csv"
    )
    if [[ "${#ollama_candidates[@]}" -eq 0 ]]; then
      ollama_candidates=("$default_ollama_image")
    fi
    if ! compose_pull_with_fallback_chain "ollama" "OLLAMA_IMAGE" "${ollama_candidates[@]}"; then
      warn "AI image bridge pull failed"
      return 1
    fi
    selected_source="$LAST_IMAGE_SOURCE"
    selected_ollama_source="$selected_source"
    if [[ "$selected_ollama_source" != "$ollama_primary" ]]; then
      sudo docker tag "$selected_ollama_source" "$ollama_primary"
      ok "Retagged ollama fallback to canonical reference: $ollama_primary"
    fi
    ok "Selected ollama image source: $selected_source"
  fi

  if [[ -n "${requested_map[opencode]:-}" ]]; then
    source_seen=()
    mapfile -t opencode_candidates < <(
      append_source_list "$opencode_primary"
      append_source_list "$opencode_fallbacks_csv"
    )
    if [[ "${#opencode_candidates[@]}" -eq 0 ]]; then
      opencode_candidates=("$default_opencode_image")
    fi
    if ! compose_pull_with_fallback_chain "opencode" "OPENCODE_IMAGE" "${opencode_candidates[@]}"; then
      warn "AI image bridge pull failed"
      return 1
    fi
    selected_source="$LAST_IMAGE_SOURCE"
    selected_opencode_source="$selected_source"
    if [[ "$selected_opencode_source" != "$opencode_primary" ]]; then
      sudo docker tag "$selected_opencode_source" "$opencode_primary"
      ok "Retagged opencode fallback to canonical reference: $opencode_primary"
    fi
    ok "Selected opencode image source: $selected_source"
  fi

  if [[ -n "${requested_map[claude]:-}" ]]; then
    source_seen=()
    mapfile -t claude_candidates < <(
      append_source_list "$claude_primary"
      append_source_list "$claude_fallbacks_csv"
    )
    if [[ "${#claude_candidates[@]}" -eq 0 ]]; then
      claude_candidates=("$default_claude_image")
    fi
    if ! docker_pull_with_fallback_chain "claude" "${claude_candidates[@]}"; then
      warn "AI image bridge direct pull failed for claude; attempted sources: $(join_csv "${claude_candidates[@]}")"
      pull_failures=1
    else
      selected_source="$LAST_IMAGE_SOURCE"
      selected_claude_source="$selected_source"
      if [[ "$selected_claude_source" != "$claude_primary" ]]; then
        sudo docker tag "$selected_claude_source" "$claude_primary"
        ok "Retagged claude fallback to canonical reference: $claude_primary"
      fi
      ok "Selected claude image source: $selected_source"
    fi
  fi

  if [[ -n "${requested_map[openclaw]:-}" ]]; then
    source_seen=()
    mapfile -t openclaw_candidates < <(
      append_source_list "$openclaw_primary"
      append_source_list "$openclaw_fallbacks_csv"
    )
    if [[ "${#openclaw_candidates[@]}" -eq 0 ]]; then
      openclaw_candidates=("$default_openclaw_image")
    fi
    if ! docker_pull_with_fallback_chain "openclaw" "${openclaw_candidates[@]}"; then
      warn "AI image bridge direct pull failed for openclaw; attempted sources: $(join_csv "${openclaw_candidates[@]}")"
      pull_failures=1
    else
      selected_source="$LAST_IMAGE_SOURCE"
      selected_openclaw_source="$selected_source"
      if [[ "$selected_openclaw_source" != "$openclaw_primary" ]]; then
        sudo docker tag "$selected_openclaw_source" "$openclaw_primary"
        ok "Retagged openclaw fallback to canonical reference: $openclaw_primary"
      fi
      ok "Selected openclaw image source: $selected_source"
    fi
  fi

  if [[ -n "${requested_map[openvscode]:-}" ]]; then
    source_seen=()
    mapfile -t openvscode_candidates < <(
      append_source_list "$openvscode_primary"
      append_source_list "$openvscode_fallbacks_csv"
    )
    if [[ "${#openvscode_candidates[@]}" -eq 0 ]]; then
      openvscode_candidates=("$default_openvscode_image")
    fi
    if ! docker_pull_with_fallback_chain "openvscode" "${openvscode_candidates[@]}"; then
      warn "AI image bridge direct pull failed for openvscode; attempted sources: $(join_csv "${openvscode_candidates[@]}")"
      pull_failures=1
    else
      selected_source="$LAST_IMAGE_SOURCE"
      selected_openvscode_source="$selected_source"
      if [[ "$selected_openvscode_source" != "$openvscode_primary" ]]; then
        sudo docker tag "$selected_openvscode_source" "$openvscode_primary"
        ok "Retagged openvscode fallback to canonical reference: $openvscode_primary"
      fi
      ok "Selected openvscode image source: $selected_source"
    fi
  fi

  if [[ -n "${requested_map[grype]:-}" ]]; then
    source_seen=()
    mapfile -t grype_candidates < <(
      append_source_list "$grype_primary"
      append_source_list "$grype_fallbacks_csv"
    )
    if [[ "${#grype_candidates[@]}" -eq 0 ]]; then
      grype_candidates=("$grype_primary")
    fi
    if ! docker_pull_with_fallback_chain "grype" "${grype_candidates[@]}"; then
      warn "AI image bridge direct pull failed"
      return 1
    fi
    selected_source="$LAST_IMAGE_SOURCE"
    selected_grype_source="$selected_source"
    if [[ "$selected_grype_source" != "$grype_primary" ]]; then
      sudo docker tag "$selected_grype_source" "$grype_primary"
      ok "Retagged grype fallback to canonical reference: $grype_primary"
    fi
    ok "Selected grype image source: $selected_source"
  fi

  if [[ "$pull_failures" -ne 0 ]]; then
    warn "AI image bridge pull failed"
    return 1
  fi

  for image_key in "${mandatory_keys[@]}"; do
    case "$image_key" in
      ollama)
        required_ref="${selected_ollama_source:-${OLLAMA_IMAGE:-$ollama_primary}}"
        ;;
      opencode)
        required_ref="${selected_opencode_source:-${OPENCODE_IMAGE:-$opencode_primary}}"
        ;;
      claude)
        required_ref="${selected_claude_source:-${CLAUDE_IMAGE:-$claude_primary}}"
        ;;
      openclaw)
        required_ref="${selected_openclaw_source:-${OPENCLAW_IMAGE:-$openclaw_primary}}"
        ;;
      openvscode)
        required_ref="${selected_openvscode_source:-${OPENVSCODE_IMAGE:-$openvscode_primary}}"
        ;;
      grype)
        required_ref="${selected_grype_source:-${GRYPE_IMAGE:-$grype_primary}}"
        ;;
    esac
    if ! sudo docker image inspect "$required_ref" >/dev/null 2>&1; then
      warn "Mandatory image not present after pull bridge: $required_ref"
      return 1
    fi
  done

  ok "AI image bridge pull complete"
}

run_follow_on_bridges() {
  if [[ "$RUN_DOCKER_SCRIPT" == "ask" ]]; then
    if confirm_or_continue "Run follow-on Docker hardening script bridge now?"; then
      RUN_DOCKER_SCRIPT="yes"
    else
      RUN_DOCKER_SCRIPT="no"
    fi
  fi
  if [[ "$RUN_DOCKER_SCRIPT" == "yes" ]]; then
    run_docker_script_bridge || return 1
  fi

  if [[ "$INSTALL_AI_IMAGES" == "ask" ]]; then
    if confirm_or_continue "Pull Ollama + Opencode + Claude + OpenClaw + OpenVSCode + Grype images now (compose bridge)?"; then
      INSTALL_AI_IMAGES="yes"
    else
      INSTALL_AI_IMAGES="no"
    fi
  fi
  if [[ "$INSTALL_AI_IMAGES" == "yes" ]]; then
    run_ai_image_bridge || return 1
  fi
}

should_generate_keys() {
  if [[ "$GENERATE_KEYS" == "yes" ]]; then
    return 0
  fi
  if [[ "$GENERATE_KEYS" == "no" ]]; then
    return 1
  fi
  # Default behavior: if remote steps are skipped, skip key generation.
  if [[ "$SKIP_REMOTE" == "1" ]]; then
    return 1
  fi
  return 0
}

derive_alias() {
  local raw="${HOST:-target}"
  # Keep it simple and shell-safe for ssh config Host alias.
  raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9._-]/-/g')"
  printf '%s' "${raw:-target}"
}

prompt_alias_if_missing() {
  [[ "$SKIP_REMOTE" == "1" ]] && return 0
  [[ -n "$ALIAS_NAME" ]] && return 0

  local suggested
  suggested="$(derive_alias)"

  if [[ "$NON_INTERACTIVE" == "1" ]]; then
    ALIAS_NAME="$suggested"
    warn "--alias not provided in --yes mode; using derived alias: $ALIAS_NAME"
    return 0
  fi

  read -r -p "SSH alias for ~/.ssh/config [${suggested}]: " ans
  ALIAS_NAME="${ans:-$suggested}"
}

confirm_or_continue() {
  local msg="$1"
  if [[ "$NON_INTERACTIVE" == "1" ]]; then
    return 0
  fi
  read -r -p "$msg [y/N]: " ans
  [[ "${ans:-}" =~ ^[Yy]$ ]]
}

ensure_sudo() {
  if ! command -v sudo >/dev/null 2>&1; then
    die "sudo is required"
  fi
  sudo -v
}

install_packages_debian() {
  local base_packages=(
    curl wget git ca-certificates gnupg openssh-client
    python3 python3-pip python3-venv ufw fail2ban firejail ripgrep
  )
  log "Installing packages (Debian/Ubuntu)..."
  sudo apt-get update
  sudo apt-get install -y "${base_packages[@]}"

  # npm frequently conflicts with NodeSource nodejs on Pop!_OS/Ubuntu derivatives.
  # Keep baseline non-blocking and only attempt npm when absent.
  if command -v npm >/dev/null 2>&1; then
    ok "npm already present: $(command -v npm)"
  else
    warn "npm not found; attempting optional install (non-blocking)"
    if sudo apt-get install -y npm; then
      ok "Installed npm via apt"
    else
      warn "Skipping npm install due dependency conflicts; continuing"
    fi
  fi

  log "Installing Docker + Compose (with distro fallback)..."
  if sudo apt-get install -y docker.io docker-compose-plugin; then
    ok "Installed docker.io + docker-compose-plugin"
    return 0
  fi

  warn "docker-compose-plugin not available; trying docker-compose package"
  if sudo apt-get install -y docker.io docker-compose; then
    ok "Installed docker.io + docker-compose"
    return 0
  fi

  warn "Compose packages unavailable; installing docker.io only"
  sudo apt-get install -y docker.io
}

install_packages_fedora() {
  local packages=(
    curl wget git ca-certificates gnupg2 openssh-clients
    python3 python3-pip npm firejail fail2ban ripgrep
    docker docker-compose-plugin
  )
  log "Installing packages (Fedora/RHEL-family)..."
  sudo dnf install -y "${packages[@]}"
}

resolve_or_sync_tool_from_manifest_cache() {
  local tool_name="$1"

  [[ -f "$TOOLS_MANIFEST" ]] || return 1
  command -v python3 >/dev/null 2>&1 || return 1

  # Run as root so /tools cache can be updated when manifest has a valid URL.
  sudo PYTHONPATH="$SCRIPT_DIR" python3 - "$tool_name" "$TOOLS_MANIFEST" "$TOOLS_CACHE_ROOT" <<'PY'
import sys
from pathlib import Path

tool_name = sys.argv[1]
manifest_path = Path(sys.argv[2])
cache_root = Path(sys.argv[3])

try:
    from sec_bootstrapper.core.tool_cache import ToolCacheManager

    manager = ToolCacheManager(
        manifest_file=manifest_path,
        cache_root=cache_root,
        fallback_root=cache_root,
        allow_download=True,
    )
    path = manager.resolve(tool_name)
    print(path)
except Exception:
    sys.exit(1)
PY
}

install_ctop() {
  log "Installing ctop (container monitoring TUI)..."

  if command -v ctop >/dev/null 2>&1; then
    ok "ctop already present: $(command -v ctop)"
    return 0
  fi

  # Cache-first install path: use /tools + manifest (version/sha validation)
  local cached_path=""
  if cached_path="$(resolve_or_sync_tool_from_manifest_cache ctop)"; then
    if [[ -f "$cached_path" ]]; then
      log "Using cached ctop artifact: $cached_path"
      sudo install -m 0755 "$cached_path" /usr/local/bin/ctop
      if command -v ctop >/dev/null 2>&1; then
        ok "Installed ctop from tool cache"
        return 0
      fi
    fi
  fi

  warn "No valid cached ctop artifact found in /tools manifest path; falling back to package manager"

  local distro=""
  local distro_like=""
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    distro="${ID:-}"
    distro_like="${ID_LIKE:-}"
  fi

  case "$distro" in
    ubuntu|debian|parrot|pop)
      if sudo apt-get install -y ctop; then
        if command -v ctop >/dev/null 2>&1; then
          ok "Installed ctop"
          return 0
        fi
      fi
      ;;
    fedora|rhel|centos|rocky|almalinux)
      if sudo dnf install -y ctop; then
        if command -v ctop >/dev/null 2>&1; then
          ok "Installed ctop"
          return 0
        fi
      fi
      ;;
    *)
      if [[ " ${distro_like} " == *" debian "* ]]; then
        if sudo apt-get install -y ctop; then
          if command -v ctop >/dev/null 2>&1; then
            ok "Installed ctop"
            return 0
          fi
        fi
      else
        warn "Unsupported distro for ctop auto-install: ${distro:-unknown}"
      fi
      ;;
  esac

  warn "Native ctop package unavailable; installing Docker-backed ctop wrapper"
  sudo tee /usr/local/bin/ctop >/dev/null <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec docker run --rm -it \
  --name ctop \
  -v /var/run/docker.sock:/var/run/docker.sock \
  quay.io/vektorlab/ctop:latest "$@"
EOF
  sudo chmod 0755 /usr/local/bin/ctop

  if command -v ctop >/dev/null 2>&1; then
    ok "Installed Docker-backed ctop wrapper at /usr/local/bin/ctop"
    return 0
  fi

  warn "ctop could not be installed automatically"
}

install_core_apps() {
  local distro=""
  local distro_like=""
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    distro="${ID:-}"
    distro_like="${ID_LIKE:-}"
  fi

  case "$distro" in
    ubuntu|debian|parrot|pop)
      install_packages_debian
      ;;
    fedora|rhel|centos|rocky|almalinux)
      install_packages_fedora
      ;;
    *)
      if [[ " ${distro_like} " == *" debian "* ]]; then
        install_packages_debian
      elif [[ " ${distro_like} " == *" fedora "* || " ${distro_like} " == *" rhel "* ]]; then
        install_packages_fedora
      else
        die "Unsupported distro for this easy script: ${distro:-unknown}"
      fi
      ;;
  esac

  install_ctop

  log "Enabling Docker service..."
  sudo systemctl enable --now docker || warn "Could not enable/start docker via systemd"
  sudo usermod -aG docker "$USER" || warn "Could not add $USER to docker group"
  ok "Core apps + Docker install step completed"
}

ensure_ssh_dir() {
  mkdir -p "$HOME/.ssh"
  chmod 700 "$HOME/.ssh"
}

create_keys() {
  ensure_ssh_dir
  log "Creating SSH keys if missing..."

  local key
  for key in "${KEY_NAMES[@]}"; do
    local path="$HOME/.ssh/$key"
    if [[ -f "$path" && -f "$path.pub" ]]; then
      ok "Key already exists: $key"
      continue
    fi

    if [[ "$key" == id_rsa_* ]]; then
      ssh-keygen -t rsa -b 4096 -f "$path" -N "" -C "sec-bootstrapper-$key"
    else
      ssh-keygen -t ed25519 -f "$path" -N "" -C "sec-bootstrapper-$key"
    fi
    ok "Created key: $key"
  done
}

print_key_inventory() {
  log "Key inventory:"
  local i=1
  local key
  for key in "${KEY_NAMES[@]}"; do
    printf '  %d) %s (%s)\n' "$i" "$key" "$HOME/.ssh/$key.pub"
    i=$((i + 1))
  done
}

write_ssh_config_block() {
  ensure_ssh_dir
  local cfg="$HOME/.ssh/config"
  local begin="# >>> T022 EASY BOOTSTRAP ${ALIAS_NAME} >>>"
  local end="# <<< T022 EASY BOOTSTRAP ${ALIAS_NAME} <<<"

  touch "$cfg"
  chmod 600 "$cfg"

  # Remove old block for this alias if present.
  awk -v b="$begin" -v e="$end" '
    $0==b {skip=1; next}
    $0==e {skip=0; next}
    !skip {print}
  ' "$cfg" > "${cfg}.tmp"
  mv "${cfg}.tmp" "$cfg"

  {
    echo "$begin"
    echo "Host ${ALIAS_NAME}"
    echo "    HostName ${HOST}"
    echo "    User ${USER_NAME}"
    echo "    Port ${PORT}"
    echo "    IdentityFile ~/.ssh/id_ed25519_bootstrap_1"
    echo "    IdentitiesOnly yes"
    echo "    StrictHostKeyChecking yes"
    echo "    UserKnownHostsFile ~/.ssh/known_hosts"
    echo "$end"
  } >> "$cfg"

  ok "Wrote SSH config block for alias '${ALIAS_NAME}' in $cfg"
}

pin_remote_host_key() {
  ensure_ssh_dir
  log "Pinning remote host key into ~/.ssh/known_hosts..."
  ssh-keyscan -p "$PORT" "$HOST" >> "$HOME/.ssh/known_hosts"
  chmod 600 "$HOME/.ssh/known_hosts"
  ok "Host key pinned for ${HOST}:${PORT}"
}

copy_pubkeys_to_remote() {
  local remote="${USER_NAME}@${HOST}"
  log "Copying all public keys to ${remote} authorized_keys..."
  local key
  for key in "${KEY_NAMES[@]}"; do
    ssh-copy-id -i "$HOME/.ssh/$key.pub" -p "$PORT" "$remote"
  done
  ok "All keys copied to remote authorized_keys"
}

print_next_steps() {
  cat <<EOF

==== DONE ====
Baseline complete.

Bridge handoff reminder:
1) Run follow-on bridge hooks if not already selected:
   ./easy_bootstrap.sh --run-docker-script --install-ai-images --skip-remote
2) Or run stage bridge directly:
   sudo .venv/bin/python -m sec_bootstrapper.cli.main run --stage stage2 --phase server --config config/config.local.yaml --accept-stage
   sudo .venv/bin/python -m sec_bootstrapper.cli.main run --stage stage3 --phase server --config config/config.local.yaml

1) Re-open your shell (or run: newgrp docker) so docker group changes apply.
2) Verify local docker:
   docker --version
   docker info
3) Verify SSH alias:
   ssh ${ALIAS_NAME} 'hostname && whoami'
4) If that works, continue with T-022 stage commands.
=============
EOF
}

main() {
  local bridge_failures=0
  parse_args "$@"
  ui_banner
  wizard_prompt_inputs
  if [[ "$SKIP_REMOTE" != "1" ]]; then
    [[ -n "$HOST" ]] || die "--host is required unless --skip-remote is set"
    [[ -n "$USER_NAME" ]] || die "--user is required unless --skip-remote is set"
  fi
  prompt_alias_if_missing
  build_effective_stage_config

  log "easy_bootstrap starting as user: $USER (HOME=$HOME)"
  ensure_sudo

  ui_step "Baseline packages and Docker"
  if confirm_or_continue "Install core apps and Docker now?"; then
    install_core_apps
  else
    warn "Skipping package install step"
  fi

  ui_step "Optional debloat review"
  if [[ "$RUN_DEBLOAT" == "yes" ]]; then
    if [[ "$USE_GUI" == "1" ]]; then
      run_debloat_gui_review
    else
      run_debloat_scan
    fi
  elif [[ "$RUN_DEBLOAT" == "ask" ]]; then
    if confirm_or_continue "Run debloat recommendation scan now?"; then
      if [[ "$USE_GUI" == "1" ]]; then
        run_debloat_gui_review
      else
        run_debloat_scan
      fi
    else
      warn "Skipping debloat recommendation scan"
    fi
  else
    warn "Debloat recommendation scan disabled via --no-debloat"
  fi

  ui_step "SSH bootstrap preparation"
  if should_generate_keys; then
    create_keys
    print_key_inventory
  else
    warn "Skipping key generation"
  fi

  if ! run_requested_stages; then
    warn "Stage bridge reported failures; review output before continuing"
    bridge_failures=1
  fi
  if ! run_follow_on_bridges; then
    warn "Follow-on bridge actions reported failures; review output before continuing"
    bridge_failures=1
  fi

  if [[ "$SKIP_REMOTE" == "1" ]]; then
    warn "--skip-remote set: skipping SSH config/known_hosts/ssh-copy-id steps"
    print_next_steps
    exit "$bridge_failures"
  fi

  write_ssh_config_block

  if confirm_or_continue "Pin remote host key to known_hosts now?"; then
    pin_remote_host_key
  else
    warn "Skipped host key pinning"
  fi

  if confirm_or_continue "Copy all 4 public keys to remote authorized_keys now?"; then
    copy_pubkeys_to_remote
  else
    warn "Skipped ssh-copy-id step"
  fi

  print_next_steps
  exit "$bridge_failures"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
