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
    github_server.reply("PATCH", "/repos/octo/widgets/issues/comments/18", {"id": 18})

    GitHubClient("token", github_server.url).upsert_issue_comment(
        "octo/widgets", 9, STATUS_MARKER, "Review complete."
    )

    assert [request["path"] for request in github_server.requests] == [
        first_page,
        second_page,
        "/repos/octo/widgets/issues/comments/18",
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


# --- D-227: the author's `intended` / `unintended` reply under a yellow line --


def _value_parent(comment_id: int = 501) -> dict[str, object]:
    return {
        "id": comment_id,
        "user": {"type": "Bot", "login": "attest[bot]"},
        "path": "pkg/money.py",
        "line": 41,
        "body": (
            "<!-- attest:value:0123456789ab -->\n"
            "[yellow] pkg/money.py:41 — for money.rate('EUR'), the merge base returned "
            "Decimal('1.05') and head returns Decimal('1.10') (3/3 and 3/3 runs each side); "
            "no base test, docstring or changelog pins either — note 0123456789ab\n\n"
            "<details><summary>The two observations</summary>\n\n"
            "Expression: `money.rate('EUR')`\n\n</details>\n\n"
            "Action: if the new value is intended, add a test that pins it at "
            "`pkg/money.py:41`; otherwise restore what the merge base returned there. "
            "Reply `intended` or `unintended` to record it."
        ),
    }


def _reply(comment_id: int, parent: int, body: str, *, bot: bool = False) -> dict[str, object]:
    return {
        "id": comment_id,
        "in_reply_to_id": parent,
        "user": {"type": "Bot" if bot else "User", "login": "octocat"},
        "body": body,
        "created_at": "2026-09-12T08:00:00Z",
    }


def test_thread_replies_returns_the_authors_word_under_the_products_own_line(
    github_server: _FakeGitHub,
) -> None:
    """RED, owner authorisation 3 of 2026-09-12: a reply is recorded only when
    its parent is one of this product's marker-bearing comments, its whole
    body is one of the two words, and a person wrote it. Everything else in
    the thread -- a bot's reply, a sentence, a reply to somebody else's
    comment -- is not a reply the ledger may carry."""
    from attest.github.client import GitHubClient

    listing = "/repos/octo/widgets/pulls/9/comments?per_page=100&page=1"
    github_server.reply(
        "GET",
        listing,
        [
            _value_parent(501),
            _reply(601, 501, "  Intended \n"),
            _reply(602, 501, "I think this is intended", ),
            _reply(603, 501, "unintended", bot=True),
            {"id": 700, "user": {"type": "User", "login": "someone"}, "body": "plain review",
             "path": "pkg/money.py", "line": 3},
            _reply(701, 700, "intended"),
            _reply(702, 999, "unintended"),
        ],
    )

    replies = GitHubClient("secret-token", github_server.url).thread_replies("octo/widgets", 9)

    assert len(replies) == 1
    reply = replies[0]
    assert reply["note_kind"] == "value" and reply["note_id"] == "0123456789ab"
    assert reply["reply"] == "intended"
    assert reply["author"] == "octocat" and reply["ts"] == "2026-09-12T08:00:00Z"
    assert reply["path"] == "pkg/money.py" and reply["line"] == 41
    assert "Expression: `money.rate('EUR')`" in str(reply["parent_body"])
    assert reply["reply_id"] == 601
    assert github_server.requests[-1]["method"] == "GET"


def test_thread_replies_fails_open_on_an_api_error(github_server: _FakeGitHub) -> None:
    """Audit, not publication: a listing that cannot be read records nothing
    and never fails the review it runs inside."""
    from attest.github.client import GitHubClient

    listing = "/repos/octo/widgets/pulls/9/comments?per_page=100&page=1"
    github_server.reply("GET", listing, {"message": "boom"}, status=500)

    assert GitHubClient("secret-token", github_server.url).thread_replies("octo/widgets", 9) == []
