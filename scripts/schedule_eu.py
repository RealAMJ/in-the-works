#!/usr/bin/env python3
"""
European schedule check from the leagues' own fixture lists, once a day (like schedule_us.py for NBA/NCAA).

Leagues: EuroLeague (official API), Champions League (BCL game list), BBL (season id table, re-read
for our clubs' games), ABA League (season calendar), LBA (current round from the league's front page) and
ProB (the league's team calendars, which also give the live-ticker game id) and the Icelandic league
(Genius Sports team schedule pages, whose match ids are the FIBA LiveStats ids).
For every club we follow in those competitions (from data/schedule.json and data/coachgames.json) it
looks 3 days back and 8 days ahead and:
  * fixes the date/time (Swedish time) of upcoming games that are already listed
  * adds games that are missing
It never removes a game. Liga ACB, FEB, LKL and the FIBA LiveStats leagues are left to the
twice-weekly check.

Run: python3 scripts/schedule_eu.py           (only at 07:00-07:05 Stockholm)
     python3 scripts/schedule_eu.py --force
"""
import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402
import sources as S  # noqa: E402

UTC = dt.timezone.utc


def se(t):
    return t.astimezone(U.STHLM)


def euroleague():
    j = U.get('https://api-live.euroleague.net/v2/competitions/E/seasons/E2026/games')
    for g in j.get('data', []):
        if g.get('utcDate'):
            yield dict(at=dt.datetime.fromisoformat(g['utcDate'].replace('Z', '+00:00')), home=g['local']['club']['name'],
                       away=g['road']['club']['name'], confirmed=g.get('confirmedDate', True))


def bcl():
    h = S.page('https://www.championsleague.basketball/en/games').replace('\\"', '"')
    seen = set()
    for m in re.finditer(r'"teamA":\{[^{}]*"officialName":"([^"]*)"[^{}]*\},"teamB":\{[^{}]*"officialName":"([^"]*)"[^{}]*\}.*?"gameDateTimeUTC":"([^"]+)","hasTimeGameDateTime":(\w+)', h):
        a, b, when, has_time = m.groups()
        if when.startswith('0001') or (a, b, when) in seen:
            continue
        seen.add((a, b, when))
        yield dict(at=dt.datetime.fromisoformat(when[:19]).replace(tzinfo=UTC), home=a, away=b, confirmed=has_time == 'true')


