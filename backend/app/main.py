# backend/app/main.py - Updated with Real Data Integration
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn
from datetime import datetime, timedelta
import random
import json
import asyncio
import logging
from typing import List, Optional
from pydantic import BaseModel

# Import our new data service
from app.services.data_service import (
    data_service, 
    get_real_air_quality_data, 
    EnhancedReading,
    setup_api_keys
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Data Models (Enhanced)
class AirQualityReading(BaseModel):
    sensor_id: str
    location_name: str
    latitude: float
    longitude: float
    aqi: int
    pm25: float
    pm10: float
    no2: float
    o3: float
    co: float
    temperature: float
    humidity: int
    timestamp: datetime
    data_sources: List[str] = ["simulated"]
    confidence_score: float = 1.0

class PredictionResponse(BaseModel):
    sensor_id: str
    predicted_aqi: float
    category: str
    hours_ahead: int
    confidence: float
    timestamp: datetime
    model_version: str = "v1.0"

class SystemStatus(BaseModel):
    status: str
    timestamp: datetime
    version: str
    data_sources_available: List[str]
    api_keys_configured: dict
    cache_status: str
    active_sensors: int

# Enhanced Data Generator (fallback for when no API keys)
class EnhancedDataGenerator:
    def __init__(self):
        self.cities = [
            {"name": "New York", "lat": 40.7128, "lng": -74.0060},
            {"name": "Los Angeles", "lat": 34.0522, "lng": -118.2437},
            {"name": "Chicago", "lat": 41.8781, "lng": -87.6298},
            {"name": "Houston", "lat": 29.7604, "lng": -95.3698},
            {"name": "Phoenix", "lat": 33.4484, "lng": -112.0740},
            {"name": "Philadelphia", "lat": 39.9526, "lng": -75.1652},
            {"name": "San Antonio", "lat": 29.4241, "lng": -98.4936},
            {"name": "San Diego", "lat": 32.7157, "lng": -117.1611},
            {"name": "Dallas", "lat": 32.7767, "lng": -96.7970},
            {"name": "San Jose", "lat": 37.3382, "lng": -121.8863},
        ]
        
    def generate_enhanced_readings(self, count: int = None) -> List[AirQualityReading]:
        if count is None:
            count = len(self.cities)
            
        readings = []
        for i, city in enumerate(self.cities[:count]):
            # Generate more realistic data with temporal patterns
            hour = datetime.now().hour
            base_aqi = self._get_city_base_aqi(city["name"])
            
            # Add daily patterns (worse air quality during rush hours)
            if 7 <= hour <= 9 or 17 <= hour <= 19:  # Rush hours
                aqi_modifier = random.uniform(1.2, 1.5)
            elif 2 <= hour <= 5:  # Early morning (best air quality)
                aqi_modifier = random.uniform(0.7, 0.9)
            else:
                aqi_modifier = random.uniform(0.9, 1.2)
            
            aqi = max(5, int(base_aqi * aqi_modifier + random.uniform(-8, 8)))
            pm25 = max(0.1, aqi * 0.35 + random.uniform(-3, 3))
            pm10 = max(0.1, pm25 * 1.3 + random.uniform(-5, 5))
            
            reading = AirQualityReading(
                sensor_id=f"sim_{i+1:03d}",
                location_name=city["name"],
                latitude=city["lat"],
                longitude=city["lng"],
                aqi=aqi,
                pm25=round(pm25, 1),
                pm10=round(pm10, 1),
                no2=round(random.uniform(5, 35) + hour * 0.5, 1),  # Higher during day
                o3=round(random.uniform(15, 75) + max(0, hour - 12) * 2, 1),  # Peak afternoon
                co=round(random.uniform(0.3, 2.1), 1),
                temperature=round(random.uniform(15, 30), 1),
                humidity=random.randint(40, 80),
                timestamp=datetime.now(),
                data_sources=["simulated"],
                confidence_score=0.75  # Lower confidence for simulated data
            )
            readings.append(reading)
            
        return readings
    
    def _get_city_base_aqi(self, city_name: str) -> int:
        """Get realistic base AQI for different cities."""
        city_base_aqi = {
            "New York": 55, "Los Angeles": 85, "Chicago": 42,
            "Houston": 68, "Phoenix": 72, "Philadelphia": 52,
            "San Antonio": 48, "San Diego": 38, "Dallas": 62, "San Jose": 44
        }
        return city_base_aqi.get(city_name, 50)

# Initialize FastAPI app
app = FastAPI(
    title="AirSense Intelligence Platform API",
    description="Advanced air quality monitoring and prediction system with real-time data integration",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize enhanced data generator (fallback)
enhanced_generator = EnhancedDataGenerator()

# Cache for performance
app_cache = {
    "last_real_data_fetch": None,
    "cached_readings": [],
    "api_status": {}
}

async def get_api_keys_status():
    """Check which API keys are configured."""
    import os
    return {
        "openweather": bool(os.getenv("OPENWEATHER_API_KEY")),
        "epa": bool(os.getenv("EPA_API_KEY")),
        "nasa": bool(os.getenv("NASA_API_KEY"))
    }

async def get_current_readings() -> List[AirQualityReading]:
    """Get current readings, preferring real data when available."""
    api_keys = await get_api_keys_status()
    
    if any(api_keys.values()):
        # Try to get real data
        try:
            logger.info("Fetching real air quality data...")
            real_readings = await get_real_air_quality_data()
            
            if real_readings:
                # Convert EnhancedReading to AirQualityReading
                converted_readings = []
                for reading in real_readings:
                    converted = AirQualityReading(
                        sensor_id=reading.sensor_id,
                        location_name=reading.location.city,
                        latitude=reading.location.latitude,
                        longitude=reading.location.longitude,
                        aqi=reading.air_quality.aqi,
                        pm25=reading.air_quality.pm25,
                        pm10=reading.air_quality.pm10,
                        no2=reading.air_quality.no2,
                        o3=reading.air_quality.o3,
                        co=reading.air_quality.co,
                        temperature=reading.weather.temperature,
                        humidity=reading.weather.humidity,
                        timestamp=reading.timestamp,
                        data_sources=reading.data_sources,
                        confidence_score=reading.confidence_score
                    )
                    converted_readings.append(converted)
                
                logger.info(f"Successfully fetched {len(converted_readings)} real readings")
                app_cache["cached_readings"] = converted_readings
                app_cache["last_real_data_fetch"] = datetime.now()
                return converted_readings
                
        except Exception as e:
            logger.error(f"Error fetching real data, falling back to simulated: {e}")
    
    # Fallback to enhanced simulated data
    logger.info("Using enhanced simulated data")
    return enhanced_generator.generate_enhanced_readings()

# Routes
@app.get("/", response_class=HTMLResponse)
async def root():
    api_keys = await get_api_keys_status()
    data_source = "Real APIs" if any(api_keys.values()) else "Simulated Data"
    
    return f"""
    <html>
        <head>
            <title>AirSense Intelligence Platform</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
                .container {{ background: rgba(255,255,255,0.1); padding: 30px; border-radius: 15px; backdrop-filter: blur(10px); }}
                .header {{ color: #ffffff; margin-bottom: 20px; }}
                .status {{ background: rgba(255,255,255,0.2); padding: 15px; border-radius: 10px; margin: 10px 0; }}
                .endpoint {{ background: rgba(255,255,255,0.1); padding: 10px; margin: 10px 0; border-radius: 5px; }}
                .api-key {{ display: inline-block; margin: 5px; padding: 5px 10px; border-radius: 15px; font-size: 12px; }}
                .configured {{ background: #10b981; color: white; }}
                .missing {{ background: #ef4444; color: white; }}
                a {{ color: #60a5fa; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="header">🌬️ AirSense Intelligence Platform API v2.0</h1>
                <p>Advanced air quality monitoring and prediction system with real-time data integration</p>
                
                <div class="status">
                    <h3>📊 Current Data Source: {data_source}</h3>
                    <p>API Keys Status:</p>
                    <span class="api-key {'configured' if api_keys['openweather'] else 'missing'}">
                        OpenWeather: {'✅' if api_keys['openweather'] else '❌'}
                    </span>
                    <span class="api-key {'configured' if api_keys['epa'] else 'missing'}">
                        EPA: {'✅' if api_keys['epa'] else '❌'}
                    </span>
                    <span class="api-key {'configured' if api_keys['nasa'] else 'missing'}">
                        NASA: {'✅' if api_keys['nasa'] else '❌'}
                    </span>
                </div>
                
                <h2>🔗 Available Endpoints:</h2>
                <div class="endpoint"><strong>GET /health</strong> - Comprehensive system health check</div>
                <div class="endpoint"><strong>GET /api/v1/air-quality/current</strong> - Current air quality data (real or simulated)</div>
                <div class="endpoint"><strong>GET /api/v1/air-quality/predictions/{{sensor_id}}</strong> - AI-powered predictions</div>
                <div class="endpoint"><strong>GET /api/v1/air-quality/summary</strong> - Platform statistics and metrics</div>
                <div class="endpoint"><strong>GET /api/v1/system/status</strong> - Detailed system status</div>
                <div class="endpoint"><strong>POST /api/v1/system/refresh-data</strong> - Force data refresh</div>
                
                <p><a href="/docs">🔗 View Interactive API Documentation</a></p>
                <p><a href="/api/v1/system/setup-guide">🔧 API Setup Guide</a></p>
            </div>
        </body>
    </html>
    """

@app.get("/health")
async def health_check():
    api_keys = await get_api_keys_status()
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "version": "2.0.0",
        "message": "AirSense Intelligence Platform is running!",
        "data_source": "real" if any(api_keys.values()) else "simulated",
        "api_keys_configured": sum(api_keys.values()),
        "uptime": "running"
    }

@app.get("/api/v1/system/status", response_model=SystemStatus)
async def get_system_status():
    """Get comprehensive system status."""
    api_keys = await get_api_keys_status()
    
    # Check cache status
    cache_status = "active" if app_cache["last_real_data_fetch"] else "empty"
    if app_cache["last_real_data_fetch"]:
        time_since_cache = datetime.now() - app_cache["last_real_data_fetch"]
        if time_since_cache > timedelta(minutes=30):
            cache_status = "stale"
    
    data_sources = []
    if api_keys["openweather"]:
        data_sources.append("OpenWeatherMap")
    if api_keys["epa"]:
        data_sources.append("EPA AirNow")
    if api_keys["nasa"]:
        data_sources.append("NASA")
    if not data_sources:
        data_sources.append("Simulated")
    
    return SystemStatus(
        status="operational",
        timestamp=datetime.now(),
        version="2.0.0",
        data_sources_available=data_sources,
        api_keys_configured=api_keys,
        cache_status=cache_status,
        active_sensors=len(app_cache.get("cached_readings", []))
    )

@app.get("/api/v1/system/setup-guide")
async def get_setup_guide():
    """Get API setup instructions."""
    return {
        "title": "🔑 API Keys Setup Guide",
        "description": "Follow these steps to enable real data sources",
        "steps": [
            {
                "step": 1,
                "service": "OpenWeatherMap",
                "url": "https://openweathermap.org/api",
                "instructions": "1. Sign up for free account\n2. Go to API keys section\n3. Copy your API key\n4. Add to .env: OPENWEATHER_API_KEY=your_key",
                "features": ["Current weather", "Air pollution data", "5-day forecast"],
                "cost": "Free (1000 calls/day)"
            },
            {
                "step": 2,
                "service": "EPA AirNow",
                "url": "https://docs.airnowapi.org/",
                "instructions": "1. Request API key (approval within 24h)\n2. Receive key via email\n3. Add to .env: EPA_API_KEY=your_key",
                "features": ["Official US air quality data", "AQI readings", "Health advisories"],
                "cost": "Free (government service)"
            },
            {
                "step": 3,
                "service": "NASA API",
                "url": "https://api.nasa.gov/",
                "instructions": "1. Get instant API key\n2. Add to .env: NASA_API_KEY=your_key",
                "features": ["Satellite air quality data", "Global coverage", "Historical data"],
                "cost": "Free (1000 calls/hour)"
            }
        ],
        "restart_command": "docker-compose restart api",
        "verification": "Check /api/v1/system/status to see configured APIs"
    }

@app.post("/api/v1/system/refresh-data")
async def refresh_data(background_tasks: BackgroundTasks):
    """Force refresh of air quality data."""
    background_tasks.add_task(refresh_cache)
    return {
        "message": "Data refresh initiated",
        "timestamp": datetime.now(),
        "estimated_completion": "30 seconds"
    }

async def refresh_cache():
    """Background task to refresh data cache."""
    try:
        readings = await get_current_readings()
        app_cache["cached_readings"] = readings
        app_cache["last_real_data_fetch"] = datetime.now()
        logger.info(f"Cache refreshed with {len(readings)} readings")
    except Exception as e:
        logger.error(f"Cache refresh failed: {e}")

@app.get("/api/v1/air-quality/current", response_model=List[AirQualityReading])
async def get_current_air_quality(
    city: Optional[str] = None, 
    limit: int = 10,
    force_refresh: bool = False
):
    """Get current air quality readings for all monitored locations."""
    try:
        if force_refresh or not app_cache.get("cached_readings"):
            readings = await get_current_readings()
        else:
            readings = app_cache.get("cached_readings", [])
        
        if city:
            readings = [r for r in readings if city.lower() in r.location_name.lower()]
        
        return readings[:limit]
        
    except Exception as e:
        logger.error(f"Error fetching air quality data: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching air quality data: {str(e)}")

@app.get("/api/v1/air-quality/predictions/{sensor_id}", response_model=PredictionResponse)
async def get_air_quality_predictions(sensor_id: str, hours_ahead: int = 6):
    """Get AI-powered air quality predictions for a specific sensor."""
    try:
        if hours_ahead < 1 or hours_ahead > 168:
            raise HTTPException(status_code=400, detail="hours_ahead must be between 1 and 168")
        
        # Get current reading for the sensor
        readings = await get_current_readings()
        sensor_reading = next((r for r in readings if r.sensor_id == sensor_id), None)
        
        if not sensor_reading:
            raise HTTPException(status_code=404, detail="Sensor not found")
        
        # Enhanced prediction logic
        base_aqi = sensor_reading.aqi
        
        # Factor in data source confidence
        confidence_modifier = sensor_reading.confidence_score
        
        # Time-based trend (pollution tends to vary by time of day)
        future_hour = (datetime.now() + timedelta(hours=hours_ahead)).hour
        if 7 <= future_hour <= 9 or 17 <= future_hour <= 19:  # Rush hours
            trend = random.uniform(5, 15)
        elif 2 <= future_hour <= 5:  # Early morning
            trend = random.uniform(-15, -5)
        else:
            trend = random.uniform(-5, 5)
        
        # Weather influence (simplified)
        if sensor_reading.temperature > 25:  # Hot weather can worsen air quality
            trend += random.uniform(0, 8)
        
        # Distance influence on confidence
        confidence = max(0.5, confidence_modifier - (hours_ahead * 0.01))
        
        # Final prediction
        predicted_aqi = max(5, min(500, base_aqi + trend + random.uniform(-8, 8)))
        category = get_aqi_category(predicted_aqi)
        
        return PredictionResponse(
            sensor_id=sensor_id,
            predicted_aqi=round(predicted_aqi, 1),
            category=category,
            hours_ahead=hours_ahead,
            confidence=round(confidence, 2),
            timestamp=datetime.now() + timedelta(hours=hours_ahead),
            model_version="v2.0_enhanced"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating prediction: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating prediction: {str(e)}")

@app.get("/api/v1/air-quality/sensors")
async def get_sensors():
    """Get list of available sensors with current status."""
    readings = await get_current_readings()
    sensors = []
    
    for r in readings:
        sensors.append({
            "sensor_id": r.sensor_id,
            "location_name": r.location_name,
            "latitude": r.latitude,
            "longitude": r.longitude,
            "current_aqi": r.aqi,
            "data_sources": r.data_sources,
            "confidence_score": r.confidence_score,
            "last_updated": r.timestamp,
            "status": "active"
        })
    
    return {
        "sensors": sensors,
        "total_count": len(sensors),
        "data_freshness": app_cache.get("last_real_data_fetch", "simulated")
    }

@app.get("/api/v1/air-quality/summary")
async def get_summary():
    """Get platform summary statistics."""
    readings = await get_current_readings()
    
    if not readings:
        raise HTTPException(status_code=500, detail="No data available")
    
    total_sensors = len(readings)
    avg_aqi = sum(r.aqi for r in readings) / len(readings)
    good_quality_count = sum(1 for r in readings if r.aqi <= 50)
    concerning_count = sum(1 for r in readings if r.aqi > 100)
    
    # Data source breakdown
    real_data_count = sum(1 for r in readings if "simulated" not in r.data_sources)
    data_quality = "High" if real_data_count > 0 else "Simulated"
    
    return {
        "total_sensors": total_sensors,
        "cities_monitored": total_sensors,
        "average_aqi": round(avg_aqi, 1),
        "good_quality_locations": good_quality_count,
        "concerning_locations": concerning_count,
        "daily_predictions": f"{total_sensors * 24 * 4}",  # 4 predictions per hour
        "data_quality": data_quality,
        "real_data_sources": real_data_count,
        "last_updated": max(r.timestamp for r in readings),
        "system_version": "2.0.0"
    }

@app.get("/api/v1/air-quality/historical/{sensor_id}")
async def get_historical_data(sensor_id: str, days: int = 7):
    """Get historical air quality data (simulated with realistic patterns)."""
    if days > 30:
        raise HTTPException(status_code=400, detail="Maximum 30 days of historical data")
    
    # Get current reading to base historical data on
    readings = await get_current_readings()
    sensor_reading = next((r for r in readings if r.sensor_id == sensor_id), None)
    
    if not sensor_reading:
        raise HTTPException(status_code=404, detail="Sensor not found")
    
    # Generate realistic historical data
    historical_data = []
    base_time = datetime.now() - timedelta(days=days)
    base_aqi = sensor_reading.aqi
    
    for i in range(days * 24):  # Hourly data
        timestamp = base_time + timedelta(hours=i)
        hour = timestamp.hour
        day_of_week = timestamp.weekday()
        
        # Daily and weekly patterns
        if 7 <= hour <= 9 or 17 <= hour <= 19:  # Rush hours
            hour_modifier = random.uniform(1.1, 1.4)
        elif 2 <= hour <= 5:  # Early morning
            hour_modifier = random.uniform(0.7, 0.9)
        else:
            hour_modifier = random.uniform(0.9, 1.1)
        
        # Weekend effect (generally better air quality)
        weekend_modifier = 0.85 if day_of_week >= 5 else 1.0
        
        # Seasonal trend (simplified)
        seasonal_trend = 5 * random.sin(i * 0.02)  # Subtle seasonal variation
        
        aqi = max(10, base_aqi * hour_modifier * weekend_modifier + seasonal_trend + random.uniform(-12, 12))
        
        historical_data.append({
            "timestamp": timestamp,
            "aqi": round(aqi, 1),
            "pm25": round(aqi * 0.35, 1),
            "pm10": round(aqi * 0.45, 1),
            "confidence": 0.85 if "simulated" not in sensor_reading.data_sources else 0.75
        })
    
    return {
        "sensor_id": sensor_id,
        "location_name": sensor_reading.location_name,
        "data_period": f"{days} days",
        "data_points": len(historical_data),
        "data": historical_data[-168:] if days > 7 else historical_data  # Limit to last week for performance
    }

def get_aqi_category(aqi: float) -> str:
    """Get AQI category based on value."""
    if aqi <= 50:
        return "Good"
    elif aqi <= 100:
        return "Moderate"
    elif aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    elif aqi <= 200:
        return "Unhealthy"
    elif aqi <= 300:
        return "Very Unhealthy"
    else:
        return "Hazardous"

# Startup event to warm up cache
@app.on_event("startup")
async def startup_event():
    logger.info("🌬️ AirSense Intelligence Platform starting up...")
    
    # Check API configuration
    api_keys = await get_api_keys_status()
    logger.info(f"API Keys configured: {sum(api_keys.values())}/3")
    
    # Warm up cache with initial data
    try:
        await refresh_cache()
        logger.info("✅ Initial data cache warmed up successfully")
    except Exception as e:
        logger.warning(f"⚠️ Initial cache warm-up failed, will use simulated data: {e}")
    
    logger.info("🚀 AirSense Intelligence Platform ready!")

# Background task to refresh data every 30 minutes
@app.on_event("startup")
async def setup_background_tasks():
    async def periodic_refresh():
        while True:
            await asyncio.sleep(1800)  # 30 minutes
            try:
                await refresh_cache()
            except Exception as e:
                logger.error(f"Background refresh failed: {e}")
    
    asyncio.create_task(periodic_refresh())

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )