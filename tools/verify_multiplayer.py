"""Separate host process + real pyglet guest input, screenshots and synchronized state.

    SAGA2D_SILENT=1 uv run python tools/verify_multiplayer.py /tmp/multiplayer

Runs one small match at a time. Native frames are paced at 30 FPS; server waits
between polls. Captures title, host/join form and accepted gameplay for each game.
"""
from __future__ import annotations
import argparse
import importlib
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def definitions(name):
    module = importlib.import_module(name + '.multiplayer')
    if name == 'tribes':
        return module.TribesMatch, module.NetworkMapScene, 'tribes-v1'
    if name == 'warband':
        return module.WarbandMatch, module.NetworkGameScene, 'warband-v1'
    return module.ShardboundMatch, module.NetworkShardScene, 'shardbound-v1'


def serve(name, pipe, stop):
    from saga2d import MatchHost
    factory, _, protocol = definitions(name)
    match = factory()
    host = MatchHost(protocol, match.apply, match.snapshot, address=('127.0.0.1', 0), token='test')
    pipe.send(host.address[1])
    last_tick, handed = time.monotonic(), False
    try:
        while not stop.is_set():
            host.poll()
            if name == 'tribes' and host.ready and not handed:
                host.submit({'action': 'end_turn'})
                handed = True
            if name == 'warband' and host.ready and time.monotonic() - last_tick >= .05:
                match.step()
                host.publish()
                last_tick = time.monotonic()
            if pipe.poll():
                request = pipe.recv()
                if request == 'snapshot':
                    pipe.send(match.snapshot(1))
                else:
                    assert request == 'finish' and name == 'tribes'
                    while match.world.winner is None:
                        match.apply(match.world.current, {'action': 'end_turn'})
                    host.publish()
            time.sleep(.005)
    finally:
        host.close()
        pipe.close()


def verify(name, output):
    from saga2d import Game, MatchMenu, fonts
    from tools.native_frames import tick
    context = multiprocessing.get_context('spawn')
    parent, child = context.Pipe()
    stop = context.Event()
    server = context.Process(target=serve, args=(name, child, stop))
    server.start()
    assert parent.poll(10), 'host did not start'
    port = parent.recv()
    game = None
    try:
        with tempfile.TemporaryDirectory() as profile:
            style = importlib.import_module(name + '.style')
            if name == 'eador':
                from eador.app import create_game
                from eador.scene import TitleScene, BattleScene
                game = create_game(visible=False, save_dir=Path(profile) / 'saves', resolution=(1280, 800))
            else:
                TitleScene = importlib.import_module(name + '.title').TitleScene
                game = Game(name, visible=False, resolution=(1280, 800), theme=style.build_theme(), save_dir=Path(profile) / 'saves')
                fonts.load(game)
            from pyglet.window import key, mouse
            def frame(n=1):
                for _ in range(n):
                    tick(game, 1/30)
            def wait(until):
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    frame()
                    if until():
                        return
                raise AssertionError(f'{name}: state did not converge; {type(game.scene).__name__}')
            def press(symbol):
                game.backend.window.dispatch_event('on_key_press', symbol, 0)
                game.backend.window.dispatch_event('on_key_release', symbol, 0)
                frame()
            def click(x, y, button=mouse.LEFT):
                backend = game.backend
                px = int(x * backend.scale_factor + backend.offset_x)
                py = int((game.height-y) * backend.scale_factor + backend.offset_y)
                backend.window.dispatch_event('on_mouse_press', px, py, button, 0)
                backend.window.dispatch_event('on_mouse_release', px, py, button, 0)
                frame()
            def shot(label):
                frame(2)
                path = output / f'{name}-{label}.png'
                game.backend.capture_frame().save(path)
                print(path, flush=True)
            game.push(TitleScene())
            shot('title')
            press(key.M)
            assert isinstance(game.scene, MatchMenu)
            lan = next(button for button in game.scene.ui.walk() if getattr(button, 'text', None) == 'LAN')
            x, y, w, h = lan.bounds
            click(x + w / 2, y + h / 2)
            assert game.scene.mode == 'lan'
            press(key.TAB)
            for digit in str(port):
                press(getattr(key, '_' + digit))
            press(key.TAB)
            for letter in 'test':
                press(getattr(key, letter.upper()))
            shot('join')
            press(key.ENTER)
            _, scene_type, _ = definitions(name)
            wait(lambda: isinstance(game.scene, scene_type))
            scene = game.scene
            if name == 'tribes':
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
                sx, sy = scene.camera.world_to_screen((unit.x-2)*32, unit.y*32)
                click(sx, sy, mouse.RIGHT)
                wait(lambda: scene.world.units[ident].pos != old)
                # Menus must not suspend the authoritative clock or disconnect the guest.
                press(key.F10)
                before = scene.world.tick
                wait(lambda: scene.world.tick > before + 3)
                press(key.ESCAPE)
                assert scene.session.ready
            else:
                press(key.X)
                wait(lambda: isinstance(game.scene, BattleScene))
                ident = game.scene.selected
                press(key.G)
                wait(lambda: game.scene.battle.unit(ident).acted)
                press(key.E)
                wait(lambda: isinstance(game.scene, BattleScene) and game.scene.battle.round == 2)
            frame(90)
            shot('match')
            parent.send('snapshot')
            assert parent.poll(3), 'host snapshot unavailable'
            snapshot = parent.recv()
            if name == 'tribes':
                from tribes.model import World
                from tribes.scene import GameOverScene
                from tribes.scores import HighScores
                assert World.from_dict(snapshot['world']).to_dict() == scene.world.to_dict()
                parent.send('finish')
                wait(lambda: isinstance(game.scene, GameOverScene))
                assert HighScores(game.data_dir).load() == []
                shot('result')
            elif name == 'eador':
                assert snapshot['campaign'] == game.scene.root.state.to_json()
            else:
                assert snapshot['world']['tick'] >= scene.world.tick
            print(f'{name}: native guest commands accepted by separate host process', flush=True)
    finally:
        if game is not None:
            game.close()
        stop.set()
        server.join(5)
        if server.is_alive():
            server.terminate()
            server.join()
        assert server.exitcode == 0, f'host exited with {server.exitcode}'
        parent.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--game', choices=('tribes', 'warband', 'eador'))
    args = parser.parse_args()
    os.environ['SAGA2D_SILENT'] = '1'
    args.output.mkdir(parents=True, exist_ok=True)
    for name in [args.game] if args.game else ['tribes', 'warband', 'eador']:
        verify(name, args.output.resolve())


if __name__ == '__main__':
    main()
