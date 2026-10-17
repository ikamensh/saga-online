/* Serve the real built site with public HTTP fixtures; never fabricate frontend DOM. */
const http = require('node:http');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '../..');

async function buildSite() {
  const temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'warband-browser-'));
  const site = path.join(temporary, 'site');
  const result = spawnSync('uv', ['run', '--project', 'publishing', '--locked', 'python', 'tools/build_site.py', '--output', site], { cwd: root, encoding: 'utf8' });
  if (result.status !== 0) throw new Error(result.stderr || result.stdout);
  return { site, cleanup: () => fs.rm(temporary, { recursive: true, force: true }) };
}

function players(count = 12) {
  const names = ['IronWarden', 'Moonwell', 'Stoneheart', 'AshenBanner', 'Wildwood', 'Grimhammer', 'Sunstrider', 'Thornwatch', 'Deepforge', 'Frostveil', 'Stormcaller', 'Oakshield'];
  return Array.from({ length: count }, (_, index) => ({
    player_id: `commander-${String(index + 1).padStart(3, '0')}`,
    name: names[index] || `Commander ${index + 1}`,
    rating: 1928 - index * 17,
    wins: 31 - index % 24,
    losses: 10 + index % 14,
    games: 41 - index % 24 + index % 14,
  }));
}

function activity(hours) {
  const end = Date.parse('2026-10-17T17:40:00Z');
  const samples = [];
  for (let minute = 0; minute < hours * 60; minute++) {
    // This unobserved interval must remain a gap, never become zero-valued data.
    if (minute > 260 && minute < 560) continue;
    const count = Math.max(0, Math.round(5 + 4 * Math.sin(minute / 79) + 3 * Math.cos(minute / 43)));
    samples.push({ timestamp: new Date(end - (hours * 60 - minute) * 60000).toISOString(), players: count, observers: count > 6 ? 1 : 0, rooms: Math.ceil(count / 3), ready_rooms: Math.floor(count / 4) });
  }
  return { game: 'warband-v2', hours, sample_interval_seconds: 60, server_time: new Date(end).toISOString(), collected_since: '2026-10-12T00:00:00Z', current: { players: 8, observers: 1, rooms: 3, ready_rooms: 2 }, samples };
}

async function serve(site, overrides = {}) {
  const state = { players: players(), requests: [], leaderboardStatus: 200, activityStatus: 200, emptyActivity: false, ...overrides };
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://localhost');
    state.requests.push(url);
    if (url.pathname === '/leaderboard' || url.pathname === '/activity') {
      const ranking = url.pathname === '/leaderboard';
      response.writeHead(ranking ? state.leaderboardStatus : state.activityStatus, { 'content-type': 'application/json' });
      if (ranking) {
        const q = (url.searchParams.get('q') || '').toLocaleLowerCase();
        const matching = state.players.filter(player => player.name.toLocaleLowerCase().includes(q) || player.player_id.toLocaleLowerCase().includes(q));
        const offset = Number(url.searchParams.get('offset') || 0);
        const limit = Number(url.searchParams.get('limit') || 100);
        response.end(JSON.stringify({ game: 'warband-v2', total: matching.length, players: matching.slice(offset, offset + limit) }));
      } else {
        const data = activity(Number(url.searchParams.get('hours') || 24));
        if (state.emptyActivity) data.samples = [];
        if (state.activitySamples) data.samples = state.activitySamples;
        response.end(JSON.stringify(data));
      }
      return;
    }
    try {
      const relative = url.pathname === '/' ? 'warband-online/index.html' : decodeURIComponent(url.pathname).replace(/^\/+/, '');
      const file = path.resolve(site, relative);
      if (!file.startsWith(site + path.sep)) throw new Error('Invalid path');
      const content = await fs.readFile(file);
      const mime = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.jpg': 'image/jpeg', '.woff2': 'font/woff2', '.ttf': 'font/ttf' }[path.extname(file)] || 'application/octet-stream';
      response.writeHead(200, { 'content-type': mime });
      response.end(content);
    } catch {
      response.writeHead(404);
      response.end('Not found');
    }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { state, url: `http://127.0.0.1:${server.address().port}`, close: () => new Promise(resolve => server.close(resolve)) };
}

module.exports = { buildSite, serve, players };

if (require.main === module) {
  (async () => {
    const build = await buildSite();
    const preview = await serve(build.site);
    console.log(preview.url);
    process.once('SIGTERM', async () => { await preview.close(); await build.cleanup(); process.exit(0); });
    process.once('SIGINT', async () => { await preview.close(); await build.cleanup(); process.exit(0); });
  })().catch(error => { console.error(error); process.exit(1); });
}
