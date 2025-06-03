# backend/app/services/data_service.py
import asyncio
import aiohttp
import redis
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from pydantic import BaseModel
import os
from functools import wraps

# Configuration
class Config:
    OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
    EPA_API_KEY = os.getenv("EPA_API_KEY")
    NASA_API_KEY = os.getenv("NASA_API_KEY")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_TTL = 1800  # 30 minutes
    REQUEST_TIMEOUT = 30
    MAX_RETRIES = 3

# Data Models
class WeatherData(BaseModel):
    temperature: float
    humidity: int
    pressure: float
    wind_speed: float
    wind_direction: float
    visibility: float

class AirQualityData(BaseModel):
    aqi: int
    pm25: float
    pm10: float
    no2: float
    o3: float
    co: float

class LocationData(BaseModel):
    city: str
    state: str
    country: str
    latitude: float
    longitude: float
    timezone: str

class EnhancedReading(BaseModel):
    sensor_id: str
    location: LocationData
    air_quality: AirQualityData
    weather: WeatherData
    timestamp: datetime
    data_sources: List[str]
    confidence_score: float

# Caching decorator
def cached(ttl: int = 1800):
    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            # Create cache key from function name and arguments
            cache_key = f"{func.__name__}:{hash(str(args) + str(kwargs))}"
            
            try:
                # Try to get from cache
                cached_data = self.redis_client.get(cache_key)
                if cached_data:
                    return json.loads(cached_data)
            except Exception as e:
                logging.warning(f"Cache read error: {e}")
            
            # If not in cache, execute function
            result = await func(self, *args, **kwargs)
            
            try:
                # Store in cache
                self.redis_client.setex(
                    cache_key, 
                    ttl, 
                    json.dumps(result, default=str)
                )
            except Exception as e:
                logging.warning(f"Cache write error: {e}")
            
            return result
        return wrapper
    return decorator

