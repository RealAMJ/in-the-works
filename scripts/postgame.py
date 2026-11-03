#!/usr/bin/env python3
"""
After-game paperwork, done automatically once a game is final and its full box score is in data/fullbox.json:

  * teamform rows for both teams (score, result, top scorer, leaders "Name|pts|reb|ast;...")
  * the season record in data/teams.json (only when the record already lists that competition)
    plus a "Last game: ..." line at the start of the notes
  * a data/gamelogs.json row for every Swede who played, and his data/stats.json averages for that
    competition (only when the stats row and the game log agree on the games played before this one)
  * a data/highlights.json row (English + Swedish) for 20+ points, a double-double, perfect shooting
    or a season high (3+ earlier games in that competition)

Each game is done once: the schedule/coachgames row gets "post_done": true.
Anything the script can't do safely (no record to update, stats that don't line up) is left for
the morning check and printed as "left for review".

Run: python3 scripts/postgame.py
"""
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

# How each competition is written in data/teams.json records (first match wins)
LABELS = {
    'Liga ACB': ['ACB'], 'Champions League (BCL)': ['BCL'], 'Orlen Basket Liga': ['Orlen Basket Liga', 'PLK'],
    'Croatian Premier League': ['Premijer liga'], 'Icelandic Premier League': ['Bónus deild'], 'LBA (Italy)': ['LBA'],
    'ABA League': ['ABA'], 'Austrian Superliga': ['Austrian Superliga', 'Superliga'], 'NBA': ['NBA'], 'NCAA': ['NCAA'],
    'EuroLeague': ['EuroLeague'], 'FIBA Europe Cup': ['FIBA Europe Cup'], 'Primera FEB': ['Primera FEB'],
    'Segunda FEB': ['Segunda FEB'], 'LKL': ['LKL'], 'BBL': ['BBL'], 'Liga Națională': ['Liga Națională'], 'ENBL': ['ENBL'],
}
MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MAN = ['jan', 'feb', 'mar', 'apr', 'maj', 'jun', 'jul', 'aug', 'sep', 'okt', 'nov', 'dec']


SUFFIX = {'jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v'}


def surname(n):
    p = [w for w in str(n).split() if w.lower() not in SUFFIX] or str(n).split()
    return p[-1] if len(p) > 1 else (p[0] if p else str(n))


def slug(s):
    return re.sub(r'\s+', '-', U.norm(s)).strip('-')


def mk(s):
    m = re.match(r'(\d+)/(\d+)', str(s or ''))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def bump_record(rec, comp, won):
    for lab in LABELS.get(comp, [comp]):
        m = re.search(r'(\d+)-(\d+)(\s*\(?)' + re.escape(lab) + r'(?![A-Za-z])', rec or '')
        if m:
            w, l = int(m.group(1)), int(m.group(2))
            w, l = (w + 1, l) if won else (w, l + 1)
            return rec[:m.start()] + f'{w}-{l}' + rec[m.start() + len(f'{m.group(1)}-{m.group(2)}'):]
    return None


