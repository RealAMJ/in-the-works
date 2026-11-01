"""
More free live sources the GitHub job can read (FIBA LiveStats, NBA via ESPN and EuroLeague are in update.py):
  ACB (Liga Endesa)          live_feed "acb:<match id>"   page live.acb.com/es/partidos/x-<id>/estadisticas
  FEB (Primera / Segunda)    live_feed "feb:<match id>"   page baloncestoenvivo.feb.es/partido/<id>
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
    names = re.findall(r"(?:4C|Todos 1C 2C 3C 4C|\d+ \d+) ([^\d][^|]{1,40}?) Filtrar Jugador", t)
    if len(names) < 2:
        names = re.findall(r"([A-ZÀ-ÿa-z][\wÀ-ÿ .'-]{2,40}?) Filtrar Jugador", t)
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


# ------------------------------------------------------------------ FEB
def read_feb(pid, row=None):
    h = page(f'https://baloncestoenvivo.feb.es/partido/{pid}')
    t = text(h)
    sm = re.search(r'Estad[ií]sticas (.+?) (\d+) p (\d+) (.+?) \d', t)
    names = re.findall(r'% (.+?) Rebotes Tapones', t)
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


FEB_COMP = {'Primera FEB': 'primerafeb', 'Segunda FEB': 'segundafeb'}


def find_feb(row):
    comp = FEB_COMP.get(row.get('competition'))
    if not comp:
        return None
    day = dt.date.fromisoformat(row['date']).strftime('%d/%m/%Y')
    for g in range(1, 7):
        try:
            h = page(f'https://baloncestoenvivo.feb.es/resultados/{comp}/{g}/2026')
        except Exception:
            continue
        for tr in re.findall(r'<tr>(.*?)</tr>', h, re.S):
            if day not in tr:
                continue
            teams = [clean(x) for x in re.findall(r'Equipo\.aspx\?i=\d+">(.*?)</a>', tr)]
            pid = re.search(r'Partido\.aspx\?p=(\d+)', tr)
            if len(teams) == 2 and pid and same_game(teams[0], teams[1], row):
                return f'feb:{pid.group(1)}'
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
