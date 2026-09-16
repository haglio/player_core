"""The corpus harvester, run against an invented forum.

Every topic, title, upload key and file name here is made up.
"""
from __future__ import annotations

import email.message
import io
import json
import logging
import urllib.error

from tools import harvest_eroscripts as harvest


class TestFindingTheScriptsInAPost:
    def test_only_main_axis_funscripts_are_taken(self):
        cooked = (
            '<p>Enjoy.</p>'
            '<a class="attachment" href="/uploads/short-url/aaaaaaaaaaaaaaaaaaaaaaaaaaa.funscript">'
            'scene one.funscript</a> (12.3 KB)'
            '<a class="attachment" href="/uploads/short-url/bbbbbbbbbbbbbbbbbbbbbbbbbbb.funscript">'
            'scene one.roll.funscript</a> (4 KB)'
            '<a class="attachment" href="/uploads/short-url/ccccccccccccccccccccccccccc.funscript">'
            'scene one.pitch.funscript</a> (4 KB)'
            '<a class="attachment" href="/uploads/short-url/ddddddddddddddddddddddddddd.zip">'
            'scene one.zip</a> (400 KB)'
            '<a class="attachment" href="/uploads/short-url/eeeeeeeeeeeeeeeeeeeeeeeeeee.funscript">'
            'scene two &amp; three.funscript</a> (20 KB)'
        )

        found = harvest.attachments_in(cooked)

        assert found == [
            harvest.Attachment("/uploads/short-url/aaaaaaaaaaaaaaaaaaaaaaaaaaa.funscript",
                               "scene one.funscript"),
            harvest.Attachment("/uploads/short-url/eeeeeeeeeeeeeeeeeeeeeeeeeee.funscript",
                               "scene two & three.funscript"),
        ]


class _FakeResponse:
    def __init__(self, body: bytes, headers: dict | None = None):
        self._body = body
        self.headers = headers or {}
        self.status = 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


