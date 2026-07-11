#!/bin/sh
set -eu

APP_CONTAINER="${APP_CONTAINER:-slowlink_app}"
REDIS_CONTAINER="${REDIS_CONTAINER:-slowlink_redis}"
CHECK_INTERVAL="${CHECK_INTERVAL:-20}"
CPU_THRESHOLD="${CPU_THRESHOLD:-90}"
HIGH_COUNT_LIMIT="${HIGH_COUNT_LIMIT:-4}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-600}"
LOG_FILE="${LOG_FILE:-/opt/slowlink/watchdog.log}"

high_count=0
last_restart=0

log() {
  ts="$(date '+%Y-%m-%d %H:%M:%S')"
  line="[$ts] $*"
  echo "$line"
  printf '%s\n' "$line" >> "$LOG_FILE" 2>/dev/null || true
}

container_cpu() {
  docker stats --no-stream --format '{{.CPUPerc}}' "$APP_CONTAINER" 2>/dev/null | tr -d '%' | awk '{printf "%.0f", $1}'
}

capture_python_state() {
  reason=$1
  log "python stack requested: $reason"
  docker kill --signal=USR1 "$APP_CONTAINER" >> "$LOG_FILE" 2>&1 || true
  sleep 1
  flow="$(docker exec "$REDIS_CONTAINER" redis-cli --raw GET listener_flow_stats 2>/dev/null || true)"
  log "listener flow: ${flow:-unavailable}"
  docker top "$APP_CONTAINER" -eo pid,tid,ppid,comm,%cpu,%mem,etime >> "$LOG_FILE" 2>&1 || true
  docker logs --tail 160 "$APP_CONTAINER" >> "$LOG_FILE" 2>&1 || true
}

snapshot() {
  log "snapshot: load=$(cut -d ' ' -f1-3 /proc/loadavg 2>/dev/null || true)"
  docker stats --no-stream "$APP_CONTAINER" >> "$LOG_FILE" 2>/dev/null || true
  ps -eo pid,tid,ppid,comm,%cpu,%mem,etime --sort=-%cpu | head -20 >> "$LOG_FILE" 2>/dev/null || true
  capture_python_state "sustained high CPU"
}

log "watchdog started: container=$APP_CONTAINER threshold=${CPU_THRESHOLD}% count=$HIGH_COUNT_LIMIT interval=${CHECK_INTERVAL}s cooldown=${COOLDOWN_SECONDS}s"

while true; do
  cpu="$(container_cpu || true)"
  case "$cpu" in
    ''|*[!0-9]*)
      high_count=0
      sleep "$CHECK_INTERVAL"
      continue
      ;;
  esac

  if [ "$cpu" -ge "$CPU_THRESHOLD" ]; then
    high_count=$((high_count + 1))
    log "high CPU: ${cpu}% (${high_count}/${HIGH_COUNT_LIMIT})"
    if [ "$high_count" -eq 1 ]; then
      capture_python_state "first high CPU sample"
    fi
  else
    if [ "$high_count" -gt 0 ]; then
      log "CPU recovered: ${cpu}% (reset high count)"
    fi
    high_count=0
  fi

  now="$(date +%s)"
  if [ "$high_count" -ge "$HIGH_COUNT_LIMIT" ]; then
    since=$((now - last_restart))
    if [ "$last_restart" -eq 0 ] || [ "$since" -ge "$COOLDOWN_SECONDS" ]; then
      snapshot
      log "restarting $APP_CONTAINER after sustained high CPU"
      if docker restart "$APP_CONTAINER" >> "$LOG_FILE" 2>&1; then
        log "restart completed for $APP_CONTAINER"
        last_restart="$now"
      else
        log "restart failed for $APP_CONTAINER"
      fi
    else
      log "restart skipped by cooldown: ${since}s/${COOLDOWN_SECONDS}s"
    fi
    high_count=0
  fi

  sleep "$CHECK_INTERVAL"
done
