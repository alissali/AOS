FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY spicebus.py aos-bus.py README.md ./
ENV SPICEBUS_DIR=/data
RUN mkdir -p /data
EXPOSE 5555
CMD ["gunicorn", "spicebus:app", "--bind", "0.0.0.0:5555", "--workers", "2"]
