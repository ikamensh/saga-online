(function () {
  'use strict';
  var ua = navigator.userAgent || '';
  var visitorOS = /Windows/.test(ua) ? 'windows' : /Macintosh|Mac OS X/.test(ua) ? 'macos' : /Linux/.test(ua) ? 'linux' : '';

  function highlightDownloads(root) {
    var buttons = (root || document).querySelectorAll('.button[data-os]');
    var matched = false;
    buttons.forEach(function (button) {
      if (button.getAttribute('data-os') === visitorOS && !matched) {
        button.classList.add('for-you');
        var hint = button.querySelector('.for-you-hint');
        if (hint) { hint.textContent = 'Recommended for this computer'; }
        matched = true;
      }
    });
  }

  function copyText(text, button) {
    if (!navigator.clipboard) { return; }
    navigator.clipboard.writeText(text).then(function () {
      var original = button.textContent;
      button.textContent = 'Copied!';
      setTimeout(function () { button.textContent = original; }, 1600);
    });
  }

  function packageButton(game, pkg) {
    var label = {windows: 'Windows', macos: 'Mac', linux: 'Linux'}[pkg.os] + ' · ' + {x64: '64-bit', arm64: 'Apple Silicon'}[pkg.arch];
    var kind = {installer: 'installer', 'portable-zip': 'portable ZIP', 'app-zip': 'app', dmg: 'disk image'}[pkg.kind];
    var mb = pkg.bytes ? (pkg.bytes / 1048576).toFixed(0) + ' MB' : '';
    var a = document.createElement('a');
    a.className = 'button' + (pkg.kind === 'installer' || pkg.kind === 'app-zip' ? ' primary' : '');
    a.href = pkg.url;
    a.setAttribute('data-os', pkg.os);
    a.innerHTML = '<span>Download for ' + label + '</span><small>' + kind + (mb ? ' · ' + mb : '') + ' · ' + game.version + '</small><small class="for-you-hint"></small>';
    return a;
  }

  function renderInvite() {
    var root = document.getElementById('invite');
    if (!root) { return; }
    var parts = location.pathname.replace(/\/+$/, '').split('/');
    var gameId = parts[2] || '', code = (parts[3] || '').toLowerCase();
    var valid = /^[a-z][a-z0-9-]*-v[1-9][0-9]*$/.test(gameId) && /^[a-z0-9]{1,12}$/.test(code);
    var title = document.getElementById('invite-title');
    var body = document.getElementById('invite-body');
    if (!valid) {
      title.textContent = 'This invitation link is incomplete';
      body.innerHTML = '<p>Ask your friend to copy the invite link or room code again from the game\'s waiting screen.</p><p><a class="button" href="/">See the games</a></p>';
      return;
    }
    fetch('/releases.json', {cache: 'no-cache'}).then(function (r) { return r.json(); }).then(function (catalog) {
      var slug = null, game = null;
      Object.keys(catalog.games).forEach(function (key) {
        if (catalog.games[key].game_ids.indexOf(gameId) >= 0) { slug = key; game = catalog.games[key]; }
      });
      if (!game) { throw new Error('unknown game'); }
      document.title = 'Join a ' + game.name + ' room';
      title.textContent = 'You are invited to play ' + game.name;
      var html = '<p class="muted">Room code</p><div class="code" id="room-code">' + code + '</div>' +
        '<p><button class="button" id="copy-code" type="button">Copy room code</button></p>' +
        '<h2>Already have ' + game.name + '?</h2>' +
        '<ol class="steps" style="text-align:left"><li>Open <b>' + game.name + '</b> and choose <b>Multiplayer</b>' + (slug === 'shardbound' ? ' (Co-op)' : '') + '.</li>' +
        '<li>Choose <b>Paste code</b> (or type the code above), then <b>Join room</b>.</li>' +
        '<li>The game starts as soon as you both connect.</li></ol>';
      if (game.packages.length) {
        html += '<h2>Need to install it first?</h2><p class="muted">Free download. Keep this page open; the room code works throughout installation.</p><div class="download-row" id="invite-downloads"></div>' +
          '<p><a href="/' + slug + '/">Installation steps and requirements</a></p>';
      } else {
        html += '<h2>Need to install it first?</h2><p>' + game.name + ' has no published download yet. <a href="/' + slug + '/">Read how to run it</a>.</p>';
      }
      body.innerHTML = html;
      document.getElementById('copy-code').addEventListener('click', function (event) { copyText(code, event.currentTarget); });
      var row = document.getElementById('invite-downloads');
      if (row) {
        game.packages.forEach(function (pkg) { if (pkg.kind !== 'portable-zip') { row.appendChild(packageButton(game, pkg)); } });
        highlightDownloads(row);
      }
    }).catch(function () {
      title.textContent = 'This invitation is for a game we do not list';
      body.innerHTML = '<p>The link names <code>' + gameId + '</code>, which is not in the current release catalog. Ask your friend which game and version they are using.</p><p><a class="button" href="/">See the games</a></p>';
    });
  }

  function renderStatus() {
    var root = document.getElementById('service-status');
    if (!root) { return; }
    var dot = root.querySelector('.dot'), text = root.querySelector('.status-text');
    var started = Date.now();
    fetch('/healthz', {cache: 'no-store'}).then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); }).then(function (body) {
      var ms = Date.now() - started;
      dot.className = 'dot ok';
      text.textContent = 'Online service reachable (' + ms + ' ms) at ' + new Date().toLocaleTimeString();
    }).catch(function () {
      dot.className = 'dot down';
      text.textContent = 'The online service did not answer. Offline play still works; try again in a few minutes.';
    });
  }

  document.querySelectorAll('[data-copy]').forEach(function (button) {
    button.addEventListener('click', function () { copyText(button.getAttribute('data-copy'), button); });
  });
  highlightDownloads(document);
  renderInvite();
  renderStatus();
})();
