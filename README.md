# GitHub PR Scraper

A Python scraper that fetches merged pull requests from Apache IoTDB repository and stores them in MySQL database.

## Features

- Fetches merged pull requests from GitHub API
- Extracts PR details (number, title, body, created_at, merged_at, user, labels, etc.)
- Retrieves all comments for each PR
- Downloads and stores images from comments
- Stores all data in MySQL database
- Scheduled daily execution

## Database Schema

### Tables:
- `iotdb_prs_db`: Stores PR information
- `pr_comments`: Stores PR comments
- `pr_images`: Stores images from comments

## Setup Instructions

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up MySQL Database
- Make sure MySQL is running
- Update database credentials in `database.py` (host, user, password)
- Run the setup script:
```bash
python setup_database.py
```

### 3. Run the Scraper
#### One-time execution:
```bash
python scraper.py
```

#### Scheduled execution:
```bash
python scheduler.py
```

## Configuration

### Database Configuration
Update `database.py` with your MySQL credentials:
```python
self.connection = mysql.connector.connect(
    host='localhost',
    user='your_username',
    password='your_password',
    database='iotdb_prs_db'
)
```

### GitHub Token
The GitHub token is hardcoded in the files. Replace `your_github_token_here` with your own token.

## Files Structure

- `database.py`: Database management and table creation
- `github_client.py`: GitHub API client
- `scraper.py`: Main scraper logic
- `scheduler.py`: Daily execution scheduler
- `setup_database.py`: Database setup script
- `requirements.txt`: Python dependencies

## Usage Examples

### Scrape PRs from last 30 days
```python
from scraper import PRScraper

scraper = PRScraper("your_github_token")
scraper.run(days_back=30)
```

### Scrape PRs from last 7 days
```python
scraper.run(days_back=7)
```

## Scheduler

The scheduler runs daily at 2 AM by default. You can modify the schedule in `scheduler.py`:

```python
# Change to run at different time
schedule.every().day.at("10:30").do(self.daily_scrape)

# For testing: run every 5 minutes
schedule.every(5).minutes.do(self.daily_scrape)
```

## Logging

Logs are written to `pr_scraper.log` and console output.

## Notes

- The scraper respects GitHub API rate limits
- Images are stored as BLOB data in the database
- Duplicate PRs and comments are updated rather than re-inserted
- The scraper only processes merged pull requests
