# backend/app/api/v1/endpoints/air_quality.py
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio

from app.models.air_quality import AirQualityReading, AirQualityResponse
from app.services.prediction_service import PredictionService
from app.core.database import get_db

router = APIRouter()

@router.get("/current", response_model=List[AirQualityResponse])
async def get_current_air_quality(
    city: Optional[str] = Query(None, description="Filter by city"),
    limit: int = Query(100, le=1000, description="Maximum number of records"),
    db=Depends(get_db)
):
    """Get current air quality readings for all monitored locations."""
    try:
        query = """
        SELECT DISTINCT ON (sensor_id) 
            sensor_id, location_name, latitude, longitude,
            aqi, pm25, pm10, no2, o3, co, timestamp
        FROM air_quality_readings 
        WHERE timestamp >= NOW() - INTERVAL '1 hour'
        ORDER BY sensor_id, timestamp DESC
        LIMIT %s
        """
        
        params = [limit]
        if city:
            query += " AND location_name ILIKE %s"
            params.insert(-1, f"%{city}%")
            
        result = await db.fetch_all(query, params)
        return [AirQualityResponse(**row) for row in result]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@router.get("/predictions/{sensor_id}")
async def get_air_quality_predictions(
    sensor_id: str,
    hours_ahead: int = Query(6, ge=1, le=168, description="Hours to predict ahead"),
    prediction_service: PredictionService = Depends()
):
    """Get air quality predictions for a specific sensor."""
    return await prediction_service.predict_aqi(sensor_id, hours_ahead)

@router.get("/historical/{sensor_id}")
async def get_historical_data(
    sensor_id: str,
    start_date: datetime = Query(..., description="Start date for historical data"),
    end_date: datetime = Query(..., description="End date for historical data"),
    db=Depends(get_db)
):
    """Get historical air quality data for analysis."""
    if end_date - start_date > timedelta(days=90):
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")
    
    query = """
    SELECT timestamp, aqi, pm25, pm10, no2, o3, co
    FROM air_quality_readings 
    WHERE sensor_id = %s AND timestamp BETWEEN %s AND %s
    ORDER BY timestamp
    """
    
    result = await db.fetch_all(query, [sensor_id, start_date, end_date])
    return {"sensor_id": sensor_id, "data": result}

@router.post("/alerts/subscribe")
async def subscribe_to_alerts(
    email: str,
    sensor_ids: List[str],
    threshold: int = Query(100, description="AQI threshold for alerts"),
    background_tasks: BackgroundTasks
):
    """Subscribe to air quality alerts for specific sensors."""
    background_tasks.add_task(setup_alert_subscription, email, sensor_ids, threshold)
    return {"message": "Alert subscription created successfully"}