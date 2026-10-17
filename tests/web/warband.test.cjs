/* Browser journeys exercise the published HTML and its real JavaScript over HTTP.
 * Fixture APIs represent public server replies, so markup/layout can change freely.
 */
const assert = require('node:assert/strict');
const { test, before, after } = require('node:test');
const { chromium } = require('playwright');
const { buildSite, serve, players } = require('./fixture-server.cjs');

let build, browser;
before(async () => {
  build = await buildSite();
  browser = await chromium.launch();
});
after(async () => {
  if (browser) await browser.close();
  if (build) await build.cleanup();
});

async function journey(t, state = {}, viewport = { width: 1440, height: 1000 }) {
  const server = await serve(build.site, state);
  const page = await browser.newPage({ viewport, locale: 'en-GB', timezoneId: 'UTC' });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  t.after(async () => {
    await page.close();
    await server.close();
    assert.deepEqual(errors, [], 'The public page must not throw JavaScript exceptions');
  });
  return { page, ...server };
}

// A public ladder may grow beyond its first API page, and names are untrusted text.
test('players can paginate all rankings and search the server without executing player names', async t => {
  const roster = players(205);
  roster[0].name = '<img src=x onerror="alert(1)">';
  const { page, url, state } = await journey(t, { players: roster });
  await page.goto(url);
  await page.getByText('1–100 of 205', { exact: true }).waitFor();
  assert.equal(await page.locator('#ranking-rows tr').count(), 100);
  assert.match(await page.locator('#ranking-rows tr').first().innerText(), /<img src=x onerror="alert\(1\)">/);
  assert.equal(await page.locator('#ranking-rows img').count(), 0);
  // Three clicks in one event turn must not skip beyond the available ladder.
  await page.getByRole('button', { name: 'Next players' }).evaluate(button => { button.click(); button.click(); button.click(); });
  await page.getByText('101–200 of 205', { exact: true }).waitFor();
  assert.equal(state.requests.filter(url => url.pathname === '/leaderboard' && url.searchParams.get('offset') === '100').length, 1);
  assert.match(await page.locator('#ranking-rows tr').first().innerText(), /commander-101/);
  await page.getByRole('button', { name: 'Next players' }).click();
  await page.getByText('201–205 of 205', { exact: true }).waitFor();
  assert.equal(await page.locator('#ranking-rows tr').count(), 5);
  assert.equal(await page.getByRole('button', { name: 'Next players' }).isDisabled(), true);
  await page.getByRole('button', { name: 'Previous players' }).click();
  await page.getByText('101–200 of 205', { exact: true }).waitFor();
  const response = page.waitForResponse(response => response.url().includes('/leaderboard?') && new URL(response.url()).searchParams.get('q') === '<img');
  await page.getByRole('searchbox').fill('<img');
  await response;
  await page.getByText('1–1 of 1', { exact: true }).waitFor();
  assert.equal(await page.locator('#ranking-rows tr').count(), 1);
  const request = state.requests.filter(url => url.pathname === '/leaderboard').at(-1);
  assert.equal(request.searchParams.get('q'), '<img');
  assert.equal(request.searchParams.get('offset'), '0');
  assert.equal(request.searchParams.get('game'), 'warband-v2');
});

// An early-access server has no completed games or observations on first start.
test('empty rankings and missing history explain how data will appear', async t => {
  const { page, url } = await journey(t, { players: [], emptyActivity: true });
  await page.goto(url);
  await page.getByText('The ladder is waiting. Complete a ranked match to appear here.', { exact: true }).waitFor();
  await page.getByText('No observations in this period. History appears as the server records activity.', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: 'Next players' }).isDisabled(), true);
  assert.equal(await page.locator('#online-count').innerText(), '8');
  assert.equal(await page.locator('#peak-count').innerText(), '—');
  await page.getByRole('searchbox').fill('Nobody');
  await page.getByText('No ranked players match your search.', { exact: true }).waitFor();
});

// A transient outage must not silently replace a successful observation with zero.
test('failed periodic refresh preserves the last successful rankings and activity', async t => {
  const { page, url, state } = await journey(t);
  await page.clock.install();
  await page.goto(url);
  await page.getByText('1–12 of 12', { exact: true }).waitFor();
  await page.locator('#activity-chart svg').waitFor();
  const rows = await page.locator('#ranking-rows').innerText();
  const chart = await page.locator('#activity-chart svg').getAttribute('viewBox');
  state.leaderboardStatus = 503;
  state.activityStatus = 503;
  await page.clock.fastForward(60000);
  await page.getByText(/The table shows the last successful update/).waitFor();
  await page.getByText(/Counts and history show the last successful update/).waitFor();
  assert.equal(await page.locator('#ranking-rows').innerText(), rows);
  assert.equal(await page.locator('#online-count').innerText(), '8');
  assert.equal(await page.locator('#activity-chart svg').getAttribute('viewBox'), chart);
  state.leaderboardStatus = 200;
  state.activityStatus = 200;
  await page.clock.fastForward(60000);
  await page.locator('#ranking-error').waitFor({ state: 'hidden' });
  await page.locator('#activity-error').waitFor({ state: 'hidden' });
  assert.equal(state.requests.filter(url => url.pathname === '/leaderboard').length, 3);
});

