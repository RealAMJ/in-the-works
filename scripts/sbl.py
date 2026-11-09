#!/usr/bin/env python3
"""
SBL (Basketligan herr) standouts, found automatically.

Reads the league's official Genius Sports schedule (competition 48974), opens the FIBA LiveStats
box score of every finished game from the last few days and adds a data/sbl.json row for each
performance that meets the rules: 30+ pts, 15+ reb, 11+ ast, 6+ stl, 5+ blk, 7+ threes,
a triple-double, or a double-double with 20+ points. Rows are never removed; a row_id that is
already there is left alone.

Run: python3 scripts/sbl.py            (only at the top of the hour, so the 5-minute job stays light)
     python3 scripts/sbl.py --force    (any time)
     python3 scripts/sbl.py --days 10  (look further back)
"""
import datetime as dt
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

COMP = 48974
SCHEDULE = f'https://hosted.dcd.shared.geniussports.com/SBF/en/competition/{COMP}/schedule'

# League names -> the spellings the site uses (checked in this order, so Sloga comes before Uppsala Basket)
TEAMS = [('sloga', 'Sloga Uppsala'), ('uppsala', 'Uppsala Basket'), ('boras', 'Borås Basket'), ('nassjo', 'KFUM Nässjö'),
         ('hogsbo', 'Högsbo'), ('sodertalje', 'Södertälje Kings'), ('jamtland', 'Jämtland Basket'), ('norrkoping', 'Norrköping Dolphins'), ('koping', 'Köping Stars'),
         ('umea', 'Umeå BSKT'), ('lulea', 'BC Luleå')]


def team_name(s):
    n = U.norm(s)
    for key, name in TEAMS:
        if key in n:
            return name
    return s


_PAGE = {}


def schedule_page():
    if 'h' not in _PAGE:
        req = urllib.request.Request(SCHEDULE, headers=dict(U.BROWSER, Accept='text/html,*/*'))
        with urllib.request.urlopen(req, timeout=60) as r:
            _PAGE['h'] = r.read().decode('utf-8', 'replace')
    return _PAGE['h']


def coming_games(clubs, per_club=3):
    """The next league games of the given clubs (site spellings), from the same schedule page. The league lists
    tip-off times in Swedish time."""
    out = []
    for m in re.finditer(r'match-wrap (STATUS_\w+)"\s*id\s*=\s*"extfix_(\d+)"(.*?)(?=match-wrap STATUS_|\Z)', schedule_page(), re.S):
        status, gid, block = m.groups()
        if status != 'STATUS_SCHEDULED':
            continue
        d = re.search(r'match-time.*?<span>([A-Z][a-z]{2} \d{1,2}, \d{4}),?\s*(\d{1,2}:\d{2}\s*[AP]M)?', block, re.S)
        names = re.findall(r'team-name-full">([^<]+)<', block)
        if not d or len(names) < 2:
            continue
        day = dt.datetime.strptime(d.group(1), '%b %d, %Y').date()
        tm = dt.datetime.strptime(d.group(2).replace(' ', ''), '%I:%M%p').strftime('%H:%M') if d.group(2) else 'TBC'
        home, away = team_name(names[0].strip()), team_name(names[1].strip())
        for club, players in clubs.items():
            if club in (home, away):
                out.append(dict(game_id=f'sbl-{gid}', date=day.isoformat(), time=tm, team=club, opponent=away if club == home else home,
                                venue='Home' if club == home else 'Away', competition='Basketligan', players=', '.join(players),
                                status='upcoming', score='', sbl=True,
                                url=f'https://hosted.dcd.shared.geniussports.com/SBF/en/competition/{COMP}/match/{gid}/summary'))
    out.sort(key=lambda r: (r['date'], r['time']))
    keep, n = [], {}
    for r in out:
        if U.now().date().isoformat() <= r['date'] and n.get(r['team'], 0) < per_club:
            keep.append(r)
            n[r['team']] = n.get(r['team'], 0) + 1
    return keep


def finished_games(days):
    h = schedule_page()
    since = U.now().date() - dt.timedelta(days=days)
    out = []
    for m in re.finditer(r'match-wrap (STATUS_\w+)"\s*id\s*=\s*"extfix_(\d+)"(.*?)(?=match-wrap STATUS_|\Z)', h, re.S):
        status, gid, block = m.groups()
        if status != 'STATUS_COMPLETE':
            continue
        d = re.search(r'match-time.*?<span>([A-Z][a-z]{2} \d{1,2}, \d{4})', block, re.S)
        if not d:
            continue
        day = dt.datetime.strptime(d.group(1), '%b %d, %Y').date()
        if day >= since:
            out.append((int(gid), day.isoformat()))
    return out


