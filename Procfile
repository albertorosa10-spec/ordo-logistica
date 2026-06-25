web: python manage.py migrate && python manage.py criar_grupos && python manage.py collectstatic --noinput && gunicorn setup.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 2 --timeout 120
