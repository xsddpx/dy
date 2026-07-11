#!/usr/bin/env zsh
set -euo pipefail

PORT="9222"
REFRESH_FROM_BROWSER=0
for arg in "$@"; do
  case "${arg}" in
    --refresh-from-browser|--refresh-profile)
      REFRESH_FROM_BROWSER=1
      ;;
    <->)
      PORT="${arg}"
      ;;
    *)
      echo "未知参数：${arg}" >&2
      echo "用法：TOOLS/open_cdp_chrome.sh [端口] [--refresh-from-browser]" >&2
      exit 64
      ;;
  esac
done
CDP_HOST="127.0.0.1"
CDP_URL="http://${CDP_HOST}:${PORT}"
TARGET_USER_DATA="${HOME}/Library/Application Support/Google/Chrome-Codex-CDP"
SOURCE_USER_DATA="${HOME}/Library/Application Support/Google/Chrome"
PROFILE_DIRECTORY="${CHROME_PROFILE_DIRECTORY:-}"
if [[ -z "${PROFILE_DIRECTORY}" ]]; then
  PROFILE_DIRECTORY="$(python3 - "${SOURCE_USER_DATA}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
state_path = root / "Local State"
candidates = []
try:
    profile = json.loads(state_path.read_text(encoding="utf-8")).get("profile", {})
    if profile.get("last_used"):
        candidates.append(profile["last_used"])
    candidates.extend(reversed(profile.get("last_active_profiles") or []))
except (OSError, ValueError, TypeError):
    pass
candidates.append("Default")
seen = set()
for name in candidates:
    if name in seen:
        continue
    seen.add(name)
    if name and (root / name / "Preferences").is_file():
        print(name)
        break
PY
)"
fi
if [[ -z "${PROFILE_DIRECTORY}" ]]; then
  echo "普通 Chrome 中没有可用 Profile，请先完成 Chrome 初始化和登录。" >&2
  exit 3
fi
SOURCE_PROFILE="${SOURCE_USER_DATA}/${PROFILE_DIRECTORY}"
CHROME_APP="/Applications/Google Chrome.app"
CURRENT_USER="$(id -un)"
REOPEN_SOURCE_CHROME=0

chrome_main_processes() {
  local processes
  if ! processes="$(ps -axo user=,pid=,command= 2>/dev/null)"; then
    echo "警告：当前环境不允许读取 Chrome 进程列表，跳过普通 Chrome 排查。" >&2
    return 0
  fi
  printf '%s\n' "${processes}" \
    | awk -v user="${CURRENT_USER}" '$1 == user {sub(/^[^ ]+[[:space:]]+/, ""); print}' \
    | grep -E '^[[:space:]]*[0-9]+[[:space:]]+/Applications/Google Chrome\.app/Contents/MacOS/Google Chrome([[:space:]]|$)' \
    | grep -v grep || true
}

target_processes() {
  chrome_main_processes | grep -- "--user-data-dir=${TARGET_USER_DATA}" | grep -- "--remote-debugging-port=${PORT}" || true
}

target_profile_listener_matches() {
  local lock_target lock_pid listener_pids
  lock_target="$(readlink "${TARGET_USER_DATA}/SingletonLock" 2>/dev/null || true)"
  lock_pid="${lock_target##*-}"
  [[ "${lock_pid}" == <-> ]] || return 1
  listener_pids="$(/usr/sbin/lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN -Fp 2>/dev/null | sed -n 's/^p//p')"
  printf '%s\n' "${listener_pids}" | grep -qx "${lock_pid}"
}

source_chrome_processes() {
  chrome_main_processes | grep -v -- "--user-data-dir=${TARGET_USER_DATA}" || true
}

activate_chrome() {
  osascript -e 'tell application "Google Chrome" to activate' >/dev/null 2>&1 || true
}

cdp_is_available() {
  curl -fsS "${CDP_URL}/json/version" >/dev/null 2>&1
}

ensure_page_target() {
  local tabs
  tabs="$(curl -fsS "${CDP_URL}/json" 2>/dev/null || true)"
  if printf '%s\n' "${tabs}" | grep -q '"type"[[:space:]]*:[[:space:]]*"page"'; then
    return
  fi
  curl -fsS -X PUT "${CDP_URL}/json/new?about%3Ablank" >/dev/null 2>&1 || true
}

copy_profile_from_source() {
  local reason backup_dir
  if [[ ! -f "${SOURCE_PROFILE}/Preferences" ]]; then
    echo "找不到源 Chrome ${PROFILE_DIRECTORY}：${SOURCE_PROFILE}" >&2
    echo "请先在普通 Chrome 中完成初始化和登录，再运行本脚本。" >&2
    exit 3
  fi

  reason="${1:-初始化}"
  if [[ "${reason}" == "refresh" && -d "${TARGET_USER_DATA}" ]]; then
    backup_dir="${TARGET_USER_DATA}.backup-$(date +%Y%m%d-%H%M%S)"
    mv "${TARGET_USER_DATA}" "${backup_dir}"
    echo "已备份旧本地 CDP Chrome 用户目录：${backup_dir}"
  fi

  if [[ "${reason}" == "refresh" ]]; then
    echo "正在从普通 Chrome ${PROFILE_DIRECTORY} 临时刷新本地 CDP Chrome 登录态和站点数据。"
  else
    echo "首次初始化本地 CDP Chrome：从普通 Chrome ${PROFILE_DIRECTORY} 复制登录态和站点数据。"
  fi
  mkdir -p "${TARGET_USER_DATA}"
  rsync -a \
    --exclude='Crashpad' \
    --exclude='GrShaderCache' \
    --exclude='ShaderCache' \
    --exclude='Code Cache' \
    --exclude='GPUCache' \
    --exclude='Singleton*' \
    "${SOURCE_USER_DATA}/Local State" \
    "${TARGET_USER_DATA}/"
  rsync -a \
    --exclude='Cache' \
    --exclude='Code Cache' \
    --exclude='GPUCache' \
    --exclude='GrShaderCache' \
    --exclude='ShaderCache' \
    --exclude='Service Worker/CacheStorage' \
    --exclude='Service Worker/ScriptCache' \
    --exclude='Sessions' \
    --exclude='Singleton*' \
    "${SOURCE_PROFILE}" \
    "${TARGET_USER_DATA}/"
}

