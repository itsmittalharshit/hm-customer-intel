-- Channel habit per customer over their whole history.
CREATE OR REPLACE VIEW v_customer_channel_mix AS
SELECT
    customer_key,
    CASE
        WHEN bool_and(channel_key = 2) THEN 'online only'
        WHEN bool_and(channel_key = 1) THEN 'store only'
        ELSE 'omnichannel'
    END                          AS channel_mix,
    count(DISTINCT date_key)     AS purchase_days,
    sum(revenue)                 AS spend,
    sum(units)::BIGINT           AS units
FROM fact_sales
GROUP BY customer_key;

-- RFM segments as of the day after the data ends, over the last 52 weeks.
CREATE OR REPLACE VIEW v_rfm_segments AS
WITH base AS (
    SELECT * FROM rfm(DATE '2020-09-23', 364)
),
scored AS (                     -- quintile scores 1..5; ties share a score
    SELECT *,
        1 + least(4, floor(percent_rank() OVER (ORDER BY recency_days DESC) * 5))::INTEGER AS r_score,
        1 + least(4, floor(percent_rank() OVER (ORDER BY frequency_days)    * 5))::INTEGER AS f_score,
        1 + least(4, floor(percent_rank() OVER (ORDER BY monetary)          * 5))::INTEGER AS m_score
    FROM base
)
SELECT *,
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
        WHEN f_score >= 4                                    THEN 'Loyal'
        WHEN r_score >= 4 AND f_score <= 2                   THEN 'New / promising'
        WHEN r_score <= 2 AND f_score >= 3                   THEN 'At risk'
        WHEN r_score <= 2 AND f_score <= 2                   THEN 'Hibernating'
        ELSE 'Needs attention'
    END AS segment
FROM scored;