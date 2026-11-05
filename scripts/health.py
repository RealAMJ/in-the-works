#!/usr/bin/env python3
"""
Health check: looks for the problems that otherwise go unnoticed and sends a Telegram/ntfy message
(through notify.send) only when something is wrong. A problem is repeated at most every 6 hours, and
one "all clear" message is sent once everything is fine again. State is kept in data/_health.json.

Checks:
  * games whose tip-off is more than 6 h ago that are still not final
  * finals without post-game work, without every Swede's line, or without an alert (last 2 days)
  * the live job not having run for 30+ minutes while a game is on or about to start
  * the public site lagging more than 30 minutes behind the data in the repository
  * duplicate ids in the data files
  * averages (data/stats.json) that don't match the game logs

Run: python3 scripts/health.py            (--dry-run prints without sending or saving)
"""
import collections
import datetime as dt
import hashlib
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402
import notify  # noqa: E402

SITE = 'https://realamj.github.io/in-the-works/'
STATE = os.path.join(U.DATA, '_health.json')
REPEAT = dt.timedelta(hours=6)


def parse(ts):
    try:
        return dt.datetime.fromisoformat(str(ts))
    except Exception:
        return None


def checks(now):
    sched, coach = U.load('schedule'), U.load('coachgames')
    bx, gl, st = U.load('boxscores'), U.load('gamelogs'), U.load('stats')
    issues = []
    since = (now - dt.timedelta(days=2)).date().isoformat()
    for name, rows in (('player', sched), ('coach', coach)):
        for r in rows:
            tip = U.tip_time(r)
            if not tip or tip > now:
                continue
            what = f"{r.get('team')} {'vs' if r.get('venue') == 'Home' else 'at'} {r.get('opponent')} ({r.get('date')}, {r.get('competition')})"
            if r.get('status') != 'final':
                if now - tip > dt.timedelta(hours=6) and r.get('date', '') >= since:
                    issues.append(f"Not final {int((now - tip).total_seconds() // 3600)} h after tip-off: {what}")
                continue
            if r.get('date', '') < since:
                continue
            if not r.get('post_done') and now - tip > dt.timedelta(hours=4):
                issues.append(f"No team form/averages yet: {what}")
            if name == 'player':
                names = [p.strip() for p in str(r.get('players') or '').split(',') if p.strip()]
                have = {U.norm(b.get('player')) for b in bx if b.get('game_id') == r['game_id']}
                missing = [n for n in names if U.norm(n) not in have]
                if missing and now - tip > dt.timedelta(hours=4):
                    issues.append(f"Missing line for {', '.join(missing)}: {what}")
                if r.get('post_done') and not r.get('notified') and not missing and now - tip > dt.timedelta(hours=5):
                    issues.append(f"Alert not sent: {what}")
    # the live job: has it run lately while games are on?
    try:
        log = json.load(open(os.path.join(U.DATA, '_live_log.json')))
        last = parse(log.get('at'))
    except Exception:
        last = None
    busy = [r for r in sched + coach if U.tip_time(r) and r.get('status') != 'final'
            and U.tip_time(r) - dt.timedelta(hours=1) <= now <= U.tip_time(r) + dt.timedelta(hours=3)]
    if busy and (last is None or now - last > dt.timedelta(minutes=30)):
        ago = f"{int((now - last).total_seconds() // 60)} min" if last else 'a long time'
        issues.append(f"Live job has not run for {ago} while {len(busy)} game(s) are on or about to start")
    # duplicates
    for n, key in (('schedule', 'game_id'), ('coachgames', 'game_id'), ('boxscores', 'line_id'), ('gamelogs', 'row_id'),
                   ('stats', 'row_id'), ('highlights', 'highlight_id'), ('teamform', 'row_id'), ('thisweek', 'story_id')):
        c = collections.Counter(r.get(key) for r in U.load(n))
        d = [k for k, v in c.items() if v > 1 and k]
        if d:
            issues.append(f"Duplicate {n} ids: {', '.join(map(str, d[:5]))}")
    # averages vs game logs (game logs + box score lines of finished games)
    games = {r['game_id']: r for r in sched}
    for s in st:
        dates = {g['date'] for g in gl if g.get('player') == s.get('player') and g.get('competition') == s.get('competition')}
        for b in bx:
            g = games.get(b.get('game_id'))
            if g and b.get('player') == s.get('player') and g.get('competition') == s.get('competition') \
                    and b.get('note') != 'DNP' and g.get('status') == 'final':
                dates.add(g['date'])
        if len(dates) != s.get('gp'):
            issues.append(f"Averages out of step: {s.get('player')} {s.get('competition')} shows {s.get('gp')} games, logs have {len(dates)}")
    # is the public site up to date?
    try:
        mine = parse(json.load(open(os.path.join(U.DATA, '_version.json'))).get('updated'))
        req = urllib.request.Request(SITE + 'data/_version.json?x=' + str(int(now.timestamp())), headers=U.UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            live = parse(json.loads(r.read().decode('utf-8')).get('updated'))
        if mine and live and mine - live > dt.timedelta(minutes=30):
            issues.append(f"Public site is {int((mine - live).total_seconds() // 60)} min behind the data (publishing may be stuck)")
    except Exception as e:
        issues.append(f"Could not read the public site: {e.__class__.__name__}")
    return issues


def main(argv):
    dry = '--dry-run' in argv
    now = U.now()
    issues = checks(now)
    sig = hashlib.sha1('\n'.join(sorted(issues)).encode()).hexdigest()[:12] if issues else ''
    try:
        state = json.load(open(STATE))
    except Exception:
        state = {}
    last_sent = parse(state.get('sent_at'))
    msg = None
    if issues and (sig != state.get('sig') or not last_sent or now - last_sent > REPEAT):
        msg = 'Site check: something needs a look\n' + '\n'.join('• ' + i for i in issues[:15])
        if len(issues) > 15:
            msg += f'\n… and {len(issues) - 15} more'
    elif not issues and state.get('sig'):
        msg = 'Site check: all clear again'
    print('\n'.join(issues) if issues else 'all fine')
    if dry or not msg:
        return 0
    if notify.send(msg):
        json.dump({'sig': sig, 'sent_at': now.isoformat(timespec='seconds'), 'issues': issues}, open(STATE, 'w'), ensure_ascii=False, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
