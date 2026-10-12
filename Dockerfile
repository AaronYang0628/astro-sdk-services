FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV MPLBACKEND=Agg PYTHONPATH=/app
ARG SDK=astropy
ENV SDK=$SDK
CMD ["sh", "-c", "uvicorn sdks.${SDK}:app --host 0.0.0.0 --port 8000"]
