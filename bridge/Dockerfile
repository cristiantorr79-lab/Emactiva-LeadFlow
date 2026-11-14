FROM python:3.14.3-slim-bookworm
WORKDIR /app
COPY server.py /app/server.py
USER 65534:65534
ENTRYPOINT ["python", "/app/server.py"]
