FROM python:3.13-slim
WORKDIR /workspace/astro_services
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV MPLBACKEND=Agg PYTHONPATH=/workspace/astro_services
RUN python -c "from astropy.utils.iers import IERS_Auto; IERS_Auto.open()" || true
ARG SDK=astropy
ENV SDK=$SDK
CMD ["sh", "-c", "uvicorn sdks.${SDK}:app --host 0.0.0.0 --port 8000"]
