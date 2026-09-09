"""Render the games website from the release catalog and website content.

    uv run python tools/build_site.py            # writes dist/site

The output is a plain static directory: HTML pages, the catalog as
/releases.json, inspected screenshots resized for the web, and the game font.
Publish it with ``tools/deploy_online.py site``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path

import saga2d
import shutil
from string import Template
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.release_catalog import CATALOG, load  # noqa: E402
from website.content import GAMES, SOURCE_URL, SUPPORT_URL  # noqa: E402

SITE = ROOT / 'website'
FONTS = Path(saga2d.__file__).resolve().parent / 'assets' / 'fonts'
OS_NAMES = {'windows': 'Windows', 'macos': 'Mac', 'linux': 'Linux'}
ARCH_NAMES = {'x64': '64-bit', 'arm64': 'Apple Silicon'}
KIND_NAMES = {'installer': 'installer', 'portable-zip': 'portable ZIP', 'app-zip': 'app', 'dmg': 'disk image'}


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def megabytes(size: int) -> str:
    return f'{size / 1048576:.0f} MB' if size else ''


def render(template: str, **fields) -> str:
    return Template((SITE / 'templates' / template).read_text(encoding='utf-8')).substitute(fields)


def page(output: Path, path: str, *, title, description, content, site, names, active=None, built):
    nav = ''.join(f'<a href="/{slug}/"{" aria-current=page" if slug == active else ""}>{esc(name)}</a>'
                  for slug, name in names.items()) + f'<a href="/status/"{" aria-current=page" if active == "status" else ""}>Status</a>'
    document = render('base.html', title=esc(title), description=esc(description), canonical=esc(site + path),
                      nav=nav, content=content, source_url=SOURCE_URL, support_url=SUPPORT_URL, built=built)
    target = output / path.strip('/') / 'index.html' if path.endswith('/') else output / path.strip('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding='utf-8')
    return target


def convert_images(slug: str, screenshots, output: Path):
    """Resize inspected evidence frames to web sizes; the first is the game's cover."""
    folder = output / 'images' / slug
    folder.mkdir(parents=True, exist_ok=True)
    rendered = []
    for index, (source, alt) in enumerate(screenshots):
        image = Image.open(ROOT / source).convert('RGB')
        names = {}
        for suffix, width in (('', 1280), ('-thumb', 640)):
            copy = image.copy()
            copy.thumbnail((width, width * 10))
            name = f'{index + 1:02d}{suffix}.jpg'
            copy.save(folder / name, 'JPEG', quality=85, optimize=True, progressive=True)
            names[suffix] = f'/images/{slug}/{name}'
        rendered.append({'full': names[''], 'thumb': names['-thumb'], 'alt': alt, 'source': source})
    return rendered


def package_buttons(game, packages):
    """Installers and apps first, one button per package, in catalog order otherwise."""
    buttons = []
    for pkg in sorted(packages, key=lambda item: item['kind'] not in ('installer', 'app-zip')):
        primary = pkg['kind'] in ('installer', 'app-zip')
        detail = ' · '.join(part for part in (KIND_NAMES[pkg['kind']], megabytes(pkg['bytes']), game['version']) if part)
        buttons.append(f'<a class="button{" primary" if primary else ""}" href="{esc(pkg["url"])}" data-os="{pkg["os"]}">'
                       f'<span>Download for {OS_NAMES[pkg["os"]]} · {ARCH_NAMES[pkg["arch"]]}</span>'
                       f'<small>{esc(detail)}</small><small class="for-you-hint"></small></a>')
    return ''.join(buttons)


def package_table(packages):
    rows = ''.join(
        f'<tr><td><a href="{esc(pkg["url"])}">{esc(pkg["file"])}</a></td>'
        f'<td>{OS_NAMES[pkg["os"]]} {ARCH_NAMES[pkg["arch"]]}, {KIND_NAMES[pkg["kind"]]}</td>'
        f'<td>{esc(pkg["min_os"])}</td><td>{megabytes(pkg["bytes"])}</td>'
        f'<td>{"Yes" if pkg["signed"] else "No"}</td><td><code>{pkg["sha256"]}</code></td></tr>'
        for pkg in packages)
    return ('<div class="table-wrap"><table><thead><tr><th>File</th><th>Platform</th><th>Minimum OS</th>'
            f'<th>Size</th><th>Signed</th><th>SHA-256</th></tr></thead><tbody>{rows}</tbody></table></div>')