class _FakeClock:
    """Time that only moves when something sleeps."""

    def __init__(self):
        self.now = 1000.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class TestPacingTheForum:
    def test_requests_are_spaced_by_the_pace(self):
        clock = _FakeClock()
        asked: list[str] = []

        def opener(request, timeout):
            asked.append(request.full_url)
            return _FakeResponse(b'{"ok": 1}')

        forum = harvest.Forum("https://forum.invalid", {}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=2.5)

        forum.get_json("/a.json")
        forum.get_json("/b.json")

        assert asked == ["https://forum.invalid/a.json", "https://forum.invalid/b.json"]
        assert clock.slept == [2.5]

    def test_a_limit_the_forum_names_is_waited_out_then_retried(self):
        clock = _FakeClock()
        calls = 0

        def opener(request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise _too_many_requests(request.full_url, retry_after="7")
            return _FakeResponse(b'{"ok": 1}')

        forum = harvest.Forum("https://forum.invalid", {}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0)

        assert forum.get_json("/a.json") == {"ok": 1}
        assert calls == 2
        assert clock.slept == [7.0 + harvest.RETRY_GRACE_S]


def _too_many_requests(url: str, *, retry_after: str):
    headers = email.message.Message()
    headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(url, 429, "Too Many Requests", headers, io.BytesIO(b"{}"))


def _redirect(url: str, *, to: str):
    headers = email.message.Message()
    headers["Location"] = to
    return urllib.error.HTTPError(url, 302, "Found", headers, io.BytesIO(b""))


class TestDownloadingAScript:
    def test_the_file_is_fetched_from_where_the_forum_points_without_the_key(self):
        # The forum resolves its short link to a static host; the key is the
        # forum's business and goes nowhere else.
        clock = _FakeClock()
        seen: list[tuple[str, str | None]] = []

        def opener(request, timeout):
            seen.append((request.full_url, request.get_header("User-api-key")))
            if "/uploads/short-url/" in request.full_url:
                raise _redirect(request.full_url,
                                to="https://files.invalid/original/1/2/abc123.funscript")
            return _FakeResponse(b'{"actions": []}')

        forum = harvest.Forum("https://forum.invalid", {"User-Api-Key": "k"}, opener=opener,
                              sleep=clock.sleep, clock=lambda: clock.now, pace_s=1.0)

        body, where = forum.download("/uploads/short-url/aaa.funscript")

        assert body == b'{"actions": []}'
        assert where == "https://files.invalid/original/1/2/abc123.funscript"
        assert seen == [
            ("https://forum.invalid/uploads/short-url/aaa.funscript", "k"),
            ("https://files.invalid/original/1/2/abc123.funscript", None),
        ]
        # The pace is the forum's; a file server is not asked to wait for it.
        assert clock.slept == []


class _FakeForum:
    def __init__(self, pages: dict, topics: dict, files: dict):
        self.pages = pages
        self.topics = topics
        self.files = files
        self.asked: list[str] = []

    def get_json(self, path: str) -> dict:
        self.asked.append(path)
        if path in self.pages:
            return self.pages[path]
        topic_id = int(path.removeprefix("/t/").removesuffix(".json"))
        if topic_id not in self.topics:
            raise urllib.error.HTTPError(path, 404, "Not Found", email.message.Message(),
                                         io.BytesIO(b""))
        return self.topics[topic_id]

    def download(self, short_url: str) -> tuple[bytes, str]:
        self.asked.append(short_url)
        return self.files[short_url]


def _anchor(key: str, name: str) -> str:
    return f'<a class="attachment" href="/uploads/short-url/{key}.funscript">{name}</a>'


def _topic(topic_id: int, cooked: str) -> dict:
    return {
        "id": topic_id, "title": f"scene {topic_id}", "tags": ["alpha", "beta"],
        "created_at": "2026-01-02T03:04:05.000Z",
        "post_stream": {"posts": [{"post_number": 1, "cooked": cooked}]},
    }


class TestWalkingTheCategory:
    def test_every_new_topics_scripts_are_saved_once_under_neutral_names(self, tmp_path):
        forum = _FakeForum(
            pages={
                "/c/scripts/free-scripts/14.json?page=0": {"topic_list": {
                    "topics": [{"id": 101}, {"id": 102}],
                    "more_topics_url": "/c/scripts/free-scripts/14?page=1"}},
                "/c/scripts/free-scripts/14.json?page=1": {"topic_list": {
                    "topics": [{"id": 103}, {"id": 104}]}},
            },
            topics={
                101: _topic(101, _anchor("aaa", "scene one.funscript")
                            + _anchor("bbb", "scene one.roll.funscript")),
                103: _topic(103, _anchor("aaa", "scene one again.funscript")
                            + _anchor("ccc", "scene three.funscript")),
            },
            files={
                "/uploads/short-url/aaa.funscript": (b'{"actions": [1]}', "https://files.invalid/a"),
                "/uploads/short-url/ccc.funscript": (b'{"actions": [3]}', "https://files.invalid/c"),
            },
        )
        store = harvest.Store(tmp_path)
        store.finish(102)

        taken = harvest.harvest(forum, store, log=logging.getLogger("test"))

        assert taken == 3
        assert "/t/102.json" not in forum.asked
        assert forum.asked.count("/uploads/short-url/aaa.funscript") == 1
        assert sorted(p.name for p in (tmp_path / "scripts").iterdir()) == [
            "t101_p1_1.funscript", "t103_p1_2.funscript"]
        assert (tmp_path / "scripts" / "t103_p1_2.funscript").read_bytes() == b'{"actions": [3]}'
        records = [json.loads(line) for line in
                   (tmp_path / "index.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [r["file"] for r in records] == ["t101_p1_1.funscript", "t103_p1_2.funscript"]
        assert records[1] == {
            "file": "t103_p1_2.funscript", "topic": 103, "post": 1,
            "url": "/uploads/short-url/ccc.funscript", "where": "https://files.invalid/c",
            "name": "scene three.funscript", "title": "scene 103", "tags": ["alpha", "beta"],
            "created_at": "2026-01-02T03:04:05.000Z", "bytes": 16,
        }
        assert (tmp_path / "done_topics.txt").read_text().split() == ["102", "101", "103", "104"]

    def test_a_second_run_picks_up_where_the_first_stopped(self, tmp_path):
        forum = _FakeForum(
            pages={"/c/scripts/free-scripts/14.json?page=0": {"topic_list": {
                "topics": [{"id": 101}, {"id": 103}]}}},
            topics={101: _topic(101, _anchor("aaa", "scene one.funscript")),
                    103: _topic(103, _anchor("ccc", "scene three.funscript"))},
            files={"/uploads/short-url/aaa.funscript": (b"{}", "https://files.invalid/a"),
                   "/uploads/short-url/ccc.funscript": (b"{}", "https://files.invalid/c")},
        )
        harvest.harvest(forum, harvest.Store(tmp_path), log=logging.getLogger("test"),
                        max_topics=1)
        forum.asked.clear()

        taken = harvest.harvest(forum, harvest.Store(tmp_path), log=logging.getLogger("test"))

        assert taken == 1
        assert "/t/101.json" not in forum.asked
        assert sorted(p.name for p in (tmp_path / "scripts").iterdir()) == [
            "t101_p1_1.funscript", "t103_p1_1.funscript"]