init_profile_if_needed() {
  if [[ -f "${TARGET_USER_DATA}/${PROFILE_DIRECTORY}/Preferences" ]]; then
    return
  fi
  copy_profile_from_source "init"
}

wait_for_cdp() {
  local attempts=30
  for _ in {1..30}; do
    if cdp_is_available; then
      return 0
    fi
    sleep 1
  done
  echo "Chrome 已启动请求发出，但 ${CDP_URL} 在 ${attempts}s 内不可用。" >&2
  exit 4
}

force_close_target_chrome() {
  local lines
  lines="$(target_processes)"
  if [[ -z "${lines}" ]]; then
    return
  fi

  echo "正在关闭本地 CDP Chrome 以刷新 Profile："
  printf '%s\n' "${lines}" | sed 's/^/  /'
  printf '%s\n' "${lines}" | awk '{print $1}' | while read -r pid; do
    [[ -n "${pid}" ]] && kill "${pid}" >/dev/null 2>&1 || true
  done
  sleep 3

  lines="$(target_processes)"
  if [[ -n "${lines}" ]]; then
    echo "本地 CDP Chrome 未退出，执行强制 kill -9："
    printf '%s\n' "${lines}" | sed 's/^/  /'
    printf '%s\n' "${lines}" | awk '{print $1}' | while read -r pid; do
      [[ -n "${pid}" ]] && kill -9 "${pid}" >/dev/null 2>&1 || true
    done
    sleep 1
  fi
}

force_close_source_chrome() {
  local lines
  lines="$(source_chrome_processes)"
  if [[ -z "${lines}" ]]; then
    return
  fi

  REOPEN_SOURCE_CHROME=1
  echo "为同步 Chrome Profile，正在临时关闭普通 Chrome："
  printf '%s\n' "${lines}" | sed 's/^/  /'
  printf '%s\n' "${lines}" | awk '{print $1}' | while read -r pid; do
    [[ -n "${pid}" ]] && kill "${pid}" >/dev/null 2>&1 || true
  done
  sleep 3

  lines="$(source_chrome_processes)"
  if [[ -n "${lines}" ]]; then
    echo "普通 Chrome 仍未退出，执行强制 kill -9："
    printf '%s\n' "${lines}" | sed 's/^/  /'
    printf '%s\n' "${lines}" | awk '{print $1}' | while read -r pid; do
      [[ -n "${pid}" ]] && kill -9 "${pid}" >/dev/null 2>&1 || true
    done
    sleep 1
  fi
}

reopen_source_chrome_if_needed() {
  if [[ "${REOPEN_SOURCE_CHROME}" != "1" ]]; then
    return
  fi
  if [[ -d "${CHROME_APP}" ]]; then
    open -gna "${CHROME_APP}" --args --profile-directory="${PROFILE_DIRECTORY}" --new-window about:blank
  else
    open -gna "Google Chrome" --args --profile-directory="${PROFILE_DIRECTORY}" --new-window about:blank
  fi
}

if [[ "${REFRESH_FROM_BROWSER}" == "1" ]]; then
  force_close_target_chrome
  if [[ -n "$(source_chrome_processes)" ]]; then
    force_close_source_chrome
  fi
  copy_profile_from_source "refresh"
fi

if cdp_is_available; then
  if [[ -n "$(target_processes)" ]] || target_profile_listener_matches; then
    ensure_page_target
    activate_chrome
    echo "本地 CDP Chrome 已可用：${CDP_URL}"
    echo "用户目录：${TARGET_USER_DATA}"
    exit 0
  fi
  echo "${CDP_URL} 已可访问，但 Chrome 进程未匹配 CDP 数据目录。"
  echo "端口 ${PORT} 已被其他进程占用，无法启动本地 CDP Chrome。" >&2
  exit 2
fi

if [[ ! -f "${TARGET_USER_DATA}/${PROFILE_DIRECTORY}/Preferences" && -n "$(source_chrome_processes)" ]]; then
  force_close_source_chrome
fi

init_profile_if_needed

if [[ -d "${CHROME_APP}" ]]; then
  open -na "${CHROME_APP}" --args \
    --remote-debugging-address="${CDP_HOST}" \
    --remote-debugging-port="${PORT}" \
    --user-data-dir="${TARGET_USER_DATA}" \
    --profile-directory="${PROFILE_DIRECTORY}" \
    --no-first-run \
    --no-default-browser-check
else
  open -na "Google Chrome" --args \
    --remote-debugging-address="${CDP_HOST}" \
    --remote-debugging-port="${PORT}" \
    --user-data-dir="${TARGET_USER_DATA}" \
    --profile-directory="${PROFILE_DIRECTORY}" \
    --no-first-run \
    --no-default-browser-check
fi

wait_for_cdp
ensure_page_target
reopen_source_chrome_if_needed
activate_chrome

echo "已启动本地 CDP Chrome：${CDP_URL}"
echo "用户目录：${TARGET_USER_DATA}"
