#!/usr/bin/env python3
"""
For the live guard (.github/workflows/guard.yml): prints "due" when a game that isn't final yet
tipped off in the last 4 hours or tips off in the next 12, otherwise "idle". Times are Swedish time.
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update as U  # noqa: E402


def main():
    now = U.now()
    for name in ('schedule', 'coachgames'):
        for r in U.load(name):
            if r.get('status') == 'final':
                continue
            tip = U.tip_time(r)
            if tip and now - dt.timedelta(hours=4) <= tip <= now + dt.timedelta(hours=12):
                print('due')
                return 0
    print('idle')
    return 0


if __name__ == '__main__':
    sys.exit(main())
