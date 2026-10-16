#!/bin/sh
# Container entrypoint: one image, two processes.
#   start.sh web      gunicorn API (default)
#   start.sh worker   background jobs: emails, scheduled reports, backups, expiries
#   start.sh health   container health check for either role
set -e
role="${1:-web}"
case "$role" in
  web)
    exec gunicorn --bind "0.0.0.0:${PORT:-5000}" --workers "${WEB_CONCURRENCY:-1}" --threads 8 --timeout 60 \
      --access-logfile - --error-logfile - main:app
    ;;
  worker)
    export WORKER_HEARTBEAT_FILE="${WORKER_HEARTBEAT_FILE:-/tmp/anchorstone-worker.heartbeat}"
    echo worker > /tmp/anchorstone-role
    exec flask --app main worker
    ;;
  health)
    if [ "$(cat /tmp/anchorstone-role 2>/dev/null)" = "worker" ]; then
      # The worker touches its heartbeat file every loop (at most a few seconds apart).
      exec python -c "import os, sys, time; f = os.environ.get('WORKER_HEARTBEAT_FILE', '/tmp/anchorstone-worker.heartbeat'); sys.exit(0 if os.path.exists(f) and time.time() - os.path.getmtime(f) < 120 else 1)"
    fi
    exec python -c "import requests, sys; sys.exit(0 if requests.get('http://localhost:${PORT:-5000}/api/v1/health', timeout=5).ok else 1)"
    ;;
  *)
    exec "$@"
    ;;
esac
