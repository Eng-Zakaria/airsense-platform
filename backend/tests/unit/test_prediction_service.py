# backend/tests/unit/test_prediction_service.py
import pytest
import numpy as np
from unittest.mock import Mock, patch
from app.services.prediction_service import PredictionService

class TestPredictionService:
    @pytest.fixture
    def prediction_service(self):
        return PredictionService()
    
    @pytest.fixture
    def mock_redis(self):
        with patch('app.services.prediction_service.redis.Redis') as mock:
            yield mock.return_value
    
    @pytest.fixture
    def mock_model(self):
        mock = Mock()
        mock.predict.return_value = np.array([45.2])
        return mock
    
    @pytest.mark.asyncio
    async def test_predict_aqi_success(self, prediction_service, mock_redis, mock_model):
        # Arrange
        prediction_service.model = mock_model
        prediction_service.redis_client = mock_redis
        mock_redis.get.return_value = None
        
        with patch.object(prediction_service, '_get_latest_sensor_data') as mock_data:
            mock_data.return_value = {
                'pm25': 15.5, 'pm10': 25.0, 'no2': 20.0,
                'temperature': 22.0, 'humidity': 65.0
            }
            
            with patch.object(prediction_service, '_prepare_features') as mock_features:
                mock_features.return_value = [15.5, 25.0, 20.0, 22.0, 65.0]
                
                # Act
                result = await prediction_service.predict_aqi('sensor_001', 6)
                
                # Assert
                assert result['sensor_id'] == 'sensor_001'
                assert result['predicted_aqi'] == 45.2
                assert result['category'] == 'Good'
                assert result['hours_ahead'] == 6
                mock_model.predict.assert_called_once()
                mock_redis.setex.assert_called_once()
    
    def test_get_aqi_category(self, prediction_service):
        assert prediction_service._get_aqi_category(25) == "Good"
        assert prediction_service._get_aqi_category(75) == "Moderate"
        assert prediction_service._get_aqi_category(125) == "Unhealthy for Sensitive Groups"
        assert prediction_service._get_aqi_category(175) == "Unhealthy"
        assert prediction_service._get_aqi_category(250) == "Very Unhealthy"
        assert prediction_service._get_aqi_category(350) == "Hazardous"

# backend/tests/integration/test_api_endpoints.py
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestAirQualityAPI:
    def test_health_check(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_get_current_air_quality(self):
        response = client.get("/api/v1/air-quality/current")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_get_current_air_quality_with_city_filter(self):
        response = client.get("/api/v1/air-quality/current?city=New York")
        assert response.status_code == 200
        data = response.json()
        assert all('New York' in item['location_name'] for item in data)
    
    def test_get_predictions_valid_sensor(self):
        response = client.get("/api/v1/air-quality/predictions/sensor_001")
        assert response.status_code == 200
        data = response.json()
        assert 'predicted_aqi' in data
        assert 'category' in data
    
    def test_get_predictions_invalid_sensor(self):
        response = client.get("/api/v1/air-quality/predictions/invalid_sensor")
        assert response.status_code == 404
    
    @pytest.mark.parametrize("hours_ahead", [1, 6, 24, 168])
    def test_predictions_various_timeframes(self, hours_ahead):
        response = client.get(f"/api/v1/air-quality/predictions/sensor_001?hours_ahead={hours_ahead}")
        assert response.status_code == 200
        data = response.json()
        assert data['hours_ahead'] == hours_ahead

# Data quality tests
# backend/tests/data_quality/test_data_validation.py
import pytest
import pandas as pd
from app.utils.data_validation import AirQualityValidator

class TestDataValidation:
    @pytest.fixture
    def validator(self):
        return AirQualityValidator()
    
    @pytest.fixture
    def valid_data(self):
        return pd.DataFrame({
            'sensor_id': ['sensor_001', 'sensor_002'],
            'aqi': [45, 78],
            'pm25': [12.5, 22.1],
            'pm10': [18.3, 31.5],
            'temperature': [22.5, 18.9],
            'humidity': [65, 72],
            'timestamp': ['2024-01-01 12:00:00', '2024-01-01 12:00:00']
        })
    
    def test_validate_aqi_range(self, validator, valid_data):
        # Test valid AQI values
        assert validator.validate_aqi_range(valid_data).empty
        
        # Test invalid AQI values
        invalid_data = valid_data.copy()
        invalid_data.loc[0, 'aqi'] = -5
        invalid_data.loc[1, 'aqi'] = 600
        
        errors = validator.validate_aqi_range(invalid_data)
        assert len(errors) == 2
    
    def test_validate_pm_values(self, validator, valid_data):
        assert validator.validate_pm_values(valid_data).empty
        
        invalid_data = valid_data.copy()
        invalid_data.loc[0, 'pm25'] = -1
        
        errors = validator.validate_pm_values(invalid_data)
        assert len(errors) == 1
    
    def test_validate_completeness(self, validator, valid_data):
        assert validator.validate_completeness(valid_data).empty
        
        incomplete_data = valid_data.copy()
        incomplete_data.loc[0, 'aqi'] = None
        
        errors = validator.validate_completeness(incomplete_data)
        assert len(errors) == 1