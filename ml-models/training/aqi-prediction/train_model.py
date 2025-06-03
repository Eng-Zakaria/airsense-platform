# ml-models/training/aqi-prediction/train_model.py
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import mlflow
import mlflow.sklearn
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

class AQIPredictionModel:
    def __init__(self):
        self.models = {
            'random_forest': RandomForestRegressor(),
            'gradient_boosting': GradientBoostingRegressor(),
            'lstm': self._build_lstm_model()
        }
        
    def _build_lstm_model(self):
        model = Sequential([
            LSTM(100, return_sequences=True, input_shape=(24, 10)),
            Dropout(0.2),
            LSTM(50, return_sequences=False),
            Dropout(0.2),
            Dense(25),
            Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        return model
    
    def train_models(self, X_train, y_train, X_val, y_val):
        results = {}
        
        with mlflow.start_run():
            for name, model in self.models.items():
                if name == 'lstm':
                    # Reshape data for LSTM
                    X_train_lstm = X_train.values.reshape((X_train.shape[0], 24, -1))
                    X_val_lstm = X_val.values.reshape((X_val.shape[0], 24, -1))
                    
                    model.fit(X_train_lstm, y_train, 
                             validation_data=(X_val_lstm, y_val),
                             epochs=100, batch_size=32, verbose=0)
                    
                    predictions = model.predict(X_val_lstm)
                else:
                    model.fit(X_train, y_train)
                    predictions = model.predict(X_val)
                
                # Calculate metrics
                mae = mean_absolute_error(y_val, predictions)
                mse = mean_squared_error(y_val, predictions)
                r2 = r2_score(y_val, predictions)
                
                results[name] = {'mae': mae, 'mse': mse, 'r2': r2}
                
                # Log to MLflow
                mlflow.log_metric(f"{name}_mae", mae)
                mlflow.log_metric(f"{name}_mse", mse)
                mlflow.log_metric(f"{name}_r2", r2)
                mlflow.sklearn.log_model(model, f"{name}_model")
        
        return results