def highlight(b, g, logs_before):
    pts, reb, ast = b['pts'] or 0, b['reb'] or 0, b['ast'] or 0
    stl, blk = b.get('stl') or 0, b.get('blk') or 0
    fgm, fga = mk(b['fg']); ftm, fta = mk(b['ft'])
    tens = [(v, k) for v, k in ((pts, 'pts'), (reb, 'reb'), (ast, 'ast'), (stl, 'stl'), (blk, 'blk')) if v >= 10]
    prev = [x.get('pts') or 0 for x in logs_before]
    tag = None
    if len(tens) >= 3:
        tag = 'Triple-double'
    elif len(tens) == 2:
        tag = 'Double-double'
    elif len(prev) >= 3 and pts >= 10 and pts > max(prev):
        tag = 'Season high'
    elif pts >= 20:
        tag = '20+ points'
    elif fga >= 3 and fgm == fga and ftm == fta:
        tag = 'Perfect shooting'
    if not tag:
        return None
    won = str(g['score']).startswith('W')
    sc = str(g['score']).split()[-1]
    home = g.get('venue') != 'Away'
    nm = {'pts': ('points', 'poäng'), 'reb': ('rebounds', 'returer'), 'ast': ('assists', 'assist'), 'stl': ('steals', 'steals'), 'blk': ('blocks', 'blockar')}
    multi_en = ' and '.join(f'{v} {nm[k][0]}' for v, k in tens[:3])
    multi_sv = ' och '.join(f'{v} {nm[k][1]}' for v, k in tens[:3])
    head = {
        'Triple-double': (f'Triple-double: {multi_en}', f'Trippel-dubbel: {multi_sv}'),
        'Double-double': (f'Double-double: {multi_en}', f'Dubbel-dubbel: {multi_sv}'),
        'Season high': (f'Season-high {pts} points', f'Säsongsbästa {pts} poäng'),
        '20+ points': (f'{pts} points', f'{pts} poäng'),
        'Perfect shooting': (f'Perfect shooting: {pts} points on {b["fg"]} from the field', f'Perfekt skytte: {pts} poäng på {b["fg"]} från fältet'),
    }[tag]
    en_res = f"{g['team']} {'won' if won else 'lost'} {sc} {'at home to' if home else 'at'} {g['opponent']}"
    sv_res = f"{g['team']} {'vann' if won else 'förlorade'} med {sc} {'hemma mot' if home else 'borta mot'} {g['opponent']}"
    mins = b.get('min')
    pl = lambda n, one, many: f'{n} {one if n == 1 else many}'
    detail = (f"{surname(b['player'])} had {pl(pts, 'point', 'points')} ({b['fg']} FG, {b['three']} 3PT, {b['ft']} FT), {pl(reb, 'rebound', 'rebounds')} and {pl(ast, 'assist', 'assists')}"
              f"{f' in {mins} minutes' if mins not in ('', None) else ''} as {en_res}.")
    detail_sv = (f"{surname(b['player'])} gjorde {pts} poäng ({b['fg']} från fältet, {b['three']} från tre, {b['ft']} på straffar), "
                 f"{pl(reb, 'retur', 'returer')} och {ast} assist{f' på {mins} minuter' if mins not in ('', None) else ''} när {sv_res}.")
    return dict(highlight_id=f"{g['game_id']}-{surname(b['player']).lower()}", date=g['date'], player=b['player'], game_id=g['game_id'],
                headline=head[0], detail=detail, tag=tag, headline_sv=head[1], detail_sv=detail_sv)


