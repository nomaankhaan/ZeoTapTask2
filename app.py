from flask import Flask, render_template, jsonify, request
from datetime import datetime, timedelta
import pandas as pd
from weather_monitor import WeatherMonitor, Config, WeatherDB
import threading
import plotly
import plotly.express as px
import plotly.graph_objects as go
import json

app = Flask(__name__)

# Global variables for sharing data between threads
weather_monitor = None
monitor_thread = None

def start_monitor_thread():
    global weather_monitor, monitor_thread
    config = Config(
        api_key="2cd3f260c41cd54c29f68ddbcbca37e5",
        interval_minutes=5,
        temperature_unit='celsius',
        temp_threshold=35.0,
        consecutive_threshold_breaches=2
    )
    weather_monitor = WeatherMonitor(config)
    monitor_thread = threading.Thread(target=weather_monitor.run, daemon=True)
    monitor_thread.start()

@app.route('/')
def index():
    return render_template('index.html', cities=weather_monitor.config.cities)

@app.route('/api/current_weather/<city>')
def current_weather(city):
    data = weather_monitor.fetch_weather_data(city)
    if data:
        temp = weather_monitor.convert_temperature(data['main']['temp'])
        feels_like = weather_monitor.convert_temperature(data['main']['feels_like'])
        return jsonify({
            'temperature': round(temp, 1),
            'feels_like': round(feels_like, 1),
            'condition': data['weather'][0]['main'],
            'humidity': data['main']['humidity'],
            'timestamp': datetime.fromtimestamp(data['dt']).strftime('%Y-%m-%d %H:%M:%S')
        })
    return jsonify({'error': 'Unable to fetch weather data'}), 404

@app.route('/api/daily_summary/<city>')
def daily_summary(city):
    days = request.args.get('days', 7, type=int)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    with weather_monitor.db.db_path as conn:
        df = pd.read_sql_query(
            '''SELECT date, avg_temp, max_temp, min_temp, dominant_weather
               FROM daily_summaries 
               WHERE city = ? AND date BETWEEN ? AND ?
               ORDER BY date''',
            conn,
            params=(city, start_date.isoformat(), end_date.isoformat())
        )
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['date'], y=df['avg_temp'], name='Average',
                            line=dict(color='blue')))
    fig.add_trace(go.Scatter(x=df['date'], y=df['max_temp'], name='Maximum',
                            line=dict(color='red')))
    fig.add_trace(go.Scatter(x=df['date'], y=df['min_temp'], name='Minimum',
                            line=dict(color='green')))
    
    fig.update_layout(
        title=f'Temperature Trends for {city}',
        xaxis_title='Date',
        yaxis_title=f'Temperature (°{weather_monitor.config.temperature_unit.upper()})'
    )
    
    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    return jsonify({
        'graph': graphJSON,
        'summary': df.to_dict('records')
    })

@app.route('/api/alerts/<city>')
def alerts(city):
    # Get recent alerts from the database
    with weather_monitor.db.db_path as conn:
        alerts = pd.read_sql_query(
            '''SELECT timestamp, temp 
               FROM weather_data 
               WHERE city = ? AND temp > ?
               ORDER BY timestamp DESC
               LIMIT 10''',
            conn,
            params=(city, weather_monitor.config.temp_threshold)
        )
    return jsonify(alerts.to_dict('records'))

if __name__ == '__main__':
    start_monitor_thread()
    app.run(debug=True)