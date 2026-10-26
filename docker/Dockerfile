# Resolve the base to a registry digest during build; record the final local image ID with doctor.
ARG BASE_IMAGE=python:3.11-slim@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377
FROM ${BASE_IMAGE}
COPY docker/execute.py /runner/execute.py
USER 65534:65534
ENV PYTHONHASHSEED=0 LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC PYTHONDONTWRITEBYTECODE=1
WORKDIR /tmp
ENTRYPOINT ["python", "-I", "-c", "import time; time.sleep(86400)"]
