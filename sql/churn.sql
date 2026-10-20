-- Behavioural features per active customer at a snapshot, using only purchases BEFORE it.
-- Column names assume lookback_days = 182 (26 weeks); 12w = 84 days, 4w = 28 days.
CREATE OR REPLACE MACRO churn_features(snapshot_date, lookback_days) AS TABLE
WITH hist AS (
    SELECT f.date_key, f.customer_key, f.article_key, f.channel_key,
           f.price, f.units, f.revenue, a.product_group_name
    FROM fact_sales f
    JOIN dim_article a USING (article_key)
    WHERE f.date_key <  snapshot_date
      AND f.date_key >= snapshot_date - lookback_days
),
art_median AS (                         -- typical price of each article in the same window
    SELECT article_key, median(price) AS med_price
    FROM hist
    GROUP BY article_key
),
visit_gaps AS (                         -- days since the previous purchase day
    SELECT customer_key, date_key,
           date_diff('day',
                     lag(date_key) OVER (PARTITION BY customer_key ORDER BY date_key),
                     date_key) AS gap
    FROM (SELECT DISTINCT customer_key, date_key FROM hist)
),
gaps AS (
    SELECT customer_key,
           avg(gap)               AS gap_mean,
           arg_max(gap, date_key) AS gap_last
    FROM visit_gaps
    WHERE gap IS NOT NULL
    GROUP BY customer_key
),
behaviour AS (
    SELECT
        h.customer_key,
        date_diff('day', max(h.date_key), snapshot_date)                            AS recency_days,
        count(DISTINCT h.date_key)                                                   AS freq_26w,
        count(DISTINCT h.date_key) FILTER (WHERE h.date_key >= snapshot_date - 84)   AS freq_12w,
        count(DISTINCT h.date_key) FILTER (WHERE h.date_key >= snapshot_date - 28)   AS freq_4w,
        sum(h.revenue)                                                               AS spend_26w,
        coalesce(sum(h.revenue) FILTER (WHERE h.date_key >= snapshot_date - 84), 0)  AS spend_12w,
        coalesce(sum(h.revenue) FILTER (WHERE h.date_key >= snapshot_date - 28), 0)  AS spend_4w,
        sum(h.units)::BIGINT                                                         AS units_26w,
        sum(h.revenue) / count(DISTINCT h.date_key)                                  AS basket_value,
        coalesce(sum(h.units) FILTER (WHERE h.channel_key = 2), 0) / sum(h.units)    AS online_share,
        count(DISTINCT h.product_group_name)                                         AS n_product_groups,
        avg((h.price < m.med_price)::INTEGER)                                        AS below_median_share
    FROM hist h
    JOIN art_median m USING (article_key)
    GROUP BY h.customer_key
),
tenure AS (                             -- all history before the snapshot, not just the lookback
    SELECT customer_key, date_diff('day', min(date_key), snapshot_date) AS tenure_days
    FROM fact_sales
    WHERE date_key < snapshot_date
    GROUP BY customer_key
)
SELECT
    b.*,
    g.gap_mean,
    g.gap_last,
    g.gap_last - g.gap_mean AS gap_trend,   -- > 0: latest gap longer than usual (slowing down)
    t.tenure_days
FROM behaviour b
LEFT JOIN gaps g USING (customer_key)
JOIN tenure t    USING (customer_key);