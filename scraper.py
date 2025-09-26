import json
from datetime import datetime
from database import DatabaseManager
from github_client import GitHubClient


"""
1. 抓取单个PR
python scraper.py --number 12345

2. 抓取过去N天的PR（默认30天）
python scraper.py --days_back 30
python scraper.py  # 使用默认值

3. 抓取从某天开始的N天内PR
python scraper.py --since_date 2024-01-01 --days 7
"""


class PRScraper:
    def __init__(self, github_token):
        self.db = DatabaseManager()
        self.github = GitHubClient(github_token)

    def scrape_merged_prs(self, days_back=30):
        """
        Scrape merged pull requests and store them in the database
        """
        print(f"Fetching merged PRs from the last {days_back} days...")
        prs = self.github.get_merged_pull_requests(days=days_back)

        if not prs:
            print("No merged PRs found")
            return

        print(f"Found {len(prs)} merged PRs")

        for pr in prs:
            self.process_pr(pr)

    def scrape_single_pr(self, pr_number):
        """
        Scrape a single pull request by number
        """
        print(f"Fetching PR #{pr_number}...")
        pr_details, error = self.github.get_pull_request_details(pr_number)

        if error:
            print(f"Could not fetch PR #{pr_number}: {error}")
            return False

        # Check if PR is merged
        if not pr_details.get("merged_at"):
            print(f"PR #{pr_number} is not merged, skipping...")
            return False

        return self.process_pr(pr_details)

    def process_pr(self, pr):
        """
        Process a single pull request
        """
        print(f"Processing PR #{pr['number']}: {pr['title']}")

        # Check if PR already exists in database
        if self.db.pr_exists(pr["number"]):
            print(f"PR #{pr['number']} already exists, skipping...")
            return True

        # Extract PR data
        pr_data = {
            "number": pr["number"],
            "title": pr["title"],
            "body": pr.get("body", ""),
            "created_at": pr["created_at"],
            "merged_at": pr["merged_at"],
            "user": pr["user"]["login"],
            "labels": json.dumps([label["name"] for label in pr.get("labels", [])]),
            "head": pr["head"]["ref"],
            "base": pr["base"]["ref"],
            "diff_url": pr["diff_url"],
            "comments_url": pr["comments_url"],
            "additions": pr.get("additions", 0),
            "deletions": pr.get("deletions", 0),
        }

        # Get diff content
        diff_content, error = self.github.get_diff_content(pr["diff_url"])
        if error:
            print(f"Failed to fetch diff content for PR #{pr['number']}: {error}")
            return False

        # Get comments data
        comments_data, error = self.github.get_pull_request_comments(pr["number"])
        if error:
            print(f"Failed to fetch comments for PR #{pr['number']}: {error}")
            return False

        # Process PR, diff and comments in one transaction
        if self.db.insert_pr_diff_comments(pr_data, diff_content, comments_data):
            print(f"Successfully processed PR #{pr['number']} with all data")

            # Process images one by one after PR data is saved
            # 暂时不处理评论中的图片
            # for comment in comments_data:
            #     self.process_comment_images(comment["id"], comment["body"])
            return True
        else:
            print(f"Failed to process PR #{pr['number']}")
            return False

    def process_comment_images(self, comment_id, comment_body):
        """
        Extract and download images from comment body
        """
        if not comment_body:
            return

        image_urls = self.github.extract_images_from_text(comment_body)

        if not image_urls:
            return

        print(f"Found {len(image_urls)} images in comment {comment_id}")

        for image_url in image_urls:
            self.process_image(comment_id, image_url)

    def process_image(self, comment_id, image_url):
        """
        Process a single image
        """
        print(f"Downloading image from {image_url}")

        image_data = self.github.download_image(image_url)

        if image_data:
            image_record = {
                "comment_id": comment_id,
                "url": image_url,
                "filename": self.github.get_filename_from_url(image_url),
                "content_type": image_data["content_type"],
                "size": image_data["size"],
                "data": image_data["data"],
            }

            if self.db.insert_image(image_record):
                print(f"Stored image {image_record['filename']}")
            else:
                print(f"Failed to store image {image_record['filename']}")
        else:
            print(f"Failed to download image from {image_url}")

    def run_single_pr(self, pr_number):
        """
        Run the scraper for a single PR
        """
        try:
            print(f"Starting PR scraper for #{pr_number} at {datetime.now()}")
            success = self.scrape_single_pr(pr_number)
            if success:
                print(f"Successfully scraped PR #{pr_number}")
            else:
                print(f"Failed to scrape PR #{pr_number}")
            print(f"Scraping completed at {datetime.now()}")
        except Exception as e:
            print(f"Error during scraping: {e}")
        finally:
            self.db.close()

    def run_by_date_range(self, since_date_str, days):
        """
        Run the scraper for a specific date range
        """
        try:
            print(f"Starting PR scraper from {since_date_str} at {datetime.now()}")
            prs = self.github.get_merged_pull_requests(
                since_date=since_date_str, days=days
            )

            if not prs:
                print("No merged PRs found")
                return

            print(f"Found {len(prs)} merged PRs")

            for pr in prs:
                self.process_pr(pr)

            print(f"Scraping completed at {datetime.now()}")
        except Exception as e:
            print(f"Error during scraping: {e}")
        finally:
            self.db.close()

    def run_back_days(self, days_back=30):
        """
        Run the scraper for time range
        """
        try:
            print(f"Starting PR scraper at {datetime.now()}")
            self.scrape_merged_prs(days_back=days_back)
            print(f"Scraping completed at {datetime.now()}")
        except Exception as e:
            print(f"Error during scraping: {e}")
        finally:
            self.db.close()


if __name__ == "__main__":
    import argparse
    from datetime import datetime

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="GitHub PR Scraper")
    parser.add_argument("--number", type=int, help="Scrape a single PR by number")
    parser.add_argument(
        "--days_back",
        type=int,
        default=30,
        help="Scrape PRs from the last N days (default: 30)",
    )
    parser.add_argument(
        "--since_date", type=str, help="Start date in YYYY-MM-DD format"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to scrape from since_date (default: 7)",
    )

    args = parser.parse_args()

    # GitHub token
    GITHUB_TOKEN = "your_github_token_here"

    scraper = PRScraper(GITHUB_TOKEN)

    if args.number:
        # Scrape a single PR
        scraper.run_single_pr(args.number)
    elif args.since_date:
        # Scrape from a specific start date
        scraper.run_by_date_range(args.since_date, args.days)
    else:
        # Scrape by days back
        scraper.run_back_days(days_back=args.days_back)
