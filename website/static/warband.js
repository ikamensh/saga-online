/* Public ratings and aggregate presence, always from the authoritative server. */
(() => {
  'use strict';
  const game = document.body.dataset.game;
  const $ = id => document.getElementById(id);
  const number = value => new Intl.NumberFormat(undefined, {maximumFractionDigits: 0}).format(value);
  const clock = value => new Date(value).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
  const dateTime = value => new Date(value).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'});
  const cell = (row, value, className) => {
    const node = document.createElement('td');
    node.textContent = value;
    if (className) node.className = className;
    row.append(node);
    return node;
  };
  async function get(path, params) {
    const response = await fetch(path + '?' + new URLSearchParams({game, ...params}), {
      cache: 'no-store', signal: AbortSignal.timeout(10000)
    });
    if (!response.ok) throw new Error('Server returned HTTP ' + response.status);
    return response.json();
  }
  function error(id, message) {
    $(id).textContent = message;
    $(id).hidden = !message;
  }

  let offset = 0, query = '', rankingRequest = 0, rankingLoaded = false;
  const pageSize = 100;
  async function rankings() {
    const request = ++rankingRequest;
    try {
      const data = await get('/leaderboard', {limit: pageSize, offset, q: query});
      if (request !== rankingRequest) return;
      const rows = document.createDocumentFragment();
      data.players.forEach((player, index) => {
        const row = document.createElement('tr');
        cell(row, query ? '—' : number(offset + index + 1));
        const name = cell(row, player.name);
        const id = document.createElement('span');
        id.className = 'player-id';
        id.textContent = player.player_id;
        name.append(id);
        cell(row, number(player.rating), 'number');
        cell(row, number(player.wins), 'number');
        cell(row, number(player.losses), 'number');
        cell(row, number(player.games), 'number');
        cell(row, player.games ? number(player.wins / player.games * 100) + '%' : '—', 'number');
        rows.append(row);
      });
      if (!data.players.length) {
        const row = document.createElement('tr');
        const empty = cell(row, query ? 'No ranked players match your search.' : 'The ladder is waiting. Complete a ranked match to appear here.', 'empty');
        empty.colSpan = 7;
        rows.append(row);
      }
      $('ranking-rows').replaceChildren(rows);
      $('player-total').textContent = number(data.total) + (query ? ' matching players' : ' ranked players');
      $('ranking-updated').textContent = 'Updated ' + clock(Date.now()) + ' · refreshes every minute';
      $('ranking-page').textContent = data.total ? number(offset + 1) + '–' + number(offset + data.players.length) + ' of ' + number(data.total) : '';
      $('ranking-prev').disabled = offset === 0;
      $('ranking-next').disabled = offset + pageSize >= data.total;
      rankingLoaded = true;
      error('ranking-error', '');
    } catch (reason) {
      if (request !== rankingRequest) return;
      error('ranking-error', 'Rankings are unavailable. ' + (rankingLoaded ? 'The table shows the last successful update. ' : '') + 'Retrying every minute.');
      if (!rankingLoaded) $('ranking-rows').firstElementChild.firstElementChild.textContent = 'Could not load ranked players.';
    }
  }
  let debounce;
  $('player-search').addEventListener('input', () => {
    clearTimeout(debounce);
    // Invalidate an in-flight search immediately, before starting the next one.
    rankingRequest++;
    query = $('player-search').value.trim();
    offset = 0;
    debounce = setTimeout(rankings, 250);
  });
  $('ranking-prev').addEventListener('click', () => { offset = Math.max(0, offset - pageSize); rankings(); });
  $('ranking-next').addEventListener('click', () => { offset += pageSize; rankings(); });

  let hours = 24, activityRequest = 0, activityLoaded = false;
  const ns = 'http://www.w3.org/2000/svg';
  function svgElement(name, attrs, text) {
    const element = document.createElementNS(ns, name);
    Object.entries(attrs).forEach(([key, value]) => element.setAttribute(key, value));
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function chart(data) {
    const root = $('activity-chart');
    root.replaceChildren();
    if (!data.samples.length) {
      const empty = document.createElement('p');
      empty.className = 'empty';
      empty.textContent = 'No observations in this period. History appears as the server records activity.';
      root.append(empty);
      return;
    }
    const width = 1000, height = 230, left = 32, right = 15, top = 15, bottom = 35;
    const end = Date.parse(data.server_time), start = end - data.hours * 3600000;
    const peak = Math.max(1, ...data.samples.map(sample => sample.players));
    const maximum = Math.max(2, Math.ceil(peak / 4) * 4);
    const x = timestamp => left + (Date.parse(timestamp) - start) / (end - start) * (width - left - right);
    const y = count => height - bottom - count / maximum * (height - top - bottom);
    const svg = svgElement('svg', {viewBox: `0 0 ${width} ${height}`, role: 'img', tabindex: '0',
      'aria-label': 'Warband players online. Use left and right arrow keys to inspect observations.'});
    svg.append(svgElement('title', {}, 'Concurrent Warband players over the last ' + hours + ' hours'));
    for (let tick = 0; tick <= 4; tick++) {
      const count = maximum * tick / 4;
      svg.append(svgElement('line', {x1: left, x2: width - right, y1: y(count), y2: y(count), class: 'grid'}));
      svg.append(svgElement('text', {x: left - 12, y: y(count) + 3, 'text-anchor': 'end', class: 'chart-label'}, number(count)));
    }
    for (let tick = 0; tick <= 4; tick++) {
      const time = start + (end - start) * tick / 4;
      const label = hours > 24 ? new Date(time).toLocaleDateString([], {month: 'short', day: 'numeric'}) : clock(time);
      svg.append(svgElement('text', {x: left + (width - left - right) * tick / 4, y: height - 7,
        'text-anchor': tick === 0 ? 'start' : tick === 4 ? 'end' : 'middle', class: 'chart-label'}, label));
    }
    let segment = [], previous;
    function drawSegment() {
      if (!segment.length) return;
      svg.append(svgElement('polyline', {points: segment.map(sample => `${x(sample.timestamp)},${y(sample.players)}`).join(' '), class: 'activity-line'}));
      if (segment.length === 1) svg.append(svgElement('circle', {cx: x(segment[0].timestamp), cy: y(segment[0].players), r: 3, class: 'activity-point'}));
      segment = [];
    }
    data.samples.forEach(sample => {
      if (previous && Date.parse(sample.timestamp) - Date.parse(previous.timestamp) > data.sample_interval_seconds * 1500) drawSegment();
      segment.push(sample);
      previous = sample;
    });
    drawSegment();
    const cursor = svgElement('circle', {cx: 0, cy: 0, r: 4, class: 'activity-point', visibility: 'hidden'});
    svg.append(cursor);
    const inspection = document.createElement('p');
    inspection.className = 'muted chart-inspection';
    inspection.textContent = 'Hover over the chart, or focus it and use arrow keys, to inspect an observation.';
    let selected = data.samples.length - 1;
    function inspect(index) {
      selected = index;
      const sample = data.samples[index];
      cursor.setAttribute('cx', x(sample.timestamp));
      cursor.setAttribute('cy', y(sample.players));
      cursor.setAttribute('visibility', 'visible');
      inspection.textContent = dateTime(sample.timestamp) + ' — ' + sample.players + ' players · ' + sample.observers + ' spectators · ' + sample.rooms + ' rooms';
    }
    svg.addEventListener('pointermove', event => {
      const box = svg.getBoundingClientRect();
      const target = start + ((event.clientX - box.left) / box.width * width - left) / (width - left - right) * (end - start);
      let nearest = 0;
      data.samples.forEach((sample, index) => {
        if (Math.abs(Date.parse(sample.timestamp) - target) < Math.abs(Date.parse(data.samples[nearest].timestamp) - target)) nearest = index;
      });
      inspect(nearest);
    });
    svg.addEventListener('focus', () => inspect(selected));
    svg.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        inspect(Math.min(data.samples.length - 1, Math.max(0, selected + (event.key === 'ArrowRight' ? 1 : -1))));
      }
    });
    root.append(svg, inspection);
  }
  async function activity() {
    const request = ++activityRequest;
    try {
      const data = await get('/activity', {hours});
      if (request !== activityRequest) return;
      $('online-count').textContent = number(data.current.players);
      $('observer-count').textContent = number(data.current.observers);
      $('room-count').textContent = number(data.current.rooms);
      $('room-detail').textContent = number(data.current.ready_rooms) + ' with all required seats connected';
      $('peak-count').textContent = data.samples.length ? number(Math.max(...data.samples.map(sample => sample.players))) : '—';
      $('peak-label').textContent = 'Peak · last ' + (hours === 24 ? '24 hours' : '7 days');
      $('chart-zone').textContent = 'Times in ' + Intl.DateTimeFormat().resolvedOptions().timeZone.replaceAll('_', ' ');
      chart(data);
      $('activity-summary').textContent = 'Updated ' + clock(data.server_time) + '. ' +
        (data.collected_since ? 'Recording since ' + dateTime(data.collected_since) + '. ' : '') +
        'One observation per minute; gaps are unobserved time.';
      const rows = document.createDocumentFragment();
      data.samples.slice(-12).reverse().forEach(sample => {
        const row = document.createElement('tr');
        const time = document.createElement('time');
        time.dateTime = sample.timestamp;
        time.textContent = dateTime(sample.timestamp);
        cell(row, '').append(time);
        ['players', 'observers', 'rooms'].forEach(key => cell(row, number(sample[key]), 'number'));
        rows.append(row);
      });
      $('activity-rows').replaceChildren(rows);
      activityLoaded = true;
      error('activity-error', '');
    } catch (reason) {
      if (request !== activityRequest) return;
      error('activity-error', 'Server activity is unavailable. ' + (activityLoaded ? 'Counts and history show the last successful update. ' : '') + 'Retrying every minute.');
      if (!activityLoaded) $('activity-chart').firstElementChild.textContent = 'Could not load server activity.';
    }
  }
  document.querySelectorAll('[data-hours]').forEach(button => button.addEventListener('click', () => {
    hours = Number(button.dataset.hours);
    document.querySelectorAll('[data-hours]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    activity();
  }));
  rankings();
  activity();
  setInterval(() => { rankings(); activity(); }, 60000);
})();
