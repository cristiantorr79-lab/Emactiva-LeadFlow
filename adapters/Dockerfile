FROM python:3.14.3-slim-bookworm
WORKDIR /app
COPY server.py /app/server.py
COPY logging_policy.py /app/logging_policy.py
USER 65534:65534
CMD ["python", "/app/server.py"]
