"""
More free live sources the GitHub job can read (FIBA LiveStats, NBA via ESPN and EuroLeague are in update.py):
  ACB (Liga Endesa)          live_feed "acb:<match id>"   page live.acb.com/es/partidos/x-<id>/estadisticas
  FEB (Primera / Segunda)    live_feed "feb:<match id>"   page baloncestoenvivo.feb.es/partido/<id>
  BBL (Germany)              live_feed "bbl:<game id>"    page easycredit-bbl.de/spiele/<id> (its embedded game JSON)
  BCL (Champions League)     live_feed "bcl:<game id>"    page championsleague.basketball/en/games/<id> (FIBA's own box score)
  LBA (Italy, Serie A)       live_feed "lba:<game id>"    page legabasket.it/game/<id>/x (its __NEXT_DATA__ JSON)
  LKL (Lithuania)            live_feed "lkl:<game id>"    JSON lkl.lt/api/livestream/boxscore/<id> (id from lkl.lt/rungtynes/<id>)
Each reader returns the same shape as the other feeds: {period, clock, done, teams: [{name, score, pl: [...]}]}.
"""
import datetime as dt
import html as H
import re

import update as U

CELL = re.compile(r'<t[dh][^>]*>(.*?)</t[dh]>', re.S)


def clean(s):
    return re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', s))).strip()


