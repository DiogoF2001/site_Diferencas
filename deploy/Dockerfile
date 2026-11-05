# Build context: repository root.
FROM python:3.13.18-slim-trixie@sha256:d0a9e379c0c588befb0e427db17ca9731751d281f32c6cb1a90a1277b680bdad AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN groupadd --system --gid 10001 portal \
    && useradd --system --uid 10001 --gid portal --no-create-home portal
WORKDIR /app

FROM base AS dev
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
COPY portal/requirements/ /tmp/requirements/
RUN pip install --require-hashes -r /tmp/requirements/dev.txt
COPY portal/ /app/
USER portal
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

FROM base AS prod
COPY portal/requirements/ /tmp/requirements/
RUN pip install --require-hashes -r /tmp/requirements/base.txt
COPY portal/ /app/
# Throwaway values: these commands only need the settings module to load. gettext is only needed
# here, so it goes away in the same layer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && export DJANGO_SECRET_KEY=build-only DB_NAME=build DB_USER=build DB_PASSWORD=build \
    && python manage.py compilemessages \
    && python manage.py collectstatic --noinput \
    && apt-get purge -y --auto-remove gettext \
    && rm -rf /var/lib/apt/lists/*
USER portal
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--worker-tmp-dir", "/dev/shm", "--access-logfile", "-"]