def qualifies(p):
    """Tags for a standout line, or None. Rules (Andres, 9 Nov): 30+ pts, 15+ reb, 10+ ast, 5+ stl, 5+ blk, 6+ threes,
    every double-double and triple-double, 10+ pts on perfect shooting from the field, and a few extras:
    perfect from three (4+ made), perfect free throws (10+ made) and a 5x5."""
    cats = sum(x >= 10 for x in (p['pts'], p['reb'], p['ast'], p['stl'], p['blk']))
    tags = []
    if p['pts'] >= 30: tags.append(f"{p['pts']} PTS")
    if p['reb'] >= 15: tags.append(f"{p['reb']} REB")
    if p['ast'] >= 10: tags.append(f"{p['ast']} AST")
    if p['stl'] >= 5: tags.append(f"{p['stl']} STL")
    if p['blk'] >= 5: tags.append(f"{p['blk']} BLK")
    if p['tpm'] >= 6: tags.append(f"{p['tpm']} 3PM")
    if cats >= 4:
        tags.append('Quadruple-double')
    elif cats == 3:
        tags.append('Triple-double')
    elif cats == 2:
        tags.append('Double-double')
    if p['pts'] >= 10 and p['fga'] >= 3 and p['fgm'] == p['fga']:
        tags.append(f"Perfect FG ({p['fgm']}/{p['fga']})")
    if p['tpm'] >= 4 and p['tpm'] == p['tpa']:
        tags.append(f"Perfect from three ({p['tpm']}/{p['tpa']})")
    if p['ftm'] >= 10 and p['ftm'] == p['fta']:
        tags.append(f"Perfect FT ({p['ftm']}/{p['fta']})")
    if all(x >= 5 for x in (p['pts'], p['reb'], p['ast'], p['stl'], p['blk'])):
        tags.append('5x5')
    return tags or None


EN = {'pts': ('points', 'poäng'), 'reb': ('rebounds', 'returer'), 'ast': ('assists', 'assist'),
      'stl': ('steals', 'steals'), 'blk': ('blocks', 'blockar'), 'tpm': ('threes', 'treor')}


def headlines(p):
    # points first, then every other number that qualified or is in double figures
    parts = [('pts', p['pts'])]
    for k in ('reb', 'ast', 'stl', 'blk'):
        lim = {'reb': 10, 'ast': 10, 'stl': 5, 'blk': 5}[k]
        if p[k] >= lim:
            parts.append((k, p[k]))
    if p['tpm'] >= 6:
        parts.append(('tpm', p['tpm']))
    en = [f'{v} {EN[k][0]}' for k, v in parts]
    sv = [f'{v} {EN[k][1]}' for k, v in parts]
    join = lambda xs, a: xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + f' {a} ' + xs[-1]
    fg = f"{p['fgm']}/{p['fga']}"
    if p['fga'] and p['fgm'] == p['fga']:
        return f"{join(en, 'and')} on perfect {fg} shooting", f"{join(sv, 'och')} med perfekta {fg} från fältet"
    return f"{join(en, 'and')} ({fg} FG)", f"{join(sv, 'och')} ({fg} från fältet)"


def home_nt():
    """National team players who play in the SBL (data/ntroster.json rows with a home_club): (roster name, surname, club)."""
    out = []
    for r in U.load('ntroster'):
        if r.get('home_club'):
            out.append((r['player'], U.norm(r['player']).split()[-1], team_name(r['home_club'])))
    return out


def add_home_lines(feed, gid, day, home, gl):
    """Game-log rows for the national team players in this SBL game. Returns the players that got a new row."""
    got = set()
    for ti, t in enumerate(feed['teams']):
        o = feed['teams'][1 - ti]
        club = team_name(t['name'])
        for p in t['pl']:
            nm = U.norm(p.get('name') or '').split()
            for full, sur, hc in home:
                # the league sometimes misspells first names (Micheal Odinks), so surname + club decide
                if not nm or nm[-1] != sur or club != hc or any(x.get('player') == full and x.get('date') == day for x in gl):
                    continue
                if not p.get('min') or U.as_min(p.get('min')) == 0:
                    continue
                v = lambda k: p.get(k) or 0
                gl.append(dict(row_id=f"{sur}-{day}", player=full, date=day, competition='Basketligan', team=club, opponent=team_name(o['name']),
                               venue='Home' if ti == 0 else 'Away', result=f"{'W' if t['score'] > o['score'] else 'L'} {t['score']}-{o['score']}",
                               min=U.as_min(p['min']), pts=v('pts'), reb=v('reb'), ast=v('ast'),
                               source=f'FIBA LiveStats (Basketligan, game {gid})', fg=f"{v('fgm')}/{v('fga')}", three=f"{v('tpm')}/{v('tpa')}",
                               ft=f"{v('ftm')}/{v('fta')}", oreb=v('oreb'), dreb=v('dreb'), stl=v('stl'), blk=v('blk'), tov=v('tov'),
                               pf=v('pf'), pm=p.get('pm', ''), eff=''))
                got.add(full)
    return got


