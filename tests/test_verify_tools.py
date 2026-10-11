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


def test_move_choices_cover_an_off_diagonal_worker():
    """Seat 1 starts near x~45/y~31, where the old y-bounded x range searched
    nothing: a real worker there must get reachable destinations."""
    from verify_warband_remote_ai import move_choices

    world = importlib.import_module('warband.sim.mapgen').generate(1)
    workers = [u for u in world.player_units(1) if u.is_worker and not u.hidden]
    worker = next(u for u in workers if u.tile[0] != u.tile[1])
    choices = move_choices(world, worker)
    assert choices, f'No destinations around tile {worker.tile}'
    for point in choices:
        assert world.passable(int(point[0]), int(point[1]))
        assert world.entity_at(point) is None
        assert 1.5 <= math.dist(worker.pos, point) <= 3
    own_hall = world.player_buildings(1, importlib.import_module('warband.sim.rules').BuildingType.TOWN_HALL,
                                      done=True)[0]
    destination = min(choices, key=lambda p: math.dist(p, own_hall.center))
    assert math.dist(worker.pos, destination) <= 3


def test_hidden_worker_is_not_eligible_for_scout():
    """A worker ordered into a gold mine walks out of sight: the driven world
    marks it hidden, and scout choice passes over it for a worker in the open."""
    import math

    from verify_warband_remote_ai import choose_scout

    authority = importlib.import_module('warband.online.authority')
    match = authority.WarbandMatch(1)
    world = match.world
    worker = next(u for u in world.player_units(0) if u.is_worker and not u.hidden)
    mine = min((b for b in world.buildings.values() if b.info.mine is not None),
               key=lambda b: math.dist(worker.pos, b.center))
    match.apply(0, {'action': 'smart', 'args': [[worker.id], list(mine.center)],
                    'kwargs': {'target_id': mine.id}})
    for _ in range(4000):
        match.step()
        if world.units[worker.id].hidden:
            break
    assert world.units[worker.id].hidden, 'The driven worker never entered the mine'
    assert choose_scout(list(world.player_units(0)), []).id != worker.id


def test_trained_peasant_is_the_stable_scout_choice():
    """Training through the authority completes into a peasant standing in the
    open: scout choice prefers that id and it stays visible."""
    from verify_warband_remote_ai import choose_scout

    authority = importlib.import_module('warband.online.authority')
    rules = importlib.import_module('warband.sim.rules')
    match = authority.WarbandMatch(1)
    world = match.world
    before = {u.id for u in world.player_units(0)}
    hall = world.player_buildings(0, rules.BuildingType.TOWN_HALL, done=True)[0]
    match.apply(0, {'action': 'train', 'args': [hall.id, rules.UnitType.PEASANT], 'kwargs': {}})
    trained = None
    for _ in range(8000):
        match.step()
        fresh = [u for u in world.player_units(0) if u.id not in before]
        if fresh:
            trained = fresh[0]
            break
    assert trained is not None, 'The driven training never completed'
    assert not trained.hidden
    assert choose_scout(list(world.player_units(0)), [trained.id]).id == trained.id


def test_move_key_follows_the_live_scheme():
    """The card's Move slot resolves through the scene's own scheme bindings:
    Q on the positional cards the screenshots show, the mnemonic letter only
    on Classic."""
    controls = importlib.import_module('warband.ui.controls')
    move_slot = importlib.import_module('warband.ui.scene').UNIT_SLOTS['move']
    assert controls.SCHEMES['grid'].card_key('m', move_slot) == 'q'
    assert controls.SCHEMES['modal'].card_key('m', move_slot) == 'q'
    assert controls.SCHEMES['classic'].card_key('m', move_slot) == 'm'


def test_card_seam_pairs_live_commands_with_buttons():
    """The verifier clicks card buttons behind their labels through the public
    card/card_buttons seam: on a mock-backend scene the two pair one to one,
    a selected worker is offered Move, and the hall card names the peasant
    the scene's own unit names do."""
    saga2d = importlib.import_module('saga2d')
    warband_scene = importlib.import_module('warband.ui.scene')
    world = importlib.import_module('warband.sim.mapgen').generate(1)
    rules = importlib.import_module('warband.sim.rules')
    game = saga2d.Game('CardSeam', backend='mock', resolution=(1280, 800))
    try:
        scene = warband_scene.GameScene(world, 1, player=0, ranked=False)
        game.push(scene)
        tick = importlib.import_module('saga2d.testing.native_frames').tick
        for _ in range(5):
            tick(game, 1 / 30)
        worker = next(u for u in world.player_units(0) if u.is_worker and not u.hidden)
        scene.select([worker.id])
        assert worker.id in scene.selection
        pairs = list(zip(scene.card, scene.card_buttons, strict=True))
        assert pairs
        assert next(command for command, _ in pairs if command.label == 'Move').hotkey
        hall = world.player_buildings(0, rules.BuildingType.TOWN_HALL, done=True)[0]
        scene.select([hall.id])
        assert scene.unit_name(rules.UnitType.PEASANT) in [command.label for command in scene.card]
    finally:
        game.close()


def test_same_account_second_seat_needs_a_casual_warband_room():
    """The journeys play both seats from one profile: a rated room rejects that
    second seat while a casual room accepts it, which is why the Warband journey
    clicks the public Casual room button before Create room."""
    from websockets.sync.client import connect
    from saga2d.testing.online import handshake, running_server
    import warband.online.authority  # noqa: F401

    with running_server("warband.online.authority:ONLINE") as (url, _process):
        with connect(url, proxy=None) as host, connect(url, proxy=None) as same:
            welcome = handshake(host, game="warband-v2", options={"seed": 3}, rated=True)
            with pytest.raises(AssertionError, match="already holds a seat"):
                handshake(same, "join", game="warband-v2", room=welcome["room"],
                          player_token=welcome["player_token"])
        with connect(url, proxy=None) as host, connect(url, proxy=None) as same:
            welcome = handshake(host, game="warband-v2", options={"seed": 3}, rated=False)
            guest = handshake(same, "join", game="warband-v2", room=welcome["room"],
                              player_token=welcome["player_token"])
            assert guest["player"] == 1
