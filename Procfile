web: MALLOC_ARENA_MAX=2 gunicorn config.wsgi:application --workers 1 --threads 4 --timeout 180 --max-requests 500 --max-requests-jitter 50
worker: MALLOC_ARENA_MAX=2 celery -A config worker --loglevel=info --concurrency=2 --prefetch-multiplier=1 --max-tasks-per-child=100
beat: celery -A config beat --loglevel=info --pidfile=/tmp/celerybeat.pid --schedule=/tmp/celerybeat-schedule
