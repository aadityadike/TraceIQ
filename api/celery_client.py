from celery import Celery

from config import settings

# Minimal Celery client used by the API to dispatch tasks.
# The worker registers the actual task — API only sends messages.
celery_client = Celery(broker=settings.redis_url, backend=settings.redis_url)