def main():
    sched, coach = U.load('schedule'), U.load('coachgames')
    fb, bx, tf, tm = U.load('fullbox'), U.load('boxscores'), U.load('teamform'), U.load('teams')
    gl, st, hl = U.load('gamelogs'), U.load('stats'), U.load('highlights')
    have_tf = {(r.get('team'), r.get('date')) for r in tf}
    have_hl = {r.get('highlight_id') for r in hl}
    teams = {r.get('team'): r for r in tm}
    done = 0
    for g in sched + coach:
        if g.get('status') != 'final' or g.get('post_done') or not re.match(r'[WL] \d+-\d+', str(g.get('score') or '')):
            continue
        rows = [r for r in fb if r.get('game_id') == g['game_id']]
        if not rows:
            continue
        a, b = map(int, g['score'].split()[1].split('-'))
        d = dt.date.fromisoformat(g['date'])
        when, when_sv = f'{MON[d.month - 1]} {d.day}', f'{d.day} {MAN[d.month - 1]}'
        src = rows[0].get('source', '')
        for team, opp, us, them, ven in ((g['team'], g['opponent'], a, b, g.get('venue')),
                                        (g['opponent'], g['team'], b, a, {'Home': 'Away', 'Away': 'Home'}.get(g.get('venue'), g.get('venue')))):
            if (team, g['date']) in have_tf:
                continue
            tr = sorted([r for r in rows if r.get('team') == team], key=lambda r: -(r.get('pts') or 0))
            if not tr:
                print(f"  {g['game_id']}: no box rows for {team}, left for review")
                continue
            cut = tr[min(2, len(tr) - 1)]['pts']
            lead = [r for r in tr if r['pts'] >= cut]
            top = tr[0]
            tf.append(dict(row_id=f"{slug(team)}-{g['date']}", team=team, date=g['date'], competition=g['competition'], opponent=opp,
                           venue=ven, score=f'{us}-{them}', result='W' if us > them else 'L',
                           top=f"{surname(top['player'])} {top['pts']} pts, {top['reb']} reb", note='',
                           leaders=';'.join(f"{surname(r['player'])}|{r['pts']}|{r['reb']}|{r['ast']}" for r in lead), source=src))
            have_tf.add((team, g['date']))
            t = teams.get(team)
            if t is not None:
                new = bump_record(t.get('record', ''), g['competition'], us > them)
                if new is None:
                    print(f"  {g['game_id']}: no {g['competition']} record for {team}, left for review")
                else:
                    line = f"Last game: {'W' if us > them else 'L'} {us}-{them} {'vs' if ven == 'Home' else 'at'} {opp} ({when})."
                    notes = re.sub(r'^Last game: [^)]*\)\.\s*', '', t.get('notes') or '')
                    t.update(record=new, notes=(line + ' ' + notes).strip(), updated=g['date'])
        # Swedes: game log, averages, highlight (player games only)
        if not g['game_id'].startswith('c'):
            for b in [x for x in bx if x.get('game_id') == g['game_id'] and x.get('note') != 'DNP' and x.get('note') != 'live']:
                p, comp = b['player'], g['competition']
                # a Swede on the other team (Swede-vs-Swede game): his own side of the result
                own = next((x.get('team') for x in rows if U.norm(x.get('player')) == U.norm(p)), g['team'])
                v = g
                if own and own != g['team']:
                    sc2 = g['score'].split()[1].split('-')
                    them_won = g['score'].startswith('L')
                    v = dict(g, team=own, opponent=g['team'], venue={'Home': 'Away', 'Away': 'Home'}.get(g.get('venue'), g.get('venue')),
                             score=f"{'W' if them_won else 'L'} {sc2[1]}-{sc2[0]}")
                before = [x for x in gl if x.get('player') == p and x.get('competition') == comp and x.get('date', '') < g['date']]
                if not any(x.get('player') == p and x.get('date') == g['date'] and x.get('competition') == comp for x in gl):
                    rid = f"{surname(p).lower()}-{g['date']}"
                    if any(x.get('row_id') == rid for x in gl):
                        rid = f"{p.split()[0][0].lower()}{rid}"
                    gl.append(dict(row_id=rid, player=p, date=g['date'], competition=comp, team=v['team'], opponent=v['opponent'],
                                   venue=v.get('venue', ''), result=v['score'], min=b.get('min', ''), pts=b['pts'], reb=b['reb'], ast=b['ast'],
                                   source=b.get('source', ''), fg=b.get('fg', ''), three=b.get('three', ''), ft=b.get('ft', ''),
                                   oreb=b.get('oreb', ''), dreb=b.get('dreb', ''), stl=b.get('stl', ''), blk=b.get('blk', ''),
                                   tov=b.get('tov', ''), pf=b.get('pf', ''), pm=b.get('pm', ''), eff=b.get('eff', '')))
                    logs = [x for x in gl if x.get('player') == p and x.get('competition') == comp]
                    srow = next((x for x in st if x.get('player') == p and x.get('competition') == comp), None)
                    if srow is None and comp == 'NCAA':
                        # college season started this week: the game log is the whole season, so start his row from it
                        srow = dict(row_id=f"{surname(p).lower()}-ncaa", player=p, competition=comp, season='2026-27', gp=len(logs) - 1,
                                    min=0, pts=0, reb=0, ast=0, note='')
                        st.append(srow)
                    if srow is not None and srow.get('gp') == len(logs) - 1:
                        n = len(logs)
                        avg = lambda k: round(sum(float(x.get(k) or 0) for x in logs) / n, 1)
                        srow.update(gp=n, min=avg('min'), pts=avg('pts'), reb=avg('reb'), ast=avg('ast'),
                                    note=f"Averages from game log ({n} games, through {g['date']})")
                    else:
                        print(f"  {g['game_id']}: {p} {comp} averages don't line up (stats gp {srow and srow.get('gp')}, log {len(logs)}), left for review")
                h = highlight(b, v, before)
                if h and h['highlight_id'] not in have_hl:
                    hl.append(h)
                    have_hl.add(h['highlight_id'])
                    print(f"  {g['game_id']}: highlight {h['tag']} for {p}")
        g['post_done'] = True
        done += 1
        print(f"  {g['game_id']}: post-game done")
    if done:
        for n, v in (('schedule', sched), ('coachgames', coach), ('teamform', tf), ('teams', tm), ('gamelogs', gl), ('stats', st), ('highlights', hl)):
            U.save(n, v)
        U.write_version(True)
    print(f'postgame: {done} games')


if __name__ == '__main__':
    main()