def install_steps(name, packages):
    has = {pkg['os'] for pkg in packages}
    signed = {pkg['os']: pkg['signed'] for pkg in packages if pkg['kind'] in ('installer', 'app-zip')}
    windows = ''
    if 'windows' in has:
        windows = (f'<h3>Windows</h3><ol class="steps">'
                   f'<li>Download the installer above and open the file when the download finishes.</li>'
                   f'<li>Follow the installer with its default folder. It installs for your Windows account only; no administrator password or Python is needed.</li>'
                   f'<li>Leave <b>Play {esc(name)}</b> selected on the last page, or open Start and type <b>{esc(name)}</b> later.</li></ol>')
        if not signed.get('windows', True):
            windows += ('<div class="note"><b>Unsigned preview.</b> If Windows shows <b>Windows protected your PC</b>, choose '
                        '<b>More info → Run anyway</b>. That prompt appears because this preview build is not yet code-signed; '
                        'check the SHA-256 below if you want to verify the file. PCs with Smart App Control may refuse unsigned apps entirely.</div>')
    mac = ''
    if 'macos' in has:
        mac = (f'<h3>Mac (Apple Silicon)</h3><ol class="steps">'
               f'<li>Download the Mac app above. In Finder, open Downloads and double-click the ZIP to extract <b>{esc(name)}.app</b>.</li>'
               f'<li>Drag <b>{esc(name)}.app</b> into <b>Applications</b>. Replace an older copy when updating; your saves and settings are kept.</li>'
               f'<li>Double-click <b>{esc(name)}.app</b> to play.</li></ol>')
        if not signed.get('macos', True):
            mac += ('<div class="note"><b>Not yet notarized.</b> If macOS says it cannot verify the developer, open '
                    '<b>System Settings → Privacy &amp; Security</b>, scroll to the message about the app, choose <b>Open Anyway</b> and confirm. '
                    'This is needed once per version.</div>')
    return f'<div class="two-col"><div>{windows}</div><div>{mac}</div></div>'


def online_steps(name, slug, online, site):
    menu = 'Co-op' if slug == 'shardbound' else 'Multiplayer'
    return (f'<p>{esc(online["text"])}</p><div class="two-col"><div><h3>Create a room</h3><ol class="steps">'
            f'<li>Open <b>{esc(name)}</b> and choose <b>{menu}</b>. Leave <b>Online</b> selected.</li>'
            f'<li>Choose <b>Create room</b>, then <b>Copy invite link</b> and send it to your friend in any chat.</li>'
            f'<li>Stay on the waiting screen. The game starts when your friend connects.</li></ol></div>'
            f'<div><h3>Join a room</h3><ol class="steps">'
            f'<li>Open the invite link your friend sent, or copy just the room code from it.</li>'
            f'<li>In <b>{menu}</b> choose <b>Paste code</b>, then <b>Join room</b>.</li>'
            f'<li>Lost your connection? Reopen the game on the same computer and choose <b>Rejoin last room</b>.</li></ol></div></div>'
            f'<p class="download-note">{esc(online["retention"])} Invite links look like '
            f'<code>{esc(site)}/join/{esc(slug)}-v1/abc123</code> and contain only the game and room code, never your private seat.</p>')


