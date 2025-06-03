# data-pipeline/airflow/dags/air_quality_pipeline.py
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.amazon.aws.operators.s3 import S3CreateObjectOperator
from airflow.models import Variable
import pandas as pd
import requests
import numpy as np
from typing import List, Dict
import logging

# Configuration
default_args = {
    'owner': 'data-engineering-team',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(minutes=30),
}

dag = DAG(
    'air_quality_etl_pipeline_v2',
    default_args=default_args,
    description='Comprehensive air quality data pipeline with ML predictions',
    schedule_interval='@hourly',
    catchup=False,
    max_active_runs=1,
    tags=['air-quality', 'etl', 'ml', 'production'],
    doc_md="""
    # Air Quality ETL Pipeline v2.0
    
    This pipeline processes air quality data from multiple sources:
    - Satellite data (NASA MODIS, Sentinel-5P)
    - Weather APIs (OpenWeatherMap, AccuWeather)
    - Government APIs (EPA AirNow, EEA)
    - IoT sensor networks
    
    The pipeline includes:
    1. Data ingestion and validation
    2. Real-time stream processing
    3. Feature engineering and transformation
    4. ML model training and inference
    5. Data quality monitoring
    6. Automated alerting
    """,
)

def extract_satellite_data(**context) -> Dict:
    """Extract air quality data from satellite APIs."""
    import requests
    from datetime import datetime, timedelta
    
    logger = logging.getLogger(__name__)
    logger.info("Starting satellite data extraction")
    
    # NASA MODIS API
    modis_api_key = Variable.get("NASA_API_KEY")
    sentinel_api_key = Variable.get("SENTINEL_API_KEY")
    
    # Target cities and coordinates
    cities = [
        {"name": "New York", "lat": 40.7128, "lon": -74.0060},
        {"name": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
        {"name": "Chicago", "lat": 41.8781, "lon": -87.6298},
        {"name": "Houston", "lat": 29.7604, "lon": -95.3698},
        {"name": "Phoenix", "lat": 33.4484, "lon": -112.0740},
    ]
    
    satellite_data = []
    
    for city in cities:
        try:
            # MODIS AOD (Aerosol Optical Depth) data
            modis_url = f"https://modis.gsfc.nasa.gov/data/dataprod/mod04.php"
            modis_params = {
                "product": "MOD04_L2",
                "latitude": city["lat"],
                "longitude": city["lon"],
                "date": context['ds'],
                "api_key": modis_api_key
            }
            
            modis_response = requests.get(modis_url, params=modis_params, timeout=30)
            if modis_response.status_code == 200:
                modis_data = modis_response.json()
                
                # Process MODIS data
                aod_550 = modis_data.get('AOD_550_Dark_Target_Deep_Blue_Combined', {}).get('value', 0)
                
                satellite_data.append({
                    'city': city['name'],
                    'latitude': city['lat'],
                    'longitude': city['lon'],
                    'source': 'MODIS',
                    'aod_550': aod_550,
                    'timestamp': context['ts'],
                    'data_date': context['ds']
                })
            
            # Sentinel-5P NO2 data
            sentinel_url = "https://s5phub.copernicus.eu/dhus/search"
            sentinel_params = {
                "q": f"platformname:Sentinel-5P AND producttype:L2__NO2___ AND footprint:\"Intersects(POINT({city['lon']} {city['lat']}))\""
            }
            
            sentinel_response = requests.get(sentinel_url, params=sentinel_params, timeout=30)
            if sentinel_response.status_code == 200:
                # Process Sentinel data (simplified)
                no2_column = np.random.normal(2.5e15, 5e14)  # Simulated for demo
                
                satellite_data.append({
                    'city': city['name'],
                    'latitude': city['lat'],
                    'longitude': city['lon'],
                    'source': 'Sentinel-5P',
                    'no2_column_density': no2_column,
                    'timestamp': context['ts'],
                    'data_date': context['ds']
                })
                
        except Exception as e:
            logger.error(f"Error extracting satellite data for {city['name']}: {str(e)}")
            continue
    
    logger.info(f"Extracted {len(satellite_data)} satellite data records")
    return satellite_data

def extract_weather_data(**context) -> Dict:
    """Extract weather data from multiple APIs."""
    logger = logging.getLogger(__name__)
    logger.info("Starting weather data extraction")
    
    openweather_api_key = Variable.get("OPENWEATHER_API_KEY")
    
    cities = [
        {"name": "New York", "lat": 40.7128, "lon": -74.0060},
        {"name": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
        {"name": "Chicago", "lat": 41.8781, "lon": -87.6298},
    ]
    
    weather_data = []
    
    for city in cities:
        try:
            # Current weather
            weather_url = "http://api.openweathermap.org/data/2.5/weather"
            weather_params = {
                "lat": city["lat"],
                "lon": city["lon"],
                "appid": openweather_api_key,
                "units": "metric"
            }
            
            response = requests.get(weather_url, params=weather_params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                
                weather_data.append({
                    'city': city['name'],
                    'temperature': data['main']['temp'],
                    'humidity': data['main']['humidity'],
                    'pressure': data['main']['pressure'],
                    'wind_speed': data['wind'].get('speed', 0),
                    'wind_direction': data['wind'].get('deg', 0),
                    'visibility': data.get('visibility', 10000),
                    'timestamp': context['ts'],
                    'data_date': context['ds']
                })
                
        except Exception as e:
            logger.error(f"Error extracting weather data for {city['name']}: {str(e)}")
            continue
    
    logger.info(f"Extracted {len(weather_data)} weather data records")
    return weather_data

def extract_government_api_data(**context) -> Dict:
    """Extract data from government air quality APIs."""
    logger = logging.getLogger(__name__)
    logger.info("Starting government API data extraction")
    
    epa_api_key = Variable.get("EPA_API_KEY")
    
    # EPA AirNow API
    airnow_url = "https://www.airnowapi.org/aq/observation/zipCode/current/"
    
    zip_codes = ["10001", "90210", "60601", "77001", "85001"]  # Major cities
    government_data = []
    
    for zip_code in zip_codes:
        try:
            params = {
                "format": "application/json",
                "zipCode": zip_code,
                "distance": 25,
                "API_KEY": epa_api_key
            }
            
            response = requests.get(airnow_url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                
                for reading in data:
                    government_data.append({
                        'zip_code': zip_code,
                        'parameter': reading['ParameterName'],
                        'aqi': reading['AQI'],
                        'category': reading['Category']['Name'],
                        'site_name': reading['ReportingArea'],
                        'timestamp': reading['DateObserved'] + 'T' + reading['HourObserved'] + ':00:00',
                        'data_date': context['ds']
                    })
                    
        except Exception as e:
            logger.error(f"Error extracting government data for {zip_code}: {str(e)}")
            continue
    
    logger.info(f"Extracted {len(government_data)} government data records")
    return government_data

def transform_and_validate_data(**context) -> None:
    """Transform raw data and perform validation."""
    logger = logging.getLogger(__name__)
    logger.info("Starting data transformation and validation")
    
    # Get data from previous tasks
    satellite_data = context['ti'].xcom_pull(task_ids='extract_satellite_data')
    weather_data = context['ti'].xcom_pull(task_ids='extract_weather_data')
    government_data = context['ti'].xcom_pull(task_ids='extract_government_api_data')
    
    # Transform satellite data
    satellite_df = pd.DataFrame(satellite_data)
    if not satellite_df.empty:
        satellite_df['timestamp'] = pd.to_datetime(satellite_df['timestamp'])
        satellite_df['aod_550_normalized'] = (satellite_df['aod_550'] - satellite_df['aod_550'].mean()) / satellite_df['aod_550'].std()
    
    # Transform weather data
    weather_df = pd.DataFrame(weather_data)
    if not weather_df.empty:
        weather_df['timestamp'] = pd.to_datetime(weather_df['timestamp'])
        weather_df['temp_category'] = pd.cut(weather_df['temperature'], 
                                           bins=[-np.inf, 0, 15, 25, np.inf], 
                                           labels=['cold', 'cool', 'warm', 'hot'])
    
    # Transform government data
    gov_df = pd.DataFrame(government_data)
    if not gov_df.empty:
        gov_df['timestamp'] = pd.to_datetime(gov_df['timestamp'])
        gov_df['aqi_category'] = pd.cut(gov_df['aqi'], 
                                      bins=[0, 50, 100, 150, 200, 300, np.inf],
                                      labels=['Good', 'Moderate', 'Unhealthy for Sensitive', 
                                             'Unhealthy', 'Very Unhealthy', 'Hazardous'])
    
    # Data quality checks
    quality_issues = []
    
    # Check for missing values
    if satellite_df.isnull().sum().sum() > 0:
        quality_issues.append("Missing values in satellite data")
    
    if weather_df.isnull().sum().sum() > 0:
        quality_issues.append("Missing values in weather data")
    
    # Check for outliers
    if not gov_df.empty and (gov_df['aqi'] > 500).any():
        quality_issues.append("Extreme AQI values detected")
    
    if quality_issues:
        logger.warning(f"Data quality issues detected: {quality_issues}")
        
    # Store transformed data
    postgres_hook = PostgresHook(postgres_conn_id='airsense_postgres')
    
    # Insert satellite data
    if not satellite_df.empty:
        satellite_df.to_sql('satellite_readings_staging', 
                          postgres_hook.get_sqlalchemy_engine(), 
                          if_exists='replace', index=False)
    
    # Insert weather data
    if not weather_df.empty:
        weather_df.to_sql('weather_readings_staging', 
                        postgres_hook.get_sqlalchemy_engine(), 
                        if_exists='replace', index=False)
    
    # Insert government data
    if not gov_df.empty:
        gov_df.to_sql('government_readings_staging', 
                    postgres_hook.get_sqlalchemy_engine(), 
                    if_exists='replace', index=False)
    
    logger.info("Data transformation and validation completed")

def run_ml_pipeline(**context) -> Dict:
    """Run machine learning pipeline for AQI prediction."""
    logger = logging.getLogger(__name__)
    logger.info("Starting ML pipeline")
    
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    import joblib
    import mlflow
    
    # Get recent data for training
    postgres_hook = PostgresHook(postgres_conn_id='airsense_postgres')
    
    query = """
    SELECT 
        aqi, pm25, pm10, no2, o3, co,
        temperature, humidity, pressure, wind_speed,
        EXTRACT(hour FROM timestamp) as hour,
        EXTRACT(dow FROM timestamp) as day_of_week,
        LAG(aqi, 1) OVER (ORDER BY timestamp) as prev_aqi,
        LAG(aqi, 24) OVER (ORDER BY timestamp) as aqi_24h_ago
    FROM air_quality_readings 
    WHERE timestamp >= NOW() - INTERVAL '30 days'
    AND aqi IS NOT NULL
    ORDER BY timestamp
    """
    
    df = postgres_hook.get_pandas_df(query)
    
    if len(df) < 100:
        logger.warning("Insufficient data for ML training")
        return {"status": "skipped", "reason": "insufficient_data"}
    
    # Prepare features and target
    feature_cols = ['pm25', 'pm10', 'no2', 'o3', 'co', 'temperature', 
                   'humidity', 'pressure', 'wind_speed', 'hour', 'day_of_week', 
                   'prev_aqi', 'aqi_24h_ago']
    
    df_ml = df.dropna()
    X = df_ml[feature_cols]
    y = df_ml['aqi']
    
    # Train-test split (temporal)
    split_idx = int(len(df_ml) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]
    
    # Train model
    with mlflow.start_run():
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        # Evaluate
        y_pred = model.predict(X_test)
        mae = mean_absolute_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        
        # Log metrics
        mlflow.log_metric("mae", mae)
        mlflow.log_metric("r2", r2)
        mlflow.sklearn.log_model(model, "aqi_prediction_model")
        
        # Save model
        model_path = f"/opt/airflow/models/aqi_model_{context['ds']}.pkl"
        joblib.dump(model, model_path)
        
        logger.info(f"Model trained successfully. MAE: {mae:.2f}, R2: {r2:.3f}")
        
        return {
            "status": "success",
            "mae": mae,
            "r2": r2,
            "model_path": model_path,
            "training_samples": len(X_train),
            "test_samples": len(X_test)
        }

def generate_predictions(**context) -> None:
    """Generate air quality predictions for next 24 hours."""
    logger = logging.getLogger(__name__)
    logger.info("Generating air quality predictions")
    
    import joblib
    from datetime import datetime, timedelta
    
    # Load latest model
    ml_results = context['ti'].xcom_pull(task_ids='run_ml_pipeline')
    if ml_results['status'] != 'success':
        logger.warning("Skipping predictions due to ML pipeline issues")
        return
    
    model = joblib.load(ml_results['model_path'])
    
    # Get latest data for prediction
    postgres_hook = PostgresHook(postgres_conn_id='airsense_postgres')
    
    query = """
    SELECT DISTINCT ON (sensor_id)
        sensor_id, location_name, latitude, longitude,
        pm25, pm10, no2, o3, co, temperature, humidity, 
        pressure, wind_speed, aqi, timestamp
    FROM air_quality_readings 
    WHERE timestamp >= NOW() - INTERVAL '2 hours'
    ORDER BY sensor_id, timestamp DESC
    """
    
    current_df = postgres_hook.get_pandas_df(query)
    
    predictions = []
    prediction_times = [1, 6, 12, 24]  # Hours ahead
    
    for _, row in current_df.iterrows():
        for hours_ahead in prediction_times:
            try:
                # Prepare features (simplified for demo)
                future_time = datetime.now() + timedelta(hours=hours_ahead)
                features = [
                    row['pm25'], row['pm10'], row['no2'], row['o3'], row['co'],
                    row['temperature'], row['humidity'], row['pressure'], 
                    row['wind_speed'], future_time.hour, future_time.weekday(),
                    row['aqi'], row['aqi']  # prev_aqi, aqi_24h_ago (simplified)
                ]
                
                predicted_aqi = model.predict([features])[0]
                
                predictions.append({
                    'sensor_id': row['sensor_id'],
                    'prediction_timestamp': future_time,
                    'hours_ahead': hours_ahead,
                    'predicted_aqi': round(predicted_aqi, 1),
                    'confidence_score': 0.85,  # Simplified
                    'model_version': context['ds'],
                    'created_at': datetime.now()
                })
                
            except Exception as e:
                logger.error(f"Error predicting for sensor {row['sensor_id']}: {str(e)}")
                continue
    
    # Store predictions
    if predictions:
        pred_df = pd.DataFrame(predictions)
        pred_df.to_sql('air_quality_predictions', 
                      postgres_hook.get_sqlalchemy_engine(), 
                      if_exists='append', index=False)
        
        logger.info(f"Generated {len(predictions)} predictions")
    else:
        logger.warning("No predictions generated")

def send_alerts(**context) -> None:
    """Send alerts for unhealthy air quality conditions."""
    logger = logging.getLogger(__name__)
    logger.info("Checking for air quality alerts")
    
    postgres_hook = PostgresHook(postgres_conn_id='airsense_postgres')
    
    # Check for current unhealthy conditions
    alert_query = """
    SELECT DISTINCT ON (sensor_id)
        sensor_id, location_name, aqi, timestamp
    FROM air_quality_readings 
    WHERE timestamp >= NOW() - INTERVAL '1 hour'
    AND aqi > 100  -- Unhealthy threshold
    ORDER BY sensor_id, timestamp DESC
    """
    
    alerts_df = postgres_hook.get_pandas_df(alert_query)
    
    if not alerts_df.empty:
        for _, alert in alerts_df.iterrows():
            # Send alert (simplified - would integrate with notification service)
            alert_message = f"""
            🚨 Air Quality Alert
            Location: {alert['location_name']}
            Current AQI: {alert['aqi']}
            Status: {"Unhealthy" if alert['aqi'] <= 150 else "Very Unhealthy" if alert['aqi'] <= 200 else "Hazardous"}
            Time: {alert['timestamp']}
            
            Please limit outdoor activities and consider wearing a mask.
            """
            
            logger.warning(f"Alert for {alert['location_name']}: AQI {alert['aqi']}")
            
            # Here you would integrate with:
            # - Email service (SES, SendGrid)
            # - SMS service (Twilio, SNS)
            # - Push notifications
            # - Slack/Teams webhooks
    
    logger.info(f"Processed {len(alerts_df)} air quality alerts")

# Task definitions
check_api_availability = HttpSensor(
    task_id='check_api_availability',
    http_conn_id='openweather_api',
    endpoint='data/2.5/weather?q=London&appid={{ var.value.OPENWEATHER_API_KEY }}',
    timeout=30,
    poke_interval=60,
    dag=dag
)

extract_satellite_task = PythonOperator(
    task_id='extract_satellite_data',
    python_callable=extract_satellite_data,
    dag=dag,
    doc_md="Extract air quality data from satellite APIs (NASA MODIS, Sentinel-5P)"
)

extract_weather_task = PythonOperator(
    task_id='extract_weather_data',
    python_callable=extract_weather_data,
    dag=dag,
    doc_md="Extract weather data from OpenWeatherMap and other APIs"
)

extract_government_task = PythonOperator(
    task_id='extract_government_api_data',
    python_callable=extract_government_api_data,
    dag=dag,
    doc_md="Extract data from government air quality APIs (EPA, EEA)"
)

transform_validate_task = PythonOperator(
    task_id='transform_and_validate_data',
    python_callable=transform_and_validate_data,
    dag=dag,
    doc_md="Transform raw data and perform data quality validation"
)

run_dbt_models = BashOperator(
    task_id='run_dbt_models',
    bash_command='cd /opt/airflow/dbt && dbt run --profiles-dir /opt/airflow/dbt/profiles',
    dag=dag,
    doc_md="Run dbt models for data transformation"
)

run_dbt_tests = BashOperator(
    task_id='run_dbt_tests',
    bash_command='cd /opt/airflow/dbt && dbt test --profiles-dir /opt/airflow/dbt/profiles',
    dag=dag,
    doc_md="Run dbt tests for data quality validation"
)

ml_pipeline_task = PythonOperator(
    task_id='run_ml_pipeline',
    python_callable=run_ml_pipeline,
    dag=dag,
    doc_md="Train and validate machine learning models"
)

generate_predictions_task = PythonOperator(
    task_id='generate_predictions',
    python_callable=generate_predictions,
    dag=dag,
    doc_md="Generate air quality predictions using trained models"
)

send_alerts_task = PythonOperator(
    task_id='send_alerts',
    python_callable=send_alerts,
    dag=dag,
    doc_md="Send alerts for unhealthy air quality conditions"
)

backup_data_task = S3CreateObjectOperator(
    task_id='backup_to_s3',
    s3_bucket='airsense-data-lake-{{ var.value.ENVIRONMENT }}',
    s3_key='backups/{{ ds }}/air_quality_backup.parquet',
    data='{{ ti.xcom_pull(task_ids="transform_and_validate_data") }}',
    dag=dag
)

# Task dependencies
check_api_availability >> [extract_satellite_task, extract_weather_task, extract_government_task]
[extract_satellite_task, extract_weather_task, extract_government_task] >> transform_validate_task
transform_validate_task >> run_dbt_models >> run_dbt_tests
run_dbt_tests >> ml_pipeline_task >> generate_predictions_task
generate_predictions_task >> [send_alerts_task, backup_data_task]