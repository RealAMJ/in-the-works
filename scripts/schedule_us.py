#!/usr/bin/env python3
"""
NBA and NCAA schedule check from ESPN's free scoreboard, once a day.

For every club in data/players.json (and coach club in data/coaches.json) that plays in the NBA or
NCAA, it reads ESPN's schedule for the next 8 days and:
  * adds games that are missing (to data/schedule.json, or data/coachgames.json for coaches)
  * fixes the Swedish tip-off time of upcoming games that are already listed
It never removes a game; anything odd is left for the morning check.

Run: python3 scripts/schedule_us.py           (only at 07:00-07:05 Stockholm, so the 5-minute job stays light)
     python3 scripts/schedule_us.py --force
"""
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

DAYS = 8
SPORTS = (('nba', 'NBA', ''), ('mens-college-basketball', 'NCAA', '&groups=50&limit=500'))


GENERIC = {'state', 'university', 'college', 'basketball', 'the', 'of'}


def toks(s):
    t = re.sub(r'[^a-z0-9]+', ' ', U.norm(re.sub(r'[-./]', ' ', str(s)))).split()
    return ['saint' if w == 'st' else w for w in t]


def same(a, b):
    """Same team? Used only to compare games of one club within a day, so a loose match is safe:
    equal names, one name inside the other ('Oakland' / 'Oakland Golden Grizzlies'), or a shared distinctive word."""
    ta, tb = toks(a), toks(b)
    if not ta or not tb:
        return False
    if ta == tb or set(ta) <= set(tb) or set(tb) <= set(ta):
        return True
    return bool({w for w in ta if len(w) >= 4 and w not in GENERIC} & {w for w in tb if len(w) >= 4 and w not in GENERIC})


def events(now):
    out = []
    for sport, comp, extra in SPORTS:
        # ESPN dates are US dates: start a day early so late US games on our first day are included
        for i in range(-1, DAYS + 1):
            d = (now - dt.timedelta(hours=8)).date() + dt.timedelta(days=i)
            try:
                sb = U.get(f'https://site.api.espn.com/apis/site/v2/sports/basketball/{sport}/scoreboard?dates={d:%Y%m%d}{extra}')
            except Exception as e:
                print(f'  {comp} {d}: {e}')
                continue
            for e in sb.get('events', []):
                c = e['competitions'][0]
                t = dt.datetime.fromisoformat(e['date'].replace('Z', '+00:00')).astimezone(U.STHLM)
                tm = {x['homeAway']: x['team'] for x in c['competitors']}
                if 'home' not in tm or 'away' not in tm:
                    continue
                out.append(dict(comp=comp, at=t, neutral=bool(c.get('neutralSite')), tbd=bool(e.get('timeValid') is False),
                                state=c['status']['type'].get('state'), home=tm['home'], away=tm['away']))
    return out


def tname(team, comp):
    return team.get('displayName') if comp == 'NBA' else (team.get('location') or team.get('displayName'))


def main(argv):
    now = U.now()
    if '--force' not in argv and not (now.hour == 7 and now.minute < 6):
        return 0
    sched, coach = U.load('schedule'), U.load('coachgames')
    players, coaches = U.load('players'), U.load('coaches')
    clubs = {}
    for p in players:
        if p.get('status') == 'Confirmed' and p.get('club'):
            clubs.setdefault(p['club'], {'players': [], 'coach': None})['players'].append(p['player'])
    for c in coaches:
        if c.get('club') and re.search(r'NCAA|NBA', str(c.get('league') or '')):
            clubs.setdefault(c['club'], {'players': [], 'coach': None})['coach'] = c.get('coach') or c.get('name')
    end = now + dt.timedelta(days=DAYS)
    changed = 0
    for ev in events(now):
        if ev['state'] != 'pre' or not (now <= ev['at'] <= end):
            continue
        for side, other in (('home', 'away'), ('away', 'home')):
            me = tname(ev[side], ev['comp'])
            club = next((k for k in clubs if U.norm(k) == U.norm(me) or U.norm(k) == U.norm(ev[side].get('displayName'))), None)
            if not club:
                continue
            opp = tname(ev[other], ev['comp'])
            date, time = ev['at'].strftime('%Y-%m-%d'), ('TBC' if ev['tbd'] else ev['at'].strftime('%H:%M'))
            venue = 'Neutral' if ev['neutral'] else ('Home' if side == 'home' else 'Away')
            info = clubs[club]
            for rows, who in ((sched, 'players'), (coach, 'coach')):
                if who == 'players' and not info['players']:
                    continue
                if who == 'coach' and not info['coach']:
                    continue
                near = [r for r in rows if r.get('team') == club and r.get('date')
                        and abs((dt.date.fromisoformat(r['date']) - ev['at'].date()).days) <= 1 and same(r.get('opponent', ''), opp)]
                # the game may also be listed from the other club's side (two Swedes' teams meeting)
                near += [r for r in rows if who == 'players' and same(r.get('team', ''), opp) and U.norm(r.get('opponent', '')) == U.norm(club)
                         and r.get('date') and abs((dt.date.fromisoformat(r['date']) - ev['at'].date()).days) <= 1]
                if near:
                    r = near[0]
                    if r.get('status') == 'upcoming' and (r.get('date'), r.get('time')) != (date, time) and time != 'TBC':
                        print(f"  {r['game_id']}: {r.get('date')} {r.get('time')} -> {date} {time}")
                        r['date'], r['time'] = date, time
                        changed += 1
                    continue
                code = re.sub(r'[^a-z]', '', U.norm(club))[:4] or 'game'
                gid = ('c' if who == 'coach' else 'g') + date.replace('-', '') + code
                n = 2
                while any(x.get('game_id') == gid for x in sched + coach):
                    gid = gid.rstrip('0123456789') + str(n); n += 1
                row = dict(game_id=gid, date=date, time=time)
                if who == 'coach':
                    row['coach'] = info['coach']
                else:
                    row['players'] = ', '.join(info['players'])
                row.update(team=club, opponent=opp, venue=venue, competition=ev['comp'], note='', status='upcoming', score='')
                rows.append(row)
                print(f"  added {gid}: {club} {'vs' if venue == 'Home' else 'at'} {opp} {date} {time}")
                changed += 1
    if changed:
        key = lambda r: (r.get('date') or '', r.get('time') or '')
        sched.sort(key=key); coach.sort(key=key)
        U.save('schedule', sched); U.save('coachgames', coach)
        U.write_version(True)
    print(f'schedule_us: {changed} changes')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
