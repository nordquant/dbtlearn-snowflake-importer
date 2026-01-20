# CEU Capstone - AIRSTATS Database Setup

This file contains the SQL setup for the CEU Modern Data Platforms capstone project.
It is only executed when accessing the setup via `?course=ceu` query parameter.

```sql {#capstone_airstats}
-- AIRSTATS Database Setup for Snowflake
-- Source: OurAirports.com (Public Domain)
-- Data loaded directly from public S3 bucket: s3://dbt-datasets/airstats/csv/

-- Database and Schema Setup
CREATE DATABASE IF NOT EXISTS AIRSTATS;
USE DATABASE AIRSTATS;
CREATE SCHEMA IF NOT EXISTS RAW;
USE SCHEMA RAW;

-- AIRPORTS: Global airport data (~72K rows)
CREATE OR REPLACE TABLE airports (
    id                  INTEGER,
    ident               STRING,
    type                STRING,
    name                STRING,
    latitude_deg        FLOAT,
    longitude_deg       FLOAT,
    elevation_ft        INTEGER,
    continent           STRING,
    iso_country         STRING,
    iso_region          STRING,
    municipality        STRING,
    scheduled_service   STRING,
    gps_code            STRING,
    iata_code           STRING,
    local_code          STRING,
    home_link           STRING,
    wikipedia_link      STRING,
    keywords            STRING
);

COPY INTO airports (id, ident, type, name, latitude_deg, longitude_deg,
                    elevation_ft, continent, iso_country, iso_region,
                    municipality, scheduled_service, gps_code, iata_code,
                    local_code, home_link, wikipedia_link, keywords)
    FROM 's3://dbt-datasets/airstats/csv/airports.csv'
    FILE_FORMAT = (TYPE = 'CSV' SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"');

-- AIRPORT_COMMENTS: User comments about airports (fact table with timestamps)
CREATE OR REPLACE TABLE airport_comments (
    id                  INTEGER,
    thread_ref          INTEGER,
    airport_ref         INTEGER,
    airport_ident       STRING,
    date                DATETIME,
    member_nickname     STRING,
    subject             STRING,
    body                STRING,
    loaded_at           TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP
);

COPY INTO airport_comments (id, thread_ref, airport_ref, airport_ident,
                            date, member_nickname, subject, body)
    FROM 's3://dbt-datasets/airstats/csv/airport_comments.csv'
    FILE_FORMAT = (TYPE = 'CSV' SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"');

-- RUNWAYS: Runway information (~44K rows) - joins to airports via airport_ref/airport_ident
CREATE OR REPLACE TABLE runways (
    id                          INTEGER,
    airport_ref                 INTEGER,
    airport_ident               STRING,
    length_ft                   INTEGER,
    width_ft                    INTEGER,
    surface                     STRING,
    lighted                     INTEGER,
    closed                      INTEGER,
    le_ident                    STRING,
    le_latitude_deg             FLOAT,
    le_longitude_deg            FLOAT,
    le_elevation_ft             INTEGER,
    le_heading_degT             FLOAT,
    le_displaced_threshold_ft   INTEGER,
    he_ident                    STRING,
    he_latitude_deg             FLOAT,
    he_longitude_deg            FLOAT,
    he_elevation_ft             INTEGER,
    he_heading_degT             FLOAT,
    he_displaced_threshold_ft   INTEGER
);

COPY INTO runways (id, airport_ref, airport_ident, length_ft, width_ft, surface,
                   lighted, closed, le_ident, le_latitude_deg, le_longitude_deg,
                   le_elevation_ft, le_heading_degT, le_displaced_threshold_ft,
                   he_ident, he_latitude_deg, he_longitude_deg, he_elevation_ft,
                   he_heading_degT, he_displaced_threshold_ft)
    FROM 's3://dbt-datasets/airstats/csv/runways.csv'
    FILE_FORMAT = (TYPE = 'CSV' SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"');

-- Permission Grants for AIRSTATS database
USE ROLE ACCOUNTADMIN;

-- TRANSFORM role permissions (for dbt user)
GRANT ALL ON DATABASE AIRSTATS TO ROLE TRANSFORM;
GRANT ALL ON ALL SCHEMAS IN DATABASE AIRSTATS TO ROLE TRANSFORM;
GRANT ALL ON FUTURE SCHEMAS IN DATABASE AIRSTATS TO ROLE TRANSFORM;
GRANT ALL ON ALL TABLES IN SCHEMA AIRSTATS.RAW TO ROLE TRANSFORM;
GRANT ALL ON FUTURE TABLES IN SCHEMA AIRSTATS.RAW TO ROLE TRANSFORM;

-- REPORTER role permissions (for preset user)
GRANT USAGE ON DATABASE AIRSTATS TO ROLE REPORTER;
GRANT USAGE ON ALL SCHEMAS IN DATABASE AIRSTATS TO ROLE REPORTER;
GRANT USAGE ON FUTURE SCHEMAS IN DATABASE AIRSTATS TO ROLE REPORTER;
GRANT SELECT ON ALL TABLES IN SCHEMA AIRSTATS.RAW TO ROLE REPORTER;
GRANT SELECT ON FUTURE TABLES IN SCHEMA AIRSTATS.RAW TO ROLE REPORTER;
```
