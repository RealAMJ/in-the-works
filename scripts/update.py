#!/usr/bin/env python3
"""
Swedes Abroad live updater. Runs on GitHub Actions every few minutes (free) and needs no API keys.

For every game in data/schedule.json that is around its tip-off time it reads the live feed,
then writes the score, the game clock and full box scores into:
  data/schedule.json   status (upcoming/live/final), score from the Swedes' side, clock
  data/fullbox.json    every player on both teams
  data/boxscores.json  the Swedish players' lines
and finally data/_version.json, which the open site polls to refresh itself.

Where the feed comes from, per schedule row:
  NBA         automatic: the game id in box_url (nba.com/game/...-0022600172) or an "nba_id" field
  FIBA        add  "live_feed": "fiba:2949100"  (the number in a fibalivestats.dcd.shared.geniussports.com link)
              Used by most European leagues: Orlen Basket Liga, ABA, BCL, FIBA Europe Cup, LKL, BLNO, ...
  EuroLeague  add  "live_feed": "euroleague:E2026:45"  (season code : game code from the euroleague.net game link)

Run locally:  python3 scripts/update.py            (only games in their time window)
              python3 scripts/update.py --all      (every row that has a feed, for testing)
              python3 scripts/update.py --game g20261031ast
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
STHLM = ZoneInfo('Europe/Stockholm')
UA = {'User-Agent': 'Mozilla/5.0 (Swedes Abroad live updater; +https://github.com)', 'Accept': 'application/json'}

# How long around tip-off a game is checked
BEFORE = dt.timedelta(minutes=20)
AFTER = dt.timedelta(hours=4)


def load(name):
    with open(os.path.join(DATA, name + '.json'), encoding='utf-8') as f:
        return json.load(f)


def save(name, rows):
    path = os.path.join(DATA, name + '.json')
    new = json.dumps(rows, ensure_ascii=False, indent=1) + '\n'
    try:
        old = open(path, encoding='utf-8').read()
    except FileNotFoundError:
        old = ''
    if new != old:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new)
        return True
    return False


BROWSER = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36',
           'Accept': 'application/json, text/plain, */*', 'Accept-Language': 'en-US,en;q=0.9'}


def get(url):
    h = dict(UA)
    if 'nba.com' in url:
        h = dict(BROWSER, Referer='https://www.nba.com/', Origin='https://www.nba.com')
    elif 'euroleague' in url:
        h = dict(BROWSER, Referer='https://www.euroleaguebasketball.net/')
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def now():
    return dt.datetime.now(STHLM)


def tip_time(row):
    try:
        d = dt.date.fromisoformat(row['date'])
    except (KeyError, ValueError):
        return None
    m = re.match(r'^(\d{1,2}):(\d{2})', row.get('time') or '')
    if not m:
        return None  # "TBC": no window, skip
    return dt.datetime(d.year, d.month, d.day, int(m.group(1)), int(m.group(2)), tzinfo=STHLM)


def norm(s):
    s = (s or '').lower()
    for a, b in (('å', 'a'), ('ä', 'a'), ('ö', 'o'), ('é', 'e'), ('ø', 'o'), ('ü', 'u'), ('ł', 'l'), ('ć', 'c'), ('č', 'c'), ('š', 's'), ('ž', 'z')):
        s = s.replace(a, b)
    return re.sub(r'[^a-z ]', '', s)


def last(name):
    p = norm(name).split()
    return p[-1] if p else ''


# ---------------------------------------------------------------- feeds
# Each reader returns: {period, clock, done, teams: [{name, score, pl: [player dicts]}]}
# A player dict: name, min, pts, reb, ast, stl, blk, tov, fgm, fga, tpm, tpa, ftm, fta, pm, pf, oreb, dreb, starter

def read_fiba(fid):
    d = get(f'https://fibalivestats.dcd.shared.geniussports.com/data/{fid}/data.json')
    teams = []
    for k in ('1', '2'):
        t = (d.get('tm') or {}).get(k) or {}
        pl = []
        for p in (t.get('pl') or {}).values():
            pl.append(dict(
                name=' '.join(f"{p.get('firstName', '')} {p.get('familyName', '')}".split()),
                min=p.get('sMinutes') or '', pts=p.get('sPoints', 0), reb=p.get('sReboundsTotal', 0), ast=p.get('sAssists', 0),
                stl=p.get('sSteals', 0), blk=p.get('sBlocks', 0), tov=p.get('sTurnovers', 0),
                fgm=p.get('sFieldGoalsMade', 0), fga=p.get('sFieldGoalsAttempted', 0),
                tpm=p.get('sThreePointersMade', 0), tpa=p.get('sThreePointersAttempted', 0),
                ftm=p.get('sFreeThrowsMade', 0), fta=p.get('sFreeThrowsAttempted', 0),
                pm=p.get('sPlusMinusPoints', ''), pf=p.get('sFoulsPersonal', 0),
                oreb=p.get('sReboundsOffensive', 0), dreb=p.get('sReboundsDefensive', 0),
                starter=bool(p.get('starter'))))
        teams.append(dict(name=t.get('name') or t.get('nameInternational') or '', score=int(t.get('score') or 0), pl=pl))
    period = int(d.get('period') or 0)
    # FIBA counts overtime periods from 1 again with periodType OVERTIME
    if str(d.get('periodType') or '').upper().startswith('OVERTIME') or d.get('inOT') in (1, True, '1'):
        period = 4 + max(period, 1)
    clock = d.get('clock') or ''
    status = str(d.get('periodStatus') or d.get('status') or '').lower()
    at_zero = clock in ('00:00', '0:00', '00:00:00')
    # The play-by-play ends with a "game end" action; status words and a 0:00 clock in Q4+ with no tie back it up
    ended = any((a.get('actionType') == 'game' and a.get('subType') == 'end') for a in (d.get('pbp') or [])[:15])
    done = ended or ('final' in status or 'finished' in status or 'complete' in status) or (
        at_zero and period >= 4 and len(teams) == 2 and teams[0]['score'] != teams[1]['score'] and 'started' not in status)
    return dict(period=period, clock=clock[:5], done=done, teams=teams)


def _iso_min(s):
    m = re.match(r'PT(?:(\d+)M)?(?:([\d.]+)S)?', s or '')
    if not m:
        return '', ''
    mins = int(m.group(1) or 0)
    secs = int(float(m.group(2) or 0))
    return mins, f'{mins:02d}:{secs:02d}'


def read_nba(gid):
    d = get(f'https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{gid}.json')['game']
    teams = []
    for side in ('homeTeam', 'awayTeam'):
        t = d[side]
        pl = []
        for p in t.get('players', []):
            s = p.get('statistics') or {}
            mins, _ = _iso_min(s.get('minutes') or s.get('minutesCalculated'))
            pl.append(dict(
                name=p.get('name') or f"{p.get('firstName', '')} {p.get('familyName', '')}".strip(),
                min=mins, pts=s.get('points', 0), reb=s.get('reboundsTotal', 0), ast=s.get('assists', 0),
                stl=s.get('steals', 0), blk=s.get('blocks', 0), tov=s.get('turnovers', 0),
                fgm=s.get('fieldGoalsMade', 0), fga=s.get('fieldGoalsAttempted', 0),
                tpm=s.get('threePointersMade', 0), tpa=s.get('threePointersAttempted', 0),
                ftm=s.get('freeThrowsMade', 0), fta=s.get('freeThrowsAttempted', 0),
                pm=s.get('plusMinusPoints', ''), pf=s.get('foulsPersonal', 0),
                oreb=s.get('reboundsOffensive', 0), dreb=s.get('reboundsDefensive', 0),
                starter=str(p.get('starter')) == '1'))
        teams.append(dict(name=f"{t.get('teamCity', '')} {t.get('teamName', '')}".strip(), score=int(t.get('score') or 0), pl=pl))
    status = int(d.get('gameStatus') or 1)
    _, clock = _iso_min(d.get('gameClock'))
    return dict(period=int(d.get('period') or 0), clock=clock or '00:00', done=status == 3, notstarted=status == 1, teams=teams)


def read_euroleague(season, code):
    base = 'https://live.euroleague.net/api/'
    h = get(f'{base}Header?gamecode={code}&seasoncode={season}')
    b = get(f'{base}Boxscore?gamecode={code}&seasoncode={season}')
    teams = []
    for t in b.get('Stats', [])[:2]:
        pl = []
        for p in t.get('PlayersStats', []):
            mins = str(p.get('Minutes') or '')
            if mins.upper() in ('DNP', ''):
                mins = ''
            raw = p.get('Player') or ''
            if ',' in raw:  # "LASTNAME, FIRSTNAME"
                a, c = raw.split(',', 1)
                raw = f'{c.strip().title()} {a.strip().title()}'
            fgm = (p.get('FieldGoalsMade2') or 0) + (p.get('FieldGoalsMade3') or 0)
            fga = (p.get('FieldGoalsAttempted2') or 0) + (p.get('FieldGoalsAttempted3') or 0)
            pl.append(dict(name=raw, min=mins, pts=p.get('Points', 0), reb=p.get('TotalRebounds', 0), ast=p.get('Assistances', 0),
                           stl=p.get('Steals', 0), blk=p.get('BlocksFavour', 0), tov=p.get('Turnovers', 0), fgm=fgm, fga=fga,
                           tpm=p.get('FieldGoalsMade3', 0), tpa=p.get('FieldGoalsAttempted3', 0),
                           ftm=p.get('FreeThrowsMade', 0), fta=p.get('FreeThrowsAttempted', 0),
                           pm=p.get('Plusminus', ''), pf=p.get('FoulsCommited', 0),
                           oreb=p.get('OffensiveRebounds', 0), dreb=p.get('DefensiveRebounds', 0), starter=bool(p.get('IsStarter'))))
        teams.append(dict(name=t.get('Team', ''), score=0, pl=pl))
    if len(teams) == 2:
        teams[0]['score'] = int(h.get('ScoreA') or 0)
        teams[1]['score'] = int(h.get('ScoreB') or 0)
    q = str(h.get('Quarter') or '')
    period = int(re.sub(r'\D', '', q) or 0)
    if 'OT' in q.upper() or 'EXTRA' in q.upper():
        period = max(period, 5)
    clock = str(h.get('RemainingPartialTime') or '00:00')[:5]
    live = bool(h.get('Live'))
    done = not live and (teams and (teams[0]['score'] + teams[1]['score']) > 0)
    return dict(period=period, clock=clock, done=bool(done), teams=teams)


def feed_for(row):
    f = (row.get('live_feed') or '').strip()
    if f == 'none':
        f = ''
    if f.startswith('fiba:'):
        return 'FIBA LiveStats', lambda: read_fiba(f.split(':', 1)[1])
    if f.startswith('euroleague:'):
        _, season, code = f.split(':')
        return 'EuroLeague live', lambda: read_euroleague(season, code)
    nid = row.get('nba_id')
    if not nid:
        m = re.search(r'(00\d{8})', row.get('box_url') or '')
        nid = m.group(1) if m else None
    if f.startswith('nba:'):
        nid = f.split(':', 1)[1]
    if nid:
        return 'NBA.com', lambda: read_nba(nid)
    if row.get('competition') == 'NBA':
        def find_and_read():
            sb = get('https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json')['scoreboard']['games']
            want = {norm(row.get('team')), norm(row.get('opponent'))}
            for g in sb:
                names = {norm(f"{g[s]['teamCity']} {g[s]['teamName']}") for s in ('homeTeam', 'awayTeam')}
                if names == want:
                    row['nba_id'] = g['gameId']
                    return read_nba(g['gameId'])
            raise LookupError('game not on today\'s NBA scoreboard')
        return 'NBA.com', find_and_read
    return None, None


# ---------------------------------------------------------------- applying a feed

def which_team(feed, row, swedes):
    """Index (0/1) of the team the Swedes play for, by names first, then by club name."""
    names = {last(n) for n in swedes}
    for i, t in enumerate(feed['teams']):
        if any(last(p['name']) in names for p in t['pl']):
            return i
    club = norm(row.get('team'))
    best, score = 0, -1
    for i, t in enumerate(feed['teams']):
        words = set(norm(t['name']).split())
        s = len(words & set(club.split()))
        if s > score:
            best, score = i, s
    return best


def clock_label(feed):
    per, clk = feed['period'], feed['clock']
    if clk in ('00:00', '0:00'):
        if per == 2:
            return 'Halftime'
        return f'End of Q{per}' if per <= 4 else 'End of OT'
    if per > 4:
        return f"OT{per - 4 if per > 5 else ''} {clk}"
    return f'Q{per} {clk}'


def as_min(m):
    if m in (None, ''):
        return ''
    if isinstance(m, (int, float)):
        return int(m)
    p = str(m).split(':')
    return int(p[0]) if p[0].isdigit() else m


def apply(row, feed, src, swedes_all, sched_names, fullbox, boxscores):
    gid = row['game_id']
    swedes = [s.strip() for s in (row.get('players') or '').split(',') if s.strip()]
    si = which_team(feed, row, swedes or swedes_all)
    us, them = feed['teams'][si], feed['teams'][1 - si]
    total = us['score'] + them['score']
    started = total > 0 or feed['period'] > 1 or (feed['clock'] not in ('10:00', '12:00', '') and not feed.get('notstarted'))
    if feed.get('notstarted'):
        started = False
    if not started:
        return False
    done = bool(feed['done'])
    res = ('W' if us['score'] > them['score'] else 'L') if done else ('W' if us['score'] >= them['score'] else 'L')
    row['score'] = f"{res} {us['score']}-{them['score']}"
    row['status'] = 'final' if done else 'live'
    if done:
        row.pop('clock', None)
        row.pop('live_updated', None)
        row['live_done'] = True
    else:
        row['clock'] = clock_label(feed)
        row['live_updated'] = now().isoformat(timespec='seconds')

    # Box scores, both teams; names on our site for the two sides
    site_names = {si: row.get('team', us['name']), 1 - si: row.get('opponent', them['name'])}
    fullbox[:] = [r for r in fullbox if r.get('game_id') != gid]
    boxscores[:] = [r for r in boxscores if r.get('game_id') != gid]
    sw_last = {last(n): n for n in swedes_all}
    for ti, t in enumerate(feed['teams']):
        for i, p in enumerate(t['pl']):
            hit = sw_last.get(last(p['name']))
            # a Swede on either team counts (Swede vs Swede games)
            sw = bool(hit) and (ti == si or norm(hit) == norm(p['name']))
            name = hit if sw else p['name']
            r = dict(row_id=f'{gid}-{ti}-{i}', game_id=gid, team=site_names[ti], player=name, pos='', min=as_min(p['min']),
                     pts=p['pts'] or 0, reb=p['reb'] or 0, ast=p['ast'] or 0, stl=p['stl'] or 0, blk=p['blk'] or 0, tov=p['tov'] or 0,
                     fg=f"{p['fgm'] or 0}/{p['fga'] or 0}", three=f"{p['tpm'] or 0}/{p['tpa'] or 0}", ft=f"{p['ftm'] or 0}/{p['fta'] or 0}",
                     pm=p['pm'] if p['pm'] not in (None,) else '', swede=sw, state='final' if done else 'live', source=src)
            if r['min'] or r['pts'] or r['reb'] or r['ast']:
                fullbox.append(r)
            if sw:
                boxscores.append(dict(line_id=f"{gid}-{last(name)}", game_id=gid, player=name, min=r['min'], pts=r['pts'], reb=r['reb'],
                                      ast=r['ast'], fg=r['fg'], three=r['three'], ft=r['ft'], pm=r['pm'], source=src,
                                      note='' if done else 'live', oreb=p['oreb'] or 0, dreb=p['dreb'] or 0, stl=r['stl'], blk=r['blk'],
                                      tov=r['tov'], pf=p['pf'] or 0, eff=''))
    print(f"  {gid}: {row['status']} {row['score']} {row.get('clock', '')}")
    return True


def in_window(row, t):
    tip = tip_time(row)
    return tip is not None and tip - BEFORE <= t <= tip + AFTER


def write_version(changed_any):
    files = {}
    for fn in sorted(os.listdir(DATA)):
        if fn.endswith('.json') and not fn.startswith('_'):
            files[fn[:-5]] = hashlib.sha1(open(os.path.join(DATA, fn), 'rb').read()).hexdigest()[:12]
    path = os.path.join(DATA, '_version.json')
    try:
        old = json.load(open(path))
    except Exception:
        old = {}
    if old.get('files') == files and not changed_any:
        return False
    json.dump({'updated': now().isoformat(timespec='seconds'), 'files': files}, open(path, 'w'), indent=1)
    return True


LOG = []


def main(argv):
    only = argv[argv.index('--game') + 1] if '--game' in argv else None
    every = '--all' in argv
    sched = load('schedule')
    coach = load('coachgames')
    fullbox = load('fullbox')
    boxscores = load('boxscores')
    players = load('players')
    swedes_all = [p['player'] for p in players if p.get('player')]
    t = now()
    touched = False
    for row in sched + coach:
        if only and row.get('game_id') != only:
            continue
        back = bool(row.get('backfill'))  # finished game whose full box score should be fetched once
        if not only and row.get('live_done') and not back:
            continue
        if not only and not every and not back and not in_window(row, t):
            continue
        src, reader = feed_for(row)
        if not reader:
            continue
        try:
            feed = reader()
        except Exception as e:  # feed not up yet, network blip, format change: keep what we have
            print(f"  {row.get('game_id')}: feed error {e.__class__.__name__}: {e}")
            LOG.append({'game': row.get('game_id'), 'error': f"{e.__class__.__name__}: {e}"[:300]})
            continue
        if not feed.get('teams') or len(feed['teams']) != 2:
            continue
        if apply(row, feed, src, swedes_all, None, fullbox, boxscores):
            touched = True
            row.pop('backfill', None)
    soon = [tip_time(r) for r in sched + coach if r.get('status') != 'final' and tip_time(r)]
    soon = [x for x in soon if t - AFTER <= x <= t + dt.timedelta(hours=3)]
    if soon and not only:
        print('KEEP_GOING')
    changed = False
    if touched:
        changed |= save('schedule', sched)
        changed |= save('coachgames', coach)
        changed |= save('fullbox', fullbox)
        changed |= save('boxscores', boxscores)
    if LOG:
        json.dump({'at': now().isoformat(timespec='seconds'), 'errors': LOG}, open(os.path.join(DATA, '_live_log.json'), 'w'), indent=1)
    changed |= write_version(changed)
    print('changed' if changed else 'no changes')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
