"""Bounded load check of the online service with real clients across several rooms.

    uv run python tools/load_online.py --game warband --rooms 4 --seconds 60

Every room gets two OnlineClients that keep issuing valid orders. The report
records time to a ready room, state cadence per client (Warband publishes
every second simulation tick), the simulation rate against wall time and
health-endpoint latency sampled during the load. The server allows four new
rooms per minute per address, so larger runs pace their creation. Rooms are
left to expire under the server's retention.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.request
from urllib.parse import urlsplit, urlunsplit

from saga2d.online import OnlineClient

OPTIONS = {"warband": {"width": 40, "height": 32}, "tribes": {"size": 11}, "shardbound": {"campaign": True}}
GAME_IDS = {"warband": "warband-v1", "tribes": "tribes-v1", "shardbound": "shardbound-v1"}


class Seat:
    def __init__(self, client, game):
        self.client, self.game = client, game
        self.gaps, self.last_state, self.last_revision = [], None, None
        self.orders, self.errors = 0, []
        self.next_order = time.monotonic() + 1

    def poll(self):
        self.client.poll()
        if self.client.error:
            self.errors.append(self.client.error)
            self.client.error = ""
        if self.client.revision != self.last_revision:
            now = time.monotonic()
            if self.last_state is not None:
                self.gaps.append(now - self.last_state)
            self.last_state, self.last_revision = now, self.client.revision

    def order(self):
        """One valid order per second so the server does rules work, not only broadcasting."""
        if not self.client.ready or time.monotonic() < self.next_order:
            return
        self.next_order = time.monotonic() + 1
        state, player = self.client.state, self.client.player
        if self.game == "warband":
            units = [u for u in state["world"]["units"] if u["player"] == player]
            if units:
                unit = units[self.orders % len(units)]
                dx, dy = ((1, 0), (0, 1), (-1, 0), (0, -1))[self.orders % 4]
                self.client.submit({"action": "move", "args": [[unit["id"]], [unit["x"] + dx, unit["y"] + dy]]})
        elif self.game == "tribes":
            if state["world"]["current"] == player:
                self.client.submit({"action": "end_turn"})
        elif player == 0:
            from eador.model import State
            in_battle = State.from_json(state["campaign"]).battle is not None
            self.client.submit({"action": "resolve_battle" if in_battle else "end_turn", "target": "state", "args": []})
        self.orders += 1


def health_latency(endpoint):
    parsed = urlsplit(endpoint)
    url = urlunsplit(("https" if parsed.scheme == "wss" else "http", parsed.netloc, "/healthz", "", ""))
    started = time.monotonic()
    with urllib.request.urlopen(url, timeout=10) as response:
        assert response.read() == b"ok\n"
    return time.monotonic() - started


def run(endpoint, game, rooms, seconds):
    seats, report = [], {"endpoint": endpoint, "game": game, "rooms": [], "health_ms": []}
    started = time.monotonic()
    for index in range(rooms):
        if index and index % 4 == 0:
            time.sleep(61)  # Per-address creation limit: four new rooms per minute.
        opened = time.monotonic()
        creator = OnlineClient(GAME_IDS[game], endpoint=endpoint, options={"seed": 100 + index, **OPTIONS[game]})
        while creator.state is None and not creator.closed:
            creator.poll()
            time.sleep(.02)
        if creator.closed:
            raise RuntimeError(f"Room {index} was not created: {creator.error}")
        guest = OnlineClient(GAME_IDS[game], endpoint=endpoint, room=creator.room)
        while not (creator.ready and guest.ready):
            creator.poll()
            guest.poll()
            if creator.closed or guest.closed:
                raise RuntimeError(f"Room {index} did not become ready: {creator.error} {guest.error}")
            time.sleep(.02)
        report["rooms"].append({"code": creator.room, "ready_seconds": round(time.monotonic() - opened, 3)})
        seats.extend([Seat(creator, game), Seat(guest, game)])
    load_started = time.monotonic()
    first_tick = {seat: seat.client.state["world"].get("tick") for seat in seats} if game == "warband" else {}
    next_health = load_started
    try:
        while time.monotonic() - load_started < seconds:
            for seat in seats:
                seat.poll()
                seat.order()
            if time.monotonic() >= next_health:
                report["health_ms"].append(round(health_latency(endpoint) * 1000, 1))
                next_health += 10
            time.sleep(.01)
        elapsed = time.monotonic() - load_started
        gaps = [gap for seat in seats for gap in seat.gaps]
        report.update({
            "seats": len(seats), "load_seconds": round(elapsed, 1),
            "orders_sent": sum(seat.orders for seat in seats),
            "order_errors": sum(len(seat.errors) for seat in seats),
            "error_examples": sorted({error for seat in seats for error in seat.errors})[:5],
            "state_updates": len(gaps),
            "state_gap_ms": {"p50": round(statistics.median(gaps) * 1000, 1), "p95": round(statistics.quantiles(gaps, n=20)[18] * 1000, 1),
                             "max": round(max(gaps) * 1000, 1)} if len(gaps) >= 20 else None,
            "disconnects": sum(1 for seat in seats if seat.client.closed),
            "total_seconds": round(time.monotonic() - started, 1),
        })
        if game == "warband":
            rates = [(seat.client.state["world"]["tick"] - first_tick[seat]) / elapsed for seat in seats if seat.client.state]
            report["simulation_ticks_per_second"] = {"min": round(min(rates), 2), "max": round(max(rates), 2), "expected": 20}
    finally:
        for seat in seats:
            seat.client.close()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="wss://games.tachyon-ai.eu/play")
    parser.add_argument("--game", choices=sorted(GAME_IDS), default="warband")
    parser.add_argument("--rooms", type=int, default=4)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run(args.endpoint, args.game, args.rooms, args.seconds)
    text = json.dumps(result, indent=2)
    print(text)
    if args.output:
        with open(args.output, "w") as stream:
            stream.write(text + "\n")
