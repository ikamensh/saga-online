"""Create and join one room per game through a real server endpoint."""
import json
import sys
import urllib.parse
import urllib.request

from websockets.sync.client import connect


def receive(socket, kind, *, ready=None):
    for _ in range(100):
        message = json.loads(socket.recv(timeout=10))
        if message["type"] in ("error", "reject"):
            raise RuntimeError(message["error"])
        if message["type"] == kind and (ready is None or message["ready"] == ready):
            return message
    raise RuntimeError(f"Server did not send {kind}")


def smoke(endpoint):
    url = urllib.parse.urlsplit(endpoint)
    health = urllib.parse.urlunsplit(("https" if url.scheme == "wss" else "http", url.netloc, "/healthz", "", ""))
    with urllib.request.urlopen(health, timeout=10) as response:
        if response.status != 200 or response.read() != b"ok\n":
            raise RuntimeError("Server health response was unexpected")
    for game in ("tribes-v1", "warband-v1", "shardbound-v1"):
        with connect(endpoint, proxy=None) as host, connect(endpoint, proxy=None) as guest:
            host.send(json.dumps({"type": "create", "protocol": 1, "game": game, "options": {"seed": 7}}))
            room = receive(host, "welcome")
            receive(host, "state", ready=False)
            guest.send(json.dumps({"type": "join", "protocol": 1, "game": game, "room": room["room"]}))
            joined = receive(guest, "welcome")
            if joined["player"] != 1:
                raise RuntimeError("Guest did not receive the second seat")
            receive(host, "state", ready=True)
            receive(guest, "state", ready=True)
        print(f"{game}: create and join passed")


if __name__ == "__main__":
    smoke(sys.argv[1])
