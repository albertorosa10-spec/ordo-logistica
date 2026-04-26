web: python manage.py migrate && python manage.py criar_admin && gunicorn setup.wsgi --log-file - --workers 2 --bind 0.0.0.0:$PORT
