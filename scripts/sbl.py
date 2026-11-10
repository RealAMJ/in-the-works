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
import json, re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

COMP = 48974
SCHEDULE = f'https://hosted.dcd.shared.geniussports.com/SBF/en/competition/{COMP}/schedule'

# League names -> the spellings the site uses (checked in this order, so Sloga comes before Uppsala Basket)
TEAMS = [('sloga', 'Sloga Uppsala'), ('uppsala', 'Uppsala Basket'), ('boras', 'Borås Basket'), ('nassjo', 'Nässjö Basket'),
         ('hogsbo', 'Högsbo Lions'), ('sodertalje', 'Södertälje BBK'), ('jamtland', 'Jämtland Basket'), ('norrkoping', 'Norrköping Dolphins'), ('koping', 'Köping Stars'),
         ('umea', 'Umeå Basket'), ('lulea', 'BC Luleå')]
# the clubs' own names (Andres, 10 Nov): older spellings in our data are renamed by rename_teams()
RENAMED = {'Södertälje Kings': 'Södertälje BBK', 'KFUM Nässjö': 'Nässjö Basket', 'Högsbo': 'Högsbo Lions', 'Umeå BSKT': 'Umeå Basket'}


def rename_teams():
    """Put the clubs' current names in every data file that holds this season's SBL games (team fields only;
    career and bio text keep the name the club had then)."""
    changed = False
    for fn in ('sbl', 'sblbox', 'sblleague', 'sblgames', 'sblroster', 'sblplayers', 'gamelogs', 'stats', 'teamform', 'ntroster'):
        p = os.path.join(U.DATA, fn + '.json')
        if not os.path.exists(p):
            continue
        rows, n = json.load(open(p, encoding='utf-8')), 0
        for r in rows if isinstance(rows, list) else []:
            for k in ('team', 'opponent', 'home', 'away', 'club', 'home_club'):
                if isinstance(r, dict) and r.get(k) in RENAMED:
                    r[k] = RENAMED[r[k]]; n += 1
        if n:
            U.save(fn, rows); changed = True
    lp = os.path.join(U.DATA, 'logos.json')
    if os.path.exists(lp):
        L = json.load(open(lp, encoding='utf-8')); n = 0
        for r in L:
            if r.get('team') in RENAMED:
                r['team'] = RENAMED[r['team']]; n += 1
        if n:
            json.dump(sorted(L, key=lambda r: r['team']), open(lp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1); changed = True
    return changed


# One spelling per player: the league's feeds, RealGM and the squads spell some players differently.
# Keys are U.norm() of a spelling we have seen; values are the spelling the site uses.
ALIAS = {'stanley onyekachukwu': 'Stan Okoye', 'nicolas galette': 'Nico Galette', 'jordan ivycurry': 'Jordan Ivy Curry',
         'trevaughn minott gauthier': 'Tre-Vaughn Minott', 'ali ali youssouf': 'Ali Ali',
         'deangilo deshawn smith ii': 'DJ Smith', 'deangilo deshawn smith': 'DJ Smith', 'deangilo smith': 'DJ Smith',
         'asthon sherrel': 'Ashton Sherrell', 'atwood newton ii': 'Woody Newton', 'atwood newton': 'Woody Newton', 'markeith lee browning': 'Markeith Browning',
         'markeith browning ii': 'Markeith Browning', 'javier marin ortega': 'Javier Marin', 'fredrik andersson klamberg': 'Fredrik Andersson'}


# players who have left the league: not listed as standouts (Andres, 10 Nov)
LEFT = {'william christopher dunston jr', 'cj dunston', 'andrew akuchie'}


def canon(name):
    return ALIAS.get(U.norm(name), name)


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
    """SBL players with a profile: national team players at home (ntroster rows with a home_club) and data/sblplayers.json.
    Returns (name, surname, club)."""
    out = []
    for r in U.load('ntroster'):
        if r.get('home_club'):
            out.append((r['player'], U.norm(r['player']).split()[-1], team_name(r['home_club'])))
    # other SBL players with a profile on the site (data/sblplayers.json), e.g. a Player of the Month
    try:
        extra = U.load('sblplayers')
    except Exception:
        extra = []
    for r in extra:
        if r.get('player') and r.get('club') and not any(o[0] == r['player'] for o in out):
            out.append((r['player'], U.norm(r['player']).split()[-1], team_name(r['club'])))
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


# ---- The whole league: every game (sblleague.json), every box score (sblbox.json) and every team's logo
def league_games():
    """All league games from the schedule page: [dict(game_id, date, time, home, away, hs, as_, status)]."""
    out = []
    for m in re.finditer(r'match-wrap (STATUS_\w+)"\s*id\s*=\s*"extfix_(\d+)"(.*?)(?=match-wrap STATUS_|\Z)', schedule_page(), re.S):
        status, gid, block = m.groups()
        d = re.search(r'match-time.*?<span>([A-Z][a-z]{2} \d{1,2}, \d{4}),?\s*(\d{1,2}:\d{2}\s*[AP]M)?', block, re.S)
        names = re.findall(r'team-name-full">([^<]+)<', block)
        if not d or len(names) < 2:
            continue
        day = dt.datetime.strptime(d.group(1), '%b %d, %Y').date()
        tm = dt.datetime.strptime(d.group(2).replace(' ', ''), '%I:%M%p').strftime('%H:%M') if d.group(2) else 'TBC'
        sc = lambda cls: (re.search(cls + r'.*?fake-cell">\s*(\d+)\s*<', block, re.S) or [None, None])[1]
        hs, as_ = sc('homescore'), sc('awayscore')
        st = 'final' if status == 'STATUS_COMPLETE' else 'upcoming' if status == 'STATUS_SCHEDULED' else 'live'
        out.append(dict(game_id=f'sbl-{gid}', date=day.isoformat(), time=tm, home=team_name(names[0].strip()), away=team_name(names[1].strip()),
                        hs=int(hs) if hs and st != 'upcoming' else None, as_=int(as_) if as_ and st != 'upcoming' else None, status=st,
                        url=f'https://hosted.dcd.shared.geniussports.com/SBF/en/competition/{COMP}/match/{gid}/summary'))
    out.sort(key=lambda r: (r['date'], r['time']))
    return out


def _tip(g):
    try:
        return dt.datetime.strptime(f"{g['date']} {g['time']}", '%Y-%m-%d %H:%M').replace(tzinfo=U.now().tzinfo)
    except Exception:
        return None


def clear_bg(im):
    """The league's logos sit on a white square: make the white that touches the edges transparent and trim it."""
    from PIL import Image, ImageDraw
    im = im.convert('RGBA'); w, h = im.size
    for xy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        r, g, b, a = im.getpixel(xy)
        if a > 200 and r > 235 and g > 235 and b > 235:
            ImageDraw.floodfill(im, xy, (255, 255, 255, 0), thresh=40)
    box = im.getbbox()
    im = im.crop(box) if box else im
    # back onto a square canvas with a small margin, so tall and wide logos sit in the crest circle like the others
    side = int(max(im.size) * 1.08); sq = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
    return sq


def _save_logo(name, url, have):
    """Copy a team's logo from the league feed into logos/ (once)."""
    if not url or name in have:
        return False
    try:
        import io, logos as LG
        from PIL import Image
        with urllib.request.urlopen(urllib.request.Request(url, headers=U.UA), timeout=30) as r:
            im = Image.open(io.BytesIO(r.read())).convert('RGBA')
        im = clear_bg(im)
        im.thumbnail((128, 128))
        fn = 'logos/' + LG.slug(name) + '.png'
        im.quantize(colors=128, method=Image.Quantize.FASTOCTREE).save(os.path.join(U.ROOT, fn), optimize=True)
        have[name] = {'team': name, 'src': fn, 'source': 'Basketligan (FIBA LiveStats)', 'dark': LG.is_dark(os.path.join(U.ROOT, fn))}
        return True
    except Exception as e:
        print(f'  sbl logo {name}: {e.__class__.__name__}')
        return False


def league(only_live=False, limit=60):
    """Refresh the league's games and box scores. Finished games are read once; games that are on are read every run."""
    games = league_games()
    old = {g['game_id']: g for g in (U.load('sblleague') if os.path.exists(os.path.join(U.DATA, 'sblleague.json')) else [])}
    box = U.load('sblbox') if os.path.exists(os.path.join(U.DATA, 'sblbox.json')) else []
    lp = os.path.join(U.DATA, 'logos.json')
    have_logos = {r['team']: r for r in json.load(open(lp, encoding='utf-8'))} if os.path.exists(lp) else {}
    home = home_nt()
    now, n, changed, logos_changed = U.now(), 0, False, False
    for g in games:
        o = old.get(g['game_id']) or {}
        g['box'] = o.get('box', False)
        t = _tip(g)
        on = g['status'] == 'live' or (g['status'] == 'upcoming' and t and t <= now <= t + dt.timedelta(hours=3))
        want = on or (g['status'] == 'final' and not g['box'])
        if only_live and not on:
            continue
        if not want or n >= limit:
            continue
        n += 1
        try:
            f = U.read_fiba(g['game_id'][4:])
        except Exception as e:
            print(f"  sbl {g['game_id']}: feed error {e.__class__.__name__}")
            continue
        if len(f.get('teams') or []) != 2:
            continue
        for t in f['teams']:
            logos_changed |= _save_logo(team_name(t['name']), t.get('logo'), have_logos)
        lines = []
        for ti, t in enumerate(f['teams']):
            for i, p in enumerate(t['pl']):
                if not p['name']:
                    continue
                swede = any(U.norm(p['name']).split()[-1] == sur and team_name(t['name']) == hc for _, sur, hc in home)
                name = next((full for full, sur, hc in home if U.norm(p['name']).split()[-1] == sur and team_name(t['name']) == hc), canon(p['name']))
                lines.append(dict(row_id=f"{g['game_id']}-{ti}-{i}", game_id=g['game_id'], team=team_name(t['name']), player=name,
                                  min=U.as_min(p['min']), pts=p['pts'] or 0, reb=p['reb'] or 0, ast=p['ast'] or 0, stl=p['stl'] or 0, blk=p['blk'] or 0, tov=p['tov'] or 0,
                                  fg=f"{p['fgm'] or 0}/{p['fga'] or 0}", three=f"{p['tpm'] or 0}/{p['tpa'] or 0}", ft=f"{p['ftm'] or 0}/{p['fta'] or 0}",
                                  pm=p['pm'], starter=p.get('starter', False), swede=swede, state='final' if f.get('done') else 'live'))
        if lines:
            box = [r for r in box if r['game_id'] != g['game_id']] + lines
            g['box'] = bool(f.get('done'))
            if not f.get('done'):
                g['status'], g['clock'], g['period'] = 'live', f.get('clock') or '', f.get('period') or 0
                g['hs'], g['as_'] = f['teams'][0]['score'], f['teams'][1]['score']
            changed = True
    if [dict(x, box=None) for x in games] != [dict(x, box=None) for x in old.values()] or changed:
        U.save('sblleague', games)
        changed = True
    if changed:
        U.save('sblbox', box)
    if logos_changed:
        json.dump(sorted(have_logos.values(), key=lambda r: r['team']), open(lp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'sbl league: {len(games)} games, {n} feeds read, {len(box)} box lines')
    return changed or logos_changed


def main(argv):
    if '--force' not in argv and U.now().minute >= 6:
        # between the hourly runs, only games that are on right now (read from our own list, so it costs nothing when none are)
        try:
            p = os.path.join(U.DATA, 'sblleague.json')
            on = [g for g in (json.load(open(p, encoding='utf-8')) if os.path.exists(p) else [])
                  if g['status'] == 'live' or (g['status'] == 'upcoming' and _tip(g) and _tip(g) <= U.now() <= _tip(g) + dt.timedelta(hours=3))]
            if on and league(only_live=True):
                U.write_version(True)
        except Exception as e:
            print(f'  sbl live: {e.__class__.__name__} {e}')
        return 0
    league_changed = rename_teams()
    try:
        league_changed = league() or league_changed
    except Exception as e:
        print(f'  sbl league: {e.__class__.__name__} {e}')
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
                if not tags or not p['name'] or U.norm(p['name']) in LEFT:
                    continue
                rid = re.sub(r'[^a-z]', '', U.norm(p['name']).replace(' ', ''))[:12] + '-' + day
                if rid in have or (day, team_name(t['name']), p['pts'], p['reb'], p['ast']) in seen:
                    continue
                en, sv = headlines(p)
                # national team players at home: our spelling (the league has "Micheal Odinks")
                name = next((full for full, sur, hc in home if U.norm(p['name']).split()[-1] == sur and team_name(t['name']) == hc), canon(p['name']))
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
    if added or new_lines or coming_changed or league_changed:
        U.write_version(True)
    if added:
        rows.sort(key=lambda r: r.get('date') or '', reverse=True)
        U.save('sbl', rows)
    print(f'sbl: {added} new')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
