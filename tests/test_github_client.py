from __future__ import annotations

import json
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest


class _FakeGitHub:
    def __init__(self) -> None:
        self.responses: dict[tuple[str, str], list[tuple[int, object, dict[str, str]]]] = {}
        self.requests: list[dict[str, object]] = []
        handler = self._handler()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def reply(
        self,
        method: str,
        path: str,
        payload: object,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.responses.setdefault((method, path), []).append((status, payload, headers or {}))

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self._respond()

            def do_POST(self) -> None:  # noqa: N802
                self._respond()

            def do_PATCH(self) -> None:  # noqa: N802
                self._respond()

            def _respond(self) -> None:
                content_length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_length).decode("utf-8")
                fake.requests.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "headers": dict(self.headers.items()),
                        "body": json.loads(body) if body else None,
                    }
                )
                status, payload, headers = fake.responses[(self.command, self.path)].pop(0)
                encoded = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                for name, value in headers.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


@pytest.fixture
def github_server() -> Iterator[_FakeGitHub]:
    server = _FakeGitHub()
    server.start()
    yield server
    server.close()


def test_upsert_issue_comment_creates_sticky_comment(github_server: _FakeGitHub) -> None:
    from attest.github.client import STATUS_MARKER, GitHubClient

    comments_path = "/repos/octo/widgets/issues/9/comments?per_page=100&page=1"
    github_server.reply("GET", comments_path, [])
    github_server.reply("POST", "/repos/octo/widgets/issues/9/comments", {"id": 101})

    response = GitHubClient("secret-token", github_server.url).upsert_issue_comment(
        "octo/widgets", 9, STATUS_MARKER, "Review running."
    )

    assert response == {"id": 101}
    request = github_server.requests[-1]
    assert request["method"] == "POST"
    assert request["body"] == {"body": "<!-- attest:status -->\nReview running."}
    assert str(request["headers"]["Authorization"]) == "Bearer secret-token"


def test_upsert_issue_comment_updates_first_bot_marker_across_pages(
    github_server: _FakeGitHub,
) -> None:
    from attest.github.client import STATUS_MARKER, GitHubClient

    first_page = "/repos/octo/widgets/issues/9/comments?per_page=100&page=1"
    second_page = "/repos/octo/widgets/issues/9/comments?per_page=100&page=2"
    github_server.reply(
        "GET",
        first_page,
        [{"id": 8, "body": STATUS_MARKER, "user": {"type": "User"}}],
        headers={"Link": f'<{github_server.url}{second_page}>; rel="next"'},
    )
    github_server.reply(
        "GET",
        second_page,
        [
            {"id": 17, "body": f"old\n{STATUS_MARKER}", "user": {"type": "Bot"}},
            {"id": 18, "body": STATUS_MARKER, "user": {"type": "Bot"}},
        ],
    )
    github_server.reply("PATCH", "/repos/octo/widgets/issues/comments/17", {"id": 17})

    GitHubClient("token", github_server.url).upsert_issue_comment(
        "octo/widgets", 9, STATUS_MARKER, "Review complete."
    )

    assert [request["path"] for request in github_server.requests] == [
        first_page,
        second_page,
        "/repos/octo/widgets/issues/comments/17",
    ]
    assert github_server.requests[-1]["body"] == {
        "body": "<!-- attest:status -->\nReview complete."
    }


def test_pagination_rejects_next_link_on_a_different_origin(
    github_server: _FakeGitHub,
) -> None:
    from attest.github.client import STATUS_MARKER, GitHubApiError, GitHubClient

    first_page = "/repos/octo/widgets/issues/9/comments?per_page=100&page=1"
    github_server.reply(
        "GET",
        first_page,
        [],
        headers={"Link": '<https://attacker.invalid/steal>; rel="next"'},
    )

    with pytest.raises(GitHubApiError, match="pagination origin"):
        GitHubClient("sensitive-token", github_server.url).upsert_issue_comment(
            "octo/widgets", 9, STATUS_MARKER, "Review complete."
        )

    assert len(github_server.requests) == 1


def test_create_review_posts_one_batched_review_payload(github_server: _FakeGitHub) -> None:
    from attest.github.client import GitHubClient

    github_server.reply("POST", "/repos/octo/widgets/pulls/9/reviews", {"id": 88})
    comments: list[dict[str, object]] = [
        {"path": "src/a.py", "line": 7, "side": "RIGHT", "body": "finding"}
    ]

    response = GitHubClient("token", github_server.url).create_review(
        "octo/widgets", 9, "head-sha", comments
    )

    assert response == {"id": 88}
    assert github_server.requests == [
        {
            "method": "POST",
            "path": "/repos/octo/widgets/pulls/9/reviews",
            "headers": github_server.requests[0]["headers"],
            "body": {
                "commit_id": "head-sha",
                "body": "Attest review.",
                "event": "COMMENT",
                "comments": comments,
            },
        }
    ]


def test_http_error_is_sanitized_and_never_discloses_token(github_server: _FakeGitHub) -> None:
    from attest.github.client import GitHubApiError, GitHubClient

    token = "sensitive-token-value"
    comments_path = "/repos/octo/widgets/issues/9/comments?per_page=100&page=1"
    github_server.reply("GET", comments_path, {"message": token}, status=500)

    with pytest.raises(GitHubApiError) as raised:
        GitHubClient(token, github_server.url).upsert_issue_comment(
            "octo/widgets", 9, "<!-- marker -->", "body"
        )

    assert str(raised.value) == "GitHub API request failed with HTTP 500"
    assert token not in str(raised.value)
