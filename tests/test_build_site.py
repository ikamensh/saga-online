"""The website is generated from the catalog and shows real release facts per game."""
import json
from pathlib import Path

from tools.build_site import build
from tools.release_catalog import load


def test_site_pages_reflect_the_catalog_and_content(tmp_path):
    output = tmp_path / 'site'
    manifest = build(output)
    catalog = load()
    assert json.loads((output / 'releases.json').read_text()) == catalog
    assert set(manifest['pages']) == {'index.html', 'warband/index.html', 'tribes/index.html', 'shardbound/index.html',
                                      'join/index.html', 'status/index.html', '404.html'}
    warband = (output / 'warband/index.html').read_text()
    for package in catalog['games']['warband']['packages']:
        assert package['url'] in warband and package['sha256'] in warband
    assert 'Copy invite link' in warband and 'games.tachyon-ai.eu/join/warband-v1/' in warband
    assert 'Unsigned preview' in warband and 'Not yet notarized' in warband
    tribes = (output / 'tribes/index.html').read_text()
    for package in catalog['games']['tribes']['packages']:
        assert package['url'] in tribes
    released = [slug for slug, game in catalog['games'].items() if game['packages']]
    unreleased = [slug for slug, game in catalog['games'].items() if not game['packages']]
    for slug in unreleased:
        page = (output / slug / 'index.html').read_text()
        assert 'No download yet' in page and 'python -m ' in page
    shardbound = (output / 'shardbound/index.html').read_text()
    assert 'kept for seven days' in shardbound
    index = (output / 'index.html').read_text()
    for slug in released:
        assert f"Download {catalog['games'][slug]['version']}" in index
    assert index.count('Coming soon') == len(unreleased)
    for slug, images in manifest['images'].items():
        assert images, slug
        for image in images:
            assert (output / image.lstrip('/')).stat().st_size > 10_000
            assert (output / image.lstrip('/').replace('.jpg', '-thumb.jpg')).is_file()
    assert (output / 'fonts/Nunito.ttf').is_file() and (output / 'fonts/OFL.txt').is_file()
    assert (output / 'static/site.js').is_file() and (output / 'static/site.css').is_file()
    join = (output / 'join/index.html').read_text()
    assert 'id="invite"' in join and '/static/site.js' in join


def test_untrusted_catalog_text_is_escaped(tmp_path):
    """Catalog strings reach pages through escaping; a stray tag never becomes markup."""
    catalog = load()
    catalog['games']['warband']['notes'] = 'https://example.test/notes?<script>'
    path = tmp_path / 'catalog.json'
    path.write_text(json.dumps(catalog))
    build(tmp_path / 'site', path)
    page = (tmp_path / 'site/warband/index.html').read_text()
    assert '<script>' not in page.replace('<script src="/static/site.js" defer></script>', '')
    assert '&lt;script&gt;' in page
