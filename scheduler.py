import schedule
import time
from datetime import datetime
from scraper import PRScraper
import logging


class PRScraperScheduler:
    def __init__(self, github_token):
        self.github_token = github_token
        self.setup_logging()

    def setup_logging(self):
        """
        Setup logging for the scheduler
        """
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler("pr_scraper.log"), logging.StreamHandler()],
        )
        self.logger = logging.getLogger(__name__)

    def daily_scrape(self):
        """
        Daily scraping task
        """
        self.logger.info("Starting daily PR scraping task")
        try:
            scraper = PRScraper(self.github_token)
            scraper.run(days_back=1)  # Scrape last 1 day
            self.logger.info("Daily scraping completed successfully")
        except Exception as e:
            self.logger.error(f"Error in daily scraping: {e}")
        finally:
            if "scraper" in locals():
                scraper.db.close()

    def run(self):
        """
        Run the scheduler
        """
        self.logger.info("Starting PR scraper scheduler")

        # Schedule daily scraping at 2 AM
        schedule.every().day.at("02:00").do(self.daily_scrape)

        # For testing: run every 5 minutes
        # schedule.every(5).minutes.do(self.daily_scrape)

        self.logger.info("Scheduler started. Daily scraping scheduled for 02:00")

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            self.logger.info("Scheduler stopped by user")
        except Exception as e:
            self.logger.error(f"Scheduler error: {e}")
            raise


if __name__ == "__main__":
    # GitHub token
    GITHUB_TOKEN = "your_github_token_here"

    scheduler = PRScraperScheduler(GITHUB_TOKEN)

    # Run the scheduler
    scheduler.run()
