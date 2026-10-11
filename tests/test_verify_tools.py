"""The operator's verification tools still find every game's authoritative match, network scene, style and title."""

import importlib
import math
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


def test_remote_ai_verifier_resolves_the_moved_warband_ui():
    """The verifier once imported warband.style/textures/title; the UI moved them
    under warband.ui and warband.art, and the menu gained MatchSetupMenu."""
    from verify_warband_remote_ai import claim_scout_target, scout_destination

    assert callable(scout_destination)
    assert callable(claim_scout_target)
    multiplayer = importlib.import_module('warband.ui.multiplayer')
    assert multiplayer.GAME_ID == 'warband-v2'
    assert issubclass(multiplayer.MatchSetupMenu, importlib.import_module('saga2d').MatchMenu)
    assert isinstance(multiplayer.NetworkGameScene, type)
    for helper in ('online_identity', 'refresh_online_identity', 'stored_online_profile'):
        assert callable(getattr(multiplayer, helper)), helper
    for method in ('host', 'join', 'rejoin', 'paste_code', 'room_code_from_text'):
        assert callable(getattr(multiplayer.MatchSetupMenu, method)), method
    # The rejoin journey leaves through the live match menu, not a guessed title button.
    assert 'open_menu' in multiplayer.NetworkGameScene.__dict__
    assert callable(getattr(multiplayer.NetworkMenuScene, 'leave_match'))
    assert callable(importlib.import_module('warband.ui.style').build_theme)
    assert isinstance(importlib.import_module('warband.art.textures').TILE, int)
    assert isinstance(importlib.import_module('warband.ui.title').TitleScene, type)


def test_scout_fallback_ignores_the_live_rival_hall():
    """With no remembered sightings the scout heads for map geometry away from
    its own base — even though the live rival hall sits elsewhere in the world."""
    from verify_warband_remote_ai import scout_destination

    world = importlib.import_module('warband.sim.mapgen').generate(1)
    rules = importlib.import_module('warband.sim.rules')
    model = importlib.import_module('warband.sim.model')
    own = world.player_buildings(0, rules.BuildingType.TOWN_HALL, done=True)[0]
    rival = world.player_buildings(1, rules.BuildingType.TOWN_HALL, done=True)[0]
    target, basis = scout_destination(world, own.center, 0, 1, [])
    assert basis == 'geometry'
    corners = [(2, 2), (world.width - 3, 2), (2, world.height - 3),
               (world.width - 3, world.height - 3)]
    far = model.tile_center(max(corners, key=lambda c: math.dist(model.tile_center(c), own.center)))
    assert math.dist(target, far) <= 4.5
    assert math.dist(target, rival.center) > 4


def test_scout_prefers_a_remembered_rival_sighting():
    """A sighting the seat itself remembers steers the scout; live hidden
    positions still play no part."""
    from verify_warband_remote_ai import scout_destination

    world = importlib.import_module('warband.sim.mapgen').generate(1)
    rules = importlib.import_module('warband.sim.rules')
    own = world.player_buildings(0, rules.BuildingType.TOWN_HALL, done=True)[0]
    rival = world.player_buildings(1, rules.BuildingType.TOWN_HALL, done=True)[0]
    remembered = [{'player': 1, 'rect': [rival.x, rival.y, rival.size, rival.size]}]
    target, basis = scout_destination(world, own.center, 0, 1, remembered)
    assert basis == 'remembered'
    assert math.dist(target, rival.center) <= 4.5


def test_scout_reads_a_real_sighting_row():
    """The remembered rows are MapView.memory() Sighting dicts; one such row
    steers the scout even though the live hall is never consulted."""
    from verify_warband_remote_ai import scout_destination

    world = importlib.import_module('warband.sim.mapgen').generate(1)
    rules = importlib.import_module('warband.sim.rules')
    sighting = importlib.import_module('warband.ui.view').Sighting
    own = world.player_buildings(0, rules.BuildingType.TOWN_HALL, done=True)[0]
    rival = world.player_buildings(1, rules.BuildingType.TOWN_HALL, done=True)[0]
    target, basis = scout_destination(world, own.center, 0, 1, [sighting.of(rival).to_dict()])
    assert basis == 'remembered'
    assert math.dist(target, rival.center) <= 4.5


def test_scout_refuses_to_repeat_an_ordered_destination():
    """A leg that ends where an earlier order already went fails loudly
    instead of reissuing the same failed order forever."""
    from verify_warband_remote_ai import claim_scout_target

    ordered = set()
    claim_scout_target(ordered, (10.5, 20.5))
    with pytest.raises(AssertionError):
        claim_scout_target(ordered, (10.5, 20.5))
    claim_scout_target(ordered, (30.5, 5.5))
