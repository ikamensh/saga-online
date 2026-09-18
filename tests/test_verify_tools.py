"""The operator's verification tools still find every game's authoritative match and network scene."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from verify_multiplayer import definitions  # noqa: E402


@pytest.mark.parametrize("name, game_id", [("tribes", "tribes-v1"), ("warband", "warband-v2"), ("eador", "shardbound-v1")])
def test_every_game_resolves_to_a_match_factory_and_a_network_scene(name, game_id):
    """Warband once moved its match to warband.authority and the tool kept importing the old name;
    the public journeys then failed in the tool before touching the server."""
    factory, scene, protocol = definitions(name)
    assert protocol == game_id
    match = factory()
    assert callable(match.apply) and callable(match.snapshot)
    assert isinstance(scene, type)
