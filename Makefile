.PHONY: install-simulator install-console run-simulator run-console \
        docker-build docker-up docker-down test clean

install-simulator:
	pip install -r simulator/requirements.txt

install-console:
	pip install -r console/requirements.txt

run-simulator:
	python simulator/source_simulator.py --port 5588

run-console:
	python console/console_app.py --port 5588

docker-build:
	docker compose build simulator

docker-up:
	docker compose up simulator

docker-down:
	docker compose down

test:
	python -m py_compile simulator/*.py console/*.py common/*.py

clean:
	rm -rf simulator/captures
	find . -name "__pycache__" -type d -exec rm -rf {} +
