"""Native online create/join/rejoin journeys against a dedicated server process.

    SAGA2D_SILENT=1 uv run python tools/verify_online.py /tmp/online
    SAGA2D_SILENT=1 uv run python tools/verify_online.py /tmp/public --server wss://games.tachyon-ai.eu/play

Runs one small match at a time, with real pyglet input and paced 30 FPS frames.
Without --server, starts the production server on an OS-assigned local port.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@contextmanager
def dedicated_server(endpoint=None):
    if endpoint:
        yield endpoint
        return
    process = subprocess.Popen([sys.executable, '-m', 'online_server', '--port', '0'],
                               cwd=Path(__file__).resolve().parent.parent,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        readable, _, _ = select.select([process.stdout, process.stderr], [], [], 15)
        assert process.stdout in readable, process.stderr.readline() if readable else 'Server startup timed out'
        line = process.stdout.readline().strip()
        assert line.startswith('LISTENING ws://'), line
        yield line.removeprefix('LISTENING ')
    finally:
        process.terminate()
        try:
            _, errors = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            _, errors = process.communicate(timeout=5)
        assert process.returncode == 0, errors


def verify(name, output, endpoint):
    from saga2d import Game, MatchMenu, fonts
    from saga2d.multiplayer_ui import MatchLobby
    from saga2d.online import OnlineClient
    from tools.native_frames import tick
    from tools.verify_multiplayer import definitions
    from pyglet.window import key, mouse

    _, scene_type, protocol = definitions(name)
    os.environ['SAGA2D_SERVER_URL'] = endpoint
    partner = None
    game = None
    with tempfile.TemporaryDirectory() as profile:
        def new_game():
            if name == 'eador':
                from eador.app import create_game
                return create_game(visible=False, save_dir=Path(profile) / 'saves', resolution=(1280, 800))
            style = importlib.import_module(name + '.style')
            window = Game(name, visible=False, resolution=(1280, 800), theme=style.build_theme(), save_dir=Path(profile) / 'saves')
            fonts.load(window)
            return window

        def frame(n=1):
            for _ in range(n):
                if partner is not None:
                    partner.poll()
                tick(game, 1 / 30)

        def wait(until):
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                frame()
                if until():
                    return
            session = getattr(game.scene, 'session', None)
            raise AssertionError(f'{name}: state did not converge; {type(game.scene).__name__}; '
                                 f'{session.error if session else ""}')

        def press(symbol):
            game.backend.window.dispatch_event('on_key_press', symbol, 0)
            game.backend.window.dispatch_event('on_key_release', symbol, 0)
            frame()

        def click(x, y, button=mouse.LEFT):
            backend = game.backend
            px = int(x * backend.scale_factor + backend.offset_x)
            py = int((game.height - y) * backend.scale_factor + backend.offset_y)
            backend.window.dispatch_event('on_mouse_press', px, py, button, 0)
            backend.window.dispatch_event('on_mouse_release', px, py, button, 0)
            frame()

        def click_text(text):
            button = next(b for b in game.scene.ui.walk() if str(getattr(b, 'text', '')).startswith(text))
            x, y, w, h = button.bounds
            click(x + w / 2, y + h / 2)

        def shot(label):
            frame(2)
            path = output / f'{name}-{label}.png'
            game.backend.capture_frame().save(path)
            print(path, flush=True)

        def title(*, about=False):
            TitleScene = importlib.import_module(name + ('.scene' if name == 'eador' else '.title')).TitleScene
            game.push(TitleScene())
            frame()
            if about:
                game.scene.about()
                shot('about')
                press(key.PAGEDOWN)
                press(key.PAGEDOWN)
                shot('about-credits')
                press(key.ESCAPE)
            press(key.M)
            assert isinstance(game.scene, MatchMenu)

        try:
            game = new_game()
            title(about=name == 'eador')
            assert game.scene.mode == 'online'
            assert not game.scene.last_room['resume_token'], 'New test profile contains a saved seat'
            shot('online')
            click_text('LAN')
            assert game.scene.mode == 'lan'
            shot('lan')
            click_text('Online')
            click_text('Create room')
            assert isinstance(game.scene, MatchLobby)
            wait(lambda: bool(game.scene.session.resume_token))
            creator = game.scene.session
            assert not creator.ready
            room, token = creator.room, creator.resume_token
            shot('room')
            press(key.ESCAPE)
            assert isinstance(game.scene, MatchMenu)
            assert creator.closed
            partner = OnlineClient(protocol, endpoint=endpoint, room=room, resume_token=token)
            wait(lambda: partner.state is not None)
            # Exercise the public join form: no IP address, port, or seat credential.
            for char in room:
                press(getattr(key, '_' + char if char.isdigit() else char.upper()))
            shot('join')
            press(key.ENTER)
            wait(lambda: isinstance(game.scene, scene_type) and partner.ready)
            scene = game.scene
            assert scene.session.player == 1
            if name == 'tribes':
                partner.submit({'action': 'end_turn'}, revision=partner.revision)
                wait(lambda: scene.world.current == 1)
                press(key.TAB)
                ident = scene.selected.id
                press(key.H)
                wait(lambda: scene.world.units[ident].done)
                press(key.E)
                wait(lambda: scene.world.current == 0)
            elif name == 'warband':
                unit = scene.world.player_units(1)[0]
                ident, old = unit.id, unit.pos
                sx, sy = scene.camera.world_to_screen(unit.x * 32, unit.y * 32)
                click(sx, sy)
                assert ident in scene.selection
                sx, sy = scene.camera.world_to_screen((unit.x - 2) * 32, unit.y * 32)
                click(sx, sy, mouse.RIGHT)
                wait(lambda: scene.world.units[ident].pos != old)
                press(key.F10)
                before = scene.world.tick
                wait(lambda: scene.world.tick > before + 3)
                press(key.ESCAPE)
            else:
                from eador.scene import BattleScene
                press(key.X)
                wait(lambda: isinstance(game.scene, BattleScene))
                ident = game.scene.selected
                press(key.G)
                wait(lambda: game.scene.battle.unit(ident).acted)
                press(key.E)
                wait(lambda: isinstance(game.scene, BattleScene) and game.scene.battle.round == 2)
            frame(90 if name == 'warband' else 10)
            shot('match')
            game.close()
            game = new_game()
            title()
            wait(lambda: not partner.ready)
            shot('resume')
            click_text('Rejoin last room')
            if name == 'eador':
                wait(lambda: isinstance(game.scene, BattleScene) and partner.ready)
                resumed = game.scene.root
                assert game.scene.battle.round == 2
            else:
                wait(lambda: isinstance(game.scene, scene_type) and partner.ready)
                resumed = game.scene
            assert resumed.session.room == room
            assert resumed.session.player == 1
            if name == 'warband':
                frame(90)
            shot('rejoined')
            print(f'{name}: native create, room-code join, accepted gameplay and restart/rejoin passed', flush=True)
        finally:
            if game is not None:
                game.close()
            if partner is not None:
                partner.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--game', choices=('tribes', 'warband', 'eador'))
    parser.add_argument('--server', help='use an already running online server')
    args = parser.parse_args()
    os.environ['SAGA2D_SILENT'] = '1'
    args.output.mkdir(parents=True, exist_ok=True)
    with dedicated_server(args.server) as endpoint:
        for name in [args.game] if args.game else ['tribes', 'warband', 'eador']:
            verify(name, args.output.resolve(), endpoint)


if __name__ == '__main__':
    main()
