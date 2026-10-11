"""A rated Warband ledger survives an online SQLite backup and a restore.

A real ``saga2d.server`` process hosts a rated ``warband-v2`` duel, the guest
resigns through the validated order, and both seats see the same authoritative
receipt. The test then reads both public profiles and the public leaderboard
over HTTP, takes a live backup through the public ``deploy.backup.backup``
API (SQLite's online backup, with its own integrity check), restores that
file as ``rooms.sqlite3`` in a fresh state directory, and starts a second
real server process there. The restored server must serve the identical
profiles and leaderboard, and a public seat resume must return the same
persisted receipt without awarding a second game. Every assertion goes
through the public WebSocket protocol and the public HTTP endpoints; the
test never opens the database itself and never touches private collaborators.
Account and seat tokens stay in memory only.
"""

import json
import shutil
import stat
from urllib.request import urlopen

from websockets.sync.client import connect

from deploy.backup import backup
from saga2d.testing.online import command, handshake, receive, running_server

GAME = 'warband-v2'
SPEC = 'warband.online.authority:ONLINE'


def _duel_options():
    """A small two-seat map; resigned at once, decided at once."""
    return {'seed': 3, 'width': 48, 'height': 40}


def _settled(socket):
    """The first state carrying the server's settled result receipt."""
    return receive(socket, predicate=lambda message: message['result'] is not None)


def _get(http, path):
    """A public JSON document from the server's HTTP surface."""
    with urlopen(http + path, timeout=5) as response:
        assert response.headers.get_content_type() == 'application/json'
        return json.loads(response.read())


def test_rated_ledger_survives_backup_and_restore(tmp_path):
    """Live profiles and leaderboard match the restored server's exactly."""
    live_dir = tmp_path / 'live'
    backup_dir = tmp_path / 'backups'
    fresh_dir = tmp_path / 'fresh'
    with running_server(SPEC, arguments=('--state-dir', str(live_dir))) as (url, _process):
        http = url.replace('ws://', 'http://')
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            welcome = handshake(host, game=GAME, options=_duel_options(),
                                rated=True, player_name='BackupHost')
            guest_welcome = handshake(guest, 'join', game=GAME, room=welcome['room'],
                                      player_name='BackupGuest')
            assert guest_welcome['player_id'] != welcome['player_id']
            receive(host, predicate=lambda message: message['ready'])
            receive(guest, predicate=lambda message: message['ready'])
            command(guest, {'action': 'resign', 'args': [1]})
            decided = _settled(host)
            assert _settled(guest)['result'] == decided['result']
            result = decided['result']
            assert result['match_id'] == welcome['match_id'] and result['winner'] == 0
            room = welcome['room']
            host_token, guest_token = welcome['resume_token'], guest_welcome['resume_token']
            host_id, guest_id = welcome['player_id'], guest_welcome['player_id']
        host_profile = _get(http, f'/players/{host_id}?game={GAME}')
        guest_profile = _get(http, f'/players/{guest_id}?game={GAME}')
        board = _get(http, f'/ratings?game={GAME}')
        assert host_profile == {'player_id': host_id, 'name': 'BackupHost',
                                'rating': host_profile['rating'], 'games': 1, 'wins': 1, 'losses': 0}
        assert guest_profile == {'player_id': guest_id, 'name': 'BackupGuest',
                                 'rating': guest_profile['rating'], 'games': 1, 'wins': 0, 'losses': 1}
        assert host_profile['rating'] > 1500.0 > guest_profile['rating']
        assert [entry['player_id'] for entry in board['players']] == [host_id, guest_id]
        saved = backup(live_dir / 'rooms.sqlite3', backup_dir)
        assert stat.S_IMODE(saved.stat().st_mode) == 0o600
    fresh_dir.mkdir()
    shutil.copyfile(saved, fresh_dir / 'rooms.sqlite3')
    (fresh_dir / 'rooms.sqlite3').chmod(0o600)
    with running_server(SPEC, arguments=('--state-dir', str(fresh_dir))) as (url, _process):
        http = url.replace('ws://', 'http://')
        assert _get(http, f'/players/{host_id}?game={GAME}') == host_profile
        assert _get(http, f'/players/{guest_id}?game={GAME}') == guest_profile
        assert _get(http, f'/ratings?game={GAME}') == board
        with connect(url, proxy=None) as host, connect(url, proxy=None) as guest:
            resumed = handshake(host, 'resume', game=GAME, room=room, resume_token=host_token)
            handshake(guest, 'resume', game=GAME, room=room, resume_token=guest_token)
            assert _settled(host)['result'] == result
            assert _settled(guest)['result'] == result
            assert resumed['rating']['games'] == 1
        assert _get(http, f'/players/{host_id}?game={GAME}') == host_profile
        assert _get(http, f'/players/{guest_id}?game={GAME}') == guest_profile
