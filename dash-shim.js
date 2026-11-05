/*
 * Swedes Abroad data layer for the standalone site.
 * Gives the page the same small `dash` API it used inside Claude:
 *   dash.data(id)        -> { status: 'loading' | 'ok' | 'error', data }
 *   dash.draw(name, fn)  -> registers fn(el) for every [data-draw=name]; dash.draw(name) redraws
 *   dash.params() / dash.setParams(obj) -> remembered choices (e.g. language)
 *   dash.setLink(name)   -> puts the open page in the address bar
 * Data comes from data/<id>.json. data/_version.json is polled so live games
 * refresh on their own without reloading the page.
 */
(function () {
  'use strict';
  var DATA = 'data/';
  var POLL_MS = 20000;
  var IDS = ['awards', 'bios', 'boxscores', 'career', 'coaches', 'coachgames', 'gamelogs', 'highlights',
    'leaguetiers', 'ntgames', 'ntroster', 'photos', 'players', 'previews', 'sbl', 'schedule', 'stats', 'teamform',
    'teams', 'thisweek'];
  // Big files only some pages need: fetched the first time a page asks for them (full box scores grow all season)
  var LAZY = ['fullbox'];
  var asked = {};

  var store = {};
  var fns = {};
  var order = [];
  var loaded = false;
  var versions = {};

  function data(id) {
    if (store[id]) return store[id];
    if (LAZY.indexOf(id) >= 0) {
      if (!asked[id]) {
        asked[id] = true;
        loadIds([id], versions[id] || Date.now()).then(function () { redrawFor([id]); });
      }
      return { status: 'loading', data: null };
    }
    return loaded ? { status: 'error', data: null } : { status: 'loading', data: null };
  }

  function run(name) {
    var f = fns[name];
    if (!f) return;
    var els = document.querySelectorAll('[data-draw="' + name + '"]');
    for (var i = 0; i < els.length; i++) {
      try { f(els[i]); } catch (e) { console.error('[sa] draw ' + name, e); }
    }
  }

  function draw(name, fn) {
    if (typeof fn === 'function') {
      if (!fns[name]) order.push(name);
      fns[name] = fn;
    }
    run(name);
  }

  function redrawFor(changed) {
    order.forEach(function (name) {
      var els = document.querySelectorAll('[data-draw="' + name + '"]');
      var hit = !changed;
      for (var i = 0; !hit && i < els.length; i++) {
        var src = (els[i].getAttribute('data-source') || '').split(/\s+/);
        for (var j = 0; j < src.length; j++) if (changed.indexOf(src[j]) >= 0) { hit = true; break; }
      }
      // Drawings without a declared source (or none on screen) still refresh after a data change.
      if (!hit && changed && !els.length) hit = true;
      if (hit) run(name);
    });
    listeners.forEach(function (f) { try { f(changed); } catch (e) { console.error(e); } });
  }

  var listeners = [];
  function onData(fn) { listeners.push(fn); }

  function getJSON(path, bust) {
    return fetch(path + (bust ? '?v=' + bust : ''), { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(path + ' ' + r.status);
      return r.json();
    });
  }

  function loadIds(ids, bust) {
    return Promise.all(ids.map(function (id) {
      return getJSON(DATA + id + '.json', bust).then(function (rows) {
        store[id] = { status: 'ok', data: Array.isArray(rows) ? rows : (rows && rows.rows) || [] };
      }, function (e) {
        console.warn('[sa] could not load ' + id, e);
        if (!store[id]) store[id] = { status: 'error', data: null };
      });
    }));
  }

  function poll() {
    getJSON(DATA + '_version.json', Date.now()).then(function (v) {
      var changed = Object.keys(v.files || {}).filter(function (id) {
        // a lazy file nobody has opened yet is not fetched just because it changed
        return versions[id] !== v.files[id] && (LAZY.indexOf(id) < 0 || store[id]);
      });
      if (!changed.length) return;
      return loadIds(changed, Date.now()).then(function () {
        changed.forEach(function (id) { versions[id] = v.files[id]; });
        redrawFor(changed);
        stamp(v.updated);
      });
    }).catch(function () { /* offline or file missing: try again next round */ });
  }

  function stamp(at) {
    if (!at) return;
    document.documentElement.setAttribute('data-updated', at);
  }

  // Remembered choices
  var P_KEY = 'sa-params';
  function params() {
    try { return JSON.parse(localStorage.getItem(P_KEY) || '{}'); } catch (e) { return {}; }
  }
  function setParams(obj) {
    var p = params();
    Object.keys(obj || {}).forEach(function (k) { p[k] = obj[k]; });
    try { localStorage.setItem(P_KEY, JSON.stringify(p)); } catch (e) { /* storage blocked */ }
  }
  function setLink(name) {
    try { history.replaceState(null, '', name && name !== 'home' ? '#' + encodeURIComponent(name) : location.pathname + location.search); } catch (e) { /* ignore */ }
  }

  window.dash = { data: data, draw: draw, onData: onData, params: params, setParams: setParams, setLink: setLink };

  function start() {
    var first = getJSON(DATA + '_version.json', Date.now()).then(function (v) {
      versions = Object.assign({}, v.files || {});
      stamp(v.updated);
      return Date.now();
    }, function () { return Date.now(); });
    first.then(function (bust) { return loadIds(IDS, bust); }).then(function () {
      loaded = true;
      redrawFor(null);
      setInterval(poll, POLL_MS);
      document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
  else start();
})();

/* The two d3 helpers the page uses, so no chart library has to load. */
window.d3 = window.d3 || {
  format: function (spec) {
    return function (n) {
      var v = Number(n);
      if (!isFinite(v)) return String(n);
      return spec === ',' ? Math.round(v).toLocaleString('en-US') : String(v);
    };
  },
  rollups: function (data, reduce, key) {
    var m = new Map();
    (data || []).forEach(function (d) { var k = key(d); if (!m.has(k)) m.set(k, []); m.get(k).push(d); });
    return Array.from(m, function (e) { return [e[0], reduce(e[1])]; });
  }
};
