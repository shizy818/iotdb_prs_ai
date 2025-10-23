import mysql.connector
from mysql.connector import Error
from config import DEFAULT_DB_CONFIG


def setup_database():
    """
    Create the database for the PR scraper
    使用 config.py 中的数据库配置
    """
    try:
        # Connect to MySQL server (without specifying database)
        connection = mysql.connector.connect(
            host=DEFAULT_DB_CONFIG["host"],
            user=DEFAULT_DB_CONFIG["user"],
            password=DEFAULT_DB_CONFIG["password"],
        )

        if connection.is_connected():
            cursor = connection.cursor()

            # Create database
            database_name = DEFAULT_DB_CONFIG["database"]
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {database_name}")
            print(f"Database '{database_name}' created or already exists")

            # Grant privileges (optional - if needed)
            # cursor.execute(f"GRANT ALL PRIVILEGES ON {database_name}.* TO '{DEFAULT_DB_CONFIG['user']}'@'{DEFAULT_DB_CONFIG['host']}'")
            # cursor.execute("FLUSH PRIVILEGES")

            print("Database setup completed")

    except Error as e:
        print(f"Error setting up database: {e}")
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


if __name__ == "__main__":
    setup_database()
