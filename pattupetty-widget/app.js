'use strict';

const MOODS = {
  'Worship': 'Malayalam Christian worship songs',
  'Hymns': 'Malayalam Christian hymns',
  'Devotional': 'Malayalam Christian devotional songs',
  'Sunday morning': 'Malayalam Christian praise songs',
  'Prayer': 'Malayalam Christian prayer songs',
  'Sleep': 'Malayalam Christian slow songs',
  'Kids': 'Malayalam Christian kids songs',
  'Christmas': 'Malayalam Christmas carol songs',
};
const SCOPE = 'https://www.googleapis.com/auth/youtube.readonly';
const API = 'https://www.googleapis.com/youtube/v3';
const isMini = new URLSearchParams(location.search).has('mini');

const $ = (id) => document.getElementById(id);
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

let player = null;
let ready = false;
let queue = [];       // [{id, title}]
let index = -1;
let seen = new Set(); // video ids already played this session
let refill = null;    // async () => [{id, title}], called when the queue runs out
let token = null;     // {value, exp}
let tokenClient = null;
let sleepTimer = null;

function say(text) { $('msg').textContent = text || ''; }
function setNow(text) { $('now').textContent = text; }

// ---------- player ----------

window.onYouTubeIframeAPIReady = () => {
  player = new YT.Player('player', {
    width: '100%', height: '100%',
    playerVars: { playsinline: 1, rel: 0, modestbranding: 1 },
    events: {
      onReady: () => { ready = true; restore(); },
      onStateChange: (e) => {
        $('toggle').innerHTML = e.data === YT.PlayerState.PLAYING ? '&#10074;&#10074;' : '&#9654;';
        if (e.data === YT.PlayerState.ENDED) next();
      },
      onError: () => { say('That video cannot be played here. Skipping.'); next(); },
    },
  });
};

function persist() { store.set('queue', { queue, index }); }

function restore() {
  const saved = store.get('queue', null);
  if (!saved || !saved.queue.length) return;
  queue = saved.queue; index = Math.min(saved.index, queue.length - 1);
  setNow(queue[index].title);
  player.cueVideoById(queue[index].id);
}

function playAt(i) {
  if (!ready || !queue[i]) return;
  index = i;
  seen.add(queue[i].id);
  player.loadVideoById(queue[i].id);
  setNow(queue[i].title);
  persist();
}

async function next() {
  if (index + 1 < queue.length) return playAt(index + 1);
  if (!refill) return playAt(0); // loop a fixed list
  try {
    const more = (await refill()).filter((v) => !seen.has(v.id));
    if (!more.length) { seen.clear(); return playAt(0); }
    queue = queue.concat(more);
    playAt(index + 1);
  } catch (err) { say(err.message); }
}

function prev() { if (index > 0) playAt(index - 1); }

function startQueue(items, refillFn) {
  queue = items; index = -1; refill = refillFn || null;
  if (!items.length) { say('Nothing found.'); return; }
  playAt(0);
}

// ---------- Google login and API ----------

function clientId() { return store.get('clientId', ''); }

function authHeader() {
  return token && token.exp > Date.now() ? { Authorization: 'Bearer ' + token.value } : null;
}

function signIn() {
  const id = clientId();
  if (!id) { $('settings').showModal(); return Promise.reject(new Error('Add your Client ID in settings first.')); }
  if (!window.google || !google.accounts) return Promise.reject(new Error('Google sign-in is still loading. Try again.'));
  return new Promise((resolve, reject) => {
    tokenClient = google.accounts.oauth2.initTokenClient({
      client_id: id, scope: SCOPE,
      callback: (r) => {
        if (r.error) return reject(new Error('Sign-in failed: ' + r.error));
        token = { value: r.access_token, exp: Date.now() + (r.expires_in - 60) * 1000 };
        $('who').textContent = 'Signed in';
        resolve();
      },
    });
    tokenClient.requestAccessToken();
  });
}

async function api(path, params) {
  if (!authHeader()) await signIn();
  const url = API + path + '?' + new URLSearchParams(params);
  const res = await fetch(url, { headers: authHeader() });
  if (res.status === 401) { token = null; return api(path, params); }
  if (!res.ok) throw new Error('YouTube API error ' + res.status);
  return res.json();
}

const decode = (s) => { const t = document.createElement('textarea'); t.innerHTML = s; return t.value; };

async function searchSongs(q, pageToken) {
  const data = await api('/search', {
    part: 'snippet', type: 'video', videoCategoryId: '10', videoEmbeddable: 'true',
    maxResults: '25', q, ...(pageToken ? { pageToken } : {}),
  });
  return { next: data.nextPageToken, items: data.items.map((i) => ({ id: i.id.videoId, title: decode(i.snippet.title), thumb: i.snippet.thumbnails.default.url })) };
}

