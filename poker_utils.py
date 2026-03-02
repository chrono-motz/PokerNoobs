"""
Shared poker evaluation and Monte Carlo utilities for all bot variants.
"""
import random
from itertools import combinations

_COMBO_INDICES_7 = list(combinations(range(7), 5))

RANK_MAP = {'2': 0, '3': 1, '4': 2, '5': 3, '6': 4, '7': 5, '8': 6,
            '9': 7, 'T': 8, 'J': 9, 'Q': 10, 'K': 11, 'A': 12}
ALL_RANKS = list(RANK_MAP.keys())
ALL_SUITS = ['h', 'd', 'c', 's']
FULL_DECK = [r + s for r in ALL_RANKS for s in ALL_SUITS]

_CHEN_VALUES = {'A': 10, 'K': 8, 'Q': 7, 'J': 6, 'T': 5,
    '9': 4.5, '8': 4, '7': 3.5, '6': 3, '5': 2.5, '4': 2, '3': 1.5, '2': 1}
_RANK_ORDER = 'A23456789TJQK'


def _eval5(r0, r1, r2, r3, r4, s0, s1, s2, s3, s4):
    ranks = sorted((r0, r1, r2, r3, r4), reverse=True)
    is_flush = (s0 == s1 == s2 == s3 == s4)
    is_straight = False
    straight_high = 0
    if ranks[0] - ranks[4] == 4 and len(set(ranks)) == 5:
        is_straight = True
        straight_high = ranks[0]
    elif ranks == [12, 3, 2, 1, 0]:
        is_straight = True
        straight_high = 3
    freq = [0] * 13
    for r in ranks: freq[r] += 1
    quads = trips = pair1 = pair2 = -1
    kickers = []
    for r in range(12, -1, -1):
        f = freq[r]
        if f == 4: quads = r
        elif f == 3: trips = r
        elif f == 2:
            if pair1 == -1: pair1 = r
            else: pair2 = r
        elif f == 1: kickers.append(r)
    if is_straight and is_flush: return 0x80000 + straight_high
    if quads >= 0: return 0x70000 + quads * 16 + kickers[0]
    if trips >= 0 and pair1 >= 0: return 0x60000 + trips * 16 + pair1
    if is_flush: return 0x50000 + ranks[0]*16**4 + ranks[1]*16**3 + ranks[2]*16**2 + ranks[3]*16 + ranks[4]
    if is_straight: return 0x40000 + straight_high
    if trips >= 0: return 0x30000 + trips * 256 + kickers[0] * 16 + kickers[1]
    if pair1 >= 0 and pair2 >= 0: return 0x20000 + pair1 * 256 + pair2 * 16 + kickers[0]
    if pair1 >= 0: return 0x10000 + pair1 * 4096 + kickers[0] * 256 + kickers[1] * 16 + kickers[2]
    return ranks[0]*16**4 + ranks[1]*16**3 + ranks[2]*16**2 + ranks[3]*16 + ranks[4]


def _parse_cards(cards):
    ranks, suits = [], []
    for c in cards:
        ranks.append(RANK_MAP[c[0]])
        suits.append(ord(c[1]))
    return ranks, suits


def best_score_7(cards_7):
    rs, ss = _parse_cards(cards_7)
    best = 0
    for i0, i1, i2, i3, i4 in _COMBO_INDICES_7:
        score = _eval5(rs[i0], rs[i1], rs[i2], rs[i3], rs[i4],
                       ss[i0], ss[i1], ss[i2], ss[i3], ss[i4])
        if score > best: best = score
    return best


def mc_equity(my_hand, board, opp_known, num_sims):
    used = set(my_hand)
    if board: used.update(board)
    if opp_known: used.update(opp_known)
    remaining = [c for c in FULL_DECK if c not in used]
    need_board = 5 - len(board) if board else 5
    need_opp = 2 - len(opp_known) if opp_known else 2
    need_total = need_board + need_opp
    board_list = list(board) if board else []
    opp_list = list(opp_known) if opp_known else []
    wins = ties = 0
    n = len(remaining)
    for _ in range(num_sims):
        arr = remaining[:]
        for i in range(need_total):
            j = random.randint(i, n - 1)
            arr[i], arr[j] = arr[j], arr[i]
        sim_board = board_list + arr[:need_board]
        sim_opp = opp_list + arr[need_board:need_total]
        my_score = best_score_7(my_hand + sim_board)
        opp_score = best_score_7(sim_opp + sim_board)
        if my_score > opp_score: wins += 1
        elif my_score == opp_score: ties += 1
    if num_sims == 0: return 0.5
    return (wins + 0.5 * ties) / num_sims


def chen_score(c1, c2):
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    v1, v2 = _CHEN_VALUES[r1], _CHEN_VALUES[r2]
    score = max(v1, v2)
    if r1 == r2: return max(score * 2, 5)
    if s1 == s2: score += 2
    gap = abs(_RANK_ORDER.index(r1) - _RANK_ORDER.index(r2)) - 1
    if gap == 1: score -= 1
    elif gap == 2: score -= 2
    elif gap == 3: score -= 4
    elif gap >= 4: score -= 5
    if gap <= 1 and max(v1, v2) < 7: score += 1
    return score
