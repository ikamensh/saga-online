"""The published release catalog: one JSON consumed by the website and the games.

    uv run python tools/release_catalog.py            # validate releases/catalog.json

Each game lists its online ids, the current accepted release and immutable
package facts. Versioned binaries are never overwritten; a new release replaces
the entry after acceptance.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'releases' / 'catalog.json'
CATALOG_VERSION = 1
CHANNELS = ('preview', 'stable')
PLATFORMS = {('windows', 'x64'), ('macos', 'arm64'), ('macos', 'x64'), ('linux', 'x64')}
KINDS = ('installer', 'portable-zip', 'app-zip', 'dmg')
VERSION = re.compile(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?')
SLUG = re.compile(r'[a-z][a-z0-9-]*')
GAME_ID = re.compile(r'[a-z][a-z0-9-]*-v[1-9]\d*')


def _https(value, name):
    parsed = urlsplit(value) if isinstance(value, str) else None
    if parsed is None or parsed.scheme != 'https' or not parsed.netloc or parsed.fragment:
        raise ValueError(f'{name} must be an https URL')


def _package(game, package):
    fields = {'os', 'arch', 'kind', 'file', 'url', 'bytes', 'sha256', 'min_os', 'signed'}
    if not isinstance(package, dict) or set(package) != fields:
        raise ValueError(f'{game}: package fields must be exactly {sorted(fields)}')
    if (package['os'], package['arch']) not in PLATFORMS:
        raise ValueError(f'{game}: unsupported platform {package["os"]}/{package["arch"]}')
    if package['kind'] not in KINDS:
        raise ValueError(f'{game}: unknown package kind {package["kind"]}')
    if not isinstance(package['file'], str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', package['file']):
        raise ValueError(f'{game}: package file must be a plain file name')
    _https(package['url'], f'{game}: package url')
    if not package['url'].endswith('/' + package['file']):
        raise ValueError(f'{game}: package url must end with its file name')
    if type(package['bytes']) is not int or package['bytes'] < 0:
        raise ValueError(f'{game}: package bytes must be a non-negative integer')
    if not isinstance(package['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', package['sha256']):
        raise ValueError(f'{game}: package sha256 must be 64 lowercase hex digits')
    if not isinstance(package['min_os'], str) or not package['min_os']:
        raise ValueError(f'{game}: package min_os is required')
    if type(package['signed']) is not bool:
        raise ValueError(f'{game}: package signed must be true or false')


def validate(catalog):
    """Raise ValueError describing the first problem; return the catalog otherwise."""
    if not isinstance(catalog, dict) or catalog.get('catalog_version') != CATALOG_VERSION:
        raise ValueError(f'catalog_version must be {CATALOG_VERSION}')
    if set(catalog) != {'catalog_version', 'site', 'server', 'games'}:
        raise ValueError('catalog fields must be exactly catalog_version, site, server and games')
    _https(catalog['site'], 'site')
    server = catalog['server']
    if (not isinstance(server, dict) or set(server) != {'endpoint', 'protocol'}
            or not isinstance(server['endpoint'], str) or urlsplit(server['endpoint']).scheme != 'wss'
            or type(server['protocol']) is not int or server['protocol'] < 1):
        raise ValueError('server must give a wss endpoint and a positive protocol number')
    games = catalog['games']
    if not isinstance(games, dict) or not games:
        raise ValueError('games must be a non-empty object keyed by slug')
    seen_ids = set()
    for slug, game in games.items():
        if not SLUG.fullmatch(slug):
            raise ValueError(f'game slug {slug!r} must be lowercase letters, digits and hyphens')
        fields = {'name', 'game_ids', 'channel', 'version', 'source_commit', 'released', 'notes', 'packages'}
        if not isinstance(game, dict) or set(game) != fields:
            raise ValueError(f'{slug}: game fields must be exactly {sorted(fields)}')
        if not isinstance(game['name'], str) or not game['name']:
            raise ValueError(f'{slug}: name is required')
        ids = game['game_ids']
        if (not isinstance(ids, list) or not ids or any(not isinstance(i, str) or not GAME_ID.fullmatch(i) for i in ids)
                or seen_ids & set(ids)):
            raise ValueError(f'{slug}: game_ids must be a unique list of ids such as {slug}-v1')
        seen_ids.update(ids)
        if not isinstance(game['packages'], list):
            raise ValueError(f'{slug}: packages must be a list')
        if game['packages']:
            if game['channel'] not in CHANNELS:
                raise ValueError(f'{slug}: a released game needs a channel from {CHANNELS}')
            if not isinstance(game['version'], str) or not VERSION.fullmatch(game['version']):
                raise ValueError(f'{slug}: a released game needs a MAJOR.MINOR.PATCH version')
            if not isinstance(game['source_commit'], str) or not re.fullmatch(r'[0-9a-f]{40}', game['source_commit']):
                raise ValueError(f'{slug}: a released game needs its full source commit')
            if not isinstance(game['released'], str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', game['released']):
                raise ValueError(f'{slug}: released must be a YYYY-MM-DD date')
            if game['notes'] is not None:
                _https(game['notes'], f'{slug}: notes')
            platforms = set()
            for package in game['packages']:
                _package(slug, package)
                key = (package['os'], package['arch'], package['kind'])
                if key in platforms:
                    raise ValueError(f'{slug}: duplicate package for {key}')
                platforms.add(key)
                if game['version'] not in package['file']:
                    raise ValueError(f'{slug}: package {package["file"]} does not carry version {game["version"]}')
        elif any(game[field] is not None for field in ('channel', 'version', 'source_commit', 'released', 'notes')):
            raise ValueError(f'{slug}: an unreleased game must leave its release fields null')
    return catalog


def load(path=CATALOG):
    return validate(json.loads(Path(path).read_text(encoding='utf-8')))


def save(catalog, path=CATALOG):
    validate(catalog)
    Path(path).write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    catalog = load(Path(sys.argv[1]) if len(sys.argv) > 1 else CATALOG)
    for slug, game in catalog['games'].items():
        print(f"{slug}: {game['version'] or 'unreleased'} ({len(game['packages'])} packages)")
