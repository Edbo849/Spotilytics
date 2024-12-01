celery -A Spotilytics worker --loglevel=ERROR &

celery -A Spotilytics beat --loglevel=ERROR &

python3 manage.py runserver