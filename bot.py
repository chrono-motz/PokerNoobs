'''
Sneak Peek Hold'em Bot — IIT Pokerbots 2026
Team: PokerNoobs

Strategy:
  - Preflop: Chen formula hand ranking for raise/call/fold tiers
  - Equity: Fast Monte Carlo (50 rollouts, optimized pure Python evaluator)
  - Auction: Competitive bidding adapted to opponent's patterns
  - Post-flop: Equity-based betting with pot odds, exploiting revealed opponent cards
  - Opponent modeling: Track fold/raise rates and avg bids to adapt dynamically
'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot

import random
from itertools import combinations

# ─── Constants ───────────────────────────────────────────────────────────────
STARTING_STACK = 5000
BIG_BLIND = 20
SMALL_BLIND = 10

# Tuned for pure Python speed — ~50 rollouts stays under time budget
MC_ITERS_AUCTION = 40
MC_ITERS_POSTFLOP = 50

# ─── Fast Pure Python Hand Evaluator ─────────────────────────────────────────
# Precompute all 21 combinations of choose(7,5) indices
_COMBO_INDICES_7 = list(combinations(range(7), 5))
_COMBO_INDICES_6 = list(combinations(range(6), 5))

RANK_MAP = {'2': 0, '3': 1, '4': 2, '5': 3, '6': 4, '7': 5, '8': 6,
            '9': 7, 'T': 8, 'J': 9, 'Q': 10, 'K': 11, 'A': 12}

ALL_RANKS = list(RANK_MAP.keys())
ALL_SUITS = ['h', 'd', 'c', 's']
FULL_DECK = [r + s for r in ALL_RANKS for s in ALL_SUITS]


def _eval5(r0, r1, r2, r3, r4, s0, s1, s2, s3, s4):
    """
    Ultra-fast 5-card hand evaluation.
    Returns an integer score (higher is better).
    Ranks are ints 0-12, suits are ints 0-3.
    """
    # Sort ranks descending
    ranks = sorted((r0, r1, r2, r3, r4), reverse=True)

    is_flush = (s0 == s1 == s2 == s3 == s4)

    # Check straight
    is_straight = False
    straight_high = 0
    if ranks[0] - ranks[4] == 4 and len(set(ranks)) == 5:
        is_straight = True
        straight_high = ranks[0]
    elif ranks == [12, 3, 2, 1, 0]:  # A-2-3-4-5
        is_straight = True
        straight_high = 3

    # Frequency counts (manual for speed)
    freq = [0] * 13
    for r in ranks:
        freq[r] += 1

    # Find groups
    quads = trips = pair1 = pair2 = -1
    kickers = []
    # Scan from highest rank down
    for r in range(12, -1, -1):
        f = freq[r]
        if f == 4:
            quads = r
        elif f == 3:
            trips = r
        elif f == 2:
            if pair1 == -1:
                pair1 = r
            else:
                pair2 = r
        elif f == 1:
            kickers.append(r)

    if is_straight and is_flush:
        return 0x80000 + straight_high
    if quads >= 0:
        return 0x70000 + quads * 16 + kickers[0]
    if trips >= 0 and pair1 >= 0:
        return 0x60000 + trips * 16 + pair1
    if is_flush:
        return 0x50000 + ranks[0] * 16**4 + ranks[1] * 16**3 + ranks[2] * 16**2 + ranks[3] * 16 + ranks[4]
    if is_straight:
        return 0x40000 + straight_high
    if trips >= 0:
        return 0x30000 + trips * 256 + kickers[0] * 16 + kickers[1]
    if pair1 >= 0 and pair2 >= 0:
        return 0x20000 + pair1 * 256 + pair2 * 16 + kickers[0]
    if pair1 >= 0:
        return 0x10000 + pair1 * 4096 + kickers[0] * 256 + kickers[1] * 16 + kickers[2]
    # High card
    return ranks[0] * 16**4 + ranks[1] * 16**3 + ranks[2] * 16**2 + ranks[3] * 16 + ranks[4]


def _parse_cards(cards):
    """Parse list of card strings to (rank_list, suit_list)."""
    ranks = []
    suits = []
    for c in cards:
        ranks.append(RANK_MAP[c[0]])
        suits.append(ord(c[1]))  # just use char code for suit comparison
    return ranks, suits


def best_score_7(cards_7):
    """Best 5-card hand from 7 cards. Input: list of card strings."""
    rs, ss = _parse_cards(cards_7)
    best = 0
    for i0, i1, i2, i3, i4 in _COMBO_INDICES_7:
        score = _eval5(rs[i0], rs[i1], rs[i2], rs[i3], rs[i4],
                       ss[i0], ss[i1], ss[i2], ss[i3], ss[i4])
        if score > best:
            best = score
    return best


def best_score_n(cards):
    """Best 5-card hand from N>=5 cards."""
    rs, ss = _parse_cards(cards)
    n = len(cards)
    best = 0
    for combo in combinations(range(n), 5):
        i0, i1, i2, i3, i4 = combo
        score = _eval5(rs[i0], rs[i1], rs[i2], rs[i3], rs[i4],
                       ss[i0], ss[i1], ss[i2], ss[i3], ss[i4])
        if score > best:
            best = score
    return best


# ─── Monte Carlo Equity (Optimized) ─────────────────────────────────────────

def mc_equity(my_hand, board, opp_known, num_sims):
    """Fast Monte Carlo equity estimation."""
    used = set(my_hand)
    if board:
        used.update(board)
    if opp_known:
        used.update(opp_known)

    remaining = [c for c in FULL_DECK if c not in used]
    need_board = 5 - len(board) if board else 5
    need_opp = 2 - len(opp_known) if opp_known else 2
    need_total = need_board + need_opp

    board_list = list(board) if board else []
    opp_list = list(opp_known) if opp_known else []

    wins = 0
    ties = 0
    n = len(remaining)

    for _ in range(num_sims):
        # Fisher-Yates partial shuffle for just what we need
        arr = remaining[:]
        for i in range(need_total):
            j = random.randint(i, n - 1)
            arr[i], arr[j] = arr[j], arr[i]

        sim_board = board_list + arr[:need_board]
        sim_opp = opp_list + arr[need_board:need_total]

        my_cards = my_hand + sim_board
        opp_cards = sim_opp + sim_board

        my_score = best_score_7(my_cards)
        opp_score = best_score_7(opp_cards)

        if my_score > opp_score:
            wins += 1
        elif my_score == opp_score:
            ties += 1

    if num_sims == 0:
        return 0.5
    return (wins + 0.5 * ties) / num_sims


# ─── Chen Formula ───────────────────────────────────────────────────────────

_CHEN_VALUES = {
    'A': 10, 'K': 8, 'Q': 7, 'J': 6, 'T': 5,
    '9': 4.5, '8': 4, '7': 3.5, '6': 3, '5': 2.5,
    '4': 2, '3': 1.5, '2': 1
}

_RANK_ORDER = 'A23456789TJQK'


def chen_score(c1, c2):
    """Chen formula preflop score."""
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    v1, v2 = _CHEN_VALUES[r1], _CHEN_VALUES[r2]

    score = max(v1, v2)

    if r1 == r2:
        return max(score * 2, 5)

    if s1 == s2:
        score += 2

    gap = abs(_RANK_ORDER.index(r1) - _RANK_ORDER.index(r2)) - 1
    if gap == 1:
        score -= 1
    elif gap == 2:
        score -= 2
    elif gap == 3:
        score -= 4
    elif gap >= 4:
        score -= 5

    if gap <= 1 and max(v1, v2) < 7:
        score += 1

    return score


# ─── Bot ─────────────────────────────────────────────────────────────────────

class Player(BaseBot):

    def __init__(self):
        # Opponent stats
        self.opp_folds = 0
        self.opp_raises = 0
        self.opp_calls = 0
        self.opp_checks = 0
        self.opp_actions = 0
        self.opp_bid_sum = 0
        self.opp_bid_n = 0

        # Per-hand
        self._chen = 0.0
        self._prev_opp_wager = 0
        self._prev_street = None

    def on_hand_start(self, game_info, current_state):
        self._chen = chen_score(current_state.my_hand[0], current_state.my_hand[1])
        self._prev_opp_wager = BIG_BLIND if not current_state.is_bb else SMALL_BLIND
        self._prev_street = 'pre-flop'

    def on_hand_end(self, game_info, current_state):
        pass

    # ── Opponent stats ───────────────────────────────────────────────────────

    @property
    def fold_rate(self):
        return self.opp_folds / max(1, self.opp_actions) if self.opp_actions >= 10 else 0.3

    @property
    def raise_rate(self):
        return self.opp_raises / max(1, self.opp_actions) if self.opp_actions >= 10 else 0.3

    @property
    def avg_bid(self):
        return self.opp_bid_sum / max(1, self.opp_bid_n) if self.opp_bid_n > 0 else 50

    def _track(self, state):
        if state.street != self._prev_street:
            self._prev_opp_wager = 0
            self._prev_street = state.street
        delta = state.opp_wager - self._prev_opp_wager
        if delta > 0:
            if state.opp_wager > state.my_wager:
                self.opp_raises += 1
            else:
                self.opp_calls += 1
            self.opp_actions += 1
        self._prev_opp_wager = state.opp_wager

    # ── Main Decision ────────────────────────────────────────────────────────

    def get_move(self, game_info, current_state):
        self._track(current_state)

        if current_state.street == 'auction':
            return self._bid(current_state)
        if current_state.street == 'pre-flop':
            return self._preflop(current_state)
        return self._postflop(current_state, game_info)

    # ── Preflop ──────────────────────────────────────────────────────────────

    def _preflop(self, s):
        chen = self._chen
        cost = s.cost_to_call

        # Premium (top ~15%)
        if chen >= 10:
            if s.can_act(ActionRaise):
                lo, hi = s.raise_bounds
                amt = min(hi, max(lo, int(3.5 * BIG_BLIND) + s.opp_wager))
                return ActionRaise(amt)
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()

        # Strong
        if chen >= 8:
            if cost <= 5 * BIG_BLIND:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    amt = min(hi, max(lo, int(2.5 * BIG_BLIND) + s.opp_wager))
                    return ActionRaise(amt)
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()

        # Playable
        if chen >= 6:
            if cost <= 2 * BIG_BLIND:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if cost <= 4 * BIG_BLIND and random.random() < 0.3:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        # Marginal
        if chen >= 4:
            if cost <= BIG_BLIND:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        # Trash
        if s.can_act(ActionCheck):
            return ActionCheck()
        return ActionFold()

    # ── Auction ──────────────────────────────────────────────────────────────

    def _bid(self, s):
        # Quick equity estimation with reduced rollouts
        eq = mc_equity(s.my_hand, s.board, [], MC_ITERS_AUCTION)
        pot = s.pot
        chips = s.my_chips

        # Second-price auction: bid true value of information
        # Info is most valuable when uncertain (equity ~0.5)
        # and when pot is large
        uncertainty = 1.0 - abs(eq - 0.5) * 2  # peaks at eq=0.5

        # Base bid: fraction of pot scaled by uncertainty
        bid_value = pot * 0.20 * uncertainty

        # Don't overbid relative to stack
        bid_value = min(bid_value, chips * 0.10)

        # Adapt to opponent
        if self.opp_bid_n > 5:
            opp_avg = self.avg_bid
            # If opponent bids very high, sometimes let them pay
            if opp_avg > pot * 0.5:
                bid_value = min(bid_value, pot * 0.05)
            # If opponent bids low, slight upbid to win cheaply
            elif opp_avg < 20:
                bid_value = max(bid_value, opp_avg + 5)

        bid = max(0, min(int(bid_value), chips))
        return ActionBid(bid)

    # ── Postflop ─────────────────────────────────────────────────────────────

    def _postflop(self, s, game_info):
        # Manage time budget: if running low, skip MC and play tight
        if game_info.time_bank < 3.0:
            return self._fast_postflop(s)

        eq = mc_equity(s.my_hand, s.board, s.opp_revealed_cards, MC_ITERS_POSTFLOP)

        pot = s.pot
        cost = s.cost_to_call

        pot_odds = cost / (pot + cost) if cost > 0 else 0

        # Monster
        if eq >= 0.80:
            return self._bet_value(s, aggressive=True)

        # Strong
        if eq >= 0.65:
            return self._bet_value(s, aggressive=False)

        # Decent
        if eq >= 0.50:
            if cost == 0:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    amt = min(hi, max(lo, int(pot * 0.45)))
                    return ActionRaise(amt)
                return ActionCheck()
            if eq > pot_odds + 0.05:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        # Marginal draw
        if eq >= 0.35:
            if cost == 0:
                return ActionCheck()
            if eq > pot_odds and cost <= pot * 0.35:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        # Weak
        if eq >= 0.20:
            if cost == 0:
                # Bluff vs tight
                if self.fold_rate > 0.4 and random.random() < 0.12:
                    if s.can_act(ActionRaise):
                        lo, hi = s.raise_bounds
                        amt = min(hi, max(lo, int(pot * 0.55)))
                        return ActionRaise(amt)
                return ActionCheck()
            if eq > pot_odds and cost <= BIG_BLIND * 2:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        # Trash
        return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _fast_postflop(self, s):
        """Time-pressure fallback: no MC, just play tight."""
        if s.cost_to_call == 0:
            return ActionCheck()
        if s.cost_to_call <= BIG_BLIND and s.can_act(ActionCall):
            return ActionCall()
        return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _bet_value(self, s, aggressive):
        cost = s.cost_to_call
        pot = s.pot

        if cost > 0:
            if aggressive and s.can_act(ActionRaise):
                lo, hi = s.raise_bounds
                amt = min(hi, max(lo, int(pot * 0.65) + s.opp_wager))
                return ActionRaise(amt)
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()

        if s.can_act(ActionRaise):
            lo, hi = s.raise_bounds
            frac = 0.70 if aggressive else 0.50
            amt = min(hi, max(lo, int(pot * frac)))
            return ActionRaise(amt)
        return ActionCheck()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
