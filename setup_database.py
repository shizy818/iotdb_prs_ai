import mysql.connector
from mysql.connector import Error


def setup_database():
    """
    Create the database and user for the PR scraper
    """
    try:
        # Connect to MySQL server
        connection = mysql.connector.connect(
            host="localhost", user="root", password="1234"
        )

        if connection.is_connected():
            cursor = connection.cursor()

            # Create database
            cursor.execute("CREATE DATABASE IF NOT EXISTS github_prs")
            print("Database 'github_prs' created or already exists")

            # Grant privileges (optional)
            # cursor.execute("GRANT ALL PRIVILEGES ON github_prs.* TO 'root'@'localhost'")
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