def game_page(slug, entry, content, images, site):
    name = entry['name']
    released = bool(entry['packages'])
    pill = (f'<span class="pill {entry["channel"]}">{entry["channel"]} {esc(entry["version"])}</span>' if released
            else '<span class="pill soon">Download coming soon</span>')
    head = (f'<div class="game-head"><div><h1>{esc(name)}</h1><p class="tagline">{esc(content["tagline"])}</p>'
            f'<p>{esc(content["summary"])}</p><p class="meta">{pill}'
            + (f' <span>Released <b>{esc(entry["released"])}</b></span> <span>Source <b>{entry["source_commit"][:12]}</b></span>' if released else '')
            + f'</p></div><img src="{images[0]["full"]}" alt="{esc(images[0]["alt"])}" width="1280" height="800"></div>')
    if released:
        downloads = (f'<section class="downloads" id="download"><h2>Download {esc(name)} {esc(entry["version"])}</h2>'
                     f'<div class="download-row">{package_buttons(entry, entry["packages"])}</div>'
                     f'<p class="download-note">Free, no account needed. Everything the game needs is included; Python is not required. '
                     f'Release notes: <a href="{esc(entry["notes"])}">{esc(name)} {esc(entry["version"])}</a>.</p>'
                     f'<details><summary>All files and checksums</summary>{package_table(entry["packages"])}</details></section>'
                     f'<h2 id="install">Install</h2>{install_steps(name, entry["packages"])}')
    else:
        downloads = (f'<section class="downloads" id="download"><h2>No download yet</h2>'
                     f'<p>{esc(name)} does not have a published installer yet. It runs from the '
                     f'<a href="{SOURCE_URL}">source repository</a> with <code>uv run python -m {esc({"shardbound": "eador"}.get(slug, slug))}</code>, '
                     f'including its online mode. This page will list the installer when a release passes acceptance.</p></section>')
    online = f'<h2 id="online">Play online: {esc(content["online"]["mode"]).lower()}</h2>' + online_steps(name, slug, content['online'], site)
    first = '<h2>Your first match</h2><ol class="steps">' + ''.join(f'<li>{esc(step)}</li>' for step in content['first_match']) + '</ol>'
    gallery = '<h2>Screenshots</h2><div class="gallery">' + ''.join(
        f'<figure><a href="{img["full"]}"><img src="{img["thumb"]}" alt="{esc(img["alt"])}" loading="lazy" width="640" height="400"></a>'
        f'<figcaption>{esc(img["alt"])}</figcaption></figure>' for img in images) + '</div>'
    features = '<h2>What is in the game</h2><ul class="features">' + ''.join(f'<li>{esc(f)}</li>' for f in content['features']) + '</ul>'
    requirements = ('<div><h2>Requirements</h2><ul class="features">'
                    + ''.join(f'<li><b>{OS_NAMES[os]}:</b> {esc(text)}</li>' for os, text in content['requirements'].items())
                    + f'<li><b>Online play:</b> an internet connection; both players need the same version.</li></ul></div>')
    issues = '<div><h2>Known issues</h2><ul class="features">' + ''.join(f'<li>{esc(i)}</li>' for i in content['known_issues']) + '</ul></div>'
    support = (f'<div><h2>Help and data</h2><ul class="features">'
               f'<li><a href="{esc(content["guide"])}">Player guide</a> and <a href="{SUPPORT_URL}">issue tracker</a>. Include the game version, your OS and the exact message.</li>'
               f'<li>Saves and settings live in <code>{esc(content["data_dir"]["windows"])}</code> on Windows and <code>{esc(content["data_dir"]["macos"])}</code> on a Mac. Uninstalling keeps them; delete the folder to reset.</li>'
               f'<li>Online rooms store only the match state and two private seat tokens; nothing identifies you beyond your IP address while connected.</li>'
               f'<li>Free and open source under the MIT license (<a href="{SOURCE_URL}">source</a>). Nunito font under the SIL Open Font License.</li></ul></div>')
    return head + downloads + online + first + gallery + features + f'<div class="section-grid">{requirements}{issues}{support}</div>'


def index_page(catalog, images):
    cards = []
    for slug, entry in catalog['games'].items():
        content = GAMES[slug]
        released = bool(entry['packages'])
        platforms = ' · '.join(sorted({f'{OS_NAMES[p["os"]]} {ARCH_NAMES[p["arch"]]}' for p in entry['packages']})) if released else 'Source only for now'
        action = (f'<a class="button primary" href="/{slug}/#download">Download {esc(entry["version"])}</a>' if released
                  else f'<a class="button soon" href="/{slug}/">Coming soon</a>')
        cards.append(f'<article class="card"><a href="/{slug}/"><img src="{images[slug][0]["thumb"]}" alt="{esc(images[slug][0]["alt"])}" width="640" height="400"></a>'
                     f'<div class="card-body"><h2><a href="/{slug}/">{esc(entry["name"])}</a></h2><p class="tagline">{esc(content["tagline"])}</p>'
                     f'<p class="meta"><span><b>Online:</b> {esc(content["online"]["mode"])}</span><span><b>Platforms:</b> {esc(platforms)}</span></p>'
                     f'<div class="actions">{action}<a class="button" href="/{slug}/">About the game</a></div></div></article>')
    hero = ('<section class="hero"><h1>Three small strategy games. Install one, invite a friend.</h1>'
            '<p class="lede">Free downloads for Windows and Mac. Each game connects to the same online service: create a room, '
            'share the invite link, and play from different networks with no account, port forwarding or launcher.</p>'
            '<ul class="journey"><li data-step="1">Choose a game</li><li data-step="2">Download and install</li>'
            '<li data-step="3">Multiplayer → Create room</li><li data-step="4">Send the invite link</li><li data-step="5">Play</li></ul></section>')
    return hero + '<div class="cards">' + ''.join(cards) + '</div>'


def join_page():
    return ('<section class="invite" id="invite"><h1 id="invite-title">Loading your invitation…</h1>'
            '<div id="invite-body"><p class="muted">Reading the room code from this link.</p></div></section>')


