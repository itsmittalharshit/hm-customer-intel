.PHONY: setup test download etl warehouse data clean bench docs churn-base churn-features analyst ltv stats

warehouse:
	uv run python -m hmci.etl.build_warehouse

data: download etl warehouse

stats:
	uv run python -m hmci.analyst.stats_tests

ltv:
	uv run python -m hmci.analyst.ltv_funnel

analyst:
	uv run python -m hmci.analyst.explore

churn-base:
	uv run python -m hmci.churn.snapshots

churn-features:
	uv run python -m hmci.churn.snapshots

bench:
	uv run python -m hmci.etl.benchmark

docs:
	uv run python -m hmci.etl.data_dictionary

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