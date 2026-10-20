-- Star schema built from the Parquet lake. {processed} is filled in by Python.

CREATE OR REPLACE TABLE dim_customer AS
SELECT
    customer_key,
    customer_id,
    fn,
    active,
    club_member_status,
    fashion_news_frequency,
    age,
    CASE
        WHEN age IS NULL THEN 'unknown'
        WHEN age < 25 THEN '16-24'
        WHEN age < 35 THEN '25-34'
        WHEN age < 45 THEN '35-44'
        WHEN age < 55 THEN '45-54'
        ELSE '55+'
    END AS age_band,
    postal_code
FROM read_parquet('{processed}/customers.parquet');

CREATE OR REPLACE TABLE dim_article AS
SELECT * FROM read_parquet('{processed}/articles.parquet');

CREATE OR REPLACE TABLE dim_channel AS
SELECT * FROM (VALUES
    (1::TINYINT, 'channel 1 (likely store)'),
    (2::TINYINT, 'channel 2 (likely online)')
) AS t(channel_key, channel_name);

CREATE OR REPLACE TABLE dim_date AS
SELECT
    d::DATE                          AS date_key,
    year(d)                          AS year,
    month(d)                         AS month,
    weekofyear(d)                    AS iso_week,
    date_trunc('week', d)::DATE      AS week_start,     -- Monday-based weeks
    date_trunc('month', d)::DATE     AS month_start,
    dayofweek(d)                     AS day_of_week,
    CASE
        WHEN month(d) IN (12, 1, 2) THEN 'winter'
        WHEN month(d) IN (3, 4, 5)  THEN 'spring'
        WHEN month(d) IN (6, 7, 8)  THEN 'summer'
        ELSE 'autumn'
    END                              AS season,
    d BETWEEN DATE '2020-03-15' AND DATE '2020-05-31' AS covid_lockdown
FROM generate_series(DATE '2018-09-20', DATE '2020-09-22', INTERVAL 1 DAY) AS t(d);

CREATE OR REPLACE TABLE fact_sales AS
SELECT
    t_dat                        AS date_key,
    customer_key,
    article_key,
    sales_channel_id             AS channel_key,
    price::DOUBLE                AS price,
    units,
    price::DOUBLE * units        AS revenue
FROM read_parquet('{processed}/transactions.parquet');