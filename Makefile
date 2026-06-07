.PHONY: run test lint fmt docker-up docker-down load-test

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	python3 -m pytest tests/ -v

lint:
	python3 -m ruff check app/ tests/

fmt:
	python3 -m ruff check app/ tests/ --fix
	python3 -m ruff format app/ tests/

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-test:
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit

load-test:
	locust -f loadtests/locustfile.py --headless -u 50 -r 10 -t 30s --host http://localhost:8000