def text(h):
    return clean(re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', h, flags=re.S))


def page(url):
    import urllib.request
    req = urllib.request.Request(url, headers=dict(U.BROWSER, Accept='text/html,*/*'))
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode('utf-8', 'replace')


def ma(s):
    m = re.match(r'\s*(\d+)\s*/\s*(\d+)', s or '')
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def n(s):
    s = (s or '').strip().replace('+', '')
    return int(s) if re.fullmatch(r'-?\d+', s) else 0


def mins(s):
    m = re.match(r'(\d+):(\d+)', s or '')
    return int(m.group(1)) if m else 0


# ------------------------------------------------------------------ ACB
def read_acb(mid):
    h = page(f'https://live.acb.com/es/partidos/x-{mid}/estadisticas')
    t = text(h)
    title = re.search(r'<title>(.*?)</title>', h, re.S)
    tm = re.match(r'\s*(.+?) vs (.+?) \d+ \w+ \d{4}', H.unescape(title.group(1))) if title else None
    names = [tm.group(1), tm.group(2)] if tm else []
    sm = re.search(r'Loading\.\.\. (\d+) (.{1,24}?) (\d+) ', t)
    status = sm.group(2) if sm else ''
    tables = [x for x in re.split(r'<table', h) if 'playerRow' in x]
    teams = []
    for ti, tb in enumerate(tables[:2]):
        pl = []
        for row in re.findall(r'<tr[^>]*playerRow[^>]*>(.*?)</tr>', tb, re.S):
            c = [clean(x) for x in CELL.findall(row)]
            if len(c) < 22 or not re.match(r'\d+:\d+', c[1]):
                continue
            name = re.sub(r'^\d+\s+', '', c[0]).strip()
            t2m, t2a = ma(c[3]); t3m, t3a = ma(c[5]); ftm, fta = ma(c[7])
            pl.append(dict(name=name, min=mins(c[1]), pts=n(c[2]), fgm=t2m + t3m, fga=t2a + t3a, tpm=t3m, tpa=t3a, ftm=ftm, fta=fta,
                           oreb=n(c[9]), dreb=n(c[10]), reb=n(c[11]), ast=n(c[12]), tov=n(c[13]), stl=n(c[14]), blk=n(c[15]),
                           pf=n(c[18]), pm=n(c[20]), starter=False))
        teams.append(dict(name=names[ti] if ti < len(names) else '', score=0, pl=pl))
    if sm and len(teams) == 2:
        teams[0]['score'], teams[1]['score'] = int(sm.group(1)), int(sm.group(3))
    q = re.search(r'(\d)\s*C', status)
    clk = re.search(r'(\d{1,2}):(\d{2})', status)
    return dict(period=int(q.group(1)) if q else (4 if 'Final' in status else 1),
                clock=f'{int(clk.group(1)):02d}:{clk.group(2)}' if clk else '00:00',
                done='Final' in status, teams=teams)


# ------------------------------------------------------------------ BBL
def _bbl_page(gid):
    import json
    t = page(f'https://www.easycredit-bbl.de/spiele/{gid}').replace('\\"', '"').replace('\\\\', '\\')
    dec = json.JSONDecoder()
    i = t.find('"initialGameData":')
    if i < 0:
        raise LookupError('no game data on the BBL page')
    head, _ = dec.raw_decode(t[i + len('"initialGameData":'):])
    sides = {}
    for side in ('homeTeam', 'guestTeam'):
        m = re.search(r'"' + side + r'":\{"id":"\d+","headCoachName"', t)
        sides[side] = dec.raw_decode(t[m.start() + len(side) + 3:])[0] if m else {}
    return head, sides


def read_bbl(gid, row=None):
    head, sides = _bbl_page(gid)
    res = head.get('result') or {}
    teams = []
    for side, key in (('homeTeam', 'homeTeamFinalScore'), ('guestTeam', 'guestTeamFinalScore')):
        pl = []
        for p in (sides.get(side) or {}).get('playerStats') or []:
            sp = p.get('seasonPlayer') or {}
            g = lambda k: p.get(k) or 0
            pl.append(dict(name=' '.join(f"{sp.get('firstName', '')} {sp.get('lastName', '')}".split()), min=int(g('secondsPlayed')) // 60,
                           pts=g('points'), reb=g('totalRebounds'), ast=g('assists'), stl=g('steals'), blk=g('blocks'), tov=g('turnovers'),
                           fgm=g('fieldGoalsMade'), fga=g('fieldGoalsAttempted'), tpm=g('threePointShotsMade'), tpa=g('threePointShotsAttempted'),
                           ftm=g('freeThrowsMade'), fta=g('freeThrowsAttempted'), pm=p.get('plusMinus') if p.get('plusMinus') is not None else '',
                           pf=g('foulsCommitted'), oreb=g('offensiveRebounds'), dreb=g('defensiveRebounds'), starter=bool(p.get('isStartingFive'))))
        teams.append(dict(name=(head.get(side) or {}).get('name', ''), score=int(res.get(key) or 0), pl=pl))
    status = str(head.get('status') or '').upper()
    prog = str(head.get('gameProgress') or '')
    per = str(res.get('latestPeriod') or 'Q1')
    pn = int(re.sub(r'\D', '', per) or 1) + (4 if per.startswith('OT') else 0)
    done = status in ('OFFICIAL', 'ENDED', 'FINISHED') or prog == 'E'
    started = done or status in ('LIVE', 'RUNNING', 'STARTED') or any(t['score'] for t in teams)
    clk = str(head.get('gameTime') or '')
    m = re.search(r'(\d{1,2}):(\d{2})(?::(\d{2}))?$', clk)
    clock = '00:00' if done else (f'{int(m.group(2)) if m.group(3) else int(m.group(1)):02d}:{m.group(3) or m.group(2)}' if m else '')
    return dict(period=4 if done and pn < 4 else pn, clock=clock, done=done, notstarted=not started, teams=teams)


def find_bbl(row, seed=None):
    """BBL game ids are not in date order (the whole season is created at once), so use the id table in
    data/_bbl_ids.json ({id: {home, guest, time}}, built once from the league's game pages) and check the page itself."""
    import json
    import os
    path = os.path.join(U.DATA, '_bbl_ids.json')
    table = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    day = dt.date.fromisoformat(row['date'])
    for gid, g in sorted(table.items()):
        names = f"{g.get('home') or ''} {g.get('guest') or ''}"
        when = str(g.get('time') or '')[:10]
        if not when or not (words(row.get('team', '')) & words(names) and words(row.get('opponent', '')) & words(names)):
            continue
        if abs((dt.date.fromisoformat(when) - day).days) <= 1:
            try:
                head, _ = _bbl_page(gid)
            except Exception:
                continue
            n2 = f"{(head.get('homeTeam') or {}).get('name', '')} {(head.get('guestTeam') or {}).get('name', '')}"
            if words(row.get('team', '')) & words(n2) and words(row.get('opponent', '')) & words(n2):
                return f'bbl:{gid}'
    return None


# ------------------------------------------------------------------ BCL
def _bcl_parse(h):
    t = h.replace('\\"', '"')
    names = {m.group(1): f"{m.group(2)} {m.group(3)}" for m in re.finditer(r'"personId":(\d+),"firstName":"([^"]*)","lastName":"([^"]*)"', t)}
    starts = list(re.finditer(r'\{"Id":"T_(\d+)","Score":(\d+)', t))[:2]
    teams = []
    for i, m in enumerate(starts):
        seg = t[m.start(): starts[i + 1].start() if i + 1 < len(starts) else m.start() + 80000]
        pl = []
        for p in re.finditer(r'\{"Id":"P_(\d+)","Stats":\{([^{}]*)\}', seg):
            st = dict((k, v.strip('"')) for k, v in re.findall(r'"(\w+)":("?[^,"]*"?)', p.group(2)))
            nn = lambda k: int(float(st.get(k) or 0))
            mn = st.get('TP') or ''
            pl.append(dict(name=names.get(p.group(1), p.group(1)), min=int(mn.split(':')[0]) if mn[:1].isdigit() else 0, pts=nn('PTS'),
                           reb=nn('REB'), ast=nn('AS'), stl=nn('ST'), blk=nn('BS'), tov=nn('TO'), fgm=nn('FGM'), fga=nn('FGA'),
                           tpm=nn('FG3M'), tpa=nn('FG3A'), ftm=nn('FTM'), fta=nn('FTA'), pm=nn('PM') if st.get('PM') not in (None, '') else '',
                           pf=nn('PF'), oreb=nn('OR'), dreb=nn('DR'), starter=st.get('Starter') == 'true'))
        teams.append(dict(name='', score=int(m.group(2)), pl=pl))
    return t, teams


def read_bcl(gid, row=None):
    t, teams = _bcl_parse(page(f'https://www.championsleague.basketball/en/games/{gid}'))
    gm = re.search(r'"gameId":' + str(gid) + r',.*?"teamA":\{[^{}]*"officialName":"([^"]*)"[^{}]*\},"teamB":\{[^{}]*"officialName":"([^"]*)"[^{}]*\},"teamAScore":(\w+),"teamBScore":(\w+),"isLive":(\w+),"currentPeriod":"?(\w*)"?,"chrono":"?([^",]*)"?,"liveGameStatus":(\w+),"currentPeriodStatus":"?(\w*)', t, re.S)
    if not gm:
        raise LookupError('game header not found on the BCL page')
    a, b, sa, sb, live, per, chrono, lgs, pst = gm.groups()
    score = [int(sa) if sa.isdigit() else 0, int(sb) if sb.isdigit() else 0]
    if len(teams) != 2:
        teams = [dict(name='', score=0, pl=[]), dict(name='', score=0, pl=[])]
    for k, nm in enumerate((a, b)):
        teams[k]['name'] = nm
        teams[k]['score'] = max(teams[k]['score'], score[k])
    done = lgs == '999' or (live == 'false' and pst == 'E' and any(score))
    pn = int(re.sub(r'\D', '', per) or 1) + (4 if per.startswith('OT') else 0)
    clock = '00:00' if done else (chrono[:5] if re.match(r'\d{2}:\d{2}', chrono) else '')
    return dict(period=pn if pn else 1, clock=clock, done=done, notstarted=not done and live != 'true' and not any(score), teams=teams)


def find_bcl(row):
    h = page('https://www.championsleague.basketball/en/games').replace('\\"', '"')
    for m in re.finditer(r'\{"gameId":(\d+),"gameName":"[^"]*","gameNumber":"[^"]*","statusCode":"[^"]*","teamA":\{[^{}]*"officialName":"([^"]*)","shortName":"([^"]*)"\},"teamB":\{[^{}]*"officialName":"([^"]*)","shortName":"([^"]*)"\}.*?"gameDateTime":"([^"]*)"', h):
        gid, a1, a2, b1, b2, when = m.groups()
        names = f'{a1} {a2} {b1} {b2}'
        if words(row.get('team', '')) & words(names) and words(row.get('opponent', '')) & words(names):
            d = when[:10]
            if abs((dt.date.fromisoformat(d) - dt.date.fromisoformat(row['date'])).days) <= 1:
                return f'bcl:{gid}'
    return None


# ------------------------------------------------------------------ LBA
def _lba_game(gid):
    import json
    h = page(f'https://www.legabasket.it/game/{gid}/x')
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', h, re.S)
    return json.loads(m.group(1))['props']['pageProps']['game']


def read_lba(gid, row=None):
    g = _lba_game(gid)
    m = g['match']
    teams = []
    for side, name, final in (('ht', m.get('h_team_name'), m.get('home_final_score')), ('vt', m.get('v_team_name'), m.get('visitor_final_score'))):
        sc = (g.get('scores') or {}).get(side) or {}
        pl = []
        for p in sc.get('rows') or []:
            first = str(p.get('player_name') or '').strip()
            last = str(p.get('player_surname') or '').strip().title()
            pl.append(dict(name=f'{first} {last}'.strip(), min=int(p.get('min') or 0), pts=p.get('pun') or 0,
                           reb=p.get('rimbalzi_t') or 0, ast=p.get('ass') or 0, stl=p.get('palle_r') or 0,
                           blk=p.get('stoppate_dat') or 0, tov=p.get('palle_p') or 0,
                           fgm=(p.get('t2_r') or 0) + (p.get('t3_r') or 0), fga=(p.get('t2_t') or 0) + (p.get('t3_t') or 0),
                           tpm=p.get('t3_r') or 0, tpa=p.get('t3_t') or 0, ftm=p.get('tl_r') or 0, fta=p.get('tl_t') or 0,
                           pm=p.get('plus_minus') if p.get('plus_minus') is not None else '', pf=p.get('falli_c') or 0,
                           oreb=p.get('rimbalzi_o') or 0, dreb=p.get('rimbalzi_d') or 0, starter=False))
        total = ((sc.get('totals') or {}).get('pun')) or 0
        teams.append(dict(name=name or '', score=max(int(final or 0), int(total or 0)), pl=pl))
    status = str(m.get('game_status') or '0')
    q = str(m.get('quarter') or (g.get('scores') or {}).get('quarter') or '')
    qn = re.search(r'(\d)', q)
    per = int(qn.group(1)) if qn else 1
    if re.search(r'OT|SUPP', q, re.I):
        per = 4 + max(per, 1)
    done = status == '2'
    started = done or status == '1' or any(t['score'] for t in teams)
    return dict(period=4 if done else per, clock='00:00' if done else '', done=done, notstarted=not started, teams=teams)


def find_lba(row):
    """The league's front page lists the current round's games as /game/<id>/<home-slug>-<away-slug>."""
    h = page('https://www.legabasket.it/')
    for gid, sl in set(re.findall(r'/game/(\d+)/([a-z0-9-]+)', h)):
        if same_game(sl.replace('-', ' '), '', row) or (words(row.get('team', '')) & set(sl.split('-')) and words(row.get('opponent', '')) & set(sl.split('-'))):
            try:
                m = _lba_game(gid)['match']
            except Exception:
                continue
            if str(m.get('match_datetime', ''))[:10] in (row.get('date'),) or abs((dt.date.fromisoformat(str(m['match_datetime'])[:10]) - dt.date.fromisoformat(row['date'])).days) <= 1:
                names = f"{m.get('h_team_name')} {m.get('v_team_name')}"
                if words(row.get('team', '')) & words(names) and words(row.get('opponent', '')) & words(names):
                    return f'lba:{gid}'
    return None


# ------------------------------------------------------------------ LKL
def read_lkl(gid, row=None):
    """LKL's own live JSON. It has no team names, so home/away comes from the schedule row."""
    b = U.get(f'https://lkl.lt/api/livestream/boxscore/{gid}')['boxscore']
    sc = U.get(f'https://lkl.lt/api/livestream/game-score/{gid}')
    row = row or {}
    home_is_us = (row.get('venue') or 'Home') != 'Away'
    names = {'home': row.get('team', '') if home_is_us else row.get('opponent', ''),
             'away': row.get('opponent', '') if home_is_us else row.get('team', '')}
    v = lambda p, k: (p.get(k) or {}).get('value')
    teams = []
    for side in ('home', 'away'):
        pl = []
        for p in (b.get(side) or {}).get('players') or []:
            fgm, fga = ma(v(p, 'fg')); tpm, tpa = ma(v(p, 'fg3')); ftm, fta = ma(v(p, 'ft'))
            pl.append(dict(name=v(p, 'name') or '', min=mins(v(p, 'time')), pts=v(p, 'points') or 0, reb=v(p, 'total_rebounds') or 0,
                           ast=v(p, 'assists') or 0, stl=v(p, 'steals') or 0, blk=v(p, 'blocks') or 0, tov=v(p, 'turnovers') or 0,
                           fgm=fgm, fga=fga, tpm=tpm, tpa=tpa, ftm=ftm, fta=fta, pm=v(p, 'plus_minus') if v(p, 'plus_minus') is not None else '',
                           pf=v(p, 'fouls') or 0, oreb=v(p, 'offensive_rebounds') or 0, dreb=v(p, 'defensive_rebounds') or 0,
                           starter=bool(p.get('is_starter'))))
        teams.append(dict(name=names[side], score=int(sc.get(side) or 0), pl=pl))
    clock = str(sc.get('clock') or '')
    q = re.match(r'\s*(\d+)', clock)
    per = int(q.group(1)) if q else 0
    if re.search(r'pratęs|OT', clock, re.I):
        per = max(per, 1) + 4
    t = re.search(r'(\d{1,2}):(\d{2})\s*$', clock)
    clk = f'{int(t.group(1)):02d}:{t.group(2)}' if t else ''
    done = per >= 4 and clk == '00:00' and teams[0]['score'] != teams[1]['score']
    return dict(period=per or 1, clock=clk, done=done, notstarted=not clock and not any(x['score'] for x in teams), teams=teams)


# ------------------------------------------------------------------ FEB
def read_feb(pid, row=None):
    h = page(f'https://baloncestoenvivo.feb.es/partido/{pid}')
    t = text(h)
    sm = re.search(r'Estad[ií]sticas (.+?) (\d+) p (\d+) (.+?) \d', t)
    names = re.findall(r"([A-ZÀ-ÝÑÇ][A-ZÀ-ÝÑÇ0-9 .'&-]{2,60}?) Rebotes Tapones", t)
    tables = [x for x in re.split(r'<table', h) if 'Jugador' in x]
    teams = []
    for ti, tb in enumerate(tables[:2]):
        pl = []
        for row_h in re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S):
            c = [clean(x) for x in CELL.findall(row_h)]
            # I D Jugador MIN PT T2 T3 TC TL RO RD RT AS BR BP TF TC MT FC FR VA +/-
            if len(c) < 21 or not re.match(r'\d+:\d+', c[3]) or not c[2] or c[2].lower().startswith('total'):
                continue
            t3m, t3a = ma(c[6]); fgm, fga = ma(c[7]); ftm, fta = ma(c[8])
            nm = c[2]
            if ',' in nm:
                a, b = nm.split(',', 1)
                nm = f'{b.strip().title()} {a.strip().title()}'
            pl.append(dict(name=nm, min=mins(c[3]), pts=n(c[4]), fgm=fgm, fga=fga, tpm=t3m, tpa=t3a, ftm=ftm, fta=fta,
                           oreb=n(c[9]), dreb=n(c[10]), reb=n(c[11]), ast=n(c[12]), stl=n(c[13]), tov=n(c[14]), blk=n(c[15]),
                           pf=n(c[18]), pm=n(c[21]) if len(c) > 21 else '', starter=c[0].strip() == '*'))
        teams.append(dict(name=names[ti] if ti < len(names) else '', score=0, pl=pl))
    if sm and len(teams) == 2:
        teams[0]['score'], teams[1]['score'] = int(sm.group(2)), int(sm.group(3))
        teams[0]['name'] = teams[0]['name'] or sm.group(1)
        teams[1]['name'] = teams[1]['name'] or sm.group(4)
    qs = re.findall(r'(\d)º C', t)
    period = int(qs[-1]) if qs else 1
    done = bool(re.search(r'\bFinal(izado)?\b', t))
    if row is not None:
        tip = U.tip_time(row)
        if tip and U.now() > tip + dt.timedelta(hours=2, minutes=40):
            done = True
    return dict(period=period, clock='00:00' if done else '', done=done, teams=teams)


