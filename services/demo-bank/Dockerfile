FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir fastapi uvicorn pydantic

COPY services/demo-bank /app/services/demo-bank
ENV PYTHONPATH=/app/services/demo-bank

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
