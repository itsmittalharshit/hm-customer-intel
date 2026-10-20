# Benchmarks

MacBook Air M4, median of 5 runs after one warm-up, 28.8M fact rows.

| Query | Engine | Median (s) | Rows |
| --- | --- | --- | --- |
| customer RFM at snapshot | DuckDB (native tables) | 0.184 | 714,936 |
| customer RFM at snapshot | DuckDB (on Parquet) | 0.209 | 714,936 |
| customer RFM at snapshot | Polars (lazy, Parquet) | 0.057 | 714,936 |
| top-100 articles, last 4 weeks | DuckDB (native tables) | 0.003 | 100 |
| top-100 articles, last 4 weeks | DuckDB (on Parquet) | 0.013 | 100 |
| top-100 articles, last 4 weeks | Polars (lazy, Parquet) | 0.004 | 100 |
| weekly revenue by department | DuckDB (native tables) | 0.069 | 24,209 |
| weekly revenue by department | DuckDB (on Parquet) | 0.128 | 24,209 |
| weekly revenue by department | Polars (lazy, Parquet) | 0.151 | 24,209 |
