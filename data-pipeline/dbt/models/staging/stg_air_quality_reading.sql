-- data-pipeline/dbt/models/staging/stg_air_quality_readings.sql
{{ config(
    materialized='incremental',
    unique_key='reading_id',
    on_schema_change='fail'
) }}

WITH source_data AS (
    SELECT 
        sensor_id || '_' || timestamp AS reading_id,
        sensor_id,
        location_name,
        latitude,
        longitude,
        aqi,
        pm25,
        pm10,
        no2,
        o3,
        co,
        temperature,
        humidity,
        pressure,
        wind_speed,
        wind_direction,
        visibility,
        timestamp,
        created_at
    FROM {{ source('raw', 'air_quality_readings') }}
    WHERE timestamp IS NOT NULL
    
    {% if is_incremental() %}
        AND timestamp > (SELECT MAX(timestamp) FROM {{ this }})
    {% endif %}
),

validated_data AS (
    SELECT *,
        CASE 
            WHEN aqi BETWEEN 0 AND 500 THEN aqi
            ELSE NULL 
        END AS validated_aqi,
        CASE 
            WHEN pm25 >= 0 AND pm25 <= 500 THEN pm25
            ELSE NULL 
        END AS validated_pm25,
        CASE 
            WHEN temperature BETWEEN -50 AND 60 THEN temperature
            ELSE NULL 
        END AS validated_temperature
    FROM source_data
),

final AS (
    SELECT 
        reading_id,
        sensor_id,
        location_name,
        latitude,
        longitude,
        validated_aqi AS aqi,
        validated_pm25 AS pm25,
        validated_pm10 AS pm10,
        no2,
        o3,
        co,
        validated_temperature AS temperature,
        humidity,
        pressure,
        wind_speed,
        wind_direction,
        visibility,
        timestamp,
        created_at,
        CURRENT_TIMESTAMP AS dbt_updated_at
    FROM validated_data
    WHERE validated_aqi IS NOT NULL
)

SELECT * FROM final

-- data-pipeline/dbt/models/marts/air_quality_hourly_summary.sql
{{ config(materialized='table') }}

WITH hourly_readings AS (
    SELECT 
        sensor_id,
        location_name,
        latitude,
        longitude,
        DATE_TRUNC('hour', timestamp) AS hour,
        AVG(aqi) AS avg_aqi,
        MAX(aqi) AS max_aqi,
        MIN(aqi) AS min_aqi,
        AVG(pm25) AS avg_pm25,
        AVG(pm10) AS avg_pm10,
        AVG(no2) AS avg_no2,
        AVG(o3) AS avg_o3,
        AVG(co) AS avg_co,
        AVG(temperature) AS avg_temperature,
        AVG(humidity) AS avg_humidity,
        AVG(pressure) AS avg_pressure,
        AVG(wind_speed) AS avg_wind_speed,
        COUNT(*) AS reading_count
    FROM {{ ref('stg_air_quality_readings') }}
    WHERE timestamp >= CURRENT_DATE - INTERVAL '7 days'
    GROUP BY 1, 2, 3, 4, 5
),

aqi_categories AS (
    SELECT *,
        CASE 
            WHEN avg_aqi <= 50 THEN 'Good'
            WHEN avg_aqi <= 100 THEN 'Moderate'
            WHEN avg_aqi <= 150 THEN 'Unhealthy for Sensitive Groups'
            WHEN avg_aqi <= 200 THEN 'Unhealthy'
            WHEN avg_aqi <= 300 THEN 'Very Unhealthy'
            ELSE 'Hazardous'
        END AS aqi_category,
        CASE 
            WHEN avg_aqi <= 100 THEN 'Acceptable'
            ELSE 'Concerning'
        END AS health_status
    FROM hourly_readings
)

SELECT * FROM aqi_categories
ORDER BY hour DESC, sensor_id

-- data-pipeline/dbt/models/marts/city_air_quality_rankings.sql
{{ config(materialized='table') }}

WITH latest_city_data AS (
    SELECT 
        location_name AS city,
        AVG(avg_aqi) AS current_aqi,
        AVG(avg_pm25) AS current_pm25,
        COUNT(DISTINCT sensor_id) AS sensor_count,
        MAX(hour) AS last_updated
    FROM {{ ref('air_quality_hourly_summary') }}
    WHERE hour >= CURRENT_DATE - INTERVAL '24 hours'
    GROUP BY location_name
),

city_rankings AS (
    SELECT *,
        RANK() OVER (ORDER BY current_aqi) AS aqi_rank,
        CASE 
            WHEN current_aqi <= 50 THEN '🟢'
            WHEN current_aqi <= 100 THEN '🟡'
            WHEN current_aqi <= 150 THEN '🟠'
            ELSE '🔴'
        END AS status_emoji
    FROM latest_city_data
)

SELECT * FROM city_rankings
ORDER BY aqi_rank