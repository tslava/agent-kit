test:
	uv run pytest

lint:
	uv run isort src tests
	uv run ruff check src tests

requirements:
	uv export --no-dev --no-hashes --no-emit-project -o src/requirements.txt

lambda: requirements
	cd src; uv run chalice package ../out;cd -;