// Failure before any response has no retained values; communicate that explicitly.
test('first-load server errors show unavailable states and recover on the next refresh', async t => {
  const { page, url, state } = await journey(t, { leaderboardStatus: 503, activityStatus: 503 });
  await page.clock.install();
  await page.goto(url);
  await page.getByText('Could not load ranked players.', { exact: true }).waitFor();
  await page.getByText('Could not load server activity.', { exact: true }).waitFor();
  assert.equal(await page.locator('#online-count').innerText(), '—');
  assert.doesNotMatch(await page.locator('#ranking-error').innerText(), /last successful/);
  state.leaderboardStatus = 200;
  state.activityStatus = 200;
  await page.clock.fastForward(60000);
  await page.getByText('1–12 of 12', { exact: true }).waitFor();
  await page.locator('#activity-chart svg').waitFor();
  assert.equal(await page.locator('#online-count').innerText(), '8');
});

// Missing observations are unknown time, so the drawn line must visibly break.
test('activity range requests seven days and leaves observation gaps undrawn', async t => {
  const samples = [
    { timestamp: '2026-10-17T16:00:00Z', players: 3, observers: 0, rooms: 1 },
    { timestamp: '2026-10-17T16:01:00Z', players: 4, observers: 1, rooms: 2 },
    { timestamp: '2026-10-17T17:00:00Z', players: 7, observers: 1, rooms: 3 },
    { timestamp: '2026-10-17T17:01:00Z', players: 8, observers: 1, rooms: 3 },
  ];
  const { page, url, state } = await journey(t, { activitySamples: samples });
  await page.goto(url);
  await page.locator('#activity-chart svg').waitFor();
  const lines = page.locator('#activity-chart svg polyline');
  assert.equal(await lines.count(), 2, 'No line should bridge the hour with no observations');
  for (const line of await lines.all()) {
    const points = (await line.getAttribute('points')).split(' ');
    assert.equal(points.length, 2, 'Only observed samples belong to each line segment');
    for (const point of points) assert.ok(Number(point.split(',')[1]) < 195, 'No fictional zero is inserted at the gap');
  }
  // Inspect the visible point itself, including after the page changes width.
  async function hoverFirstObservation() {
    const firstSegment = page.locator('#activity-chart svg polyline').first();
    await firstSegment.scrollIntoViewIfNeeded();
    const box = await firstSegment.boundingBox();
    await page.mouse.move(box.x, box.y + box.height);
    await page.getByText('17 Oct 2026, 16:00 — 3 players · 0 spectators · 1 rooms', { exact: true }).waitFor();
  }
  await hoverFirstObservation();
  await page.setViewportSize({ width: 375, height: 812 });
  await page.waitForFunction(() => document.querySelector('#activity-chart svg').viewBox.baseVal.width < 375);
  const resizedLabel = await page.locator('#activity-chart svg text').first().boundingBox();
  assert.ok(resizedLabel && resizedLabel.height >= 7, 'A resized desktop chart must keep phone labels readable');
  await hoverFirstObservation();
  const response = page.waitForResponse(response => response.url().includes('/activity?') && new URL(response.url()).searchParams.get('hours') === '168');
  await page.getByRole('button', { name: '7 days', exact: true }).click();
  await response;
  await page.getByText('Peak · last 7 days', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: '7 days', exact: true }).getAttribute('aria-pressed'), 'true');
  assert.equal(state.requests.filter(url => url.pathname === '/activity').at(-1).searchParams.get('hours'), '168');
  await page.getByText('View recent observations', { exact: true }).click();
  assert.equal(await page.locator('#activity-rows time').count(), 4);
  assert.equal(await page.locator('#activity-rows time').first().getAttribute('datetime'), samples.at(-1).timestamp);
  const chart = page.getByRole('img', { name: /Warband players online/ });
  await chart.focus();
  await page.keyboard.press('ArrowLeft');
  assert.match(await page.locator('.chart-inspection').innerText(), /7 players · 1 spectators · 3 rooms/);
});

// The requested MMR/win/loss values must remain readable on a narrow phone.
test('mobile viewport exposes MMR, wins and losses without page overflow', async t => {
  const { page, url } = await journey(t, {}, { width: 375, height: 812 });
  await page.goto(url);
  await page.getByText('1–12 of 12', { exact: true }).waitFor();
  await page.locator('#activity-chart svg').waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  const table = page.locator('.rankings');
  for (const heading of ['MMR', 'Wins', 'Losses']) {
    const box = await table.getByRole('columnheader', { name: new RegExp(heading) }).boundingBox();
    assert.ok(box && box.x >= 0 && box.x + box.width <= 375, `${heading} must fit on screen`);
  }
  const values = page.locator('#ranking-rows tr').first().getByRole('cell');
  for (const index of [2, 3, 4]) {
    const box = await values.nth(index).boundingBox();
    assert.ok(box && box.x + box.width <= 375, 'The player rating and results must fit');
  }
  // SVG labels must be sized for the phone, not shrunk from a desktop canvas.
  const text = await page.locator('#activity-chart svg text').first().boundingBox();
  assert.ok(text && text.height >= 7, 'Chart labels should remain legible at the narrow viewport');
  assert.ok(await page.getByRole('link', { name: /Download for Windows/ }).first().isVisible());
});
