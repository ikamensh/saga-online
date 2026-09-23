"""Create, join and issue a real order in every game; retain private receipts for restart checks."""
import json
import sys
import urllib.parse
import urllib.request

from websockets.sync.client import connect


def receive(socket, kind, *, ready=None, predicate=lambda message: True):
    for _ in range(100):
        message = json.loads(socket.recv(timeout=10))
        if message["type"] in ("error", "reject"):
            raise RuntimeError(message["error"])
        if message["type"] == kind and (ready is None or message["ready"] == ready) and predicate(message):
            return message
    raise RuntimeError(f"Server did not send {kind}")


def smoke(endpoint, games=("tribes-v1", "warband-v2", "shardbound-v1")):
    url = urllib.parse.urlsplit(endpoint)
    health = urllib.parse.urlunsplit(("https" if url.scheme == "wss" else "http", url.netloc, "/healthz", "", ""))
    with urllib.request.urlopen(health, timeout=10) as response:
        if response.status != 200 or response.read() != b"ok\n":
            raise RuntimeError("Server health response was unexpected")
    records = []
    for game in games:
        with connect(endpoint, proxy=None) as host, connect(endpoint, proxy=None) as guest:
            host.send(json.dumps({"type": "create", "protocol": 1, "game": game, "options": {"seed": 7}}))
            room = receive(host, "welcome")
            receive(host, "state", ready=False)
            guest.send(json.dumps({"type": "join", "protocol": 1, "game": game, "room": room["room"]}))
            joined = receive(guest, "welcome")
            if joined["player"] != 1:
                raise RuntimeError("Guest did not receive the second seat")
            before = receive(host, "state", ready=True)["state"]
            receive(guest, "state", ready=True)
            if game == "tribes-v1":
                order = {"action": "end_turn"}
                accepted = lambda message: message["state"]["world"]["current"] == 1
            elif game == "warband-v2":
                order = {"action": "set_assembly", "args": [0, [12, 12]]}
                accepted = lambda message: message["state"]["world"]["players"][0]["assembly"] == [12, 12]
            else:
                turn = json.loads(before["campaign"])["turn"]
                order = {"action": "end_turn", "target": "state", "args": []}
                accepted = lambda message: json.loads(message["state"]["campaign"])["turn"] > turn
            host.send(json.dumps({"type": "command", "command": order}))
            receive(host, "state", predicate=accepted)
            guest.close()
            paused = receive(host, "state", ready=False)["state"]
            records.append({"game": game, "room": room["room"], "seats": [room, joined], "state": paused})
    return records


def resume(endpoint, records):
    """Private seat credentials restore the exact paused state after a process restart."""
    for record in records:
        with connect(endpoint, proxy=None) as host, connect(endpoint, proxy=None) as guest:
            for socket, seat in zip((host, guest), record["seats"]):
                socket.send(json.dumps({"type": "resume", "protocol": 1, "game": record["game"],
                                       "room": record["room"], "resume_token": seat["resume_token"]}))
                if receive(socket, "welcome")["player"] != seat["player"]:
                    raise RuntimeError("A resumed seat changed player")
                if socket is host and receive(host, "state", ready=False)["state"] != record["state"]:
                    raise RuntimeError(f"Restored state differs for {record['game']}")
            receive(guest, "state", ready=True)


if __name__ == "__main__":
    for record in smoke(sys.argv[1]):
        print(f"{record['game']}: create, join and order passed")
