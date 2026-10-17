"""Activity is public aggregate history; real SQLite preserves it across restarts."""
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from saga2d.testing.online import handshake, receive
from saga2d.server.storage import RoomStore
from websockets.sync.client import connect

from deploy.activity import ActivityHistory
from tests.test_attested_server import release, server


def get(endpoint, path):
    with urlopen(endpoint.replace("ws://", "http://") + path, timeout=5) as response:
        assert response.headers.get_content_type() == "application/json"
        assert response.headers["Cache-Control"] == "no-store"
        return json.load(response)


def test_ranked_leaderboard_keeps_losers_visible_among_unplayed_identities(release, tmp_path):
    """Filtering precedes ranking and pagination, so unplayed accounts cannot hide rated players."""
    root, _ = release
    state = tmp_path / "state"
    store = RoomStore(state)
    unplayed = {"name": "Unplayed", "rating": 1500.0, "games": 0, "wins": 0, "losses": 0}
    for index in range(110):
        store.save_profile("warband-v2", f"unplayed-{index}", unplayed)
    winner = {"name": "Raven", "rating": 1516.0, "games": 1, "wins": 1, "losses": 0}
    loser = {"name": "Wren", "rating": 1484.0, "games": 1, "wins": 0, "losses": 1}
    store.save_profile("warband-v2", "winner-id", winner)
    store.save_profile("warband-v2", "loser-id", loser)
    store.save_profile("tribes-v1", "other-game", winner)
    store.close()
    with server(root, state) as (endpoint, _):
        board = get(endpoint, "/leaderboard?game=warband-v2&limit=100&offset=0")
        assert board == {"game": "warband-v2", "players": [
            {"player_id": "winner-id", **winner}, {"player_id": "loser-id", **loser}],
            "total": 2, "offset": 0, "limit": 100}
        page = get(endpoint, "/leaderboard?game=warband-v2&limit=1&offset=1")
        assert page["players"] == [{"player_id": "loser-id", **loser}] and page["total"] == 2
        for query in ("WrEn", "loser-ID"):
            result = get(endpoint, f"/leaderboard?game=warband-v2&q={query}")
            assert result["players"] == [{"player_id": "loser-id", **loser}] and result["total"] == 1
        assert get(endpoint, "/leaderboard?game=warband-v2&q=unplayed")["total"] == 0


def test_ranked_search_covers_every_page_and_ties_keep_their_order(release, tmp_path):
    """A player below the first hundred remains searchable, with repeatable pagination for ties."""
    root, _ = release
    state = tmp_path / "state"
    store = RoomStore(state)
    for index in reversed(range(105)):
        profile = {"name": f"Player {index:03}", "rating": 1500.0, "games": 2, "wins": 1, "losses": 1}
        store.save_profile("warband-v2", f"player-{index:03}", profile)
    store.close()
    with server(root, state) as (endpoint, _):
        first = get(endpoint, "/leaderboard?game=warband-v2&limit=100")
        last = get(endpoint, "/leaderboard?game=warband-v2&limit=100&offset=100")
        assert first["total"] == last["total"] == 105
        assert [player["player_id"] for player in first["players"] + last["players"]] == [
            f"player-{index:03}" for index in range(105)]
        result = get(endpoint, "/leaderboard?game=warband-v2&q=104")
        assert result["total"] == 1 and result["players"][0]["player_id"] == "player-104"


def test_bad_leaderboard_queries_are_bounded_json_errors(release, tmp_path):
    """Malformed pagination and oversized searches cannot request an unbounded response."""
    root, _ = release
    with server(root, tmp_path / "state") as (endpoint, _):
        for suffix in ("limit=0", "limit=101", "limit=many", "offset=-1", "offset=100001", "offset=many", "q=" + "x" * 101):
            with pytest.raises(HTTPError) as failure:
                get(endpoint, "/leaderboard?game=warband-v2&" + suffix)
            assert failure.value.code == 400
            assert failure.value.headers["Cache-Control"] == "no-store"
            assert json.load(failure.value)["error"]
        with pytest.raises(HTTPError) as failure:
            get(endpoint, "/leaderboard?game=missing")
        assert failure.value.code == 404
        with pytest.raises(HTTPError) as failure:
            urlopen(Request(endpoint.replace("ws://", "http://") + "/leaderboard?game=warband-v2", method="POST"))
        assert failure.value.code == 405


