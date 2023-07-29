# OpenWeatherMapAPI-ETL

This repository contains the code for a data engineering project that extracts, transforms, and loads (ETL) weather data from the OpenWeatherMap API into a PostgreSQL database. The ETL process is orchestrated using Apache Airflow and the entire setup is containerized using Docker.

## Project Structure

- `dags/weather-etl.py`: This is the main Airflow DAG (Directed Acyclic Graph) file that defines the ETL process. The process includes creating necessary tables in the PostgreSQL database, fetching weather data from the OpenWeatherMap API, and merging the fetched data into the main database table.

- `docker-compose.yaml`: This file defines the Docker services, networks, and volumes for the project. It sets up an Apache Airflow environment with PostgreSQL as the metadata database, Redis as the message broker, and Celery as the task execution engine. PGAdmin is also included for managing the PostgreSQL database.

## Setup and Running

1. Clone the repository to your local machine.

2. Create a `.env` file in the root directory of the project and add the following environment variables:

    ```
    POSTGRES_USER=...
    POSTGRES_PASSWORD=...
    POSTGRES_DB=...
    PGADMIN_DEFAULT_EMAIL=...
    PGADMIN_DEFAULT_PASSWORD=...
    _AIRFLOW_WWW_USER_USERNAME=...
    _AIRFLOW_WWW_USER_PASSWORD=...
    OPENWEATHERMAP_API_KEY=...
    ```

    Replace the `...` with your actual values.

3. Navigate to the project directory and run `docker-compose up` to start the Docker services.

4. Access the Airflow web UI at `localhost:8080`. 

5. In the Airflow web interface, navigate to `Admin > Connections` and create the following connections:

    - **PostgreSQL Connection**: Click on `Create` and fill in the following details:
        - Conn Id: `weather_pg_conn`
        - Conn Type: `Postgres`
        - Host: `postgres`
        - Schema: `<Your POSTGRES_DB value>`
        - Login: `<Your POSTGRES_USER value>`
        - Password: `<Your POSTGRES_PASSWORD value>`
        - Port: `5432`

    - **OpenWeatherMap API Connection**: Click on `Create` and fill in the following details:
        - Conn Id: `openweathermap_conn_id`
        - Conn Type: `HTTP`
        - Host: `http://api.openweathermap.org`

6. Trigger the `weather-etl` DAG to start the ETL process.

7. Access the PGAdmin web UI at `localhost:5050` using the `PGADMIN_DEFAULT_EMAIL` and `PGADMIN_DEFAULT_PASSWORD` values you set in the `.env` file.

8. In the PGAdmin interface, create a new server with the following details:
    - General > Name: `WeatherDB`
    - Connection > Host: `postgres`
    - Connection > Port: `5432`
    - Connection > Maintenance database: `<Your POSTGRES_DB value>`
    - Connection > Username: `<Your POSTGRES_USER value>`
    - Connection > Password: `<Your POSTGRES_PASSWORD value>`

## Querying the Data

Once the ETL process has run and data has been loaded into the PostgreSQL database, you can query the data using PGAdmin:

1. In the PGAdmin interface, expand the `Servers` > `WeatherDB` > `Databases` > `<Your POSTGRES_DB value>` > `Schemas` > `public` > `Tables` tree in the left panel.

2. Right-click on the `weather` table and select `View/Edit Data` > `All Rows`.

3. This will open a SQL Query window with a `SELECT * FROM public.weather;` query. Click on the `Execute/Refresh` button (or press F5) to run the query and view the data.

## ETL Process

The ETL process runs every 5 minutes and consists of the following steps:

1. Creating the main 'weather' table in the PostgreSQL database if it doesn't exist.

2. Creating a temporary 'weather_temp' table in the PostgreSQL database.

3. Fetching weather data for selected cities from the OpenWeatherMap API and inserting it into the 'weather_temp' table.

4. Merging the data in the 'weather_temp' table into the 'weather' table.

## Dependencies

This project relies on several Airflow components and packages including:

- Airflow's PostgresHook for interacting with the PostgreSQL database
- Airflow's PostgresOperator for executing SQL queries on the PostgreSQL database
- Airflow's HttpHook for making HTTP requests to the OpenWeatherMap API
