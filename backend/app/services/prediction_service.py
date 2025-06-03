# backend/app/services/prediction_service.py
from fastapi import HTTPException
import joblib
import numpy as np
import redis
import json

class PredictionService:
    def __init__(self):
        self.model = joblib.load('models/aqi_prediction_model.pkl')
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        
    async def predict_aqi(self, sensor_id: str, hours_ahead: int = 6):
        try:
            # Get latest sensor data
            latest_data = await self._get_latest_sensor_data(sensor_id)
            
            # Check cache first
            cache_key = f"prediction:{sensor_id}:{hours_ahead}"
            cached_result = self.redis_client.get(cache_key)
            
            if cached_result:
                return json.loads(cached_result)
            
            # Prepare features
            features = self._prepare_features(latest_data, hours_ahead)
            
            # Make prediction
            prediction = self.model.predict([features])[0]
            
            # Determine air quality category
            category = self._get_aqi_category(prediction)
            
            result = {
                'sensor_id': sensor_id,
                'predicted_aqi': round(prediction, 1),
                'category': category,
                'hours_ahead': hours_ahead,
                'confidence': self._calculate_confidence(features)
            }
            
            # Cache result for 30 minutes
            self.redis_client.setex(cache_key, 1800, json.dumps(result))
            
            return result
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")
    
    def _get_aqi_category(self, aqi_value):
        if aqi_value <= 50:
            return "Good"
        elif aqi_value <= 100:
            return "Moderate"
        elif aqi_value <= 150:
            return "Unhealthy for Sensitive Groups"
        elif aqi_value <= 200:
            return "Unhealthy"
        elif aqi_value <= 300:
            return "Very Unhealthy"
        else:
            return "Hazardous"