async function playlistVideos(playlistId, pageToken) {
  const data = await api('/playlistItems', {
    part: 'snippet', maxResults: '50', playlistId, ...(pageToken ? { pageToken } : {}),
  });
  return { next: data.nextPageToken, items: data.items.filter((i) => i.snippet.resourceId && i.snippet.resourceId.videoId).map((i) => ({ id: i.snippet.resourceId.videoId, title: decode(i.snippet.title) })) };
}

// Endless radio: keep pulling the next search page, then rotate to a fresh query word.
function radioFor(query) {
  let pageToken;
  return async () => {
    const page = await searchSongs(query, pageToken);
    pageToken = page.next;
    return page.items;
  };
}

function pagedPlaylist(playlistId) {
  let pageToken;
  let done = false;
  return async () => {
    if (done) return [];
    const page = await playlistVideos(playlistId, pageToken);
    pageToken = page.next; done = !page.next;
    return page.items;
  };
}

// ---------- UI ----------

function listItem(v, onClick) {
  const b = document.createElement('button');
  b.className = 'item';
  if (v.thumb) { const img = document.createElement('img'); img.src = v.thumb; img.alt = ''; b.append(img); }
  const s = document.createElement('span'); s.textContent = v.title; b.append(s);
  b.onclick = onClick;
  return b;
}

function showTab(name) {
  document.querySelectorAll('.tab').forEach((t) => { t.hidden = t.id !== 'tab-' + name; });
  document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('on', b.dataset.tab === name));
}

function buildMoods() {
  for (const [label, query] of Object.entries(MOODS)) {
    const b = document.createElement('button');
    b.textContent = label;
    b.onclick = async () => {
      say('');
      try {
        const refillFn = radioFor(query);
        const first = await refillFn();
        startQueue(first, refillFn);
      } catch (err) { say(err.message); }
    };
    $('moods').append(b);
  }
}

async function loadLibrary() {
  const list = $('lib-list'); list.textContent = '';
  try {
    const liked = document.createElement('button'); liked.className = 'item';
    liked.innerHTML = '<span>Liked videos</span>';
    liked.onclick = async () => {
      const data = await api('/videos', { part: 'snippet', myRating: 'like', maxResults: '50' });
      startQueue(data.items.map((v) => ({ id: v.id, title: decode(v.snippet.title) })));
    };
    list.append(liked);
    const data = await api('/playlists', { part: 'snippet', mine: 'true', maxResults: '50' });
    for (const p of data.items) {
      list.append(listItem({ title: decode(p.snippet.title), thumb: p.snippet.thumbnails && p.snippet.thumbnails.default.url }, async () => {
        const refillFn = pagedPlaylist(p.id);
        startQueue(await refillFn(), refillFn);
      }));
    }
  } catch (err) { say(err.message); }
}

function parseLink(text) {
  try {
    const u = new URL(text.trim());
    const list = u.searchParams.get('list');
    const v = u.searchParams.get('v') || (u.hostname === 'youtu.be' ? u.pathname.slice(1) : null);
    return { list, v };
  } catch { return {}; }
}

function wire() {
  buildMoods();
  $('tabs').onclick = (e) => { const t = e.target.dataset.tab; if (t) showTab(t); };
  $('prev').onclick = prev;
  $('next').onclick = next;
  $('toggle').onclick = () => {
    if (!ready) return;
    player.getPlayerState() === YT.PlayerState.PLAYING ? player.pauseVideo() : player.playVideo();
  };
  $('gear').onclick = () => { $('client-id').value = clientId(); $('settings').showModal(); };
  $('save-settings').onclick = () => store.set('clientId', $('client-id').value.trim());
  $('popout').onclick = () => window.open(location.pathname + '?mini=1', 'pattupetty-mini', 'popup,width=380,height=360');
  $('signin').onclick = async () => { try { await signIn(); await loadLibrary(); } catch (err) { say(err.message); } };

  $('search-form').onsubmit = async (e) => {
    e.preventDefault(); say('');
    const q = $('q').value.trim(); if (!q) return;
    try {
      const page = await searchSongs(q);
      $('results').textContent = '';
      page.items.forEach((v, i) => $('results').append(listItem(v, () => {
        const refillFn = radioFor(q);
        startQueue(page.items.slice(i), refillFn);
      })));
    } catch (err) { say(err.message); }
  };

  $('link-form').onsubmit = (e) => {
    e.preventDefault(); say('');
    const { list, v } = parseLink($('link').value);
    if (!ready) return say('Player is still loading.');
    if (list) {
      queue = []; index = -1; refill = null;
      player.loadPlaylist({ list, listType: 'playlist' });
      player.setLoop(true);
      setNow('Playlist');
    } else if (v) {
      startQueue([{ id: v, title: 'Pasted video' }]);
    } else { say('That does not look like a YouTube link.'); }
  };

  $('sleep').onchange = (e) => {
    clearTimeout(sleepTimer);
    const mins = Number(e.target.value);
    if (mins) sleepTimer = setTimeout(() => { if (ready) player.pauseVideo(); $('sleep').value = '0'; }, mins * 60000);
  };
}

if (isMini) document.body.classList.add('mini');
wire();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
