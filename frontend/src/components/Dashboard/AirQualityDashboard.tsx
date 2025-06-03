// frontend/src/components/Dashboard/AirQualityDashboard.tsx
import React, { useState, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AirQualityMap } from './AirQualityMap';
import { PredictionChart } from './PredictionChart';
import { MetricsGrid } from './MetricsGrid';
import { CityComparison } from './CityComparison';
import { airQualityApi } from '@/services/api';

interface AirQualityData {
  sensor_id: string;
  location_name: string;
  latitude: number;
  longitude: number;
  aqi: number;
  pm25: number;
  pm10: number;
  timestamp: string;
}

export const AirQualityDashboard: React.FC = () => {
  const [selectedCity, setSelectedCity] = useState<string>('');
  const queryClient = useQueryClient();

  const { data: currentData, isLoading: isLoadingCurrent } = useQuery({
    queryKey: ['airQuality', 'current', selectedCity],
    queryFn: () => airQualityApi.getCurrentAirQuality(selectedCity),
    refetchInterval: 30000, // Refresh every 30 seconds
  });

  const { data: predictions, isLoading: isLoadingPredictions } = useQuery({
    queryKey: ['predictions', selectedCity],
    queryFn: () => airQualityApi.getPredictions(selectedCity),
    enabled: !!selectedCity,
  });

  const handleCitySelect = (city: string) => {
    setSelectedCity(city);
    queryClient.invalidateQueries({ queryKey: ['predictions'] });
  };

  if (isLoadingCurrent) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
      <div className="max-w-7xl mx-auto space-y-6">
        <header className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            🌬️ AirSense Intelligence Platform
          </h1>
          <p className="text-xl text-gray-600">
            Real-time air quality monitoring and predictive analytics
          </p>
        </header>

        <MetricsGrid data={currentData} />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                🗺️ Real-time Air Quality Map
              </CardTitle>
            </CardHeader>
            <CardContent>
              <AirQualityMap 
                data={currentData} 
                onCitySelect={handleCitySelect}
                selectedCity={selectedCity}
              />
            </CardContent>
          </Card>

          <Card className="lg:col-span-1">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                📊 Prediction Timeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <PredictionChart 
                predictions={predictions}
                isLoading={isLoadingPredictions}
              />
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              🏙️ Multi-City Comparison
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CityComparison data={currentData} />
          </CardContent>
        </Card>
      </div>
    </div>
  );
};