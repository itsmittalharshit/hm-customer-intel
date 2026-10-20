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