def test_public_activity_counts_only_the_requested_game_and_survives_restart(release, tmp_path):
    """Real room connections update live counts without exposing a room or a player's secrets."""
    root, _ = release
    state = tmp_path / "state"
    with server(root, state) as (endpoint, process):
        before = get(endpoint, "/activity?game=warband-v2&hours=24")
        assert before["current"] == {"players": 0, "observers": 0, "rooms": 0, "ready_rooms": 0}
        assert before["samples"][0]["players"] == 0
        with connect(endpoint, proxy=None) as host, connect(endpoint, proxy=None) as guest:
            seat = handshake(host, game="warband-v2", player_name="ActivityPrivateName")
            handshake(guest, "join", game="warband-v2", room=seat["room"])
            receive(host, predicate=lambda message: message["ready"])
            current = get(endpoint, "/activity?game=warband-v2&hours=168")
            assert current["current"] == {"players": 2, "observers": 0, "rooms": 1, "ready_rooms": 1}
            assert get(endpoint, "/activity?game=tribes-v1")["current"]["players"] == 0
            blob = json.dumps(current)
            for secret in (seat["room"], seat["resume_token"], seat["player_token"], seat["player_id"], "ActivityPrivateName"):
                assert secret not in blob
        assert process.poll() is None
    with server(root, state) as (endpoint, _):
        after = get(endpoint, "/activity?game=warband-v2")
        assert after["collected_since"] == before["collected_since"]
        assert after["current"]["players"] == 0
        assert after["samples"][0] == before["samples"][0]


@pytest.mark.parametrize("path,status", [
    ("/activity?game=missing", 404),
    ("/activity?game=warband-v2&hours=1", 400),
    ("/activity?game=warband-v2&hours=week", 400),
])
def test_bad_activity_queries_are_clear_json_errors(release, tmp_path, path, status):
    """Clients see a useful failure, never a fabricated empty history for a malformed query."""
    root, _ = release
    with server(root, tmp_path / "state") as (endpoint, _):
        with pytest.raises(HTTPError) as failure:
            get(endpoint, path)
        assert failure.value.code == status
        assert failure.value.headers.get_content_type() == "application/json"
        assert failure.value.headers["Cache-Control"] == "no-store"
        assert json.load(failure.value)["error"]
        with pytest.raises(HTTPError) as failure:
            urlopen(Request(endpoint.replace("ws://", "http://") + "/activity?game=warband-v2", method="POST"))
        assert failure.value.code == 405


def test_reports_bound_the_time_window_and_retention(tmp_path):
    """A week includes observations a day excludes; thirty-day retention stays bounded."""
    start = 1_800_000_000
    counts = {"players": 1, "observers": 0, "rooms": 1, "ready_rooms": 0}
    history = ActivityHistory(tmp_path)
    assert history.report("warband-v2", 24, current=counts, now=start)["collected_since"] is None
    for day in (0, 29, 31):
        history.record({"warband-v2": counts}, now=start + day * 86400)
    now = start + 31 * 86400
    day = history.report("warband-v2", 24, current=counts, now=now)
    week = history.report("warband-v2", 168, current=counts, now=now)
    history.close()

    assert len(day["samples"]) == 1
    assert len(week["samples"]) == 2
    assert day["collected_since"] == week["samples"][0]["timestamp"]


def test_samples_survive_restart_without_filling_the_gap_or_inventing_prehistory(tmp_path):
    """A quiet minute is observed zero; an unobserved minute remains absent after restart."""
    start = 1_800_000_000
    quiet = {"players": 0, "observers": 0, "rooms": 0, "ready_rooms": 0}
    busy = {"players": 2, "observers": 1, "rooms": 1, "ready_rooms": 1}
    history = ActivityHistory(tmp_path)
    history.record({"warband-v2": quiet, "tribes-v1": busy}, now=start)
    history.record({"warband-v2": busy}, now=start + 60)
    history.close()

    history = ActivityHistory(tmp_path)
    history.record({"warband-v2": quiet}, now=start + 180)
    report = history.report("warband-v2", 24, current=quiet, now=start + 200)
    history.close()

    assert report["current"] == quiet
    assert report["sample_interval_seconds"] == 60
    assert report["retention_days"] == 30
    assert report["collected_since"] == "2027-01-15T08:00:00Z"
    assert report["server_time"] == "2027-01-15T08:03:20Z"
    assert report["samples"] == [
        {"timestamp": "2027-01-15T08:00:00Z", **quiet},
        {"timestamp": "2027-01-15T08:01:00Z", **busy},
        {"timestamp": "2027-01-15T08:03:00Z", **quiet},
    ]
