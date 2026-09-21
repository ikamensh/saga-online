"""A three-seat Warband room on a server fills in order, starts with every seat
present, sends each seat only its own units at home, and refuses a client that
declares no seats (one from before Saga2D 0.3.8) with an update message."""
import json
import sys
from contextlib import ExitStack

from websockets.sync.client import connect

from saga2d.testing.online import handshake, receive

GAME = "warband-v2"


def verify(url: str) -> str:
    with ExitStack() as stack:
        sockets = [stack.enter_context(connect(url, proxy=None, max_queue=None)) for _ in range(3)]
        welcome = handshake(sockets[0], game=GAME, seats=4, options={"seed": 7, "width": 64, "height": 48, "players": 3})
        seats = [welcome] + [handshake(socket, "join", game=GAME, room=welcome["room"], seats=4) for socket in sockets[1:]]
        assert [(seat["player"], seat["seats"]) for seat in seats] == [(0, 3), (1, 3), (2, 3)], seats
        ready = receive(sockets[0], predicate=lambda message: message["ready"])
        # Warband's world carries one player past the seats — the wilds, which own the neutral
        # creatures — and marks it, exactly as its own loader reads it back.  Count the seats.
        served = ready["state"]["world"]["players"]
        assert ready["present"] == 3 and len([p for p in served if not p.get("neutral")]) == 3, served
        assert {unit["player"] for unit in ready["state"]["world"]["units"]} == {0}, "a seat was sent another's units at home"
        with connect(url, proxy=None) as old:
            old.send(json.dumps({"type": "join", "protocol": 1, "game": GAME, "room": welcome["room"]}))
            refused = json.loads(old.recv(timeout=10))
            assert refused["type"] == "reject" and refused.get("reason") == "incompatible", refused
        return (f"three-seat room {welcome['room']} on {url}: filled in order, started with 3 of 3, "
                f"each seat sent its own; a client from before 0.3.8 refused: {refused['error']!r}")


if __name__ == "__main__":
    print(verify(sys.argv[1] if len(sys.argv) > 1 else "wss://games.tachyon-ai.eu/play"))
