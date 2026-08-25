FROM python:3.11.9-slim
WORKDIR /app
COPY zero_trust_access /app/zero_trust_access
COPY sample_case.json /app/sample_case.json
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["sh", "-c", "trap 'exit 0' TERM INT; while :; do sleep 3600 & wait $!; done"]
