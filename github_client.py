import requests
import json
from datetime import datetime, timedelta
import re
from urllib.parse import urlparse
import os
from logger_config import setup_logger

logger = setup_logger(__name__)


class GitHubClient:
    def __init__(self, token):
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _transform_pr_data(self, pr_node, owner="apache", repo="iotdb"):
        """
        Transform GraphQL PR node to REST API compatible format
        """
        # Process comments
        comments_data = []
        for comment in pr_node.get("comments", {}).get("nodes", []):
            author = comment.get("author")
            user = author["login"] if author else "unknown"
            if author and author.get("__typename", "User") == "Bot":
                user = f"{user}[bot]"

            comments_data.append(
                {
                    "id": comment["databaseId"],
                    "user": user,
                    "body": comment.get("body", ""),
                    "created_at": comment["createdAt"],
                    "updated_at": comment["updatedAt"],
                    "html_url": comment.get("url", ""),
                }
            )

        # Extract merge commit oid
        merge_commit = None
        if pr_node.get("mergeCommit"):
            merge_commit = pr_node["mergeCommit"].get("oid")

        # Transform to REST API compatible format
        pr = {
            "number": pr_node["number"],
            "title": pr_node["title"],
            "body": pr_node.get("body", ""),
            "created_at": pr_node["createdAt"],
            "merged_at": pr_node["mergedAt"],
            "user": {
                "login": (
                    pr_node["author"]["login"] if pr_node.get("author") else "unknown"
                )
            },
            "labels": [{"name": label["name"]} for label in pr_node["labels"]["nodes"]],
            "comments": comments_data,
            "head": {"ref": pr_node["headRefName"]},
            "base": {"ref": pr_node["baseRefName"]},
            "additions": pr_node["additions"],
            "deletions": pr_node["deletions"],
            "merge_commit": merge_commit,
            "diff_url": f"https://github.com/{owner}/{repo}/pull/{pr_node['number']}.diff",
            "comments_url": f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_node['number']}/comments",
        }

        return pr

    def get_iotdb_prs(
        self, owner="apache", repo="iotdb", since_date="2024-01-01", days=7
    ):
        """
        Fetch merged pull requests from since_date for N days
        Uses GitHub GraphQL API v4 with search for efficient data fetching

        Args:
            since_date: Start date in YYYY-MM-DD format (required)
            days: Number of days from since_date (default: 30)
        """
        if since_date is None:
            raise ValueError("since_date is required")

        # Calculate date range, [start_date, end_date]
        start_dt = datetime.strptime(since_date, "%Y-%m-%d")
        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = (start_dt + timedelta(days=days - 1)).strftime("%Y-%m-%d")

        # GraphQL API endpoint
        url = "https://api.github.com/graphql"

        # GraphQL query using search API with all required fields for process_pr
        query = """
        query($searchQuery: String!, $cursor: String) {
          search(query: $searchQuery, type: ISSUE, first: 100, after: $cursor) {
            issueCount
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              ... on PullRequest {
                number
                title
                body
                createdAt
                mergedAt
                author {
                  login
                }
                labels(first: 50) {
                  nodes {
                    name
                  }
                }
                comments(first: 100) {
                  nodes {
                    databaseId
                    author {
                      login
                      __typename
                    }
                    body
                    createdAt
                    updatedAt
                    url
                  }
                }
                headRefName
                baseRefName
                additions
                deletions
                mergeCommit {
                  oid
                }
              }
            }
          }
        }
        """

        # Build search query string
        search_query = (
            f"repo:{owner}/{repo} type:pr is:merged merged:{start_date}..{end_date}"
        )

        prs = []
        cursor = None

        while True:
            variables = {"searchQuery": search_query, "cursor": cursor}

            try:
                response = requests.post(
                    url,
                    json={"query": query, "variables": variables},
                    headers=self.headers,
                    timeout=30,
                )

                if response.status_code != 200:
                    logger.error(f"GraphQL API error: HTTP {response.status_code}")
                    return []

                result = response.json()

                # Check for errors
                if "errors" in result:
                    logger.error(f"GraphQL error: {result['errors']}")
                    return []

                # Extract PR data
                search_result = result["data"]["search"]
                nodes = search_result["nodes"]

                # Transform to REST API compatible format for process_pr
                for node in nodes:
                    pr = self._transform_pr_data(node, owner, repo)
                    prs.append(pr)

                # Check if there are more pages
                page_info = search_result["pageInfo"]
                if not page_info["hasNextPage"]:
                    break

                cursor = page_info["endCursor"]

            except requests.exceptions.RequestException as e:
                logger.error(f"Network error: {str(e)}")
                return []
            except Exception as e:
                logger.error(f"Error processing GraphQL response: {str(e)}")
                return []

        return prs

    def get_iotdb_pr(self, pr_number, owner="apache", repo="iotdb"):
        """
        Get detailed information about a specific pull request using GraphQL
        Returns data in the same format as get_iotdb_prs for consistency
        """
        # GraphQL API endpoint
        url = "https://api.github.com/graphql"

        # GraphQL query for a single PR with all fields including comments
        query = """
        query($owner: String!, $repo: String!, $number: Int!) {
          repository(owner: $owner, name: $repo) {
            pullRequest(number: $number) {
              number
              title
              body
              createdAt
              mergedAt
              author {
                login
              }
              labels(first: 50) {
                nodes {
                  name
                }
              }
              comments(first: 100) {
                nodes {
                  databaseId
                  author {
                    login
                    __typename
                  }
                  body
                  createdAt
                  updatedAt
                  url
                }
              }
              headRefName
              baseRefName
              additions
              deletions
              mergeCommit {
                oid
              }
            }
          }
        }
        """

        variables = {"owner": owner, "repo": repo, "number": pr_number}

        try:
            response = requests.post(
                url,
                json={"query": query, "variables": variables},
                headers=self.headers,
                timeout=30,
            )

            if response.status_code != 200:
                return None, f"GraphQL API error: HTTP {response.status_code}"

            result = response.json()

            # Check for errors
            if "errors" in result:
                return None, f"GraphQL error: {result['errors']}"

            # Extract PR data
            pr_data = result["data"]["repository"]["pullRequest"]

            if not pr_data:
                return None, f"PR #{pr_number} not found"

            # Transform to REST API compatible format
            pr = self._transform_pr_data(pr_data, owner, repo)

            return pr, None

        except requests.exceptions.RequestException as e:
            return None, f"Network error: {str(e)}"
        except Exception as e:
            return None, f"Error processing GraphQL response: {str(e)}"

    def get_pull_request_comments(self, pr_number, owner="apache", repo="iotdb"):
        """
        Get all comments for a pull request and return processed data
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        params = {"per_page": 100}

        comments = []
        page = 1

        while True:
            params["page"] = page
            try:
                response = requests.get(
                    url, headers=self.headers, params=params, timeout=30
                )

                if response.status_code != 200:
                    return None, f"HTTP {response.status_code}"

                page_comments = response.json()
                if not page_comments:
                    break

                comments.extend(page_comments)
                page += 1
            except requests.exceptions.RequestException as e:
                return None, f"Network error: {str(e)}"

        # Process comments data
        comments_data = []
        for comment in comments:
            comments_data.append(
                {
                    "id": comment["id"],
                    "user": comment["user"]["login"],
                    "body": comment["body"],
                    "created_at": comment["created_at"],
                    "updated_at": comment["updated_at"],
                    "html_url": comment["html_url"],
                }
            )

        return comments_data, None

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
            logger.error(f"Error downloading image {image_url}: {e}")

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
                return response.text, None
            else:
                return None, f"HTTP {response.status_code}"
        except Exception as e:
            return None, f"Download error: {str(e)}"
