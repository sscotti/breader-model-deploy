FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

ENV AUTHGATE_USERS_FILE=/auth/users.basicauth \
    AUTHGATE_LISTEN=0.0.0.0 \
    AUTHGATE_PORT=9090 \
    AUTHGATE_MAX_FAILURES=3 \
    AUTHGATE_LOCKOUT_SECONDS=900

EXPOSE 9090
CMD ["python", "-u", "main.py"]
