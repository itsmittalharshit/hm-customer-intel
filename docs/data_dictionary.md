# Data dictionary

Generated from `warehouse.duckdb` by `make docs`. Do not edit by hand.

## `dim_article` (105,542 rows)

One row per article, including 995 never sold.

| Column | Type | Description |
| --- | --- | --- |
| `article_key` | INTEGER | int32 surrogate key, assigned by sorting the original 10-digit article_id. |
| `article_id` | VARCHAR |  |
| `product_code` | BIGINT |  |
| `prod_name` | VARCHAR |  |
| `product_type_name` | VARCHAR |  |
| `product_group_name` | VARCHAR |  |
| `graphical_appearance_name` | VARCHAR |  |
| `colour_group_name` | VARCHAR |  |
| `perceived_colour_master_name` | VARCHAR |  |
| `department_name` | VARCHAR |  |
| `index_name` | VARCHAR |  |
| `index_group_name` | VARCHAR |  |
| `section_name` | VARCHAR |  |
| `garment_group_name` | VARCHAR |  |
| `detail_desc` | VARCHAR |  |

## `dim_channel` (2 rows)

Two sales channels; meaning inferred, not documented.

| Column | Type | Description |
| --- | --- | --- |
| `channel_key` | TINYINT | 1 or 2; 2 is likely online. |
| `channel_name` | VARCHAR |  |

## `dim_customer` (1,371,980 rows)

One row per customer, including 9,699 who never purchased.

| Column | Type | Description |
| --- | --- | --- |
| `customer_key` | INTEGER | int32 surrogate key, assigned by sorting the original customer_id. |
| `customer_id` | VARCHAR |  |
| `fn` | TINYINT | 1 if subscribed to fashion news, else 0 (nulls treated as 0). |
| `active` | TINYINT | 1 if the customer is flagged active for communication, else 0 (nulls treated as 0). |
| `club_member_status` | VARCHAR |  |
| `fashion_news_frequency` | VARCHAR |  |
| `age` | SMALLINT |  |
| `age_band` | VARCHAR | Age grouped into bands; 'unknown' when age is missing. |
| `postal_code` | VARCHAR |  |

## `dim_date` (734 rows)

One row per calendar day, 2018-09-20 to 2020-09-22.

| Column | Type | Description |
| --- | --- | --- |
| `date_key` | DATE | Calendar date (DATE); the key of dim_date. |
| `year` | BIGINT |  |
| `month` | BIGINT |  |
| `iso_week` | BIGINT |  |
| `week_start` | DATE |  |
| `month_start` | DATE |  |
| `day_of_week` | BIGINT |  |
| `season` | VARCHAR |  |
| `covid_lockdown` | BOOLEAN | True between 2020-03-15 and 2020-05-31 (approximate). |

## `fact_sales` (28,813,419 rows)

One row per (day, customer, article, price, channel); identical raw rows collapsed into units.

| Column | Type | Description |
| --- | --- | --- |
| `date_key` | DATE | Calendar date (DATE); the key of dim_date. |
| `customer_key` | INTEGER | int32 surrogate key, assigned by sorting the original customer_id. |
| `article_key` | INTEGER | int32 surrogate key, assigned by sorting the original 10-digit article_id. |
| `channel_key` | TINYINT | 1 or 2; 2 is likely online. |
| `price` | DOUBLE | Scaled price per unit (not real currency). |
| `units` | SMALLINT | Number of identical raw rows collapsed into this row. |
| `revenue` | DOUBLE | price * units, in scaled units. |

## `v_customer_cohort` (1,362,281 rows)

First purchase date, cohort month and first channel per customer; cohorts before 2019-03 are left-censored.

| Column | Type | Description |
| --- | --- | --- |
| `customer_key` | INTEGER | int32 surrogate key, assigned by sorting the original customer_id. |
| `first_purchase` | DATE |  |
| `cohort_month` | DATE |  |
| `first_channel` | TINYINT |  |

## `v_weekly_category_demand` (2,226 rows)

Weekly units, revenue and buyers per garment group; days_observed < 7 = partial week.

| Column | Type | Description |
| --- | --- | --- |
| `week_start` | DATE |  |
| `garment_group_name` | VARCHAR |  |
| `units` | BIGINT | Number of identical raw rows collapsed into this row. |
| `revenue` | DOUBLE | price * units, in scaled units. |
| `buyers` | BIGINT |  |
| `days_observed` | BIGINT | Distinct days with sales in that week; 7 = full week. |
