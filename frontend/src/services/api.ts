// frontend/src/services/api.ts
import axios, { AxiosResponse } from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for auth tokens
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('authToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('authToken');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const airQualityApi = {
  getCurrentAirQuality: async (city?: string): Promise<AirQualityData[]> => {
    const params = city ? { city } : {};
    const response: AxiosResponse<AirQualityData[]> = await apiClient.get('/air-quality/current', { params });
    return response.data;
  },

  getPredictions: async (sensorId: string, hoursAhead: number = 24) => {
    const response = await apiClient.get(`/air-quality/predictions/${sensorId}`, {
      params: { hours_ahead: hoursAhead }
    });
    return response.data;
  },

  getHistoricalData: async (sensorId: string, startDate: string, endDate: string) => {
    const response = await apiClient.get(`/air-quality/historical/${sensorId}`, {
      params: { start_date: startDate, end_date: endDate }
    });
    return response.data;
  },

  subscribeToAlerts: async (email: string, sensorIds: string[], threshold: number) => {
    const response = await apiClient.post('/air-quality/alerts/subscribe', {
      email,
      sensor_ids: sensorIds,
      threshold
    });
    return response.data;
  }
};