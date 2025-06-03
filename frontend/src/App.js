// frontend/src/App.js
import React, { useState, useEffect } from 'react';
import './App.css';

// API service
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = {
  getCurrentAirQuality: async () => {
    const response = await fetch(`${API_BASE_URL}/api/v1/air-quality/current`);
    return response.json();
  },
  
  getPredictions: async (sensorId, hoursAhead = 6) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/air-quality/predictions/${sensorId}?hours_ahead=${hoursAhead}`);
    return response.json();
  },
  
  getSummary: async () => {
    const response = await fetch(`${API_BASE_URL}/api/v1/air-quality/summary`);
    return response.json();
  },
  
  getHistoricalData: async (sensorId, days = 7) => {
    const response = await fetch(`${API_BASE_URL}/api/v1/air-quality/historical/${sensorId}?days=${days}`);
    return response.json();
  }
};

// Components
const MetricCard = ({ title, value, status, icon }) => (
  <div className="metric-card">
    <div className="metric-icon">{icon}</div>
    <div className="metric-content">
      <div className={`metric-value ${status}`}>{value}</div>
      <div className="metric-title">{title}</div>
    </div>
  </div>
);

const AirQualityMap = ({ data, onCitySelect, selectedCity }) => (
  <div className="map-container">
    <h3>🗺️ Real-time Air Quality Map</h3>
    <div className="map-grid">
      {data.map((reading) => (
        <div 
          key={reading.sensor_id}
          className={`map-location ${selectedCity === reading.sensor_id ? 'selected' : ''}`}
          onClick={() => onCitySelect(reading.sensor_id)}
        >
          <div className="location-name">{reading.location_name}</div>
          <div className={`aqi-value ${getAQIStatus(reading.aqi)}`}>
            {reading.aqi}
          </div>
          <div className="location-coords">
            {reading.latitude.toFixed(2)}, {reading.longitude.toFixed(2)}
          </div>
        </div>
      ))}
    </div>
  </div>
);

const PredictionChart = ({ predictions, isLoading }) => {
  if (isLoading) {
    return <div className="loading">Loading predictions...</div>;
  }
  
  if (!predictions) {
    return <div className="no-data">Select a city to view predictions</div>;
  }

  return (
    <div className="prediction-container">
      <h3>🔮 AI-Powered Predictions</h3>
      <div className="prediction-card">
        <div className="prediction-time">Next {predictions.hours_ahead} Hours</div>
        <div className={`prediction-aqi ${getAQIStatus(predictions.predicted_aqi)}`}>
          {predictions.predicted_aqi}
        </div>
        <div className="prediction-category">{predictions.category}</div>
        <div className="prediction-confidence">
          Confidence: {(predictions.confidence * 100).toFixed(0)}%
        </div>
      </div>
    </div>
  );
};

const HistoricalChart = ({ historicalData }) => {
  if (!historicalData || !historicalData.data) {
    return <div className="no-data">No historical data available</div>;
  }

  const last7Days = historicalData.data.slice(-24 * 7, -1).filter((_, index) => index % 6 === 0); // Show every 6th hour

  return (
    <div className="chart-container">
      <h3>📊 Historical Trends (7 Days)</h3>
      <div className="mini-chart">
        {last7Days.map((point, index) => (
          <div key={index} className="chart-point">
            <div 
              className={`chart-bar ${getAQIStatus(point.aqi)}`}
              style={{ height: `${Math.min(point.aqi, 200) / 2}px` }}
              title={`${new Date(point.timestamp).toLocaleDateString()}: AQI ${point.aqi}`}
            ></div>
          </div>
        ))}
      </div>
      <div className="chart-labels">
        <span>7 days ago</span>
        <span>Today</span>
      </div>
    </div>
  );
};

const CityComparison = ({ data }) => {
  const sortedCities = [...data].sort((a, b) => a.aqi - b.aqi);
  
  return (
    <div className="comparison-container">
      <h3>🏙️ City Air Quality Rankings</h3>
      <div className="city-rankings">
        {sortedCities.map((city, index) => (
          <div key={city.sensor_id} className="city-rank-item">
            <div className="rank-number">#{index + 1}</div>
            <div className="city-info">
              <div className="city-name">{city.location_name}</div>
              <div className="city-details">
                PM2.5: {city.pm25} | PM10: {city.pm10}
              </div>
            </div>
            <div className={`city-aqi ${getAQIStatus(city.aqi)}`}>
              {city.aqi}
            </div>
            <div className="status-emoji">
              {getAQIEmoji(city.aqi)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// Utility functions
const getAQIStatus = (aqi) => {
  if (aqi <= 50) return 'good';
  if (aqi <= 100) return 'moderate';
  if (aqi <= 150) return 'unhealthy-sensitive';
  if (aqi <= 200) return 'unhealthy';
  if (aqi <= 300) return 'very-unhealthy';
  return 'hazardous';
};

const getAQIEmoji = (aqi) => {
  if (aqi <= 50) return '🟢';
  if (aqi <= 100) return '🟡';
  if (aqi <= 150) return '🟠';
  return '🔴';
};

// Main App Component
function App() {
  const [currentData, setCurrentData] = useState([]);
  const [summary, setSummary] = useState(null);
  const [selectedCity, setSelectedCity] = useState('');
  const [predictions, setPredictions] = useState(null);
  const [historicalData, setHistoricalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [predictionsLoading, setPredictionsLoading] = useState(false);

  // Fetch initial data
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [airQualityData, summaryData] = await Promise.all([
          api.getCurrentAirQuality(),
          api.getSummary()
        ]);
        
        setCurrentData(airQualityData);
        setSummary(summaryData);
        
        // Auto-select first city
        if (airQualityData.length > 0) {
          setSelectedCity(airQualityData[0].sensor_id);
        }
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    
    // Set up real-time updates every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  // Fetch predictions when city is selected
  useEffect(() => {
    const fetchPredictions = async () => {
      if (!selectedCity) return;
      
      try {
        setPredictionsLoading(true);
        const [predictionData, histData] = await Promise.all([
          api.getPredictions(selectedCity, 6),
          api.getHistoricalData(selectedCity, 7)
        ]);
        
        setPredictions(predictionData);
        setHistoricalData(histData);
      } catch (error) {
        console.error('Error fetching predictions:', error);
      } finally {
        setPredictionsLoading(false);
      }
    };

    fetchPredictions();
  }, [selectedCity]);

  if (loading) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner"></div>
        <div>Loading AirSense Intelligence Platform...</div>
      </div>
    );
  }

  return (
    <div className="App">
      {/* Header */}
      <header className="app-header">
        <div className="header-content">
          <h1>🌬️ AirSense Intelligence Platform</h1>
          <p>Real-time air quality monitoring and predictive analytics</p>
          <div className="last-updated">
            Last updated: {new Date().toLocaleTimeString()}
          </div>
        </div>
      </header>

      {/* Metrics Dashboard */}
      {summary && (
        <section className="metrics-section">
          <div className="metrics-grid">
            <MetricCard
              title="Current AQI"
              value={summary.average_aqi}
              status={getAQIStatus(summary.average_aqi)}
              icon="🌬️"
            />
            <MetricCard
              title="Cities Monitored"
              value={summary.cities_monitored}
              status="good"
              icon="🏙️"
            />
            <MetricCard
              title="Good Quality"
              value={summary.good_quality_locations}
              status="good"
              icon="🟢"
            />
            <MetricCard
              title="Daily Predictions"
              value={summary.daily_predictions}
              status="good"
              icon="🔮"
            />
          </div>
        </section>
      )}

      {/* Main Dashboard */}
      <main className="main-content">
        <div className="dashboard-grid">
          {/* Air Quality Map */}
          <div className="dashboard-card">
            <AirQualityMap 
              data={currentData}
              onCitySelect={setSelectedCity}
              selectedCity={selectedCity}
            />
          </div>

          {/* Predictions */}
          <div className="dashboard-card">
            <PredictionChart 
              predictions={predictions}
              isLoading={predictionsLoading}
            />
          </div>

          {/* Historical Chart */}
          <div className="dashboard-card">
            <HistoricalChart historicalData={historicalData} />
          </div>

          {/* City Comparison */}
          <div className="dashboard-card full-width">
            <CityComparison data={currentData} />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="app-footer">
        <div className="footer-content">
          <p>🛠️ Built with FastAPI, React, and modern data engineering practices</p>
          <div className="tech-stack">
            <span className="tech-badge">FastAPI</span>
            <span className="tech-badge">React</span>
            <span className="tech-badge">PostgreSQL</span>
            <span className="tech-badge">Docker</span>
            <span className="tech-badge">ML Models</span>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default App;