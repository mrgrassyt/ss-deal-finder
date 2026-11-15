# mrgrass.me: the portfolio site. Content and uploads live in /data (mounted from the server), so rebuilding never touches them.
FROM python:3.13-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV SITE_DATA=/data PYTHONUNBUFFERED=1
EXPOSE 8770
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8770/healthz')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8770", "--proxy-headers", "--forwarded-allow-ips", "*"]
