import datetime
import pendulum
import os
import logging

from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.http.hooks.http import HttpHook

@dag(
    dag_id="weather-etl",
    schedule_interval="*/5 * * * *",
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    catchup=False,
    dagrun_timeout=datetime.timedelta(minutes=5),
)
def WeatherETL():
    create_weather_table = PostgresOperator(
        task_id="create_weather_table",
        postgres_conn_id="weather_pg_conn",
        sql="""
            CREATE TABLE IF NOT EXISTS weather (
                "Time" TIMESTAMP,
                "City_Name" TEXT,
                "Weather_Description" TEXT,
                "Temperature" FLOAT,
                PRIMARY KEY ("Time", "City_Name")
            );""",
    )

    create_weather_temp_table = PostgresOperator(
        task_id="create_weather_temp_table",
        postgres_conn_id="weather_pg_conn",
        sql="""
            DROP TABLE IF EXISTS weather_temp;
            CREATE TABLE weather_temp (
                "Time" TIMESTAMP,
                "City_Name" TEXT,
                "Weather_Description" TEXT,
                "Temperature" FLOAT,
                PRIMARY KEY ("Time", "City_Name")
            );""",
    )

    @task
    def get_data():
        # Define the cities for which we will fetch weather data
        cities = ["Papendrecht","Dordrecht","Sliedrecht", "Alblasserdam", "Zwijndrecht", 
                "Hendrik-Ido-Ambacht", "Ridderkerk", "Rotterdam", "Barendrecht", 
                "Amsterdam","Breda,nl", "Tilburg"]

        # Get the OpenWeatherMap API key from environment variables
        api_key = os.getenv("OPENWEATHERMAP_API_KEY")
        if not api_key:
            raise Exception("Missing OPENWEATHERMAP_API_KEY environment variable")
        
        # Establish a connection to the OpenWeatherMap API
        http_hook = HttpHook(method='GET', http_conn_id='openweathermap_conn_id')
        postgres_hook = PostgresHook(postgres_conn_id="weather_pg_conn")
        conn = postgres_hook.get_conn()
        cur = conn.cursor()

        for city in cities:
            # Make a GET request to the OpenWeatherMap API
            endpoint = f"/data/2.5/weather?q={city}&appid={api_key}&units=metric"
            response = http_hook.run(endpoint)
            
            # The API response is in JSON format, so we parse it into a Python dictionary
            data = response.json()
            logging.info(data)
            
            # Extract the relevant data points
            time = datetime.datetime.utcfromtimestamp(data['dt'])
            timezone_offset = datetime.timedelta(seconds=data['timezone'])
            local_time = time + timezone_offset
            city_name = data['name']
            weather_description = ", ".join([weather['description'] for weather in data['weather']])
            temperature = data['main']['temp']

            # Prepare SQL insert statement
            insert_sql = """
                INSERT INTO weather_temp ("Time", "City_Name", "Weather_Description", "Temperature")
                VALUES (%s, %s, %s, %s);
            """

            # Execute SQL statement
            cur.execute(insert_sql, (local_time, city_name, weather_description, temperature))

        # Commit all transactions
        conn.commit()

    @task
    def merge_data():
        query = """
            INSERT INTO weather
            SELECT *
            FROM (
                SELECT DISTINCT *
                FROM weather_temp
            ) t
            ON CONFLICT ("Time", "City_Name") DO UPDATE
            SET
            "Weather_Description" = excluded."Weather_Description",
            "Temperature" = excluded."Temperature";
        """
        try:
            postgres_hook = PostgresHook(postgres_conn_id="weather_pg_conn")
            conn = postgres_hook.get_conn()
            cur = conn.cursor()
            cur.execute(query)
            conn.commit()
            return 0
        except Exception as e:
            return 1

    [create_weather_table, create_weather_temp_table] >> get_data() >> merge_data()

dag = WeatherETL()
