-- Monthly cohort retention: of the customers who first bought in month M,
-- how many bought again in month M+k? Split by first-purchase channel.
CREATE OR REPLACE VIEW v_cohort_retention AS
WITH activity AS (                      -- one row per customer per month with any purchase
    SELECT DISTINCT customer_key,
           date_trunc('month', date_key)::DATE AS activity_month
    FROM fact_sales
),
sizes AS (
    SELECT cohort_month, first_channel, count(*) AS cohort_size
    FROM v_customer_cohort
    GROUP BY ALL
)
SELECT
    c.cohort_month,
    c.first_channel,
    a.activity_month,
    date_diff('month', c.cohort_month, a.activity_month) AS months_since_first,
    count(*)                       AS active_customers,
    any_value(s.cohort_size)       AS cohort_size,
    c.cohort_month < DATE '2019-03-01'   AS left_censored,   -- may include pre-existing customers
    a.activity_month >= DATE '2020-09-01' AS partial_month    -- data ends 2020-09-22
FROM v_customer_cohort c
JOIN activity a USING (customer_key)
JOIN sizes s    USING (cohort_month, first_channel)
GROUP BY ALL;