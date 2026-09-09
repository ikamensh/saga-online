"""Play a native Warband client against an AI running in a separate online seat.

    SAGA2D_SILENT=1 uv run python tools/verify_warband_remote_ai.py /tmp/remote-ai \
        --server wss://games.tachyon-ai.eu/play --room ABC123

The remote bot must create the room first and remain connected throughout.
This verifier joins through the actual multiplayer form, uses pyglet input to
move, harvest, train and scout, and checks received authoritative snapshots.
The opponent is revealed by scouting; fog and world state are never changed.
No server or AI is started by this process. Frames are paced at 30 FPS.
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def verify(output: Path, server: str, room: str, timeout: float, visible: bool) -> None:
    from pyglet.window import key, mouse
    from saga2d import Game, MatchMenu, fonts
    from saga2d.testing.native_frames import tick
    from warband.model import Harvest, Move, tile_center
    from warband.multiplayer import NetworkGameScene
    from warband.rules import BuildingType, Resource, Terrain, UnitType
    from warband.style import build_theme
    from warband.textures import TILE
    from warband.title import TitleScene

    output.mkdir(parents=True, exist_ok=True)
    os.environ['SAGA2D_SERVER_URL'] = server
    started = time.monotonic()
    report = {'status': 'running', 'server': server, 'room': room.lower(),
              'local_ai': False, 'orders': [], 'screenshots': []}
    game = None
    scene = None

    with tempfile.TemporaryDirectory(prefix='warband-remote-ai-') as profile:
        def frames(count=1):
            for _ in range(count):
                tick(game, 1 / 30)

        def wait(predicate, label):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                frames()
                if predicate():
                    return
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

        try:
            game = Game('Warband remote AI verification', resolution=(1280, 800),
                        visible=visible, theme=build_theme(), save_dir=Path(profile) / 'saves')
            fonts.load(game)
            game.push(TitleScene())
            frames()
            press(key.M)
            assert isinstance(game.scene, MatchMenu) and game.scene.mode == 'online'
            for character in room:
                press(getattr(key, '_' + character if character.isdigit() else character.upper()))
            shot('01-online-room')
            press(key.ENTER)
            wait(lambda: isinstance(game.scene, NetworkGameScene) and game.scene.session.ready,
                 'Join remote AI room through multiplayer menu')
            scene = game.scene
            assert scene.session.online and scene.session.endpoint == server
            assert scene.session.room == room.lower()
            assert scene.match is None and scene.brains == [], 'The human client must not run a match or AI'
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
            worker_id, scout_id = workers[0].id, workers[1].id
            initial_local_ids = {u.id for u in scene.world.player_units(human)}

            # Move one worker by the same command-card key and world click a player uses.
            worker = scene.world.units[worker_id]
            click_world(worker.pos)
            assert worker_id in scene.selection
            candidates = [tile_center((x, y))
                          for y in range(max(0, worker.tile[1] - 3), min(scene.world.height, worker.tile[1] + 4))
                          for x in range(max(0, worker.tile[0] - 3), min(scene.world.width, worker.tile[0] + 4))
                          if scene.world.passable(x, y) and 1.5 <= math.dist(worker.pos, tile_center((x, y))) <= 3
                          and scene.world.entity_at(tile_center((x, y))) is None]
            assert candidates, 'No open nearby destination for the move input'
            destination = min(candidates, key=lambda p: math.dist(p, hall.center))
            before_revision, old_position = scene.session.revision, worker.pos
            press(key.M)
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
            press(key.P)
            wait(lambda: UnitType.PEASANT in scene.world.buildings[hall_id].queue, 'Authoritative training queue')
            row = accepted('train', before_revision, 'buildings', hall_id, unit_type=UnitType.PEASANT.value)
            assert UnitType.PEASANT.value in row['queue']
            shot('04-authoritative-training')

            # Scout normally, using the minimap to send a worker across the map.
            scout = scene.world.units[scout_id]
            click_world(scout.pos)
            assert scout_id in scene.selection
            enemy_hall = scene.world.player_buildings(opponent, BuildingType.TOWN_HALL, done=True)[0]
            approaches = [tile_center((x, y))
                          for y in range(enemy_hall.y - 4, enemy_hall.y + enemy_hall.size + 4)
                          for x in range(enemy_hall.x - 4, enemy_hall.x + enemy_hall.size + 4)
                          if scene.world.passable(x, y) and 2.5 <= math.dist(tile_center((x, y)), enemy_hall.center) <= 4]
            assert approaches, 'No scouting approach near the remote base'
            approach = min(approaches, key=lambda p: math.dist(scout.pos, p))
            before_revision = scene.session.revision
            minimap(approach, mouse.RIGHT)
            wait(lambda: isinstance(scene.world.units[scout_id].order, Move), 'Authoritative scouting order')
            accepted('scout', before_revision, 'units', scout_id, target=approach)
            wait(lambda: bool(visible_opponents()), 'Scout naturally reveals a rendered remote AI unit')
            enemy = min(visible_opponents(), key=lambda u: (not u.is_worker, not bool(u.orders)))
            enemy_id, enemy_position = enemy.id, enemy.pos
            minimap(enemy.pos)
            shot('05-remote-ai-visible')
            report['visible_opponent'] = {'id': enemy_id, 'position': enemy_position,
                                          'tick': scene.world.tick, 'state': received('units', enemy_id)}
            visible_before = {u.id: (u.pos, u.state, u.timer) for u in visible_opponents()}
            wait(lambda: any(u.id in visible_before and (math.dist(u.pos, visible_before[u.id][0]) > .15
                             or u.state != visible_before[u.id][1]
                             or abs(u.timer - visible_before[u.id][2]) > .3) for u in visible_opponents()),
                 'Visible remote AI workers or soldiers continue acting')
            report['visible_opponent_progress'] = [received('units', u.id) for u in visible_opponents()]

            wait(lambda: bool({u.id for u in scene.world.player_units(human)} - initial_local_ids),
                 'Server completes local peasant training')
            wait(lambda: scene.world.units[worker_id].carrying is Resource.LUMBER
                 or scene.world.players[human].lumber > initial_lumber,
                 'Server produces harvested lumber')
            report['harvest_result'] = {'unit': received('units', worker_id),
                                        'initial_lumber': initial_lumber,
                                        'final_lumber': scene.world.players[human].lumber}
            # Remote progression is independently observable in snapshots without running a local Brain.
            final = opponent_summary()
            original_units = {u['id']: u for u in baseline['units']}
            moved = [u['id'] for u in final['units'] if u['id'] in original_units
                     and math.dist((u['x'], u['y']), (original_units[u['id']]['x'], original_units[u['id']]['y'])) > .5]
            new_units = [u['id'] for u in final['units'] if u['id'] not in original_units]
            old_buildings = {b['id']: b for b in baseline['buildings']}
            construction = [b['id'] for b in final['buildings']
                            if b['id'] not in old_buildings or b['progress'] > old_buildings[b['id']]['progress']]
            active_orders = [{'unit': u['id'], 'orders': u['orders']} for u in final['units'] if u['orders']]
            assert final['tick'] > baseline['tick'] and active_orders, 'Remote seat did not issue orders'
            assert moved or new_units or construction, 'Remote seat did not progress'
            assert scene.match is None and not scene.brains and scene.session.ready
            report.update(status='passed', final_tick=scene.world.tick, opponent_after=final,
                          trained_units=sorted({u.id for u in scene.world.player_units(human)} - initial_local_ids),
                          remote_progress={'moved_units': moved, 'new_units': new_units,
                                           'construction': construction, 'active_orders': active_orders})
            shot('06-remote-ai-progression')
            press(key.HOME)
            frames(12)
            shot('07-local-economy')
            print(f'PASS: native player {human} against remote player {opponent}; room={room}', flush=True)
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
    from saga2d.online import server_endpoint
    parser.add_argument('--server', default=server_endpoint(), help='TLS WebSocket endpoint (default: public server)')
    parser.add_argument('--room', required=True, help='Existing room created by the remote AI')
    parser.add_argument('--timeout', type=float, default=120, help='Maximum seconds per expected gameplay transition')
    parser.add_argument('--visible', action='store_true', help='Show the native window while verifying')
    args = parser.parse_args()
    if not args.room.isalnum() or args.timeout <= 0:
        parser.error('--room must be alphanumeric and --timeout must be positive')
    os.environ['SAGA2D_SILENT'] = '1'
    verify(args.output.resolve(), args.server, args.room, args.timeout, args.visible)


if __name__ == '__main__':
    main()
