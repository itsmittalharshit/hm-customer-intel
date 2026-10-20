-- Revenue by cohort, first channel and month since first purchase (input to LTV curves).
CREATE OR REPLACE VIEW v_cohort_revenue AS
SELECT
    c.cohort_month,
    c.first_channel,
    date_diff('month', c.cohort_month, date_trunc('month', f.date_key)::DATE) AS months_since_first,
    sum(f.revenue) AS revenue
FROM fact_sales f
JOIN v_customer_cohort c USING (customer_key)
GROUP BY ALL;

-- One row per customer: purchase journey within 365 days of their first purchase.
CREATE OR REPLACE VIEW v_customer_journey AS
WITH visits AS (
    SELECT customer_key, date_key,
           row_number() OVER (PARTITION BY customer_key ORDER BY date_key) AS visit_no
    FROM (SELECT DISTINCT customer_key, date_key FROM fact_sales)
),
first_basket AS (               -- most common product group in the first day's basket
    SELECT f.customer_key, mode(a.product_group_name) AS first_group
    FROM fact_sales f
    JOIN v_customer_cohort c USING (customer_key)
    JOIN dim_article a       USING (article_key)
    WHERE f.date_key = c.first_purchase
    GROUP BY f.customer_key
)
SELECT
    c.customer_key,
    c.cohort_month,
    c.first_channel,
    c.first_purchase,
    b.first_group,
    count(*) FILTER (WHERE v.date_key < c.first_purchase + 365)   AS visits_365d,
    min(v.date_key) FILTER (WHERE v.visit_no = 2)                 AS second_purchase,
    min(v.date_key) FILTER (WHERE v.visit_no = 3)                 AS third_purchase
FROM v_customer_cohort c
JOIN visits v       USING (customer_key)
JOIN first_basket b USING (customer_key)
GROUP BY c.customer_key, c.cohort_month, c.first_channel, c.first_purchase, b.first_group;