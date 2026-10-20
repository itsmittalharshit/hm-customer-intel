.PHONY: setup test download clean

setup:
	uv sync

test:
	uv run pytest -q

download:
	uv run python -m hmci.etl.download

clean:
	rm -rf data/interim data/processed data/warehouse.duckdb