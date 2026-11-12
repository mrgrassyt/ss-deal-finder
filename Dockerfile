FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SSDEAL_HOME=/data SSDEAL_SERVER=1
WORKDIR /app
COPY requirements.txt .
RUN grep -v '^pytest' requirements.txt > /tmp/req.txt && pip install --no-cache-dir -r /tmp/req.txt
COPY ssdeal ./ssdeal
COPY web ./web
COPY run_service.pyw .
VOLUME /data
EXPOSE 8765
HEALTHCHECK --interval=60s --timeout=10s --start-period=60s CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8765/api/status', timeout=8)" || exit 1
CMD ["python", "run_service.pyw", "--server", "--port", "8765"]
