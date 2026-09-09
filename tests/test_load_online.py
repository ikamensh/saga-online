"""The bounded load check drives every game with valid orders through real sockets."""
import pytest

from tools.load_online import run
from saga2d.packaging.verify import local_server

GAMES = ('tribes.multiplayer:ONLINE', 'warband.multiplayer:ONLINE', 'eador.multiplayer:ONLINE')


@pytest.mark.parametrize('game', ['tribes', 'warband', 'shardbound'])
def test_load_check_reports_ready_rooms_orders_and_state_cadence(game):
    with local_server(*GAMES) as endpoint:
        report = run(endpoint, game, rooms=1, seconds=2.5)
    assert len(report['rooms']) == 1 and report['seats'] == 2 and report['disconnects'] == 0
    assert report['orders_sent'] >= 2 and report['order_errors'] == 0, report
    assert report['state_updates'] >= 2 and report['health_ms']
    if game == 'warband':
        assert 15 <= report['simulation_ticks_per_second']['min'] <= 21
        assert report['state_gap_ms']['p50'] < 200
