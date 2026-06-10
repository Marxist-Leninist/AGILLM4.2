#!/usr/bin/env bash
# AGILLM4.2 disk janitor: continuous pruning so the 64GB overlay can never fill
# and kill training again (full disk -> python can't start -> watchdog crash-loop).
# Respects the .pinned convention from agillm4_local_prune_guard.py: checkpoints
# listed in $CKPT/.pinned (basename or absolute path, #