class DataIntegrationService:
    def __init__(self):
        self.config = Config()
        self.redis_client = redis.from_url(self.config.REDIS_URL)
        self.session: Optional[aiohttp.ClientSession] = None
        self.logger = logging.getLogger(__name__)
        
        # Major cities with coordinates
        self.cities = [
            {"name": "New York", "state": "NY", "lat": 40.7128, "lng": -74.0060, "country": "US"},
            {"name": "Los Angeles", "state": "CA", "lat": 34.0522, "lng": -118.2437, "country": "US"},
            {"name": "Chicago", "state": "IL", "lat": 41.8781, "lng": -87.6298, "country": "US"},
            {"name": "Houston", "state": "TX", "lat": 29.7604, "lng": -95.3698, "country": "US"},
            {"name": "Phoenix", "state": "AZ", "lat": 33.4484, "lng": -112.0740, "country": "US"},
            {"name": "Philadelphia", "state": "PA", "lat": 39.9526, "lng": -75.1652, "country": "US"},
            {"name": "San Antonio", "state": "TX", "lat": 29.4241, "lng": -98.4936, "country": "US"},
            {"name": "San Diego", "state": "CA", "lat": 32.7157, "lng": -117.1611, "country": "US"},
            {"name": "Dallas", "state": "TX", "lat": 32.7767, "lng": -96.7970, "country": "US"},
            {"name": "San Jose", "state": "CA", "lat": 37.3382, "lng": -121.8863, "country": "US"},
        ]
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.REQUEST_TIMEOUT)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _make_request_with_retry(self, url: str, params: dict = None) -> dict:
        """Make HTTP request with retry logic and error handling."""
        last_exception = None
        
        for attempt in range(self.config.MAX_RETRIES):
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:  # Rate limited
                        wait_time = 2 ** attempt
                        self.logger.warning(f"Rate limited. Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        self.logger.error(f"HTTP {response.status} for {url}")
                        continue
                        
            except asyncio.TimeoutError as e:
                last_exception = e
                self.logger.warning(f"Timeout on attempt {attempt + 1} for {url}")
                await asyncio.sleep(1)
                continue
            except Exception as e:
                last_exception = e
                self.logger.error(f"Request failed on attempt {attempt + 1}: {e}")
                await asyncio.sleep(1)
                continue
        
        raise Exception(f"Failed after {self.config.MAX_RETRIES} attempts: {last_exception}")

    @cached(ttl=1800)  # Cache for 30 minutes
    async def fetch_openweather_data(self, lat: float, lng: float) -> Dict:
        """Fetch weather and air quality data from OpenWeatherMap."""
        if not self.config.OPENWEATHER_API_KEY:
            raise ValueError("OpenWeatherMap API key not configured")
        
        base_url = "http://api.openweathermap.org/data/2.5"
        
        # Fetch current weather
        weather_params = {
            "lat": lat,
            "lon": lng,
            "appid": self.config.OPENWEATHER_API_KEY,
            "units": "metric"
        }
        
        # Fetch air pollution data
        pollution_params = {
            "lat": lat,
            "lon": lng,
            "appid": self.config.OPENWEATHER_API_KEY
        }
        
        try:
            # Make parallel requests
            weather_task = self._make_request_with_retry(
                f"{base_url}/weather", weather_params
            )
            pollution_task = self._make_request_with_retry(
                f"{base_url}/air_pollution", pollution_params
            )
            
            weather_data, pollution_data = await asyncio.gather(
                weather_task, pollution_task, return_exceptions=True
            )
            
            if isinstance(weather_data, Exception):
                raise weather_data
            if isinstance(pollution_data, Exception):
                raise pollution_data
            
            return {
                "weather": weather_data,
                "pollution": pollution_data,
                "timestamp": datetime.now(),
                "source": "openweathermap"
            }
            
        except Exception as e:
            self.logger.error(f"OpenWeatherMap API error: {e}")
            raise

    @cached(ttl=3600)  # Cache for 1 hour
    async def fetch_epa_data(self, zip_code: str) -> Dict:
        """Fetch air quality data from EPA AirNow."""
        if not self.config.EPA_API_KEY:
            self.logger.warning("EPA API key not configured, skipping EPA data")
            return None
        
        url = "https://www.airnowapi.org/aq/observation/zipCode/current/"
        params = {
            "format": "application/json",
            "zipCode": zip_code,
            "distance": 25,
            "API_KEY": self.config.EPA_API_KEY
        }
        
        try:
            data = await self._make_request_with_retry(url, params)
            return {
                "data": data,
                "timestamp": datetime.now(),
                "source": "epa_airnow"
            }
        except Exception as e:
            self.logger.error(f"EPA AirNow API error: {e}")
            return None

    def _convert_openweather_to_standard(self, ow_data: Dict, city_info: Dict) -> EnhancedReading:
        """Convert OpenWeatherMap data to standard format."""
        weather_info = ow_data["weather"]
        pollution_info = ow_data["pollution"]
        
        # Extract weather data
        weather = WeatherData(
            temperature=weather_info["main"]["temp"],
            humidity=weather_info["main"]["humidity"],
            pressure=weather_info["main"]["pressure"],
            wind_speed=weather_info.get("wind", {}).get("speed", 0),
            wind_direction=weather_info.get("wind", {}).get("deg", 0),
            visibility=weather_info.get("visibility", 10000) / 1000  # Convert to km
        )
        
        # Extract pollution data (OpenWeatherMap uses different scale)
        pollution = pollution_info["list"][0]
        components = pollution["components"]
        
        # Convert to AQI (simplified conversion)
        pm25 = components.get("pm2_5", 0)
        pm10 = components.get("pm10", 0)
        no2 = components.get("no2", 0)
        o3 = components.get("o3", 0)
        co = components.get("co", 0)
        
        # Simple AQI calculation (US EPA formula approximation)
        aqi = max(
            self._pm25_to_aqi(pm25),
            self._pm10_to_aqi(pm10),
            self._no2_to_aqi(no2),
            self._o3_to_aqi(o3),
            self._co_to_aqi(co)
        )
        
        air_quality = AirQualityData(
            aqi=int(aqi),
            pm25=pm25,
            pm10=pm10,
            no2=no2,
            o3=o3,
            co=co
        )
        
        location = LocationData(
            city=city_info["name"],
            state=city_info["state"],
            country=city_info["country"],
            latitude=city_info["lat"],
            longitude=city_info["lng"],
            timezone=weather_info.get("timezone", "UTC")
        )
        
        sensor_id = f"ow_{city_info['name'].lower().replace(' ', '_')}"
        
        return EnhancedReading(
            sensor_id=sensor_id,
            location=location,
            air_quality=air_quality,
            weather=weather,
            timestamp=datetime.now(),
            data_sources=["openweathermap"],
            confidence_score=0.85  # Base confidence for API data
        )

    def _pm25_to_aqi(self, pm25: float) -> float:
        """Convert PM2.5 concentration to AQI."""
        if pm25 <= 12.0:
            return (50 / 12.0) * pm25
        elif pm25 <= 35.4:
            return 50 + ((100 - 50) / (35.4 - 12.1)) * (pm25 - 12.1)
        elif pm25 <= 55.4:
            return 100 + ((150 - 100) / (55.4 - 35.5)) * (pm25 - 35.5)
        elif pm25 <= 150.4:
            return 150 + ((200 - 150) / (150.4 - 55.5)) * (pm25 - 55.5)
        elif pm25 <= 250.4:
            return 200 + ((300 - 200) / (250.4 - 150.5)) * (pm25 - 150.5)
        else:
            return 300 + ((500 - 300) / (500.4 - 250.5)) * (pm25 - 250.5)

    def _pm10_to_aqi(self, pm10: float) -> float:
        """Convert PM10 concentration to AQI."""
        if pm10 <= 54:
            return (50 / 54) * pm10
        elif pm10 <= 154:
            return 50 + ((100 - 50) / (154 - 55)) * (pm10 - 55)
        elif pm10 <= 254:
            return 100 + ((150 - 100) / (254 - 155)) * (pm10 - 155)
        elif pm10 <= 354:
            return 150 + ((200 - 150) / (354 - 255)) * (pm10 - 255)
        elif pm10 <= 424:
            return 200 + ((300 - 200) / (424 - 355)) * (pm10 - 355)
        else:
            return 300 + ((500 - 300) / (604 - 425)) * (pm10 - 425)

    def _no2_to_aqi(self, no2: float) -> float:
        """Convert NO2 concentration to AQI (simplified)."""
        # Convert µg/m³ to ppb (approximate)
        no2_ppb = no2 * 0.5319
        
        if no2_ppb <= 53:
            return (50 / 53) * no2_ppb
        elif no2_ppb <= 100:
            return 50 + ((100 - 50) / (100 - 54)) * (no2_ppb - 54)
        else:
            return 100 + ((150 - 100) / (360 - 101)) * (no2_ppb - 101)

    def _o3_to_aqi(self, o3: float) -> float:
        """Convert O3 concentration to AQI (simplified)."""
        # Convert µg/m³ to ppb (approximate)
        o3_ppb = o3 * 0.5
        
        if o3_ppb <= 54:
            return (50 / 54) * o3_ppb
        elif o3_ppb <= 70:
            return 50 + ((100 - 50) / (70 - 55)) * (o3_ppb - 55)
        else:
            return 100 + ((150 - 100) / (85 - 71)) * (o3_ppb - 71)

    def _co_to_aqi(self, co: float) -> float:
        """Convert CO concentration to AQI (simplified)."""
        # Convert µg/m³ to ppm (approximate)
        co_ppm = co / 1150
        
        if co_ppm <= 4.4:
            return (50 / 4.4) * co_ppm
        elif co_ppm <= 9.4:
            return 50 + ((100 - 50) / (9.4 - 4.5)) * (co_ppm - 4.5)
        else:
            return 100 + ((150 - 100) / (12.4 - 9.5)) * (co_ppm - 9.5)

    async def get_all_current_readings(self) -> List[EnhancedReading]:
        """Fetch current air quality readings for all monitored cities."""
        readings = []
        
        async with self:
            # Process cities in batches to avoid overwhelming APIs
            batch_size = 3
            for i in range(0, len(self.cities), batch_size):
                batch = self.cities[i:i + batch_size]
                batch_tasks = []
                
                for city in batch:
                    task = self._fetch_city_data(city)
                    batch_tasks.append(task)
                
                # Process batch
                batch_results = await asyncio.gather(
                    *batch_tasks, return_exceptions=True
                )
                
                for result in batch_results:
                    if isinstance(result, Exception):
                        self.logger.error(f"Error fetching city data: {result}")
                        continue
                    if result:
                        readings.append(result)
                
                # Rate limiting delay between batches
                if i + batch_size < len(self.cities):
                    await asyncio.sleep(1)
        
        return readings

    async def _fetch_city_data(self, city: Dict) -> Optional[EnhancedReading]:
        """Fetch data for a single city."""
        try:
            # Fetch OpenWeatherMap data
            ow_data = await self.fetch_openweather_data(city["lat"], city["lng"])
            
            # Convert to standard format
            reading = self._convert_openweather_to_standard(ow_data, city)
            
            return reading
            
        except Exception as e:
            self.logger.error(f"Error fetching data for {city['name']}: {e}")
            return None

    async def get_enhanced_reading(self, sensor_id: str) -> Optional[EnhancedReading]:
        """Get enhanced reading for a specific sensor."""
        city_name = sensor_id.replace("ow_", "").replace("_", " ").title()
        city = next((c for c in self.cities if c["name"] == city_name), None)
        
        if not city:
            return None
        
        async with self:
            return await self._fetch_city_data(city)

# Singleton instance
data_service = DataIntegrationService()

# FastAPI integration example
async def get_real_air_quality_data():
    """Get real air quality data from multiple sources."""
    try:
        readings = await data_service.get_all_current_readings()
        return readings
    except Exception as e:
        logging.error(f"Error fetching real air quality data: {e}")
        return []

# Environment setup script
def setup_api_keys():
    """Instructions for setting up API keys."""
    instructions = """
    🔑 API Keys Setup Instructions:
    
    1. OpenWeatherMap (FREE):
       - Go to: https://openweathermap.org/api
       - Sign up for free account
       - Get API key from dashboard
       - Add to .env: OPENWEATHER_API_KEY=your_key_here
    
    2. EPA AirNow (FREE):
       - Go to: https://docs.airnowapi.org/
       - Request API key (usually approved within 24 hours)
       - Add to .env: EPA_API_KEY=your_key_here
    
    3. NASA API (FREE):
       - Go to: https://api.nasa.gov/
       - Get API key instantly
       - Add to .env: NASA_API_KEY=your_key_here
    
    4. Restart your application:
       docker-compose restart api
    
    🎯 With API keys, you'll have REAL data flowing through your system!
    """
    print(instructions)

if __name__ == "__main__":
    setup_api_keys()