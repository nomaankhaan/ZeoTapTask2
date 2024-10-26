# Weather Monitoring System

A Flask-based web application that monitors weather conditions across multiple Indian cities, providing real-time updates, historical data analysis, and temperature threshold alerts.


## Features

1. Real-time weather monitoring for major Indian cities

2. Temperature threshold alerts with email notifications

3. Daily weather summaries and trend analysis

4. Interactive visualizations using Plotly

5. REST API endpoints for weather data

6. Support for complex nested conditions

7. Persistent data storage using SQLite

## Project Setup

1. Clone the Repository

```bash
  git clone https://github.com/nomaankhaan/ZeoTapTask2.git
  cd ZeoTapTask2
```

2. Create and Activate Virtual Environment

```bash
  python -m venv venv
  venv\Scripts\activate
```
3. Install Dependencies

```bash
  pip install -r requirements.txt
```

4. Update the .env files with necessary credentials 

5. Running the Application

    1. Start the Application:

```bash
  python app.py
```
2. Access the Application:

Open your browser and navigate to http://localhost:5000

The dashboard will display current weather conditions, temperature trends, and recent alerts

6. Testing

Run the test suite:

```bash
  python -m unittest test_weather.py
```
