echo "Stopping any existing Celery workers and beat instances..."
pkill -f "celery -A Spotilytics worker"
pkill -f "celery -A Spotilytics beat"

sleep 2

echo "Starting Celery worker..."
celery -A Spotilytics worker --loglevel=ERROR &

echo "Starting Celery beat..."
celery -A Spotilytics beat --loglevel=ERROR &

echo "Starting Django server..."
python3 manage.py runserver