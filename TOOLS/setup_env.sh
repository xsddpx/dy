#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"
USER_BIN="${HOME}/.local/bin"
RECREATE=0

for arg in "$@"; do
  case "${arg}" in
    --recreate)
      RECREATE=1
      ;;
    *)
      echo "未知参数：${arg}" >&2
      echo "用法：zsh TOOLS/setup_env.sh [--recreate]" >&2
      exit 64
      ;;
  esac
done

if [[ "${RECREATE}" -eq 1 && ( -e "${VENV_DIR}" || -L "${VENV_DIR}" ) ]]; then
  backup_root="${ROOT_DIR}/TEMP/env-backups"
  backup_dir="${backup_root}/.venv-$(date +%Y%m%d-%H%M%S)-$$"
  mkdir -p "${backup_root}"
  mv "${VENV_DIR}" "${backup_dir}"
  echo "原项目环境已备份：${backup_dir}"
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/TOOLS/requirements.txt"

media_info="$("${VENV_DIR}/bin/python" - <<'PY'
from static_ffmpeg import run

ffmpeg, ffprobe = run.get_or_fetch_platform_executables_else_raise()
print(f"FFMPEG_PATH={ffmpeg}")
print(f"FFPROBE_PATH={ffprobe}")
PY
)"
ffmpeg_path="$(printf '%s\n' "${media_info}" | sed -n 's/^FFMPEG_PATH=//p' | tail -1)"
ffprobe_path="$(printf '%s\n' "${media_info}" | sed -n 's/^FFPROBE_PATH=//p' | tail -1)"

if [[ -z "${ffmpeg_path}" || -z "${ffprobe_path}" ]]; then
  echo "无法解析 ffmpeg/ffprobe 安装路径。" >&2
  exit 1
fi

mkdir -p "${USER_BIN}"
ln -sfn "${ffmpeg_path}" "${USER_BIN}/ffmpeg"
ln -sfn "${ffprobe_path}" "${USER_BIN}/ffprobe"

"${VENV_DIR}/bin/python" -c 'import cv2, numpy, playwright, pytest'
"${USER_BIN}/ffmpeg" -version >/dev/null
"${USER_BIN}/ffprobe" -version >/dev/null

echo "项目环境已就绪：${VENV_DIR}"
echo "媒体命令已链接：${USER_BIN}/ffmpeg、${USER_BIN}/ffprobe"
