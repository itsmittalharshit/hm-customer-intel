-- RFM features for any snapshot date: only purchases strictly BEFORE the snapshot.
CREATE OR REPLACE MACRO rfm(snapshot_date, lookback_days) AS TABLE
SELECT
    customer_key,
    date_diff('day', max(date_key), snapshot_date) AS recency_days,
    count(DISTINCT date_key)                       AS frequency_days,
    sum(revenue)                                   AS monetary,
    sum(units)::BIGINT                             AS units
FROM fact_sales
WHERE date_key <  snapshot_date
  AND date_key >= snapshot_date - lookback_days
GROUP BY customer_key;

-- Active customers at a snapshot (>=1 purchase in lookback) with their churn label:
-- churned = 1 if no purchase in [snapshot, snapshot + horizon_days).
CREATE OR REPLACE MACRO churn_labels(snapshot_date, lookback_days, horizon_days) AS TABLE
WITH active AS (
    SELECT * FROM rfm(snapshot_date, lookback_days)
),
future AS (
    SELECT DISTINCT customer_key
    FROM fact_sales
    WHERE date_key >= snapshot_date
      AND date_key <  snapshot_date + horizon_days
)
SELECT
    snapshot_date::DATE                AS snapshot,
    a.*,
    (f.customer_key IS NULL)::TINYINT  AS churned
FROM active a
LEFT JOIN future f USING (customer_key);