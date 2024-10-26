import requests
import time
from datetime import datetime, timedelta
import sqlite3
from collections import Counter
import smtplib
from email.mime.text import MIMEText
import logging
from typing import Dict, List, Optional
import json
from dataclasses import dataclass
import pandas as pd
import matplotlib.pyplot as plt

# Configuration
@dataclass
class Config:
    api_key: str
    interval_minutes: int = 5
    temperature_unit: str = 'celsius'  # or 'fahrenheit'
    cities: List[str] = None
    email_config: Dict = None
    temp_threshold: float = 35.0
    consecutive_threshold_breaches: int = 2

    def __post_init__(self):
        if self.cities is None:
            self.cities = ['Delhi', 'Mumbai', 'Chennai', 'Bangalore', 'Kolkata', 'Hyderabad']
        if self.email_config is None:
            self.email_config = {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'sender_email': '',
                'sender_password': '',
                'recipient_email': ''
            }

class WeatherDB:
    def __init__(self, db_path: str = 'weather_data.db'):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS weather_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city TEXT,
                    timestamp INTEGER,
                    main TEXT,
                    temp REAL,
                    feels_like REAL
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS daily_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    city TEXT,
                    date TEXT,
                    avg_temp REAL,
                    max_temp REAL,
                    min_temp REAL,
                    dominant_weather TEXT
                )
            ''')

    def store_weather_data(self, city: str, timestamp: int, main: str, temp: float, feels_like: float):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                'INSERT INTO weather_data (city, timestamp, main, temp, feels_like) VALUES (?, ?, ?, ?, ?)',
                (city, timestamp, main, temp, feels_like)
            )

    def store_daily_summary(self, city: str, date: str, avg_temp: float, max_temp: float, 
                          min_temp: float, dominant_weather: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                '''INSERT INTO daily_summaries 
                   (city, date, avg_temp, max_temp, min_temp, dominant_weather) 
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (city, date, avg_temp, max_temp, min_temp, dominant_weather)
            )

    def get_daily_data(self, city: str, date: str) -> List[tuple]:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                'SELECT * FROM weather_data WHERE city = ? AND date(timestamp, "unixepoch") = ?',
                (city, date)
            ).fetchall()

