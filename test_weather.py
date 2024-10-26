import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
import json
from weather_monitor import WeatherMonitor, Config, WeatherDB

class TestWeatherMonitor(unittest.TestCase):
    def setUp(self):
        self.config = Config(
            api_key="test_api_key",
            interval_minutes=5,
            temperature_unit='celsius',
            temp_threshold=35.0,
            consecutive_threshold_breaches=2
        )
        self.monitor = WeatherMonitor(self.config)

    def test_system_setup(self):
        """Test 1: System Setup - Verify system starts and connects to API"""
        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = {'main': {'temp': 300}}
            
            data = self.monitor.fetch_weather_data('Delhi')
            self.assertIsNotNone(data)
            mock_get.assert_called_once()
            self.assertTrue('main' in data)

    def test_data_retrieval(self):
        """Test 2: Data Retrieval - Test API calls and response parsing"""
        sample_response = {
            'weather': [{'main': 'Clear'}],
            'main': {
                'temp': 300.15,
                'feels_like': 305.15
            },
            'dt': int(datetime.now().timestamp())
        }

        with patch('requests.get') as mock_get:
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = sample_response
            
            data = self.monitor.fetch_weather_data('Mumbai')
            self.assertEqual(data['weather'][0]['main'], 'Clear')
            self.assertEqual(data['main']['temp'], 300.15)

    def test_temperature_conversion(self):
        """Test 3: Temperature Conversion - Test Kelvin to Celsius/Fahrenheit"""
        # Test Celsius conversion
        kelvin_temp = 300.15
        celsius = self.monitor.kelvin_to_celsius(kelvin_temp)
        self.assertAlmostEqual(celsius, 27.0, places=1)

        # Test Fahrenheit conversion
        self.monitor.config.temperature_unit = 'fahrenheit'
        fahrenheit = self.monitor.convert_temperature(kelvin_temp)
        self.assertAlmostEqual(fahrenheit, 80.6, places=1)

    @patch('weather_monitor.WeatherDB')
    def test_daily_summary(self, mock_db):
        """Test 4: Daily Weather Summary - Test summary calculations"""
        # Mock weather data for a day with tied weather conditions
        mock_data = [
            (1, 'Delhi', 1635724800, 'Clear', 25.0, 26.0),
            (2, 'Delhi', 1635728400, 'Clear', 27.0, 28.0),
            (3, 'Delhi', 1635732000, 'Rain', 23.0, 24.0),
            (4, 'Delhi', 1635735600, 'Rain', 22.0, 23.0)
        ]
        
        mock_db.get_daily_data.return_value = mock_data
        self.monitor.db = mock_db

        date = '2023-10-31'
        self.monitor.calculate_daily_summary('Delhi', date)

        # Verify the summary calculations
        call_args = mock_db.store_daily_summary.call_args[0]
        
        # Test basic statistics
        self.assertEqual(call_args[0], 'Delhi')  # city
        self.assertEqual(call_args[1], date)     # date
        self.assertAlmostEqual(call_args[2], 24.25)  # avg_temp
        self.assertEqual(call_args[3], 27.0)    # max_temp
        self.assertEqual(call_args[4], 22.0)    # min_temp
        
        # Test dominant weather with tie-breaking
        self.assertEqual(call_args[5], 'Rain')  # Should choose Rain over Clear due to severity

    def test_dominant_weather_calculation(self):
        """Additional test for dominant weather calculation with various scenarios"""
        mock_data = [
            # Test case 1: Clear winner
            [
                (1, 'Delhi', 1635724800, 'Rain', 25.0, 26.0),
                (2, 'Delhi', 1635728400, 'Rain', 27.0, 28.0),
                (3, 'Delhi', 1635732000, 'Clear', 23.0, 24.0),
            ],
            # Test case 2: Tie with different severities
            [
                (1, 'Delhi', 1635724800, 'Clear', 25.0, 26.0),
                (2, 'Delhi', 1635728400, 'Rain', 27.0, 28.0),
                (3, 'Delhi', 1635732000, 'Clear', 23.0, 24.0),
                (4, 'Delhi', 1635735600, 'Rain', 22.0, 23.0),
            ],
            # Test case 3: Three-way tie
            [
                (1, 'Delhi', 1635724800, 'Clear', 25.0, 26.0),
                (2, 'Delhi', 1635728400, 'Rain', 27.0, 28.0),
                (3, 'Delhi', 1635732000, 'Snow', 23.0, 24.0),
            ]
        ]

        expected_results = ['Rain', 'Rain', 'Snow']
        
        with patch('weather_monitor.WeatherDB') as mock_db:
            for data, expected in zip(mock_data, expected_results):
                mock_db.get_daily_data.return_value = data
                self.monitor.db = mock_db
                
                self.monitor.calculate_daily_summary('Delhi', '2023-10-31')
                result = mock_db.store_daily_summary.call_args[0][5]
                self.assertEqual(result, expected, 
                    f"Failed for case with data {[d[3] for d in data]}, expected {expected} but got {result}")
    def test_alerting_thresholds(self):
        """Test 5: Alerting Thresholds - Test threshold monitoring and alerts"""
        with patch.object(self.monitor, 'trigger_alert') as mock_alert:
            # Test consecutive breaches
            self.monitor.check_temperature_threshold('Delhi', 36.0)
            self.assertEqual(self.monitor.consecutive_breaches['Delhi'], 1)
            self.assertFalse(mock_alert.called)

            # Second breach should trigger alert
            self.monitor.check_temperature_threshold('Delhi', 37.0)
            self.assertEqual(self.monitor.consecutive_breaches['Delhi'], 2)
            self.assertTrue(mock_alert.called)

            # Reset after normal temperature
            self.monitor.check_temperature_threshold('Delhi', 30.0)
            self.assertEqual(self.monitor.consecutive_breaches['Delhi'], 0)

if __name__ == '__main__':
    unittest.main()