def bbl(clubs, lo, hi):
    path = os.path.join(U.DATA, '_bbl_ids.json')
    table = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    changed = False
    for gid, g in table.items():
        names = f"{g.get('home') or ''} {g.get('guest') or ''}"
        if not any(S.words(c) & S.words(names) for c in clubs):
            continue
        when = g.get('time')
        at = dt.datetime.fromisoformat(when.replace('Z', '+00:00')) if when else None
        if at and not (lo - dt.timedelta(days=3) <= at <= hi + dt.timedelta(days=3)):
            continue
        try:  # times move: read the game page again for games near the window
            head, _ = S._bbl_page(gid)
            new = head.get('scheduledTime')
            if new and new != when:
                g['time'] = new
                changed = True
                at = dt.datetime.fromisoformat(new.replace('Z', '+00:00'))
        except Exception:
            pass
        if at:
            yield dict(at=at, home=g.get('home') or '', away=g.get('guest') or '', confirmed=True)
    if changed:
        json.dump(table, open(path, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)


def aba():
    h = S.page('https://www.aba-liga.com/calendar/')
    seen = set()
    for m in re.finditer(r'/match/(\d+)/(\d+)/1/Overview/', h):
        if m.group(1) in seen:
            continue
        a = h.rfind('<tr', 0, m.start()); b = h.find('</tr>', m.start())
        cell = S.clean(h[a:b])
        d = re.search(r'(\d{2})\.(\d{2})\.(\d{4})\s+(\d{1,2}):(\d{2})', cell)
        t = re.search(r'[A-Z]{2,4} : [A-Z]{2,4}\s+(.+?)\s+:\s+(.+?)\s+\w+day,', cell)
        if not d or not t:
            continue
        seen.add(m.group(1))
        at = dt.datetime(int(d.group(3)), int(d.group(2)), int(d.group(1)), int(d.group(4)), int(d.group(5)), tzinfo=U.STHLM)
        yield dict(at=at, home=t.group(1), away=t.group(2), confirmed=True)


def lba():
    h = S.page('https://www.legabasket.it/')
    for gid in sorted(set(re.findall(r'/game/(\d+)/', h))):
        try:
            m = S._lba_game(gid)['match']
        except Exception:
            continue
        when = m.get('match_datetime')
        if when:
            yield dict(at=dt.datetime.fromisoformat(when), home=m.get('h_team_name', ''), away=m.get('v_team_name', ''), confirmed=True)


# ProA/ProB clubs we follow -> the league's team id (calendar api.2basketballbundesliga.de/cal/<id>, ids from the
# live ticker's /init/<game id>). The calendar lists the club's own games with the ticker game id in each UID.
PROB_TEAMS = {'Basketball Löwen Erfurt': 563, 'Culture City Weimar': 588}


def prob(clubs=None):
    import urllib.request
    for club, tid in PROB_TEAMS.items():
        req = urllib.request.Request(f'https://api.2basketballbundesliga.de/cal/{tid}', headers=U.UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            ics = r.read().decode('utf-8')
        ics = re.sub(r'\r?\n[ \t]', '', ics)
        for ev in ics.split('BEGIN:VEVENT')[1:]:
            f = dict(re.findall(r'^([A-Z-]+)(?:;[^:]*)?:(.*?)\r?$', ev, re.M))
            gid = re.search(r'liga2-(\d+)@', f.get('UID', ''))
            m = re.search(r'Spiel (.+?) vs (.+)$', f.get('SUMMARY', ''))
            when = re.match(r'(\d{8}T\d{6})Z', f.get('DTSTART', ''))
            if not (gid and m and when):
                continue
            # the calendar uses the league's short names ("Basketball Löwen"); put ours in so the matching is exact
            def ours(n):
                return next((c for c in PROB_TEAMS if U.norm(n) == U.norm(c) or (S.words(n) - {'basketball'} and
                                                                                    S.words(n) - {'basketball'} <= S.words(c))), n)
            home, away = ours(m.group(1).strip()), ours(m.group(2).strip())
            if club not in (home, away):
                continue
            yield dict(at=dt.datetime.strptime(when.group(1), '%Y%m%dT%H%M%S').replace(tzinfo=UTC), home=home, away=away,
                       confirmed=True, feed=f'prob:{gid.group(1)}')


# Leagues run on Genius Sports' hosted pages (the same system as FIBA LiveStats): each club we follow has a team
# schedule page with the whole season, and the match id there is the FIBA LiveStats id. Times are local to the league.
GENIUS_TEAMS = {
    # site club name: (federation code, competition id, team id, league time zone, site competition)
    'KR Basket': ('KKI', 49040, 168328, 'Atlantic/Reykjavik', 'Icelandic Premier League'),
}


def genius(comp):
    import urllib.request
    from zoneinfo import ZoneInfo
    for club, (org, cid, tid, tz, c) in GENIUS_TEAMS.items():
        if c != comp:
            continue
        url = f'https://hosted.dcd.shared.geniussports.com/{org}/en/competition/{cid}/team/{tid}/schedule'
        req = urllib.request.Request(url, headers=dict(U.UA, Accept='text/html,*/*'))
        with urllib.request.urlopen(req, timeout=60) as r:
            h = r.read().decode('utf-8', 'replace')
        for b in h.split('<div class="match-wrap')[1:]:
            gid = re.search(r'match/(\d+)/', b)
            when = re.search(r'match-time">.*?<span>([^<]+)', b, re.S) or re.search(r'notlive-match-time">([^<]+)', b)
            home = re.search(r'home-team.*?team/(\d+)/.*?class="teamnames">([^<]+)<', b, re.S)
            away = re.search(r'away-team.*?team/(\d+)/.*?class="teamnames">([^<]+)<', b, re.S)
            if not (gid and when and home and away):
                continue
            m = re.match(r'\s*([A-Z][a-z]{2} \d{1,2}, \d{4}),?\s*(\d{1,2}:\d{2}\s*[AP]M)?', when.group(1))
            if not m:
                continue
            t = dt.datetime.strptime(m.group(1) + ' ' + (m.group(2) or '12:00 PM').replace(' ', ''), '%b %d, %Y %I:%M%p').replace(tzinfo=ZoneInfo(tz))
            hn, an = ' '.join(home.group(2).split()), ' '.join(away.group(2).split())
            # our club is the side whose team id is the page's; it gets the site's spelling
            if home.group(1) == str(tid):
                hn = club
            elif away.group(1) == str(tid):
                an = club
            else:
                continue
            yield dict(at=t.astimezone(UTC), home=hn, away=an, confirmed=bool(m.group(2)), feed=f'fiba:{gid.group(1)}')


# BLNO (Norway): the federation's match API lists the whole season; times are Norwegian time (= Swedish time)
NIF_TEAMS = {'Froya Basket Laksevåg': (449378, 'Frøya')}   # site club name: (tournament id, team name in the API)


def nif():
    for club, (tid, short) in NIF_TEAMS.items():
        for m in (S.nif_get(f'ta/TournamentMatches/?tournamentId={tid}') or {}).get('matches') or []:
            h, a = S.nif_team(m.get('hometeam')), S.nif_team(m.get('awayteam'))
            if short not in (h, a) or not m.get('matchDate'):
                continue
            hm = int(m.get('matchStartTime') or 0)
            t = dt.datetime.fromisoformat(m['matchDate'][:10] + f'T{hm // 100:02d}:{hm % 100:02d}').replace(tzinfo=U.STHLM)
            yield dict(at=t.astimezone(UTC), home=club if h == short else (m.get('hometeamOrgName') or h), away=club if a == short else (m.get('awayteamOrgName') or a),
                       confirmed=bool(hm), feed=f"nif:{m['matchId']}")


def main(argv):
    now = U.now()
    if '--force' not in argv and not (now.hour == 7 and now.minute < 6):
        return 0
    sched, coach, players = U.load('schedule'), U.load('coachgames'), U.load('players')
    lo, hi = now - dt.timedelta(days=3), now + dt.timedelta(days=8)
    comps = {'EuroLeague': euroleague, 'Champions League (BCL)': bcl, 'BBL': None, 'ABA League': aba, 'LBA (Italy)': lba,
             'ProB (Germany)': prob, 'Icelandic Premier League': lambda: genius('Icelandic Premier League'), 'BLNO (Norway)': nif}
    changes = 0
    for comp, reader in comps.items():
        # clubs we follow in this competition, and who to list for them
        clubs = {}
        for rows, who in ((sched, 'players'), (coach, 'coach')):
            for r in rows:
                if r.get('competition') == comp and r.get('team'):
                    clubs.setdefault((r['team'], who), r.get(who) or '')
        # also clubs whose players are listed in this competition but have no game of it on the schedule yet
        key = {'EuroLeague': 'euroleague', 'Champions League (BCL)': 'champions league', 'BBL': 'bbl',
               'ABA League': 'aba', 'LBA (Italy)': 'lba', 'ProB (Germany)': 'prob', 'Icelandic Premier League': 'icelandic premier league', 'BLNO (Norway)': 'blno'}[comp]
        for p in players:
            comps = str(p.get('competitions') or '').lower()
            if p.get('status') == 'Confirmed' and p.get('club') and re.search(r'(^|[^a-z])' + re.escape(key) + r'([^a-z]|$)', comps) \
                    and 'pokal' not in comps.split(key)[-1][:8]:
                k = next((c for c in clubs if c[0] == p['club'] and c[1] == 'players'), (p['club'], 'players'))
                listed = [x.strip() for x in str(clubs.get(k) or '').split(',') if x.strip()]
                if p['player'] not in listed:
                    listed.append(p['player'])
                clubs[k] = ', '.join(listed)
        if not clubs:
            continue
        try:
            fixtures = list(bbl({c for c, _ in clubs}, lo, hi) if comp == 'BBL' else reader())
        except Exception as e:
            print(f'  {comp}: could not read the fixture list ({e.__class__.__name__}: {e})')
            continue
        for (club, who), names in clubs.items():
            rows = sched if who == 'players' else coach
            for f in fixtures:
                if not (lo <= f['at'] <= hi):
                    continue
                cw = S.words(club)
                if f['home'] == club:
                    venue, opp = 'Home', f['away']
                elif f['away'] == club:
                    venue, opp = 'Away', f['home']
                elif comp in ('ProB (Germany)', 'Icelandic Premier League', 'BLNO (Norway)'):
                    continue
                elif cw & S.words(f['home']):
                    venue, opp = 'Home', f['away']
                elif cw & S.words(f['away']):
                    venue, opp = 'Away', f['home']
                else:
                    continue
                t = se(f['at'])
                date, time = t.strftime('%Y-%m-%d'), (t.strftime('%H:%M') if f.get('confirmed', True) else 'TBC')
                near = [r for r in rows if r.get('team') == club and r.get('competition') == comp and r.get('date')
                        and abs((dt.date.fromisoformat(r['date']) - t.date()).days) <= 2
                        and (S.words(r.get('opponent', '')) & S.words(opp) or U.norm(r.get('opponent', '')) == U.norm(opp))]
                if f.get('feed'):
                    # one row per game: a derby of two clubs we follow is listed once, with both teams' Swedes
                    near = near or [r for r in rows if r.get('live_feed') == f['feed']]
                if near:
                    r = near[0]
                    if who == 'players' and r.get('team') != club:
                        have = [x.strip() for x in str(r.get('players') or '').split(',') if x.strip()]
                        add = [x for x in names.split(', ') if x and x not in have]
                        if add:
                            r['players'] = ', '.join(have + add); changes += 1
                    if f.get('feed') and not r.get('live_feed'):
                        r['live_feed'] = f['feed']; changes += 1
                    if r.get('status') == 'upcoming' and f['at'] > now and (r.get('date'), r.get('time')) != (date, time) and time != 'TBC':
                        print(f"  {r['game_id']}: {r.get('date')} {r.get('time')} -> {date} {time} ({comp})")
                        r['date'], r['time'] = date, time
                        changes += 1
                    continue
                if f['at'] < now:
                    print(f"  missing past game, left for the morning check: {club} vs {opp} {date} ({comp})")
                    continue
                code = re.sub(r'[^a-z]', '', U.norm(club))[:4] or 'game'
                gid = ('c' if who == 'coach' else 'g') + date.replace('-', '') + code
                n = 2
                while any(x.get('game_id') == gid for x in sched + coach):
                    gid = gid.rstrip('0123456789') + str(n); n += 1
                row = dict(game_id=gid, date=date, time=time, **{who: names}, team=club, opponent=opp, venue=venue,
                           competition=comp, note='', status='upcoming', score='')
                if f.get('feed'):
                    row['live_feed'] = f['feed']
                rows.append(row)
                print(f"  added {gid}: {club} {'vs' if venue == 'Home' else 'at'} {opp} {date} {time} ({comp})")
                changes += 1
    if changes:
        key = lambda r: (r.get('date') or '', r.get('time') or '')
        sched.sort(key=key); coach.sort(key=key)
        U.save('schedule', sched); U.save('coachgames', coach)
        U.write_version(True)
    print(f'schedule_eu: {changes} changes')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
