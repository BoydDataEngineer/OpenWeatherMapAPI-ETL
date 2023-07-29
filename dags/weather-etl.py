"""
This DAG is for the extraction, transformation, and loading (ETL) of weather data.
The data is fetched from the OpenWeatherMap API and stored in a PostgreSQL database.

The ETL process runs every 5 minutes (as per the schedule_interval parameter).
The process consists of the following steps:

1. Creating the main 'weather' table in the PostgreSQL database if it doesn't exist
   - The 'weather' table has columns for Time, City Name, Weather Description, and Temperature.

2. Creating a temporary 'weather_temp' table in the PostgreSQL database. 
   - This table has the same structure as the 'weather' table. It's dropped and recreated in each DAG run.

3. Fetching weather data for selected cities from the OpenWeatherMap API
   - The cities are specified in the 'get_data' function. The function fetches weather data for these cities using the OpenWeatherMap API and inserts it into the 'weather_temp' table.
   - The OpenWeatherMap API key is retrieved from the environment variables.

4. Merging the data in the 'weather_temp' table into the 'weather' table.
   - The 'merge_data' function handles this. It inserts distinct records from 'weather_temp' into 'weather'. 
   - If a record with the same time and city name already exists in 'weather', the function updates the weather description and temperature of that record with the values from 'weather_temp'.

Dependencies: 
This DAG relies on several Airflow components and packages including:
- Airflow's PostgresHook for interacting with the PostgreSQL database
- Airflow's PostgresOperator for executing SQL queries on the PostgreSQL database
- Airflow's HttpHook for making HTTP requests to the OpenWeatherMap API
"""

import datetime
import pendulum
import os
import logging

from airflow.decorators import dag, task
from airflow.providers.postgres.hooks.postgres import PostgresHook
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.http.hooks.http import HttpHook

# @dag is a decorator that turns the function into a DAG factory. The function will be called once for each
# DagRun, and it will return a DAG object. This decorator allows for dynamic generation of DAGs.
@dag(
    # The unique identifier for the DAG. This is the name that is used when identifying the DAG in the Airflow web UI.
    dag_id="weather-etl",
    
    # How often the DAG should run, specified as a cron expression.
    schedule_interval="*/5 * * * *",
    
    # The datetime when the DAG should start running tasks for the first time. Here we're using the pendulum library 
    # to generate a timezone-aware datetime object.
    start_date=pendulum.datetime(2023, 1, 1, tz="UTC"),
    
    # If set to False, the DAG runs the latest run only. If set to True, the scheduler catches up on every run 
    # missed since the defined start_date.
    catchup=False,
    
    # The maximum amount of time a DagRun should take. If a DagRun takes longer than this amount of time, 
    # Airflow will mark it as failed. Here, we set the timeout to 5 minutes.
    dagrun_timeout=datetime.timedelta(minutes=5),
    
    # Markdown text that will be displayed on the DAG's detail view in the Airflow web UI. The text can be used 
    # to provide a description or documentation for the DAG.
    doc_md=__doc__,
)
def WeatherETL():
    # Task to create the main weather table in PostgreSQL
    # Using PostgresOperator to execute a SQL command, in this case to create the table if it does not exist
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

    # Task to create a temporary weather table in PostgreSQL for the ETL process
    # This table is used to temporarily hold the fetched data before merging it into the main 'weather' table
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

    # Task to fetch weather data from the OpenWeatherMap API
    # The function first fetches the API key from an environment variable, and then makes HTTP GET requests to fetch weather data
    @task
    def get_data():
        # List of cities to fetch weather data for
        cities = ["Papendrecht","Dordrecht","Sliedrecht", "Alblasserdam", "Zwijndrecht", 
                "Hendrik-Ido-Ambacht", "Ridderkerk", "Rotterdam", "Barendrecht", 
                "Amsterdam","Breda,nl", "Tilburg"]

        # Fetching the OpenWeatherMap API key from environment variables
        api_key = os.getenv("OPENWEATHERMAP_API_KEY")
        if not api_key:
            raise Exception("Missing OPENWEATHERMAP_API_KEY environment variable")
        
        # Establishing a connection to the OpenWeatherMap API
        http_hook = HttpHook(method='GET', http_conn_id='openweathermap_conn_id')
        postgres_hook = PostgresHook(postgres_conn_id="weather_pg_conn")
        conn = postgres_hook.get_conn()
        cur = conn.cursor()

        for city in cities:
            # Making a GET request to the OpenWeatherMap API for each city
            endpoint = f"/data/2.5/weather?q={city}&appid={api_key}&units=metric"
            response = http_hook.run(endpoint)
            
            # Parsing the JSON response into a Python dictionary
            data = response.json()
            logging.info(data)
            
            # Extracting relevant data from the response
            time = datetime.datetime.utcfromtimestamp(data['dt'])
            timezone_offset = datetime.timedelta(seconds=data['timezone'])
            local_time = time + timezone_offset
            city_name = data['name']
            weather_description = ", ".join([weather['description'] for weather in data['weather']])
            temperature = data['main']['temp']

            # Preparing SQL insert statement
            insert_sql = """
                INSERT INTO weather_temp ("Time", "City_Name", "Weather_Description", "Temperature")
                VALUES (%s, %s, %s, %s);
            """

            # Executing the SQL statement
            cur.execute(insert_sql, (local_time, city_name, weather_description, temperature))

        # Committing all transactions to ensure that the changes are saved
        conn.commit()

    # This task is responsible for merging data from the temporary table into the main 'weather' table.
    @task
    def merge_data():
        # SQL query for merging the data. 
        # It inserts distinct records from the 'weather_temp' table into the 'weather' table.
        # In case of conflict on 'Time' and 'City_Name' (the primary key), it updates the 
        # 'Weather_Description' and 'Temperature' fields in the 'weather' table with those from the 'weather_temp' table.
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
            # Establish connection to PostgreSQL using the provided connection ID
            postgres_hook = PostgresHook(postgres_conn_id="weather_pg_conn")
            conn = postgres_hook.get_conn()
            cur = conn.cursor()
            
            # Execute the SQL query
            cur.execute(query)
            
            # Commit changes to the database
            conn.commit()
            
            # If all operations succeed, return 0
            return 0
        except Exception as e:
            # In case of any exception, return 1
            return 1

    # The operator '>>' sets the execution order of tasks. 
    # 'create_weather_table' and 'create_weather_temp_table' tasks are executed first, 
    # followed by 'get_data', and finally 'merge_data'.
    [create_weather_table, create_weather_temp_table] >> get_data() >> merge_data()

# The 'dag' variable is assigned the DAG object. This is necessary for Airflow to recognize this script as a valid DAG.
dag = WeatherETL()
