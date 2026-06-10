#!/usr/bin/env bash
# AGILLM 4.2 disk janitor.
#
# Runs continuously and independently of the trainer so the 64GB overlay never
# wedges ("No space left on device" -> Python can't start -> watchdog crash-loop).
# It is conservative: it only removes regenerable / transient artifacts and the
# oldest checkpoints beyond a keep-count, never the newest full checkpoint, never
# the resume/seed deltas, and never anything listed in <save_dir>/.pinned.
#
# Usage: disk_janitor.sh [--once]
set -uo pipefail

SAVE_DIR="${SAVE_DIR:-/workspace/agillm4_4090_ckpts}"
SIDE_ROUNDS="${SIDE_ROUNDS:-/workspace/agillm41_side_rounds}"
LOG="${DISK_JANITOR_LOG:-/workspace/agillm41_disk_janitor.log}"
TARGET_FREE_GB="${TARGET_FREE_GB:-20}"      # keep at least this much free (> uploader MIN_FREE_GB=18)
KEEP_FULL="${KEEP_FULL:-2}"                 # newest N pretrain_step*.pt
KEEP_DELTA="${KEEP_DELTA:-2}"               # newest N pretrain_delta_step*.pt
KEEP_SIDE_ROUNDS="${KEEP_SIDE_ROUNDS:-2}"   # newest N side-cycle round dirs
INTERVAL="${DISK_JANITOR_INTERVAL_SEC:-120}"
ONCE=0; [ "${1:-}" = "--once" ] && ONCE=1

log(){ echo "{\"t\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"free_gb\":$(free_gb),\"msg\":\"$1\"}" >> "$LOG"; }
free_gb(){ df -P / | awk 'NR==2{printf "%d",$4/1024/1024}'; }
pinned_basenames(){ grep -vE '^\s*#|^\s*$' "$SAVE_DIR/.pinned" 2>/dev/null | sed 's#.*/##'; }
is_pinned(){ pinned_basenames | grep -qxF "$(basename "$1")"; }

# prune_keep <keepN> <glob...> : delete oldest-by-mtime beyond keepN, skipping pinned.
prune_keep(){
  local keep="$1"; shift
  ls -1dt "$@" 2>/dev/null | tail -n +$((keep+1)) | while IFS= read -r f; do
    [ -e "$f" ] || continue
    if is_pinned "$f"; then log "skip pinned $(basename "$f")"; continue; fi
    local sz; sz=$(du -sm "$f" 2>/dev/null | cut -f1)
    rm -rf "$f" && log "pruned $(basename "$f") (${sz}MB)"
  done
}

janitor_pass(){
  # 1) always: clear partial writes older than 5 min (a live save is younger)
  find "$SAVE_DIR" -maxdepth 1 -name '*.tmp' -mmin +5 -print -delete 2>/dev/null \
    | grep -q . && log "cleared stale .tmp partials"
  # 2) routine retention
  prune_keep "$KEEP_FULL"        "$SAVE_DIR"/pretrain_step*.pt
  prune_keep "$KEEP_DELTA"       "$SAVE_DIR"/pretrain_delta_step*.pt
  prune_keep "$KEEP_SIDE_ROUNDS" "$SIDE_ROUNDS"/*/
  # 3) emergency: still under the floor -> escalate on transient artifacts only
  local f; f=$(free_gb)
  if [ "${f:-0}" -lt "$TARGET_FREE_GB" ]; then
    log "below floor: ${f}GB < ${TARGET_FREE_GB}GB, escalating"
    prune_keep 1 "$SIDE_ROUNDS"/*/
    prune_keep 1 "$SAVE_DIR"/pretrain_delta_step*.pt
    f=$(free_gb); log "after escalation: ${f}GB free"
  fi
}

log "disk_janitor start (keep_full=$KEEP_FULL keep_delta=$KEEP_DELTA keep_rounds=$KEEP_SIDE_ROUNDS floor=${TARGET_FREE_GB}GB once=$ONCE)"
while true; do
  janitor_pass
  [ "$ONCE" = "1" ] && break
  sleep "$INTERVAL"
done
