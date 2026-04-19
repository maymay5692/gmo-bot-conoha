#!/usr/bin/env bash
# FR Monitor Watchdog.
#
# Checks that log files are being updated. If stale (>STALE_MIN minutes),
# restarts the corresponding monitor with caffeinate.
#
# Usage:
#   scripts/monitor_watchdog.sh            # one-shot check
#   */5 * * * * /path/to/monitor_watchdog.sh >> ~/monitor_watchdog.cron.log 2>&1
set -u

REPO_DIR="/Users/okadasusumutakashi/Desktop/gmo-bot-conoha"
LOG_DIR="$REPO_DIR/scripts/data_cache"
WATCHDOG_LOG="$LOG_DIR/watchdog.log"
STALE_MIN=10  # restart if log not touched within this many minutes
PYTHON=/usr/bin/python3
PY_FLAGS="-u"   # unbuffered stdout so log mtime stays fresh

# CSV prefix is checked first (most-recent UTC-dated file). Fallback to log.
declare -a MONITORS=(
  "bitget:fr_monitor.py:fr_monitor.log:fr_snapshots_"
  "hyperliquid:hl_fr_monitor.py:hl_fr_monitor.log:hl_fr_snapshots_"
  "mexc:mexc_fr_monitor.py:mexc_fr_monitor.log:mexc_fr_snapshots_"
)

ts() { date '+%Y-%m-%d %H:%M:%S'; }

log() { echo "[$(ts)] $*" >> "$WATCHDOG_LOG"; }

is_running() {
  local script=$1
  # Match any Python invocation of the script (system python, Xcode python, etc.)
  pgrep -f "scripts/$script( |$)" > /dev/null 2>&1
}

newest_mtime() {
  # echoes newest mtime (epoch) across all matching files, or 0 if none
  local pattern=$1
  local newest=0
  for f in $pattern; do
    [ -f "$f" ] || continue
    local m
    m=$(stat -f %m "$f")
    if [ "$m" -gt "$newest" ]; then newest=$m; fi
  done
  echo "$newest"
}

is_stale() {
  # Args: log_path, csv_prefix_path
  # Stale if BOTH log and newest CSV are older than threshold.
  local log=$1
  local csv_prefix=$2
  local now
  now=$(date +%s)
  local log_mtime=0
  [ -f "$log" ] && log_mtime=$(stat -f %m "$log")
  local csv_mtime
  csv_mtime=$(newest_mtime "${csv_prefix}*.csv")
  local latest=$log_mtime
  [ "$csv_mtime" -gt "$latest" ] && latest=$csv_mtime
  if [ "$latest" -eq 0 ]; then
    return 0
  fi
  local age=$(( (now - latest) / 60 ))
  [ "$age" -gt "$STALE_MIN" ]
}

restart() {
  local script=$1
  local logfile=$2
  cd "$REPO_DIR" || exit 1
  # kill existing — SIGTERM then SIGKILL fallback to ensure no overlap.
  # Match any Python variant (system, Xcode, pyenv) via script-path anchor.
  pkill -TERM -f "scripts/$script( |$)" 2>/dev/null
  pkill -TERM -f "caffeinate.*$script" 2>/dev/null
  sleep 2
  pkill -KILL -f "scripts/$script( |$)" 2>/dev/null
  pkill -KILL -f "caffeinate.*$script" 2>/dev/null
  sleep 1
  # Verify no process before starting new
  if pgrep -f "scripts/$script( |$)" > /dev/null 2>&1; then
    log "  WARN: $script still running after SIGKILL — aborting restart"
    return
  fi
  nohup caffeinate -i $PYTHON $PY_FLAGS "scripts/$script" >> "$LOG_DIR/$logfile" 2>&1 &
  log "RESTARTED $script (pid=$!)"
}

mkdir -p "$LOG_DIR"
touch "$WATCHDOG_LOG"

for entry in "${MONITORS[@]}"; do
  IFS=':' read -r name script logfile csv_prefix <<< "$entry"
  logpath="$LOG_DIR/$logfile"
  csv_prefix_path="$LOG_DIR/$csv_prefix"

  running=0
  if is_running "$script"; then running=1; fi

  stale=0
  if is_stale "$logpath" "$csv_prefix_path"; then stale=1; fi

  if [ "$running" -eq 0 ]; then
    log "$name DOWN (no process) — restarting"
    restart "$script" "$logfile"
  elif [ "$stale" -eq 1 ]; then
    log "$name STALE (log >${STALE_MIN}min old) — restarting"
    restart "$script" "$logfile"
  else
    : # ok, no output to keep logs tidy
  fi
done
