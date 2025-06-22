# app/celery_worker.py
import os
from celery import Celery

# Get Redis URL from environment variables (Heroku will provide REDIS_URL)
# Fallback to localhost for local development
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

celery_app = Celery(
    'exami_backend_app', # A unique name for your Celery app
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['app.tasks'] # IMPORTANT: Tell Celery where to find your tasks
)

# Optional: Configure Celery to retry tasks on failure
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.broker_connection_retry_on_startup = True