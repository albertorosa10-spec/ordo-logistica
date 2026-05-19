web: python manage.py migrate && python manage.py criar_admin && python manage.py criar_grupos && python manage.py setup_inicial && gunicorn setup.wsgi --log-file - --workers 2 --bind 0.0.0.0:$PORT