# ------------------------------------------------------------------ discovery
def words(s):
    return {w for w in U.norm(s).split() if len(w) > 2 and w not in {'club', 'basket', 'basquet', 'baloncesto', 'bàsquet', 'caja', 'rural', 'grupo'}}


def same_game(a1, a2, row):
    t, o = words(row.get('team')), words(row.get('opponent'))
    w1, w2 = words(a1), words(a2)
    return bool((t & w1 and o & w2) or (t & w2 and o & w1))


FEB_COMP = {'Primera FEB': 1, 'Segunda FEB': 2}


def feb_teams(pid):
    t = text(page(f'https://baloncestoenvivo.feb.es/partido/{pid}'))
    m = re.search(r'Estad[ií]sticas (.+?) \d+ p \d+ (.+?) \d', t) or re.search(r'Estad[ií]sticas (.+?) p (.+?) \d', t)
    d = re.search(r'Fecha (\d{2}/\d{2}/\d{4})', t)
    return (m.group(1), m.group(2), d.group(1) if d else '') if m else None


def find_feb(row):
    g = FEB_COMP.get(row.get('competition'))
    if not g:
        return None
    day = dt.date.fromisoformat(row['date']).strftime('%d/%m/%Y')
    h = page(f'https://baloncestoenvivo.feb.es/resultados.aspx?g={g}&t=2026')
    ids = []
    for tr in re.findall(r'<tr>(.*?)</tr>', h, re.S):
        pid = re.search(r'Partido\.aspx\?p=(\d+)', tr)
        if not pid:
            continue
        ids.append(int(pid.group(1)))
        teams = [clean(x) for x in re.findall(r'Equipo\.aspx\?i=\d+">(.*?)</a>', tr)]
        if day in tr and len(teams) == 2 and same_game(teams[0], teams[1], row):
            return f'feb:{pid.group(1)}'
    # other groups (e.g. Segunda FEB "B") are not on the default page: their games have ids close to these
    if not ids:
        return None
    lo, hi = min(ids), max(ids)
    for pid in list(range(hi + 1, hi + 60)) + list(range(lo - 40, lo)):
        try:
            tm = feb_teams(pid)
        except Exception:
            continue
        if tm and tm[2] == day and same_game(tm[0], tm[1], row):
            return f'feb:{pid}'
    return None


def find_acb(row, seed):
    for k in list(range(1, 60)) + [-k for k in range(1, 30)]:
        mid = seed + k
        try:
            h = page(f'https://live.acb.com/es/partidos/x-{mid}/estadisticas')
        except Exception:
            continue
        title = re.search(r'<title>(.*?)</title>', h, re.S)
        if not title:
            continue
        m = re.match(r'\s*(.+?) vs (.+?) (\d+ \w+ \d{4})', H.unescape(title.group(1)))
        if m and same_game(m.group(1), m.group(2), row):
            return f'acb:{mid}'
    return None


def find_euroleague(row):
    j = U.get('https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games')
    for g in j.get('data', []):
        if str(g.get('date', ''))[:10] not in (row['date'], (dt.date.fromisoformat(row['date']) - dt.timedelta(days=1)).isoformat()):
            continue
        if same_game(g['local']['club']['name'], g['road']['club']['name'], row):
            return f"euroleague:E2026:{g['gameCode']}"
    return None