class WeatherMonitor:
    def __init__(self, config: Config):
        self.config = config
        self.db = WeatherDB()
        self.logger = self._setup_logger()
        self.consecutive_breaches = {city: 0 for city in config.cities}
        
    def _setup_logger(self):
        logger = logging.getLogger('WeatherMonitor')
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        return logger

    def kelvin_to_celsius(self, kelvin: float) -> float:
        return kelvin - 273.15

    def kelvin_to_fahrenheit(self, kelvin: float) -> float:
        return (kelvin - 273.15) * 9/5 + 32

    def convert_temperature(self, kelvin: float) -> float:
        if self.config.temperature_unit == 'celsius':
            return self.kelvin_to_celsius(kelvin)
        return self.kelvin_to_fahrenheit(kelvin)

    def fetch_weather_data(self, city: str) -> Optional[Dict]:
        try:
            url = f"http://api.openweathermap.org/data/2.5/weather"
            params = {
                'q': f"{city},IN",
                'appid': self.config.api_key
            }
            response = requests.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Error fetching weather data for {city}: {str(e)}")
            return None

    def process_weather_data(self, city: str, data: Dict):
        if not data:
            return

        temp = self.convert_temperature(data['main']['temp'])
        feels_like = self.convert_temperature(data['main']['feels_like'])
        main_weather = data['weather'][0]['main']
        timestamp = data['dt']

        # Store raw data
        self.db.store_weather_data(city, timestamp, main_weather, temp, feels_like)

        # Check thresholds
        self.check_temperature_threshold(city, temp)

        # Calculate daily summary if it's end of day
        current_time = datetime.fromtimestamp(timestamp)
        if current_time.hour == 23 and current_time.minute >= 55:
            self.calculate_daily_summary(city, current_time.date().isoformat())

    def calculate_daily_summary(self, city: str, date: str):
        data = self.db.get_daily_data(city, date)
        if not data:
            return

        temperatures = [row[4] for row in data]  # temp column
        weather_conditions = [row[3] for row in data]  # main column

        avg_temp = sum(temperatures) / len(temperatures)
        max_temp = max(temperatures)
        min_temp = min(temperatures)
        
        # Calculate dominant weather with tie-breaking logic
        weather_counter = Counter(weather_conditions)
        most_common = weather_counter.most_common()
        
        # If there's a tie, prioritize more severe weather conditions
        weather_severity = {
            'Thunderstorm': 5,
            'Snow': 4,
            'Rain': 3,
            'Drizzle': 2,
            'Clouds': 1,
            'Clear': 0
        }
        
        if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
            # Sort tied conditions by severity
            tied_conditions = [condition for condition, count in most_common if count == most_common[0][1]]
            dominant_weather = max(tied_conditions, key=lambda x: weather_severity.get(x, 0))
        else:
            dominant_weather = most_common[0][0]

        self.db.store_daily_summary(
            city, date, avg_temp, max_temp, min_temp, dominant_weather
        )

    def check_temperature_threshold(self, city: str, temp: float):
        if temp > self.config.temp_threshold:
            self.consecutive_breaches[city] += 1
            if self.consecutive_breaches[city] >= self.config.consecutive_threshold_breaches:
                self.trigger_alert(city, temp)
        else:
            self.consecutive_breaches[city] = 0

    def trigger_alert(self, city: str, temp: float):
        message = f"Temperature Alert: {city} has exceeded {self.config.temp_threshold}°{self.config.temperature_unit.upper()} "\
                 f"for {self.config.consecutive_threshold_breaches} consecutive readings. Current temperature: {temp:.1f}°{self.config.temperature_unit.upper()}"
        self.logger.warning(message)
        self.send_email_alert(message)

    def send_email_alert(self, message: str):
        if not all(self.config.email_config.values()):
            self.logger.warning("Email configuration incomplete. Skipping email alert.")
            return

        try:
            msg = MIMEText(message)
            msg['Subject'] = 'Weather Alert'
            msg['From'] = self.config.email_config['sender_email']
            msg['To'] = self.config.email_config['recipient_email']

            with smtplib.SMTP(self.config.email_config['smtp_server'], 
                            self.config.email_config['smtp_port']) as server:
                server.starttls()
                server.login(
                    self.config.email_config['sender_email'],
                    self.config.email_config['sender_password']
                )
                server.send_message(msg)
        except Exception as e:
            self.logger.error(f"Failed to send email alert: {str(e)}")

    def generate_visualizations(self, city: str, start_date: str, end_date: str):
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                '''SELECT date, avg_temp, max_temp, min_temp 
                   FROM daily_summaries 
                   WHERE city = ? AND date BETWEEN ? AND ?''',
                conn,
                params=(city, start_date, end_date)
            )

        # Temperature trends
        plt.figure(figsize=(12, 6))
        plt.plot(df['date'], df['avg_temp'], label='Average Temp')
        plt.plot(df['date'], df['max_temp'], label='Max Temp')
        plt.plot(df['date'], df['min_temp'], label='Min Temp')
        plt.title(f'Temperature Trends for {city}')
        plt.xlabel('Date')
        plt.ylabel(f'Temperature (°{self.config.temperature_unit.upper()})')
        plt.legend()
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(f'{city}_temperature_trends.png')
        plt.close()

    def run(self):
        self.logger.info("Starting Weather Monitoring System")
        while True:
            for city in self.config.cities:
                data = self.fetch_weather_data(city)
                self.process_weather_data(city, data)
            
            time.sleep(self.config.interval_minutes * 60)

def main():
    # Load configuration from file or environment variables
    config = Config(
        api_key="2cd3f260c41cd54c29f68ddbcbca37e5",
        interval_minutes=5,
        temperature_unit='celsius',
        temp_threshold=35.0,
        consecutive_threshold_breaches=2
    )
    
    monitor = WeatherMonitor(config)
    monitor.run()

if __name__ == "__main__":
    main()