def status_page(catalog):
    rows = ''.join(f'<tr><td><a href="/{slug}/">{esc(entry["name"])}</a></td><td>{esc(entry["version"] or "not published")}</td>'
                   f'<td>{esc(entry["channel"] or "—")}</td><td>{esc(entry["released"] or "—")}</td></tr>'
                   for slug, entry in catalog['games'].items())
    return (f'<h1>Service status</h1><p class="status-line" id="service-status"><span class="dot"></span><span class="status-text">Checking the online service…</span></p>'
            f'<p>Games connect to <code>{esc(catalog["server"]["endpoint"])}</code>, a single server in Paris. Rooms have two seats; '
            f'match rooms expire after 15 minutes without both players and Shardbound campaign rooms after 7 days.</p>'
            f'<h2>Current releases</h2><div class="table-wrap"><table><thead><tr><th>Game</th><th>Version</th><th>Channel</th><th>Released</th></tr></thead><tbody>{rows}</tbody></table></div>'
            f'<p class="muted">Installed games check <a href="/releases.json">this catalog</a> when you open Multiplayer and offer the download page if a newer version exists. Both players need the same version.</p>'
            '<h2>If something goes wrong</h2><div class="table-wrap"><table><thead><tr><th>What you see</th><th>What to do</th></tr></thead><tbody>'
            '<tr><td>Cannot reach the online server</td><td>Check your internet connection and this page. If the dot above is red, the service is down; offline play still works.</td></tr>'
            '<tr><td>Update your game client</td><td>Your version is no longer compatible. Install the current release from the game page; saves are kept.</td></tr>'
            '<tr><td>Room not found for this game</td><td>The code was mistyped or the room expired. Ask for a fresh invite link.</td></tr>'
            '<tr><td>Both seats are claimed</td><td>Use <b>Rejoin last room</b> on the computer that originally joined instead of entering the code again.</td></tr>'
            '<tr><td>The server is full</td><td>Capacity is limited while the service is small (32 rooms). Wait a few minutes and create the room again.</td></tr>'
            '</tbody></table></div>'
            '<h2>Capacity</h2><p>The service holds up to 32 rooms and admits four new rooms per minute from one address. '
            'A bounded check on 2026-09-08 ran four simultaneous Warband matches for 90 seconds with orders from all eight seats: '
            'the simulation held 19.4 to 19.6 ticks per second against its 20 Hz target, state updates arrived every 98 ms at the median '
            'and 124 ms at the 95th percentile, and the health endpoint answered within 91 to 170 ms from Western Europe. '
            'Two Tribes rooms and Shardbound co-op rooms were checked the same way. This describes a small friendly load, not a capacity guarantee.</p>'
            '<h2>Data and retention</h2><p>The service stores each room\'s game state and two private seat tokens until the room expires, then deletes them. '
            'Logs keep connection errors for a short time. No accounts, names or chat exist. Downloads are served from GitHub releases and this site.</p>')


def build(output: Path, catalog_path: Path = CATALOG) -> dict:
    catalog = load(catalog_path)
    if set(catalog['games']) != set(GAMES):
        raise ValueError(f'Website content covers {sorted(GAMES)} but the catalog lists {sorted(catalog["games"])}')
    names = {slug: entry['name'] for slug, entry in catalog['games'].items()}
    site = catalog['site']
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    shutil.copytree(SITE / 'static', output / 'static')
    (output / 'fonts').mkdir()
    for font in FONTS.iterdir():
        shutil.copyfile(font, output / 'fonts' / font.name)
    (output / 'releases.json').write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')
    built = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    images = {slug: convert_images(slug, GAMES[slug]['screenshots'], output) for slug in catalog['games']}
    pages = [page(output, '/', title='Saga2D Games', description='Free strategy games for Windows and Mac with online play by invitation.',
                  content=index_page(catalog, images), site=site, names=names, built=built)]
    for slug, entry in catalog['games'].items():
        pages.append(page(output, f'/{slug}/', title=f'{entry["name"]} — download and play online',
                          description=GAMES[slug]['tagline'], content=game_page(slug, entry, GAMES[slug], images[slug], site),
                          site=site, names=names, active=slug, built=built))
    pages.append(page(output, '/join/', title='Join a room', description='Join a friend\'s online room.',
                      content=join_page(), site=site, names=names, built=built))
    pages.append(page(output, '/status/', title='Service status', description='Online service status, current releases and troubleshooting.',
                      content=status_page(catalog), site=site, names=names, active='status', built=built))
    pages.append(page(output, '/404.html', title='Page not found', description='Page not found.',
                      content='<h1>Page not found</h1><p>That address does not exist. <a href="/">See the games</a>.</p>', site=site, names=names, built=built))
    return {'output': str(output), 'pages': [str(p.relative_to(output)) for p in pages],
            'images': {slug: [img['full'] for img in items] for slug, items in images.items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist' / 'site')
    parser.add_argument('--catalog', type=Path, default=CATALOG)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve(), args.catalog), indent=2))


if __name__ == '__main__':
    main()
