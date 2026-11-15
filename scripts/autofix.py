#!/usr/bin/env python3
"""
Automatic data fixes, run by the live job after the post-game step (no person needed):

  * game logs: every Swede's line in a final box score (data/boxscores.json) gets its row in
    data/gamelogs.json, if the post-game step missed it
  * averages: stats rows built from the game log ("Averages from game log ...") are recomputed when their
    games-played count no longer matches the log
  * rosters: a player listed for a game that hasn't been played, whose club (data/players.json) is neither
    of the two teams, is taken off that game

What it fixes, and what it finds but can't fix (team notes older than the team's latest game, finals held
back because the box score doesn't add up), goes to data/_autofix.json for the health check's morning report.

Run: python3 scripts/autofix.py            (--dry-run prints without saving)
"""
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

LOG = os.path.join(U.DATA, '_autofix.json')
GENERIC = {'basket', 'basketball', 'club', 'baskets', 'team', 'bbk', 'bk', 'the'}


def words(s):
    return {w for w in U.norm(s).split() if len(w) > 2 and w not in GENERIC}


def same_team(a, b):
    return U.norm(a) == U.norm(b) or bool(words(a) & words(b))


def surname(n):
    return str(n).split()[-1]


def missing_logs(sched, bx, gl, players):
    fixed = []
    club_of = {p.get('player'): p.get('club') for p in players if p.get('player')}
    rows = {r['game_id']: r for r in sched}
    for b in bx:
        g = rows.get(b.get('game_id'))
        if not g or g.get('status') != 'final' or b.get('note') in ('DNP', 'live') or not re.match(r'[WL] \d+-\d+', str(g.get('score') or '')):
            continue
        p = b['player']
        if any(x.get('player') == p and x.get('date') == g['date'] for x in gl):
            continue
        v = dict(g)
        own = club_of.get(p)
        if own and not same_team(own, g['team']) and same_team(own, g.get('opponent', '')):
            # a Swede on the other team (Swede-vs-Swede game): his side of the result
            a, c = g['score'].split()[1].split('-')
            v = dict(g, team=g['opponent'], opponent=g['team'], venue={'Home': 'Away', 'Away': 'Home'}.get(g.get('venue'), g.get('venue')),
                     score=f"{'W' if g['score'].startswith('L') else 'L'} {c}-{a}")
        rid = f"{surname(p).lower()}-{g['date']}"
        if any(x.get('row_id') == rid for x in gl):
            rid = f"{p.split()[0][0].lower()}{rid}"
        gl.append(dict(row_id=rid, player=p, date=g['date'], competition=g['competition'], team=v['team'], opponent=v['opponent'],
                       venue=v.get('venue', ''), result=v['score'], min=b.get('min', ''), pts=b['pts'], reb=b['reb'], ast=b['ast'],
                       source=b.get('source', ''), fg=b.get('fg', ''), three=b.get('three', ''), ft=b.get('ft', ''),
                       oreb=b.get('oreb', ''), dreb=b.get('dreb', ''), stl=b.get('stl', ''), blk=b.get('blk', ''),
                       tov=b.get('tov', ''), pf=b.get('pf', ''), pm=b.get('pm', ''), eff=b.get('eff', '')))
        fixed.append(f"Added the missing game-log row for {p}, {g['date']} ({g['competition']})")
    return fixed


def averages(st, gl):
    fixed, issues = [], []
    for s in st:
        if not s.get('player') or s.get('season') not in (None, '', '2026-27'):
            continue
        logs = [x for x in gl if x.get('player') == s['player'] and x.get('competition') == s.get('competition')
                and x.get('note') != 'DNP' and x.get('pts') not in ('', None) and str(x.get('date', '')) >= '2026-08-01']
        if not logs or len(logs) == s.get('gp'):
            continue
        if not str(s.get('note') or '').startswith('Averages from game log'):
            issues.append(f"Averages for {s['player']} ({s.get('competition')}) show {s.get('gp')} games, the game log has {len(logs)}")
            continue
        n = len(logs)
        avg = lambda k: round(sum(float(x.get(k) or 0) for x in logs) / n, 1)
        last = max(x['date'] for x in logs)
        old = s.get('gp')
        s.update(gp=n, min=avg('min'), pts=avg('pts'), reb=avg('reb'), ast=avg('ast'),
                 note=re.sub(r'\(\d+ games, through [0-9-]+', f'({n} games, through {last}', s['note']))
        fixed.append(f"Recounted {s['player']}'s {s.get('competition')} averages from his game log ({old} → {n} games)")
    return fixed, issues


def rosters(sched, players):
    fixed = []
    club_of = {p.get('player'): p.get('club') for p in players if p.get('player') and p.get('club')}
    for r in sched:
        if r.get('status') == 'final' or not r.get('players'):
            continue
        names = [n.strip() for n in str(r['players']).split(',') if n.strip()]
        keep = [n for n in names if n not in club_of or same_team(club_of[n], r.get('team', '')) or same_team(club_of[n], r.get('opponent', ''))]
        if keep and keep != names:
            gone = [n for n in names if n not in keep]
            r['players'] = ', '.join(keep)
            fixed.append(f"Took {', '.join(gone)} off {r.get('team')} vs {r.get('opponent')} ({r.get('date')}): not on either team")
    return fixed


def stale_notes(sched, teams, now):
    issues = []
    latest = {}
    for r in sched:
        if r.get('status') == 'final' and r.get('date'):
            latest[r['team']] = max(latest.get(r['team'], ''), r['date'])
    recent = (now - dt.timedelta(days=10)).date().isoformat()
    for t in teams:
        last = latest.get(t.get('team'))
        upd = str(t.get('updated') or '')
        if last and last >= recent and upd and upd < last and (t.get('notes') or t.get('record')):
            issues.append(f"Team notes for {t['team']} are from {upd}; they last played {last}")
    return issues


def held(sched, now):
    return [f"Final held back (box score doesn't add up yet): {r.get('team')} vs {r.get('opponent')} ({r.get('date')})"
            for r in sched if r.get('held')]


def main(argv):
    dry = '--dry-run' in argv
    now = U.now()
    sched, coach, bx, gl, st = U.load('schedule'), U.load('coachgames'), U.load('boxscores'), U.load('gamelogs'), U.load('stats')
    players, teams = U.load('players'), U.load('teams')
    fixes = missing_logs(sched, bx, gl, players)
    f2, issues = averages(st, gl)
    fixes += f2
    fixes += rosters(sched, players)
    issues += stale_notes(sched + coach, teams, now) + held(sched + coach, now)
    for x in fixes + issues:
        print(' ', x)
    if dry:
        return 0
    changed = False
    if fixes:
        changed |= U.save('schedule', sched)
        changed |= U.save('gamelogs', gl)
        changed |= U.save('stats', st)
    try:
        log = json.load(open(LOG))
    except Exception:
        log = {}
    keep_from = (now - dt.timedelta(days=3)).isoformat(timespec='seconds')
    hist = [x for x in log.get('fixes', []) if x.get('at', '') >= keep_from] + [{'at': now.isoformat(timespec='seconds'), 'what': f} for f in fixes]
    new = {'fixes': hist, 'issues': issues}
    if new != log:
        json.dump(new, open(LOG, 'w'), ensure_ascii=False, indent=1)
        changed = True
    if changed:
        U.write_version(True)
    print(f'autofix: {len(fixes)} fixes, {len(issues)} open')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
