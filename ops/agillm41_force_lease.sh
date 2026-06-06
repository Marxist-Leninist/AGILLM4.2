#!/usr/bin/env bash
# Manually force a lease publish without waiting for the hourly side_cycle.
#   agillm41_force_lease.sh            -> run ONE full adaptive cycle now (CPU dispatch + device-sized GPU lease)
#   agillm41_force_lease.sh --republish-> just bump current lease mtime so the V100/workers re-pull immediately
set -uo pipefail
cd /workspace
GK=/root/.ssh/agillm41_geth_ed25519; GH=root@5.75.217.57; OPP=/root/agillm41_opportunistic
if [ "${1:-}" = "--republish" ]; then
  ssh -i "$GK" -o BatchMode=yes -o StrictHostKeyChecking=no "$GH" \
    "touch $OPP/current/lease_laptop-auto.pt $OPP/current/lease_laptop-auto.json $OPP/current/shared_frozen.pt 2>/dev/null && echo republished_\$(date -u +%H:%M:%SZ)"
  exit 0
fi
echo "FORCE_LEASE $(date -u +%Y-%m-%dT%H:%M:%SZ) running one adaptive cycle"
exec env AGILLM41_SIDE_CYCLE_SEC=3600 AGILLM41_SIDE_THREADS=8 AGILLM41_SMALL_NODE_THREADS=2 AGILLM41_SIDE_KEEP_ROUNDS=2 \
  bash /workspace/agillm41_vast_side_cycle.sh --once
