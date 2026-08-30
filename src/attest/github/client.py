"""Small GitHub REST adapter for pull-request comments and reviews."""

from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

STATUS_MARKER = "<!-- attest:status -->"
_NEXT_LINK_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


class GitHubApiError(RuntimeError):
    """An API failure whose message deliberately excludes request secrets."""


class GitHubClient:
    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        self._token = token
        self._api_url = api_url.rstrip("/")

    def upsert_issue_comment(self, repository: str, number: int, marker: str, body: str) -> dict:
        """Update the first bot marker comment, or create a fresh sticky comment."""
        comment_body = f"{marker}\n{body}"
        existing = self._find_marker_comment(repository, number, marker)
        if existing is None:
            response, _ = self._request(
                "POST",
                f"/repos/{repository}/issues/{number}/comments",
                {"body": comment_body},
            )
        else:
            response, _ = self._request(
                "PATCH",
                f"/repos/{repository}/issues/comments/{existing}",
                {"body": comment_body},
            )
        return _object_response(response)

    def create_review(
        self, repository: str, number: int, commit_id: str, comments: list[dict[str, object]]
    ) -> dict:
        """Create one batched inline review against the given pull-request commit."""
        response, _ = self._request(
            "POST",
            f"/repos/{repository}/pulls/{number}/reviews",
            {
                "commit_id": commit_id,
                "body": "Attest review.",
                "event": "COMMENT",
                "comments": comments,
            },
        )
        return _object_response(response)

    def _find_marker_comment(self, repository: str, number: int, marker: str) -> int | None:
        url: str | None = (
            f"{self._api_url}/repos/{repository}/issues/{number}/comments?per_page=100&page=1"
        )
        while url:
            response, headers = self._request("GET", url)
            if not isinstance(response, list):
                raise GitHubApiError("GitHub API returned an invalid response")
            for comment in response:
                if _is_bot_marker(comment, marker):
                    return int(comment["id"])
            url = _next_page(headers.get("Link"))
        return None

    def _request(
        self, method: str, path_or_url: str, payload: dict[str, object] | None = None
    ) -> tuple[object, dict[str, str]]:
        if path_or_url.startswith(("http://", "https://")):
            url = path_or_url
            configured = urlsplit(self._api_url)
            requested = urlsplit(url)
            if (requested.scheme, requested.netloc) != (configured.scheme, configured.netloc):
                raise GitHubApiError("GitHub pagination origin does not match configured API")
        else:
            url = self._api_url + path_or_url
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._token}",
            "User-Agent": "attest",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310 -- API URL is explicit adapter input.
                decoded = json.loads(response.read().decode("utf-8"))
                return decoded, dict(response.headers.items())
        except HTTPError as exc:
            raise GitHubApiError(f"GitHub API request failed with HTTP {exc.code}") from None
        except (URLError, OSError):
            raise GitHubApiError("GitHub API request failed") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise GitHubApiError("GitHub API returned an invalid response") from None


def _is_bot_marker(comment: object, marker: str) -> bool:
    if not isinstance(comment, dict):
        return False
    user = comment.get("user")
    return (
        isinstance(user, dict)
        and user.get("type") == "Bot"
        and isinstance(comment.get("body"), str)
        and marker in comment["body"]
        and isinstance(comment.get("id"), int)
    )


def _next_page(link_header: str | None) -> str | None:
    if not link_header:
        return None
    match = _NEXT_LINK_RE.search(link_header)
    return match.group(1) if match else None


def _object_response(response: object) -> dict:
    if not isinstance(response, dict):
        raise GitHubApiError("GitHub API returned an invalid response")
    return response
