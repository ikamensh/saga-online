"""The committed catalog is valid and its validator rejects the mistakes that matter."""
import copy
import json

import pytest

from tools.release_catalog import CATALOG, load, save, validate


def test_committed_catalog_lists_every_game_with_immutable_package_facts():
    catalog = load()
    assert set(catalog['games']) == {'warband', 'tribes', 'shardbound'}
    assert catalog['server']['endpoint'] == 'wss://games.tachyon-ai.eu/play'
    warband = catalog['games']['warband']
    assert warband['version'] and warband['packages']
    assert {(p['os'], p['arch']) for p in warband['packages']} >= {('windows', 'x64'), ('macos', 'arm64')}


@pytest.mark.parametrize('change, fragment', [
    (lambda c: c['games']['warband']['packages'][0].update(sha256='abc'), 'sha256'),
    (lambda c: c['games']['warband']['packages'][0].update(url='http://example.test/x.exe'), 'https'),
    (lambda c: c['games']['warband']['packages'][0].update(file='other.exe'), 'end with its file name'),
    (lambda c: c['games']['warband'].update(version=None), 'version'),
    (lambda c: c['games']['warband'].update(source_commit='85becd0'), 'source commit'),
    (lambda c: c['games']['tribes'].update(version='0.1.0'), 'unreleased'),
    (lambda c: c['games']['tribes'].update(game_ids=['warband-v1']), 'unique'),
    (lambda c: c['games'].update({'Bad Slug': c['games']['tribes']}), 'slug'),
    (lambda c: c['games']['warband']['packages'].append(dict(c['games']['warband']['packages'][0])), 'duplicate'),
    (lambda c: c['games']['warband']['packages'][0].pop('signed'), 'exactly'),
    (lambda c: c.update(server={'endpoint': 'ws://games.tachyon-ai.eu/play', 'protocol': 1}), 'wss'),
])
def test_validation_names_the_first_problem(change, fragment):
    catalog = copy.deepcopy(load())
    change(catalog)
    with pytest.raises(ValueError, match=fragment):
        validate(catalog)


def test_save_round_trips_and_refuses_invalid_catalogs(tmp_path):
    catalog = load()
    target = tmp_path / 'catalog.json'
    save(catalog, target)
    assert json.loads(target.read_text()) == json.loads(CATALOG.read_text())
    broken = copy.deepcopy(catalog)
    broken['games']['warband']['packages'][0]['bytes'] = -1
    with pytest.raises(ValueError, match='bytes'):
        save(broken, target)
    assert json.loads(target.read_text()) == catalog
