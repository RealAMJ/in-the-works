#!/usr/bin/env python3
"""
Calendar feeds (.ics) people can subscribe to on their phone or computer:
  data/cal/all.ics        every game of every Swede we follow
  data/cal/<player-slug>.ics one player's games
Times come from data/schedule.json (Swedish time) and are written in UTC, so every calendar shows them
in the reader's own time zone. Finished games get the result in the title. Files are only rewritten
when their content changes.

Run: python3 scripts/calendar_feeds.py
"""
import datetime as dt
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402

OUT = os.path.join(U.DATA, 'cal')
SITE = 'https://realamj.github.io/in-the-works/'


def slug(name):
    return re.sub(r'[^a-z0-9]+', '-', U.norm(name)).strip('-')


def esc(s):
    return str(s or '').replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def fold(line):
    # iCalendar lines are at most 75 bytes; longer ones continue on the next line after a space
    out, b = [], line.encode('utf-8')
    while len(b) > 75:
        cut = 75
        while cut > 0 and (b[cut] & 0xC0) == 0x80:
            cut -= 1
        out.append(b[:cut].decode('utf-8')); b = b' ' + b[cut:]
    out.append(b.decode('utf-8'))
    return '\r\n'.join(out)


def event(r, who):
    tip = U.tip_time(r)
    stamp = 'DTSTAMP:20260101T000000Z'
    where = 'vs' if r.get('venue') != 'Away' else 'at'
    title = f"{who}: {r['team']} {where} {r['opponent']}"
    if r.get('status') == 'final' and r.get('score'):
        title += f" ({r['score']})"
    desc = f"{r.get('competition', '')}. Players: {r.get('players', '')}. {SITE}"
    lines = ['BEGIN:VEVENT', f"UID:{r['game_id']}@swedes-abroad", stamp]
    if tip:
        start = tip.astimezone(dt.timezone.utc)
        lines += [f"DTSTART:{start:%Y%m%dT%H%M%SZ}", f"DTEND:{start + dt.timedelta(hours=2):%Y%m%dT%H%M%SZ}"]
    else:  # time not known yet: an all-day entry on the date
        d = dt.date.fromisoformat(r['date'])
        lines += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}"]
        title += ' (time TBC)'
    lines += [f"SUMMARY:{esc(title)}", f"DESCRIPTION:{esc(desc)}", f"CATEGORIES:{esc(r.get('competition', ''))}", 'END:VEVENT']
    return [fold(x) for x in lines]


def calendar(name, events):
    head = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Swedes Abroad//Games//EN', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
            fold(f'X-WR-CALNAME:{esc(name)}'), 'X-WR-TIMEZONE:Europe/Stockholm', 'REFRESH-INTERVAL;VALUE=DURATION:PT6H',
            'X-PUBLISHED-TTL:PT6H']
    return '\r\n'.join(head + [l for e in events for l in e] + ['END:VCALENDAR']) + '\r\n'


def write(path, text):
    if os.path.exists(path) and hashlib.sha1(open(path, 'rb').read()).digest() == hashlib.sha1(text.encode('utf-8')).digest():
        return False
    open(path, 'w', encoding='utf-8', newline='').write(text)
    return True


def main():
    os.makedirs(OUT, exist_ok=True)
    sched = [r for r in U.load('schedule') if r.get('date') and r.get('team')]
    players = [p['player'] for p in U.load('players') if p.get('status') == 'Confirmed']
    changed = 0
    allev = []
    per = {p: [] for p in players}
    for r in sorted(sched, key=lambda x: (x['date'], x.get('time') or '')):
        names = [n.strip() for n in str(r.get('players') or '').split(',') if n.strip()]
        allev.append(event(r, ', '.join(n.split()[-1] for n in names) or 'Swedes'))
        for n in names:
            if n in per:
                per[n].append(event(r, n.split()[-1]))
    changed += write(os.path.join(OUT, 'all.ics'), calendar('Swedes Abroad: all games', allev))
    for p, ev in per.items():
        changed += write(os.path.join(OUT, slug(p) + '.ics'), calendar(f'Swedes Abroad: {p}', ev))
    print(f'calendars: {changed} updated')


if __name__ == '__main__':
    main()
