.PHONY: setup test download etl data clean

etl:
	uv run python -m hmci.etl.build_parquet

data: download etl

setup:
	uv sync

test:
	uv run pytest -q

download:
	uv run python -m hmci.etl.download

clean:
	rm -rf data/interim data/processed data/warehouse.duckdb