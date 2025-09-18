import requests
import json
from datetime import datetime, timedelta
import re
from urllib.parse import urlparse
import os


class GitHubClient:
    def __init__(self, token):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def get_merged_pull_requests(
        self, owner="apache", repo="iotdb", since_date=None, days=30
    ):
        """
        Fetch merged pull requests from the last N days or since a specific date
        """
        start_date = None
        end_date = None
        if since_date is None:
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            end_date = datetime.now().isoformat()
        elif isinstance(since_date, str):
            start_dt = datetime.strptime(since_date, "%Y-%m-%d")
            start_date = start_dt.isoformat()
            end_date = (start_dt + timedelta(days=days)).isoformat()

        url = f"{self.base_url}/repos/{owner}/{repo}/pulls"
        params = {
            "state": "closed",
            "sort": "merged",
            "direction": "desc",
            "per_page": 100,
        }

        prs = []
        page = 1

        while True:
            params["page"] = page
            response = requests.get(url, headers=self.headers, params=params)

            if response.status_code != 200:
                print(f"Error fetching PRs: {response.status_code}")
                break

            page_prs = response.json()
            if not page_prs:
                break

            # Filter for merged PRs and recent ones
            for pr in page_prs:
                if pr.get("merged_at") is None or pr["merged_at"] > end_date:
                    continue
                elif pr["merged_at"] >= start_date:
                    prs.append(pr)
                elif pr["merged_at"] < start_date:
                    # Since PRs are sorted by merged date, we can break early
                    return prs

            page += 1

        return prs

    def get_pull_request_details(self, pr_number, owner="apache", repo="iotdb"):
        """
        Get detailed information about a specific pull request
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            return response.json()
        else:
            print(f"Error fetching PR details: {response.status_code}")
            return None

    def get_pull_request_comments(self, pr_number, owner="apache", repo="iotdb"):
        """
        Get all comments for a pull request
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        params = {"per_page": 100}

        comments = []
        page = 1

        while True:
            params["page"] = page
            response = requests.get(url, headers=self.headers, params=params)

            if response.status_code != 200:
                print(f"Error fetching comments: {response.status_code}")
                break

            page_comments = response.json()
            if not page_comments:
                break

            comments.extend(page_comments)
            page += 1

        return comments

    def extract_images_from_text(self, text):
        """
        Extract image URLs from text content
        """
        if not text:
            return []

        # Pattern to match markdown images ![alt](url) and HTML images <img src="url">
        markdown_pattern = r"!\[.*?\]\((https?://[^\)]+)\)"
        html_pattern = r'<img[^>]+src="([^"]+)"'

        images = []

        # Find markdown images
        markdown_matches = re.findall(markdown_pattern, text)
        images.extend(markdown_matches)

        # Find HTML images
        html_matches = re.findall(html_pattern, text)
        images.extend(html_matches)

        return list(set(images))  # Remove duplicates

    def download_image(self, image_url):
        """
        Download image from URL
        """
        try:
            response = requests.get(image_url, timeout=30)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "image" in content_type:
                    return {
                        "content_type": content_type,
                        "size": len(response.content),
                        "data": response.content,
                    }
        except Exception as e:
            print(f"Error downloading image {image_url}: {e}")

        return None

    def get_filename_from_url(self, url):
        """
        Extract filename from URL
        """
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        if not filename:
            filename = f"image_{hash(url) % 10000}"
        return filename

    def get_diff_content(self, diff_url):
        """
        Fetch diff content from diff_url
        """
        try:
            response = requests.get(diff_url, headers=self.headers, timeout=30)
            if response.status_code == 200:
                return response.text
            else:
                print(f"Error fetching diff content: {response.status_code}")
                return None
        except Exception as e:
            print(f"Error downloading diff content from {diff_url}: {e}")
            return None
