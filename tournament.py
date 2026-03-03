#!/usr/bin/env python3
'''
Tournament Runner — Round-robin matches between all bot variants.
Parses engine output for bankroll, win rate, timing stats.
Prints a leaderboard sorted by total bankroll.

Usage:
    python3 tournament.py                    # 1 match per pair
    python3 tournament.py --matches 3        # 3 matches per pair
    python3 tournament.py --bots bot.py bots/bot_v2_aggro.py  # specific bots
'''
import subprocess
import sys
import os
import re
import argparse
from itertools import combinations
import tempfile
import shutil

PYTHON = sys.executable
ENGINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine.py')
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.py')
CONFIG_BAK = CONFIG_PATH + '.bak'

DEFAULT_BOTS = [
    #('v2_Aggro',    './bot_v2_aggro.py'),
    #('v3_Shark',    './bot_v3_shark.py'),
    #('v4_Auction',  './bot_v4_auction.py'),
    #('v7_Final',    './bot_v7_final.py'),
    ('sreeram_advanced',  './bot_sreeram_advanced.py'),
    ('sreeram_final',  './bot_sreeram_final.py')
]


def write_config(name1, file1, name2, file2):
    """Write config.py with bot assignments."""
    with open(CONFIG_PATH, 'w') as f:
        f.write(f'PYTHON_CMD = "{PYTHON}"\n')
        f.write(f"BOT_1_NAME = '{name1}'\n")
        f.write(f"BOT_1_FILE = '{file1}'\n\n")
        f.write(f"BOT_2_NAME = '{name2}'\n")
        f.write(f"BOT_2_FILE = '{file2}'\n\n")
        f.write("GAME_LOG_FOLDER = './logs'\n")


def parse_stats(output, name):
    """Parse engine output for a bot's stats."""
    stats = {}
    # Find the section for this bot
    pattern = rf'Stats for {re.escape(name)}:\s*\n(.*?)(?=Stats for|\Z)'
    match = re.search(pattern, output, re.DOTALL)
    if not match:
        return {'bankroll': 0, 'win_rate': 0, 'avg_payoff': 0, 'auction_win': 0, 'avg_bid': 0, 'max_time': 0}

    block = match.group(1)
    m = re.search(r'Total Bankroll:\s*([-\d]+)', block)
    stats['bankroll'] = int(m.group(1)) if m else 0
    m = re.search(r'Win Rate:\s*([\d.]+)%', block)
    stats['win_rate'] = float(m.group(1)) if m else 0
    m = re.search(r'Avg Payoff/Hand:\s*([-\d.]+)', block)
    stats['avg_payoff'] = float(m.group(1)) if m else 0
    m = re.search(r'Auction Win Rate:\s*([\d.]+)%', block)
    stats['auction_win'] = float(m.group(1)) if m else 0
    m = re.search(r'Avg Bid Amount \(Mean, Var\):\s*\(([\d.]+)', block)
    stats['avg_bid'] = float(m.group(1)) if m else 0
    m = re.search(r'Max Response Time:\s*([\d.]+)s', block)
    stats['max_time'] = float(m.group(1)) if m else 0
    return stats


def run_match(name1, file1, name2, file2):
    """Run a single match and return stats for both bots."""
    write_config(name1, file1, name2, file2)
    try:
        result = subprocess.run(
            [PYTHON, ENGINE, '--small_log'],
            capture_output=True, text=True, timeout=120,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print(f'  ⚠ Match {name1} vs {name2} timed out!')
        return None, None

    timed_out_1 = f'{name1} ran out of time' in output
    timed_out_2 = f'{name2} ran out of time' in output

    stats1 = parse_stats(output, name1)
    stats2 = parse_stats(output, name2)

    stats1['timed_out'] = timed_out_1
    stats2['timed_out'] = timed_out_2

    return stats1, stats2


def main():
    parser = argparse.ArgumentParser(description='Bot Tournament Runner')
    parser.add_argument('--matches', type=int, default=1, help='Matches per pair')
    parser.add_argument('--bots', nargs='+', help='Bot files (auto-named)')
    args = parser.parse_args()

    # Backup config
    if os.path.exists(CONFIG_PATH):
        shutil.copy2(CONFIG_PATH, CONFIG_BAK)

    if args.bots:
        bots = [(os.path.splitext(os.path.basename(f))[0], f) for f in args.bots]
    else:
        bots = DEFAULT_BOTS

    # Leaderboard
    totals = {name: {'bankroll': 0, 'wins': 0, 'matches': 0, 'timeouts': 0}
              for name, _ in bots}

    pairs = list(combinations(range(len(bots)), 2))
    total_matches = len(pairs) * args.matches

    print(f'\n🃏 POKER BOT TOURNAMENT')
    print(f'   {len(bots)} bots × {args.matches} match(es) per pair = {total_matches} total matches')
    print(f'   Bots: {", ".join(n for n, _ in bots)}')
    print('=' * 70)

    match_num = 0
    for i, j in pairs:
        n1, f1 = bots[i]
        n2, f2 = bots[j]
        for m in range(args.matches):
            match_num += 1
            label = f'[{match_num}/{total_matches}]'
            print(f'\n{label} {n1} vs {n2}', end='', flush=True)

            s1, s2 = run_match(n1, f1, n2, f2)
            if s1 is None:
                print(' — FAILED')
                continue

            b1, b2 = s1['bankroll'], s2['bankroll']
            t1 = ' ⏰' if s1.get('timed_out') else ''
            t2 = ' ⏰' if s2.get('timed_out') else ''

            winner = n1 if b1 > b2 else n2 if b2 > b1 else 'TIE'
            print(f'  →  {n1}: {b1:+d}{t1}  |  {n2}: {b2:+d}{t2}  |  Winner: {winner}')

            totals[n1]['bankroll'] += b1
            totals[n2]['bankroll'] += b2
            totals[n1]['matches'] += 1
            totals[n2]['matches'] += 1
            if b1 > b2: totals[n1]['wins'] += 1
            elif b2 > b1: totals[n2]['wins'] += 1
            if s1.get('timed_out'): totals[n1]['timeouts'] += 1
            if s2.get('timed_out'): totals[n2]['timeouts'] += 1

    # Leaderboard
    ranked = sorted(totals.items(), key=lambda x: x[1]['bankroll'], reverse=True)

    print('\n' + '=' * 70)
    print('🏆 LEADERBOARD')
    print('=' * 70)
    print(f'{"#":<4} {"Bot":<16} {"Bankroll":>10} {"W-L":>8} {"Win%":>7} {"Timeouts":>9}')
    print('-' * 70)
    for rank, (name, data) in enumerate(ranked, 1):
        m = data['matches']
        w = data['wins']
        l = m - w
        wr = (w / m * 100) if m > 0 else 0
        to = data['timeouts']
        medal = '🥇' if rank == 1 else '🥈' if rank == 2 else '🥉' if rank == 3 else '  '
        print(f'{medal}{rank:<3} {name:<16} {data["bankroll"]:>+10} {w:>3}-{l:<3} {wr:>6.1f}% {to:>8}')

    print('\n' + '=' * 70)
    champion = ranked[0][0]
    print(f'🏆 Champion: {champion} (Total Bankroll: {ranked[0][1]["bankroll"]:+d})')
    print('=' * 70)

    # Restore config
    if os.path.exists(CONFIG_BAK):
        shutil.copy2(CONFIG_BAK, CONFIG_PATH)
        os.remove(CONFIG_BAK)


if __name__ == '__main__':
    main()
