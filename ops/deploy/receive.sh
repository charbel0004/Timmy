#!/usr/bin/env bash
# Forced command in timmy-deploy's authorized_keys; no interactive shell.
set -euo pipefail
if [[ "${SSH_ORIGINAL_COMMAND:-}" =~ ^deploy\ ([0-9a-f]{40})$ ]]; then
  sha="${BASH_REMATCH[1]}"
  exec /usr/local/bin/timmy-stage-release "$sha"
fi
echo 'Rejected: only "deploy <40-character SHA>" is permitted' >&2
exit 2
