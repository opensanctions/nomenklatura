web: python nomenklatura/manage.py runserver -p $PORT -t 0.0.0.0
celeryd: NOMENKLATURA_SETTINGS=/app/heroku_settings.py celery -A nomenklatura.importer worker
