"""Play a native Warband client against a remote seat through the real public menu.

    SAGA2D_SILENT=1 uv run python tools/verify_warband_remote_ai.py /tmp/remote-ai \
        --server wss://games.tachyon-ai.eu/play --room ABC123

The remote seat must already hold the room and stay connected throughout.
This verifier starts at the real title, pastes the public invite (a full
/join/warband-v2/CODE URL) through the actual Paste invite button, joins with
Enter through the native multiplayer form, issues move/harvest/train/scout
orders through the real command card (GameScene.attempt), and checks received
authoritative snapshots. Scouting is fog-honest: the target comes from the
player's own known starting region, map geometry, or remembered sightings —
never from the live hidden rival hall. Then it leaves through the pause menu
and rejoins through Rejoin last room on the saved private seat, checking the
same player/room and a continued authoritative tick. No server or AI is started
here. Private seat tokens never appear in the report, logs, or screenshots.
Frames are paced at 30 FPS.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def scout_destination(world, scout_pos, human, opponent, remembered):
    """A fog-honest scouting target for *scout_pos*, in tile units.

    Uses only what the seat itself knows through public interfaces: its own
    buildings and units, *remembered* rival sightings (MapView.memory rows),
    and map geometry. The live rival's hidden buildings and units are never
    consulted. Returns ``(point, reason)`` where reason is ``'remembered'`` or
    ``'geometry'``.
    """
    from warband.sim.model import tile_center
    from warband.sim.rules import BuildingType

    def approaches(center):
        found = []
        for y in range(world.height):
            for x in range(world.width):
                point = tile_center((x, y))
                distance = math.dist(point, center)
                if 2.5 <= distance <= 4 and world.passable(x, y) and world.entity_at(point) is None:
                    found.append(point)
        return found

    sightings = [b for b in (remembered or [])
                 if isinstance(b, dict) and b.get('player') == opponent
                 and isinstance(b.get('rect'), (list, tuple)) and len(b['rect']) == 4]
    if sightings:
        x, y, w, h = sightings[0]['rect']
        center = (x + w / 2, y + h / 2)
        candidates = approaches(center)
        if candidates:
            return min(candidates, key=lambda p: math.dist(scout_pos, p)), 'remembered'

    halls = world.player_buildings(human, BuildingType.TOWN_HALL, done=True)
    if halls:
        anchor = halls[0].center
    else:
        own = [u.pos for u in world.player_units(human) if not u.hidden]
        anchor = min(own, key=lambda p: math.dist(scout_pos, p)) if own else scout_pos
    corners = [(2, 2), (world.width - 3, 2), (2, world.height - 3),
               (world.width - 3, world.height - 3)]
    corner = tile_center(max(corners, key=lambda c: math.dist(tile_center(c), anchor)))
    candidates = approaches(corner)
    if candidates:
        return min(candidates, key=lambda p: math.dist(scout_pos, p)), 'geometry'
    far = [(x, y) for y in range(world.height) for x in range(world.width) if world.passable(x, y)]
    assert far, 'No passable scouting ground on this map'
    tile = max(far, key=lambda c: math.dist(tile_center(c), anchor))
    return tile_center(tile), 'geometry'


def move_choices(world, worker):
    """Reachable nearby move destinations for *worker*, in tile units.

    Only public world queries: tiles around the worker's own tile that are
    passable, unoccupied, and a step away. Each axis is bounded by its own
    coordinate, so off-diagonal seats get a real search range.
    """
    from warband.sim.model import tile_center
    return [tile_center((x, y))
            for y in range(max(0, worker.tile[1] - 3), min(world.height, worker.tile[1] + 4))
            for x in range(max(0, worker.tile[0] - 3), min(world.width, worker.tile[0] + 4))
            if world.passable(x, y) and 1.5 <= math.dist(worker.pos, tile_center((x, y))) <= 3
            and world.entity_at(tile_center((x, y))) is None]


def choose_scout(units, preferred):
    """The scout from live own *units*: the first preferred id still around and
    out in the open, else the first visible worker. A worker inside a mine is
    hidden and cannot be clicked, so it is never chosen. Raises AssertionError
    when no visible worker exists."""
    visible = [u for u in units if u.is_worker and not u.hidden]
    for ident in preferred:
        match = next((u for u in visible if u.id == ident), None)
        if match is not None:
            return match
    if visible:
        return visible[0]
    raise AssertionError('No visible worker to scout with; the others are inside mines or gone')


def claim_scout_target(ordered, target):
    """Record *target* in the *ordered* set, refusing to repeat a destination.

    Raises AssertionError when the rounded target was already ordered: the
    scout must head somewhere new or the run must fail loudly instead of
    reissuing the same failed order forever.
    """
    key = (round(target[0], 1), round(target[1], 1))
    if key in ordered:
        raise AssertionError(f'Scouting repeats an already-ordered destination {target}')
    ordered.add(key)
    return key


def verify(output: Path, server: str, room: str, timeout: float, visible: bool) -> None:
    from pyglet.window import key, mouse
    from saga2d import Game, MatchMenu, fonts
    from saga2d.testing.native_frames import tick
    from warband.sim.model import Harvest, Move, tile_center
    from warband.ui.multiplayer import (MatchSetupMenu, NetworkGameScene, online_identity,
                                        stored_online_profile)
    from warband.sim.rules import BuildingType, Resource, Terrain, UnitType
    from warband.art.textures import TILE
    from warband.ui.style import build_theme
    from warband.ui.title import TitleScene

    output.mkdir(parents=True, exist_ok=True)
    os.environ['SAGA2D_SERVER_URL'] = server
    started = time.monotonic()
    report = {'status': 'running', 'server': server, 'room': room.upper(),
              'local_ai': False, 'orders': [], 'screenshots': []}
    game = None
    scene = None

    with tempfile.TemporaryDirectory(prefix='warband-remote-ai-') as profile:
        def frames(count=1):
            for _ in range(count):
                tick(game, 1 / 30)

        def wait(predicate, label, budget=None, probe=False):
            deadline = time.monotonic() + (timeout if budget is None else budget)
            while time.monotonic() < deadline:
                frames()
                if predicate():
                    return True
            if probe:
                return False
            current = game.scene
            session = getattr(current, 'session', None)
            raise AssertionError(f'{label}: timed out after {timeout:g}s; '
                                 f'scene={type(current).__name__}; '
                                 f'tick={scene.world.tick if scene else None}; '
                                 f'network_error={session.error if session else None}')

        def press(symbol):
            window = game.backend.window
            window.dispatch_event('on_key_press', symbol, 0)
            window.dispatch_event('on_key_release', symbol, 0)
            frames()

        def click(x, y, button=mouse.LEFT):
            assert 0 <= x < game.width and 0 <= y < game.height, (x, y)
            backend = game.backend
            px = int(x * backend.scale_factor + backend.offset_x)
            py = int((game.height - y) * backend.scale_factor + backend.offset_y)
            backend.window.dispatch_event('on_mouse_press', px, py, button, 0)
            backend.window.dispatch_event('on_mouse_release', px, py, button, 0)
            frames()

        def click_widget(widget, button=mouse.LEFT):
            text = getattr(widget, 'text', '')
            label = text() if callable(text) else text
            x, y, w, h = widget.bounds
            assert w > 0 and h > 0, f'Button {label!r} has no grounded bounds yet'
            click(x + w / 2, y + h / 2, button)

        def click_card(label_text):
            # The command card as it shows now: pair each command with its own
            # button and click the match through a real mouse event. The
            # command's action is never invoked directly.
            pairs = list(zip(scene.card, scene.card_buttons, strict=True))
            assert pairs, 'The command card shows no commands for this selection'
            for command, button in pairs:
                if command.label == label_text:
                    assert getattr(button, 'enabled', True), f'Command card button {label_text!r} is disabled'
                    click_widget(button)
                    return
            names = [command.label for command, _ in pairs]
            raise AssertionError(f'No command card button {label_text!r}; card shows: {names}')

        def find_button(match):
            frames(2)
            for widget in game.scene.ui.walk():
                text = getattr(widget, 'text', None)
                label = text() if callable(text) else text
                if isinstance(label, str) and match(label):
                    return widget
            names = [getattr(w, 'text', '') for w in game.scene.ui.walk()]
            raise AssertionError(f'No menu button matched; visible labels: {names}')

        def click_world(point, button=mouse.LEFT):
            click(*scene.camera.world_to_screen(point[0] * TILE, point[1] * TILE), button)

        def minimap(point, button=mouse.LEFT):
            click(*scene.minimap.to_screen(point[0] * TILE, point[1] * TILE), button)

        def shot(name):
            frames(2)
            path = output / f'{name}.png'
            game.backend.capture_frame().save(path)
            report['screenshots'].append(str(path))
            print(path, flush=True)

        def received(kind, ident):
            return next(row for row in scene.session.state['world'][kind] if row['id'] == ident)

        def accepted(action, before_revision, kind, ident, **details):
            assert scene.session.revision > before_revision
            row = received(kind, ident)
            entry = {'action': action, 'entity': ident, 'revision': scene.session.revision,
                     'tick': scene.session.state['world']['tick'], 'received_state': row, **details}
            report['orders'].append(entry)
            print(f"accepted {action}: entity={ident} tick={entry['tick']}", flush=True)
            return row

        def opponent_summary():
            data = scene.session.state['world']
            return {'tick': data['tick'], 'revision': scene.session.revision,
                    'player': next(p for p in data['players'] if p['id'] == opponent),
                    'units': [u for u in data['units'] if u['player'] == opponent],
                    'buildings': [b for b in data['buildings'] if b['player'] == opponent]}

        def visible_opponents():
            return [u for u in scene.world.player_units(opponent)
                    if not u.hidden and scene.world.is_visible(human, u.tile)
                    and (sprite := scene.view.unit_sprite(u.id)) is not None and sprite.visible]

        def remembered_sightings():
            # MapView.memory() is {"buildings": [...]}; only a genuinely empty
            # record falls back to geometry, and anything unexpected propagates.
            return scene.view.memory().get('buildings', [])

        def scout_state(unit):
            # This seat's own scout, for failure reports: never another seat.
            sprite = scene.view.unit_sprite(unit.id)
            return {'id': unit.id, 'pos': unit.pos, 'hidden': unit.hidden, 'state': unit.state,
                    'sprite_visible': sprite.visible if sprite is not None else None}

        try:
            game = Game('Warband remote AI verification', resolution=(1280, 800),
                        visible=visible, theme=build_theme(), save_dir=Path(profile) / 'saves')
            fonts.load(game)
            game.push(TitleScene())
            frames()
            press(key.M)
            menu = game.scene
            assert isinstance(menu, MatchSetupMenu) and isinstance(menu, MatchMenu) \
                and menu.mode == 'online', type(menu).__name__
            # Paste the public invite link (never a private seat): the form accepts
            # a bare code or the public /join/warband-v2/CODE URL. The player's
            # previous clipboard is restored straight after, never logged.
            previous_clipboard = game.backend.get_clipboard_text()
            game.backend.set_clipboard_text(f'https://games.tachyon-ai.eu/join/warband-v2/{room}')
            click_widget(find_button(lambda label: label == 'Paste invite'))
            assert menu.fields[2] == room.upper(), menu.fields[2]
            game.backend.set_clipboard_text(previous_clipboard)
            shot('01-online-room')
            press(key.ENTER)
            wait(lambda: isinstance(game.scene, NetworkGameScene) and game.scene.session.ready,
                 'Join remote seat through the multiplayer menu')
            scene = game.scene
            parsed = urlsplit(server)
            assert parsed.scheme in ('ws', 'wss'), server
            if parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
                assert parsed.scheme == 'wss', f'Public room servers require TLS: {server}'
            assert scene.session.online and scene.session.endpoint == server
            assert scene.session.room.lower() == room.lower(), scene.session.room
            assert scene.match is None and scene.brains == [], 'The human client must not run a match or AI'
            identity = online_identity(game)
            assert set(identity) == {'player_token', 'player_name'}, sorted(identity)
            cached = stored_online_profile(game)
            if isinstance(cached, dict):
                report['profile'] = {k: cached[k] for k in ('name', 'rating', 'games', 'wins', 'losses')
                                     if k in cached}
            assert scene.session.seats == 2, \
                f'Only two-seat duel rooms are supported, not {scene.session.seats}'
            human, opponent = scene.human, 1 - scene.human
            report.update(player=human, opponent=opponent, initial_tick=scene.world.tick,
                          seed=scene.session.state['seed'], map_size=[scene.world.width, scene.world.height])
            initial_lumber = scene.world.players[human].lumber
            baseline = opponent_summary()
            report['opponent_before'] = baseline
            shot('02-connected-base')

            hall = scene.world.player_buildings(human, BuildingType.TOWN_HALL, done=True)[0]
            hall_id = hall.id
            workers = [u for u in scene.world.player_units(human) if u.is_worker and not u.hidden]
            assert len(workers) >= 2, 'A fresh room needs two available workers for harvesting and scouting'
            worker_id = workers[0].id
            initial_local_ids = {u.id for u in scene.world.player_units(human)}

            # Move one worker through the live command card and a world click, as a player does.
            worker = scene.world.units[worker_id]
            click_world(worker.pos)
            assert worker_id in scene.selection
            candidates = move_choices(scene.world, worker)
            assert candidates, 'No open nearby destination for the move input'
            destination = min(candidates, key=lambda p: math.dist(p, hall.center))
            before_revision, old_position = scene.session.revision, worker.pos
            click_card('Move')
            assert scene.pending == 'move'
            click_world(destination)
            wait(lambda: isinstance(scene.world.units[worker_id].order, Move), 'Authoritative move order')
            row = accepted('move', before_revision, 'units', worker_id, target=destination)
            assert row['orders'][0]['kind'] == 'Move'
            wait(lambda: math.dist(scene.world.units[worker_id].pos, old_position) > .3, 'Worker moves on server')

            # Right-click a visible tree and wait until the server reports actual chopping.
            worker = scene.world.units[worker_id]
            trees = [(x, y) for y in range(scene.world.height) for x in range(scene.world.width)
                     if scene.world.terrain_at((x, y)) is Terrain.TREES and scene.world.is_visible(human, (x, y))]
            assert trees, 'The starting base should have a visible lumber source'
            tree = min(trees, key=lambda p: math.dist(worker.pos, tile_center(p)))
            before_revision = scene.session.revision
            click_world(tile_center(tree), mouse.RIGHT)
            wait(lambda: isinstance(scene.world.units[worker_id].order, Harvest), 'Authoritative lumber order')
            row = accepted('harvest', before_revision, 'units', worker_id, target=tree)
            assert row['orders'][0] == {'kind': 'Harvest', 'target': list(tree)}
            wait(lambda: scene.world.units[worker_id].state == 'chop', 'Worker reaches lumber and swings axe')
            minimap(scene.world.units[worker_id].pos)
            shot('03-authoritative-chopping')

            # Training must appear in a received server queue, then complete on that server.
            press(key.HOME)
            frames(12)
            click_world(scene.world.buildings[hall_id].center)
            assert hall_id in scene.selection
            before_revision = scene.session.revision
            click_card(scene.unit_name(UnitType.PEASANT))
            wait(lambda: UnitType.PEASANT in scene.world.buildings[hall_id].queue, 'Authoritative training queue')
            row = accepted('train', before_revision, 'buildings', hall_id, unit_type=UnitType.PEASANT.value)
            assert UnitType.PEASANT.value in row['queue']
            shot('04-authoritative-training')

            # The freshly trained peasant makes the stable scout: it walks out
            # of the hall in the open, while an older worker may since have
            # entered a mine, where no click can reach it.
            wait(lambda: bool({u.id for u in scene.world.player_units(human)} - initial_local_ids),
                 'Server completes local peasant training')
            trained_ids = sorted({u.id for u in scene.world.player_units(human)} - initial_local_ids)
            report['trained_units'] = trained_ids
            scout = choose_scout(list(scene.world.player_units(human)), trained_ids)
            scout_id = scout.id
            wait(lambda: not scene.world.units[scout_id].hidden
                 and (sprite := scene.view.unit_sprite(scout_id)) is not None and sprite.visible,
                 'Chosen scout walks out where it can be seen', budget=30)
            scout = scene.world.units[scout_id]
            press(key.HOME)
            frames(12)
            press(key.ESCAPE)
            frames(2)
            click_world(scout.pos)
            assert scout_id in scene.selection, f'Scout never selected: {scout_state(scout)}'
            # Scout fog-honestly: the target comes from remembered sightings or map
            # geometry, never from the live hidden rival hall. Retry across legs so a
            # first blind heading still finds a rendered remote unit in time.
            scout_deadline = time.monotonic() + timeout
            scout_basis, ordered_targets = None, set()
            while time.monotonic() < scout_deadline:
                if visible_opponents():
                    break
                scout = scene.world.units[scout_id]
                scout_target, scout_basis = scout_destination(
                    scene.world, scout.pos, human, opponent, remembered_sightings())
                claim_scout_target(ordered_targets, scout_target)
                before_revision = scene.session.revision
                minimap(scout_target, mouse.RIGHT)
                wait(lambda: isinstance(scene.world.units[scout_id].order, Move),
                     'Authoritative scouting order', budget=15)
                accepted('scout', before_revision, 'units', scout_id,
                         target=scout_target, basis=scout_basis)
                if wait(lambda: bool(visible_opponents()),
                        'Scout naturally reveals a rendered remote unit', budget=30, probe=True):
                    break
            assert visible_opponents(), 'Scouting never rendered the remote seat'
            enemy = min(visible_opponents(), key=lambda u: (not u.is_worker, not bool(u.orders)))
            enemy_id, enemy_position = enemy.id, enemy.pos
            minimap(enemy.pos)
            shot('05-remote-ai-visible')
            report['visible_opponent'] = {'id': enemy_id, 'position': enemy_position,
                                          'tick': scene.world.tick, 'state': received('units', enemy_id),
                                          'scout_basis': scout_basis}
            visible_before = {u.id: (u.pos, u.state, u.timer) for u in visible_opponents()}
            wait(lambda: any(u.id in visible_before and (math.dist(u.pos, visible_before[u.id][0]) > .15
                             or u.state != visible_before[u.id][1]
                             or abs(u.timer - visible_before[u.id][2]) > .3) for u in visible_opponents()),
                 'Visible remote workers or soldiers continue acting')
            report['visible_opponent_progress'] = [received('units', u.id) for u in visible_opponents()]

            wait(lambda: scene.world.units[worker_id].carrying is Resource.LUMBER
                 or scene.world.players[human].lumber > initial_lumber,
                 'Server produces harvested lumber')
            report['harvest_result'] = {'unit': received('units', worker_id),
                                        'initial_lumber': initial_lumber,
                                        'final_lumber': scene.world.players[human].lumber}
            # A seat is sent only what it sees: the remote seat's progress shows in
            # what scouting rendered and kept rendering, on top of an advancing tick.
            final = opponent_summary()
            assert final['tick'] > baseline['tick'], 'The match did not advance'
            assert report.get('visible_opponent'), 'Scouting never rendered the remote seat'
            report.update(final_tick=scene.world.tick, opponent_after=final,
                          trained_units=sorted({u.id for u in scene.world.player_units(human)} - initial_local_ids))
            shot('06-remote-ai-progression')
            press(key.HOME)
            frames(12)
            shot('07-local-economy')
            print(f'PASS (match): native player {human} against remote player {opponent}; room={room}', flush=True)

            # Rejoin through the dedicated UI on the saved private seat: pause menu
            # to the title, then the Rejoin last room button the lobby saved.
            tick_before_rejoin = scene.world.tick
            room_before_rejoin = scene.session.room
            press(key.F10)
            click_widget(find_button(lambda label: label == 'Leave match'))
            wait(lambda: isinstance(game.scene, TitleScene), 'Leave match returns to the title')
            press(key.M)
            assert isinstance(game.scene, MatchSetupMenu) and game.scene.mode == 'online'
            click_widget(find_button(lambda label: label.startswith('Rejoin last room')))
            wait(lambda: isinstance(game.scene, NetworkGameScene) and game.scene.session.ready,
                 'Rejoin last room on the saved private seat')
            scene = game.scene
            assert scene.session.room.lower() == room_before_rejoin.lower(), scene.session.room
            assert scene.human == human, (scene.human, human)
            assert scene.match is None and scene.brains == [], 'The rejoined client must not run a match or AI'
            assert scene.world.tick >= tick_before_rejoin, (scene.world.tick, tick_before_rejoin)
            report['rejoin'] = {'room': scene.session.room, 'player': scene.human,
                                'tick_before': tick_before_rejoin, 'tick_after': scene.world.tick}
            shot('08-rejoined')
            report.update(status='passed', final_tick=scene.world.tick)
            print(f'PASS: native player {human} against remote player {opponent}; '
                  f'room={room} rejoined at tick={scene.world.tick}', flush=True)
        except Exception as exc:
            report['status'] = 'failed'
            report['error'] = f'{type(exc).__name__}: {exc}'
            if game is not None:
                shot('failure')
            raise
        finally:
            report['elapsed_seconds'] = round(time.monotonic() - started, 3)
            (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
            if game is not None:
                game.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--server', default=None, help='TLS WebSocket endpoint (default: public server)')
    parser.add_argument('--room', required=True, help='Existing room held by the remote seat')
    parser.add_argument('--timeout', type=float, default=120, help='Maximum seconds per expected gameplay transition')
    parser.add_argument('--visible', action='store_true', help='Show the native window while verifying')
    args = parser.parse_args()
    if not args.room.isalnum() or args.timeout <= 0:
        parser.error('--room must be alphanumeric and --timeout must be positive')
    if args.server is None:
        from saga2d.online import server_endpoint
        args.server = server_endpoint()
    os.environ['SAGA2D_SILENT'] = '1'
    verify(args.output.resolve(), args.server, args.room, args.timeout, args.visible)


if __name__ == '__main__':
    main()
