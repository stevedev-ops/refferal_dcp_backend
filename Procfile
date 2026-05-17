web: python manage.py migrate && gunicorn core.wsgi --bind 0.0.0.0:$PORT --log-file -
release: python manage.py migrate && python manage.py reverify_members
