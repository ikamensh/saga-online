"""The operator's verification tools still find every game's authoritative match, network scene, style and title."""

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from verify_multiplayer import definitions, scenes  # noqa: E402


@pytest.mark.parametrize("name, game_id", [pytest.param("tribes", "tribes-v1", marks=pytest.mark.demo),
                                           ("warband", "warband-v2"),
                                           pytest.param("eador", "shardbound-v1", marks=pytest.mark.demo)])
def test_every_game_resolves_to_a_match_factory_and_a_network_scene(name, game_id):
    """Warband once moved its match to warband.authority and the tool kept importing the old name;
    the public journeys then failed in the tool before touching the server."""
    factory, scene, protocol = definitions(name)
    assert protocol == game_id
    match = factory()
    assert callable(match.apply) and callable(match.snapshot)
    assert isinstance(scene, type)


@pytest.mark.parametrize("name", [pytest.param("tribes", marks=pytest.mark.demo), "warband",
                                  pytest.param("eador", marks=pytest.mark.demo)])
def test_every_game_offers_the_style_and_title_screen_the_journeys_open(name):
    """Warband moved its scenes into warband.ui and the journeys kept building warband.style: the public journey
    failed in the tool before its first frame."""
    assert callable(importlib.import_module(scenes(name) + '.style').build_theme)
    title = importlib.import_module(scenes(name) + ('.scene' if name == 'eador' else '.title')).TitleScene
    assert isinstance(title, type)
