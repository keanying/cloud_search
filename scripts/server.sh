#!/usr/bin/env bash
# =====================================================================
# 云搜浏览器 服务器管理脚本（Linux）
#
#   scripts/server.sh setup     安装/更新：根目录 .venv、Chromium、前端打包、数据库迁移
#   scripts/server.sh start     启动 API（含页面）与 worker（worker.embedded=false 时）
#   scripts/server.sh stop      停止
#   scripts/server.sh restart   重启
#   scripts/server.sh status    查看进程与健康状态
#   scripts/server.sh check     健康检查（正常退出码 0，异常 1；可用于 cron / 监控）
#   scripts/server.sh logs [api|worker]   跟踪日志
#   scripts/server.sh build     仅重新打包前端
#
# 配置统一在仓库根目录 config.yaml（server.host/port、database、worker 等）。
# worker 进程数取 config.yaml 的 worker.processes（环境变量 WORKERS 可临时覆盖）；STOP_TIMEOUT=30 停止等待秒数。
# =====================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
RUN_DIR="$ROOT/run"
LOG_DIR="$ROOT/logs"
STOP_TIMEOUT="${STOP_TIMEOUT:-30}"
mkdir -p "$RUN_DIR" "$LOG_DIR"
cd "$ROOT"

export PYTHONUTF8=1 PYDANTIC_AI_NO_BANNER=1
[ -d "$ROOT/.playwright" ] && [ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" ] && export PLAYWRIGHT_BROWSERS_PATH="$ROOT/.playwright"

c_red() { printf '\033[31m%s\033[0m\n' "$*"; }
c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

find_python() {
  for p in python3.13 python3.12 python3; do
    if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      echo "$p"; return 0
    fi
  done
  return 1
}

require_venv() {
  if [ ! -x "$VENV_PY" ]; then
    c_red "尚未安装环境，请先执行：scripts/server.sh setup"; exit 1
  fi
}

# 读取 config.yaml（经程序校验）：输出 host port embedded processes
read_config() {
  "$VENV_PY" - <<'PY'
from cloudsearch.core.config import get_settings
s = get_settings()
print(s.server_host, s.server_port, "1" if s.embedded_worker else "0", s.worker_processes)
PY
}

# 进程存活：PID 存在、不是僵尸进程，且命令行确实是本项目（防止重启后 PID 被其他进程复用）
pid_alive() {
  local pid="${1:-}"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null || return 1
  if [ -r "/proc/$pid/stat" ]; then
    local state; state="$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null)"
    [ "$state" = "Z" ] && return 1
    tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null | grep -q "cloudsearch" || return 1
  fi
  return 0
}
pid_of() { [ -f "$RUN_DIR/$1.pid" ] && cat "$RUN_DIR/$1.pid"; }

health_url() {
  local host="$1" port="$2"
  [ "$host" = "0.0.0.0" ] && host="127.0.0.1"
  echo "http://$host:$port/api/health"
}

http_get() {
  if command -v curl >/dev/null 2>&1; then curl -fsS --max-time 5 "$1"
  else "$VENV_PY" -c "import sys,urllib.request;print(urllib.request.urlopen(sys.argv[1],timeout=5).read().decode())" "$1"
  fi
}

start_one() {  # name, command...
  local name="$1"; shift
  local pid; pid="$(pid_of "$name")"
  if pid_alive "$pid"; then c_yellow "$name 已在运行（PID $pid）"; return 0; fi
  nohup "$@" >>"$LOG_DIR/$name.log" 2>&1 &
  echo $! >"$RUN_DIR/$name.pid"
  echo "  $name 已启动（PID $!，日志 logs/$name.log）"
}

stop_one() {
  local name="$1" pid; pid="$(pid_of "$name")"
  if ! pid_alive "$pid"; then rm -f "$RUN_DIR/$name.pid"; return 0; fi
  kill -TERM "$pid" 2>/dev/null
  for _ in $(seq 1 "$STOP_TIMEOUT"); do pid_alive "$pid" || break; sleep 1; done
  if pid_alive "$pid"; then c_yellow "  $name 未在 ${STOP_TIMEOUT}s 内退出，强制结束"; kill -KILL "$pid" 2>/dev/null; fi
  rm -f "$RUN_DIR/$name.pid"
  echo "  $name 已停止"
}

cmd_setup() {
  local py; py="$(find_python)" || { c_red "需要 Python 3.12 或 3.13"; exit 1; }
  echo "使用 $py 执行安装（依赖 / Chromium / 前端打包 / 迁移）"
  "$py" "$ROOT/run.py" --setup-only --no-browser
}

cmd_build() {
  require_venv
  local py; py="$(find_python)" || exit 1
  "$py" "$ROOT/run.py" --setup-only --no-browser
}

cmd_start() {
  require_venv
  local cfg host port embedded processes
  cfg="$(read_config)" || { c_red "config.yaml 配置有误："; read_config; exit 1; }
  read -r host port embedded processes <<<"$cfg"
  local workers="${WORKERS:-$processes}"
  echo "启动云搜浏览器（$host:$port）"
  # 不使用 --reload；单进程 uvicorn。如需多核，可起多个 worker 进程分担任务
  start_one api "$VENV_PY" -m uvicorn cloudsearch.app:app --host "$host" --port "$port" --proxy-headers \
    --forwarded-allow-ips="127.0.0.1"
  if [ "$embedded" = "0" ]; then
    for i in $(seq 1 "$workers"); do
      CS_WORKER_ID="$(hostname)-worker-$i" start_one "worker-$i" "$VENV_PY" -m cloudsearch.worker.main
    done
  else
    echo "  worker 内嵌在 API 进程中（config.yaml: worker.embedded=true）"
  fi
  local url; url="$(health_url "$host" "$port")"
  for _ in $(seq 1 60); do
    if http_get "$url" >/dev/null 2>&1; then c_green "服务就绪：http://$host:$port"; return 0; fi
    pid_alive "$(pid_of api)" || { c_red "API 进程已退出，最近日志："; tail -n 30 "$LOG_DIR/api.log"; exit 1; }
    sleep 1
  done
  c_red "服务 60 秒内未就绪，请查看 logs/api.log"; exit 1
}

cmd_stop() {
  echo "停止云搜浏览器"
  for f in "$RUN_DIR"/worker-*.pid; do [ -e "$f" ] && stop_one "$(basename "$f" .pid)"; done
  stop_one api
}

# status：展示；check：严格判断并返回退出码
cmd_status() {
  local strict="${1:-0}" ok=1 cfg host port embedded processes
  require_venv
  cfg="$(read_config 2>/dev/null)" || { c_red "config.yaml 配置有误"; return 1; }
  read -r host port embedded processes <<<"$cfg"
  local pid; pid="$(pid_of api)"
  if pid_alive "$pid"; then echo "  api        运行中 PID $pid"; else c_red "  api        未运行"; ok=0; fi
  if [ "$embedded" = "0" ]; then
    local n=0
    for f in "$RUN_DIR"/worker-*.pid; do
      [ -e "$f" ] || continue
      local name wp; name="$(basename "$f" .pid)"; wp="$(cat "$f")"
      if pid_alive "$wp"; then echo "  $name   运行中 PID $wp"; n=$((n+1)); else c_red "  $name   已退出"; ok=0; fi
    done
    [ "$n" -eq 0 ] && { c_red "  worker     未运行（worker.embedded=false 时必须运行）"; ok=0; }
  else
    echo "  worker     内嵌于 api"
  fi
  local body
  if body="$(http_get "$(health_url "$host" "$port")" 2>/dev/null)"; then echo "  health     $body"
  else c_red "  health     接口无响应或异常（$(health_url "$host" "$port")）"; ok=0; fi
  local br mode
  br="$("$VENV_PY" -m cloudsearch.browser.launch 2>/dev/null)"
  mode="$(printf '%s' "$br" | "$VENV_PY" -c 'import sys,json;d=json.load(sys.stdin);print(d["mode"], d["detail"])' 2>/dev/null)"
  case "$mode" in
    bundled*|channel*|executable*) echo "  browser    ${mode#* }" ;;
    *) c_red "  browser    不可用：${mode#* }（执行 scripts/server.sh setup 下载 Chromium）"; ok=0 ;;
  esac
  local disk; disk="$(df -P "$ROOT" | awk 'NR==2{print $5}')"
  echo "  disk       已用 $disk"
  if [ "$ok" = "1" ]; then c_green "状态：正常"; return 0; fi
  c_red "状态：异常"
  [ "$strict" = "1" ] && return 1 || return 0
}

cmd_logs() {
  local which="${1:-api}"
  if [ "$which" = "worker" ]; then tail -n 100 -F "$LOG_DIR"/worker-*.log; else tail -n 100 -F "$LOG_DIR/$which.log"; fi
}

case "${1:-}" in
  setup) cmd_setup ;;
  build) cmd_build ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status) cmd_status 0 ;;
  check) cmd_status 1; exit $? ;;
  logs) cmd_logs "${2:-api}" ;;
  *)
    sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
    exit 1 ;;
esac
