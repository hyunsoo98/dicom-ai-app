FROM python:3.12-slim

WORKDIR /app

COPY common/ ./common/
COPY simulator/requirements.txt ./simulator/requirements.txt
RUN pip install --no-cache-dir -r simulator/requirements.txt

COPY simulator/ ./simulator/

WORKDIR /app/simulator
EXPOSE 5588

ENTRYPOINT ["python", "source_simulator.py", "--host", "0.0.0.0"]
CMD ["--port", "5588"]
