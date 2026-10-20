.PHONY: setup test download etl warehouse data clean

warehouse:
	uv run python -m hmci.etl.build_warehouse

data: download etl warehouse

etl:
	uv run python -m hmci.etl.build_parquet

setup:
	uv sync

test:
	uv run pytest -q

download:
	uv run python -m hmci.etl.download

clean:
	rm -rf data/interim data/processed data/warehouse.duckdb