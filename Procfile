web: gunicorn core.wsgi --log-file -
release: python manage.py migrate && python manage.py reverify_members
