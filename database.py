import mysql.connector
from mysql.connector import Error
import os
from datetime import datetime


def convert_iso_to_mysql_datetime(iso_datetime):
    """
    Convert ISO 8601 datetime format (e.g., "2025-03-18T01:57:54Z")
    to MySQL datetime format (e.g., "2025-03-18 01:57:54")
    """
    if not iso_datetime:
        return None

    try:
        # Parse ISO 8601 format and format as MySQL datetime
        dt = datetime.fromisoformat(iso_datetime.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None


class DatabaseManager:
    def __init__(self):
        self.connection = None
        self.connect()
        self.create_tables()

    def connect(self):
        try:
            self.connection = mysql.connector.connect(
                host="localhost",
                user="root",
                password="1234",
                database="github_prs",
                autocommit=True,
            )
            if self.connection.is_connected():
                print("Connected to MySQL database")
        except Error as e:
            print(f"Error connecting to MySQL: {e}")
            raise

    def create_tables(self):
        create_pull_requests_table = """
        CREATE TABLE IF NOT EXISTS pull_requests (
            number INT PRIMARY KEY,
            title VARCHAR(1000),
            body TEXT,
            created_at DATETIME,
            merged_at DATETIME,
            user VARCHAR(255),
            labels JSON,
            head VARCHAR(255),
            base VARCHAR(255),
            diff_url VARCHAR(1000),
            comments_url VARCHAR(1000),
            additions INT,
            deletions INT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """

        create_comments_table = """
        CREATE TABLE IF NOT EXISTS pr_comments (
            id BIGINT PRIMARY KEY,
            pr_number INT,
            user VARCHAR(255),
            body TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            html_url VARCHAR(1000),
            FOREIGN KEY (pr_number) REFERENCES pull_requests(number) ON DELETE CASCADE
        )
        """

        create_images_table = """
        CREATE TABLE IF NOT EXISTS pr_images (
            id INT AUTO_INCREMENT PRIMARY KEY,
            comment_id BIGINT,
            url VARCHAR(1000),
            filename VARCHAR(255),
            content_type VARCHAR(100),
            size INT,
            data LONGBLOB,
            FOREIGN KEY (comment_id) REFERENCES pr_comments(id) ON DELETE CASCADE
        )
        """

        create_diffs_table = """
        CREATE TABLE IF NOT EXISTS pr_diffs (
            id INT AUTO_INCREMENT PRIMARY KEY,
            pr_number INT,
            diff_content LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (pr_number) REFERENCES pull_requests(number) ON DELETE CASCADE
        )
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(create_pull_requests_table)
            cursor.execute(create_comments_table)
            cursor.execute(create_images_table)
            cursor.execute(create_diffs_table)
            print("Tables created successfully")
        except Error as e:
            print(f"Error creating tables: {e}")
        finally:
            cursor.close()

    def insert_pr(self, pr_data):
        query = """
        INSERT INTO pull_requests (number, title, body, created_at, merged_at, user, labels, head, base, diff_url, comments_url, additions, deletions)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                query,
                (
                    pr_data["number"],
                    pr_data["title"],
                    pr_data["body"],
                    convert_iso_to_mysql_datetime(pr_data["created_at"]),
                    convert_iso_to_mysql_datetime(pr_data["merged_at"]),
                    pr_data["user"],
                    pr_data["labels"],
                    pr_data["head"],
                    pr_data["base"],
                    pr_data["diff_url"],
                    pr_data["comments_url"],
                    pr_data["additions"],
                    pr_data["deletions"],
                ),
            )
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error inserting PR: {e}")
            return False
        finally:
            cursor.close()

    def insert_comment(self, comment_data):
        # 过滤掉包含 [bot] 的作者
        if "[bot]" in comment_data.get("user", "").lower():
            print(f"跳过bot评论: {comment_data.get('user', '')}")
            return True

        query = """
        INSERT INTO pr_comments (id, pr_number, user, body, created_at, updated_at, html_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                query,
                (
                    comment_data["id"],
                    comment_data["pr_number"],
                    comment_data["user"],
                    comment_data["body"],
                    convert_iso_to_mysql_datetime(comment_data["created_at"]),
                    convert_iso_to_mysql_datetime(comment_data["updated_at"]),
                    comment_data["html_url"],
                ),
            )
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error inserting comment: {e}")
            return False
        finally:
            cursor.close()

    def insert_image(self, image_data):
        query = """
        INSERT INTO pr_images (comment_id, url, filename, content_type, size, data)
        VALUES (%s, %s, %s, %s, %s, %s)
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                query,
                (
                    image_data["comment_id"],
                    image_data["url"],
                    image_data["filename"],
                    image_data["content_type"],
                    image_data["size"],
                    image_data["data"],
                ),
            )
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error inserting image: {e}")
            return False
        finally:
            cursor.close()

    def insert_diff(self, diff_data):
        query = """
        INSERT INTO pr_diffs (pr_number, diff_content)
        VALUES (%s, %s)
        """

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                query,
                (
                    diff_data["pr_number"],
                    diff_data["diff_content"],
                ),
            )
            self.connection.commit()
            return True
        except Error as e:
            print(f"Error inserting diff: {e}")
            return False
        finally:
            cursor.close()

    def pr_exists(self, pr_number):
        """
        Check if a PR already exists in the database
        """
        query = "SELECT 1 FROM pull_requests WHERE number = %s"

        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (pr_number,))
            result = cursor.fetchone()
            return result is not None
        except Error as e:
            print(f"Error checking PR existence: {e}")
            return False
        finally:
            cursor.close()

    def insert_pr_diff_comments(self, pr_data, diff_content=None, comments_list=None):
        """在一个事务中处理PR、diff和comments"""
        cursor = self.connection.cursor()
        try:
            # 调试信息：检查连接状态
            print(
                f"开始处理PR #{pr_data['number']}: autocommit={self.connection.autocommit}, in_transaction={self.connection.in_transaction}"
            )

            self.connection.start_transaction()

            # 插入PR
            pr_insert = """
            INSERT INTO pull_requests (number, title, body, created_at, merged_at, user, labels, head, base, diff_url, comments_url, additions, deletions)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                pr_insert,
                (
                    pr_data["number"],
                    pr_data["title"],
                    pr_data["body"],
                    convert_iso_to_mysql_datetime(pr_data["created_at"]),
                    convert_iso_to_mysql_datetime(pr_data["merged_at"]),
                    pr_data["user"],
                    pr_data["labels"],
                    pr_data["head"],
                    pr_data["base"],
                    pr_data["diff_url"],
                    pr_data["comments_url"],
                    pr_data["additions"],
                    pr_data["deletions"],
                ),
            )

            # 插入diff
            if diff_content:
                diff_insert = (
                    "INSERT INTO pr_diffs (pr_number, diff_content) VALUES (%s, %s)"
                )
                cursor.execute(diff_insert, (pr_data["number"], diff_content))

            # 插入comments（过滤掉 bot）
            if comments_list:
                comment_insert = """
                INSERT INTO pr_comments (id, pr_number, user, body, created_at, updated_at, html_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                for comment in comments_list:
                    # 过滤掉包含 [bot] 的作者
                    if "[bot]" in comment.get("user", "").lower():
                        print(f"跳过bot评论: {comment.get('user', '')}")
                        continue

                    cursor.execute(
                        comment_insert,
                        (
                            comment["id"],
                            pr_data["number"],
                            comment["user"],
                            comment["body"],
                            convert_iso_to_mysql_datetime(comment["created_at"]),
                            convert_iso_to_mysql_datetime(comment["updated_at"]),
                            comment["html_url"],
                        ),
                    )

            self.connection.commit()
            return True

        except Error as e:
            self.connection.rollback()
            print(f"事务失败，已回滚: {e}")
            return False
        finally:
            cursor.close()

    def delete_pr(self, pr_number):
        """删除PR（CASCADE自动删除相关数据）"""
        query = "DELETE FROM pull_requests WHERE number = %s"
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, (pr_number,))
            self.connection.commit()
            return cursor.rowcount > 0
        except Error as e:
            print(f"删除PR失败: {e}")
            return False
        finally:
            cursor.close()

    def close(self):
        if self.connection and self.connection.is_connected():
            self.connection.close()
