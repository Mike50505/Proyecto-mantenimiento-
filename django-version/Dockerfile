FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput
USER 1000
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && python manage.py bootstrap_admin && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60"]