def home_averages(players, gl, st):
    """Season averages in data/stats.json from the game log (every SBL game is read, so the log is the whole season)."""
    for full in players:
        logs = [x for x in gl if x.get('player') == full and x.get('competition') == 'Basketligan']
        if not logs:
            continue
        n = len(logs)
        avg = lambda k: round(sum(float(x.get(k) or 0) for x in logs) / n, 1)
        row = next((x for x in st if x.get('player') == full and x.get('competition') == 'Basketligan'), None)
        if row is None:
            row = dict(row_id=U.norm(full).split()[-1] + '-sbl', player=full, competition='Basketligan', season='2026-27')
            st.append(row)
        row.update(gp=n, min=avg('min'), pts=avg('pts'), reb=avg('reb'), ast=avg('ast'),
                   note=f"Averages from game log ({n} games, through {max(x['date'] for x in logs)})")


def main(argv):
    if '--force' not in argv and U.now().minute >= 6:
        return 0
    days = int(argv[argv.index('--days') + 1]) if '--days' in argv else 4
    rows = U.load('sbl')
    have = {r.get('row_id') for r in rows}
    # the same game may already be there under another spelling of the name (RealGM vs the league)
    seen = {(r.get('date'), r.get('team'), r.get('pts'), r.get('reb'), r.get('ast')) for r in rows}
    added = 0
    home, gl, st, new_lines = home_nt(), U.load('gamelogs'), U.load('stats'), set()
    for gid, day in finished_games(days):
        try:
            feed = U.read_fiba(gid)
        except Exception as e:
            print(f'  sbl {gid}: feed error {e}')
            continue
        if not feed.get('done') or len(feed.get('teams') or []) != 2:
            continue
        if home:
            new_lines |= add_home_lines(feed, gid, day, home, gl)
        for ti, t in enumerate(feed['teams']):
            o = feed['teams'][1 - ti]
            for p in t['pl']:
                p = {k: (v or 0) if k not in ('name', 'min', 'pm') else v for k, v in p.items()}
                tags = qualifies(p)
                if not tags or not p['name']:
                    continue
                rid = re.sub(r'[^a-z]', '', U.norm(p['name']).replace(' ', ''))[:12] + '-' + day
                if rid in have or (day, team_name(t['name']), p['pts'], p['reb'], p['ast']) in seen:
                    continue
                en, sv = headlines(p)
                # national team players at home: our spelling (the league has "Micheal Odinks")
                name = next((full for full, sur, hc in home if U.norm(p['name']).split()[-1] == sur and team_name(t['name']) == hc), p['name'])
                rows.append(dict(row_id=rid, date=day, player=name, team=team_name(t['name']), opponent=team_name(o['name']),
                                 venue='Home' if ti == 0 else 'Away',
                                 result=f"{'W' if t['score'] > o['score'] else 'L'} {t['score']}-{o['score']}",
                                 min=U.as_min(p['min']), pts=p['pts'], reb=p['reb'], ast=p['ast'], stl=p['stl'], blk=p['blk'],
                                 fg=f"{p['fgm']}/{p['fga']}", three=f"{p['tpm']}/{p['tpa']}", ft=f"{p['ftm']}/{p['fta']}",
                                 tags=', '.join(tags), headline=en, headline_sv=sv,
                                 source=f'FIBA LiveStats (Basketligan, game {gid})'))
                have.add(rid)
                seen.add((day, team_name(t['name']), p['pts'], p['reb'], p['ast']))
                added += 1
                print(f'  sbl: {rid} {", ".join(tags)}')
    # the next games of the national team players who play at home, for their profiles
    clubs, coming_changed = {}, False
    for full, _, club in home:
        clubs.setdefault(club, []).append(full)
    try:
        nxt = coming_games(clubs) if clubs else []
        try:
            old = U.load('sblgames')
        except Exception:
            old = None
        if nxt != old:
            U.save('sblgames', nxt)
            coming_changed = True
    except Exception as e:
        print(f'  sbl: coming games not read ({e.__class__.__name__})')
    if new_lines:
        home_averages(new_lines, gl, st)
        U.save('gamelogs', gl)
        U.save('stats', st)
        print(f"sbl: game log updated for {', '.join(sorted(new_lines))}")
    if added or new_lines or coming_changed:
        U.write_version(True)
    if added:
        rows.sort(key=lambda r: r.get('date') or '', reverse=True)
        U.save('sbl', rows)
    print(f'sbl: {added} new')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
