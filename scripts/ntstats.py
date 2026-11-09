"""
Sweden men's national team games (data/ntgames.json), tracked from the November 2026 window on.

Finds each game's FIBA LiveStats feed (the public feed many leagues and FIBA competitions use), follows it
during the game, and when it ends writes every Swede's line to data/ntlines.json and the result to
data/ntgames.json (score from Sweden's side: "W 80-75"). Called from update.py on every live run.

Finding the feed: a game's id is only there once FIBA has set the game up, close to the newest ids in use.
From two days before tip-off the script walks a window around the newest known ids a slice at a time
(hourly, every quarter of an hour in the last three hours before tip and during the game), and a game counts only when
the two team names match and Swedish squad names are on Sweden's roster.
"""
import concurrent.futures as cf
import datetime as dt
import json
import os

import update as U

LINES, SCAN = 'ntlines', os.path.join(U.DATA, '_ntscan.json')
FROM = '2026-11-27'          # tracked from this window on
SLICE, HALF = 800, 8000      # ids per pass (same load as discover.py); window either side of the newest known id


def _feed_names(fid):
    try:
        d = U.get(f'https://fibalivestats.dcd.shared.geniussports.com/data/{fid}/data.json')
    except Exception:
        return fid, None
    tm = d.get('tm') or {}
    out = []
    for k in ('1', '2'):
        t = tm.get(k) or {}
        fam = {U.norm(str(p.get('familyName') or '')) for p in (t.get('pl') or {}).values()}
        out.append((U.norm(f"{t.get('name') or ''} {t.get('nameInternational') or ''}"), fam))
    return fid, out


def _is_ours(names, g, surnames):
    if not names or len(names) != 2:
        return False
    opp = [w for w in U.norm(g['opponent']).split() if len(w) > 2]
    se = [i for i, (n, _) in enumerate(names) if 'sweden' in n or 'sverige' in n]
    if len(se) != 1 or not any(w in names[1 - se[0]][0] for w in opp):
        return False
    fam = names[se[0]][1]
    return not fam or len(fam & surnames) >= 3   # roster not entered yet, or our players are on it


def find_feed(g, now, roster):
    tip = U.tip_time(g)
    if not tip or not (tip - dt.timedelta(days=2) <= now <= tip + dt.timedelta(days=7)):
        return None
    # hourly from two days before; every quarter of an hour in the last three hours and during the game
    close = tip - dt.timedelta(hours=3) <= now <= tip + dt.timedelta(hours=3)
    if now.minute % 15 >= 6 if close else now.minute >= 6:
        return None
    try:
        st = json.load(open(SCAN))
    except Exception:
        st = {}
    seeds = json.load(open(os.path.join(U.DATA, 'feed_seeds.json')))
    top = max(int(v) for v in seeds.values())
    lo, hi = top - HALF, top + HALF
    cur = st.get(g['game_id'], lo)
    if not lo <= cur < hi:
        cur = lo
    ids = list(range(cur, min(cur + SLICE, hi)))
    surnames = {U.norm(r['player']).split()[-1] for r in roster}
    with cf.ThreadPoolExecutor(32) as ex:
        hits = [fid for fid, n in ex.map(_feed_names, ids) if _is_ours(n, g, surnames)]
    st[g['game_id']] = ids[-1] + 1 if ids[-1] + 1 < hi else lo
    json.dump(st, open(SCAN, 'w'), indent=1)
    print(f"  ntstats: scanned {ids[0]}-{ids[-1]} for {g['game_id']}" + (f", found {hits[0]}" if hits else ''))
    return f'fiba:{hits[0]}' if hits else None


def run(now=None):
    """Returns (changed, keep_going)."""
    now = now or U.now()
    games, roster = U.load('ntgames'), U.load('ntroster')
    try:
        lines = U.load(LINES)
    except Exception:
        lines = []
    changed, soon = False, False
    for g in games:
        if g.get('date', '') < FROM or g.get('status') == 'final':
            continue
        tip = U.tip_time(g)
        if tip and tip - dt.timedelta(hours=12) <= now <= tip + dt.timedelta(hours=4):
            soon = True
        if not g.get('live_feed'):
            f = find_feed(g, now, roster)
            if f:
                g['live_feed'] = f
                changed = True
        if not g.get('live_feed') or not tip or now < tip - dt.timedelta(minutes=30) or now > tip + dt.timedelta(days=7):
            continue
        try:
            feed = U.read_fiba(g['live_feed'][5:])
        except Exception as e:
            print(f"  ntstats: {g['game_id']} feed error {e.__class__.__name__}")
            continue
        t = feed.get('teams') or []
        se = [i for i, x in enumerate(t) if 'sweden' in U.norm(x.get('name')) or 'sverige' in U.norm(x.get('name'))]
        if len(t) != 2 or len(se) != 1:
            continue
        us, them = t[se[0]], t[1 - se[0]]
        if not (us['score'] or them['score']):
            continue
        score = f"{'W' if us['score'] > them['score'] else 'L'} {us['score']}-{them['score']}"
        if feed.get('done') and us['score'] != them['score']:
            g.update(status='final', score=score)
            g.pop('live_score', None)
            keep = [x for x in lines if x.get('game_id') != g['game_id']]
            for p in us['pl']:
                if not p.get('min') or U.as_min(p['min']) == 0:
                    continue
                sur = U.norm(p['name']).split()[-1] if p.get('name') else ''
                name = next((r['player'] for r in roster if U.norm(r['player']).split()[-1] == sur), p['name'])
                keep.append(dict(line_id=f"{g['game_id']}-{sur}", game_id=g['game_id'], date=g['date'], opponent=g['opponent'], venue=g['venue'],
                                 player=name, min=U.as_min(p['min']), pts=p['pts'], reb=p['reb'], ast=p['ast'], stl=p['stl'], blk=p['blk'], tov=p['tov'],
                                 fg=f"{p['fgm']}/{p['fga']}", three=f"{p['tpm']}/{p['tpa']}", ft=f"{p['ftm']}/{p['fta']}", pm=p.get('pm', ''),
                                 source=f"FIBA LiveStats (game {g['live_feed'][5:]})"))
            lines = keep
            print(f"  game {g['game_id']}: final {score}, {sum(1 for x in lines if x['game_id'] == g['game_id'])} Swedish lines")
        else:
            g.update(status='live', live_score=score.split(' ', 1)[1], clock=feed.get('clock', ''), period=feed.get('period'))
            print(f"  game {g['game_id']}: live {score} Q{feed.get('period')} {feed.get('clock', '')}")
        changed = True
    if changed:
        U.save('ntgames', games)
        U.save(LINES, lines)
    return changed, soon


if __name__ == '__main__':
    print(run())
