-- Weekly demand per garment group (input to Module 3).
CREATE OR REPLACE VIEW v_weekly_category_demand AS
SELECT
    d.week_start,
    a.garment_group_name,
    sum(f.units)::BIGINT           AS units,
    sum(f.revenue)                 AS revenue,
    count(DISTINCT f.customer_key) AS buyers,
    count(DISTINCT f.date_key)     AS days_observed   -- 7 = full week
FROM fact_sales f
JOIN dim_date d    USING (date_key)
JOIN dim_article a USING (article_key)
GROUP BY ALL;

-- First purchase and cohort per customer (input to Module 7).
CREATE OR REPLACE VIEW v_customer_cohort AS
SELECT
    customer_key,
    min(date_key)                           AS first_purchase,
    date_trunc('month', min(date_key))::DATE AS cohort_month,
    arg_min(channel_key, date_key)          AS first_channel
FROM fact_sales
GROUP BY customer_key;