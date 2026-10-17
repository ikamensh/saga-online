"""Run the packaged Saga server with compatibility attestation from its own process."""
from __future__ import annotations

import argparse
import asyncio
from http import HTTPStatus
import json
import logging
from pathlib import Path
import signal
import sys
from urllib.parse import parse_qs, urlsplit

# Package source is immutable at runtime. Do not introduce unrecorded bytecode
# into it; the installer and verifier invoke this launcher with -B as well.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime import REGISTRIES, attestation
from activity import ActivityHistory, SAMPLE_INTERVAL_SECONDS, current_counts


async def serve(args, baseline):
    from saga2d.server import MAX_MESSAGE, RoomServer, load_games
    from websockets.asyncio.server import serve as websocket_server

    rooms = RoomServer(load_games(REGISTRIES), state_dir=args.state_dir, room_ttl=args.room_ttl,
                       campaign_ttl=args.campaign_ttl, max_rooms=args.max_rooms,
                       max_connections=args.max_connections, trusted_proxy=args.trusted_proxy)
    history = ActivityHistory(args.state_dir)
    payload = json.dumps(baseline, sort_keys=True, indent=2) + "\n"

    def reply(connection, status, value):
        response = rooms.json_reply(connection, status, value)
        response.headers["Cache-Control"] = "no-store"
        return response

    def http(connection, request):
        url = urlsplit(request.path)
        if url.path in ("/activity", "/leaderboard"):
            if request.method != "GET":
                return reply(connection, HTTPStatus.METHOD_NOT_ALLOWED, {"error": "Use GET for public statistics."})
            fields = parse_qs(url.query, keep_blank_values=True)
            game = fields.get("game", [""])[0]
            if game not in rooms.games:
                return reply(connection, HTTPStatus.NOT_FOUND, {"error": "Unknown game."})
            if url.path == "/activity":
                hours = fields.get("hours", ["24"])[0]
                if hours not in ("24", "168"):
                    return reply(connection, HTTPStatus.BAD_REQUEST, {"error": "hours must be 24 or 168."})
                current = current_counts(rooms.rooms.values(), rooms.games)[game]
                return reply(connection, HTTPStatus.OK, history.report(game, int(hours), current=current))
            query = fields.get("q", [""])[0]
            try:
                limit = int(fields.get("limit", ["100"])[0])
                offset = int(fields.get("offset", ["0"])[0])
            except ValueError:
                return reply(connection, HTTPStatus.BAD_REQUEST, {"error": "limit and offset must be integers."})
            if not 1 <= limit <= 100 or not 0 <= offset <= 100000 or len(query) > 100:
                return reply(connection, HTTPStatus.BAD_REQUEST,
                             {"error": "limit must be 1 to 100, offset 0 to 100000, and q at most 100 characters."})
            query = query.casefold()
            players = [rooms.public_profile(game, player_id)
                       for (played, player_id), profile in rooms.profiles.items()
                       if played == game and profile["games"] > 0
                       and (query in profile["name"].casefold() or query in player_id.casefold())]
            players.sort(key=lambda profile: (-profile["rating"], profile["player_id"]))
            return reply(connection, HTTPStatus.OK,
                         {"game": game, "players": players[offset:offset + limit],
                          "total": len(players), "offset": offset, "limit": limit})
        if url.path == "/server-compatibility.json":
            response = connection.respond(HTTPStatus.OK, payload)
            del response.headers["Content-Type"]
            response.headers["Content-Type"] = "application/json"
            response.headers["Cache-Control"] = "no-store"
            return response
        return rooms.health(connection, request)

    async def collect_activity():
        while True:
            await asyncio.sleep(SAMPLE_INTERVAL_SECONDS)
            history.record(current_counts(rooms.rooms.values(), rooms.games))

    task = asyncio.current_task()
    if sys.platform != "win32":
        for signum in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_running_loop().add_signal_handler(signum, task.cancel)
    try:
        history.record(current_counts(rooms.rooms.values(), rooms.games))
        async with websocket_server(rooms.handle, args.host, args.port, process_request=http, origins=[None],
                                    max_size=MAX_MESSAGE, max_queue=8, ping_interval=10, ping_timeout=10,
                                    close_timeout=2, open_timeout=10, server_header=None, backlog=64) as server:
            address = server.sockets[0].getsockname()
            print(f"LISTENING ws://{address[0]}:{address[1]}", flush=True)
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(collect_activity())
                await rooms.maintain()
    finally:
        history.close()
        if rooms.store is not None:
            for room in rooms.rooms.values():
                rooms.checkpoint(room, force=True)
            rooms.store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--room-ttl", type=float, default=900)
    parser.add_argument("--campaign-ttl", type=float, default=7 * 86400)
    parser.add_argument("--max-rooms", type=int, default=32)
    parser.add_argument("--max-connections", type=int, default=96)
    parser.add_argument("--trusted-proxy", action="store_true")
    args = parser.parse_args()
    baseline = attestation(ROOT, args.release_id, args.endpoint)
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(serve(args, baseline))
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
