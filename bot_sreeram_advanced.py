#!/usr/bin/env python3
"""
Advanced Poker Bot - ULTRA AGGRESSIVE VERSION
Based on sub3's proven logic but MORE aggressive preflop
"""
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
import random
from itertools import combinations

# ────────────────────────────────────────────────────────────────────────
# POKER UTILS - Inlined from poker_utils.py (no local dependencies)
# ────────────────────────────────────────────────────────────────────────

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
    """Evaluate 5-card hand strength."""
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
    """Parse card notation to ranks and suits."""
    ranks, suits = [], []
    for c in cards:
        ranks.append(RANK_MAP[c[0]])
        suits.append(ord(c[1]))
    return ranks, suits


def best_score_7(cards_7):
    """Find best 5-card hand from 7 cards."""
    rs, ss = _parse_cards(cards_7)
    best = 0
    for i0, i1, i2, i3, i4 in _COMBO_INDICES_7:
        score = _eval5(rs[i0], rs[i1], rs[i2], rs[i3], rs[i4],
                       ss[i0], ss[i1], ss[i2], ss[i3], ss[i4])
        if score > best: best = score
    return best


def mc_equity(my_hand, board, opp_known, num_sims):
    """Monte Carlo equity calculation."""
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
    """Chen hand strength evaluation."""
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

BIG_BLIND = 20
SMALL_BLIND = 10

class Player(BaseBot):
    """Ultra-aggressive version of championship bot"""
    
    def __init__(self):
        self.opp_folds = 0
        self.opp_raises = 0
        self.opp_calls = 0
        self.opp_actions = 0
        
        self._chen = 0.0
        self._po = 0
        self._ps = None
        self._has_opponent_info = False

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        self._chen = chen_score(current_state.my_hand[0], current_state.my_hand[1])
        self._po = BIG_BLIND if not current_state.is_bb else SMALL_BLIND
        self._ps = 'pre-flop'
        self._has_opponent_info = False

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        pass

    @property
    def fold_rate(self):
        if self.opp_actions < 10:
            return 0.35
        return self.opp_folds / max(1, self.opp_actions)
    
    @property
    def raise_rate(self):
        if self.opp_actions < 10:
            return 0.25
        return self.opp_raises / max(1, self.opp_actions)

    def _track_opponent(self, state):
        if state.street != self._ps:
            self._po = 0
            self._ps = state.street
        
        d = state.opp_wager - self._po
        if d > 0:
            if state.opp_wager > state.my_wager:
                self.opp_raises += 1
            else:
                self.opp_calls += 1
            self.opp_actions += 1
        
        self._po = state.opp_wager
        if len(state.opp_revealed_cards) > 0:
            self._has_opponent_info = True

    def get_move(self, game_info: GameInfo, current_state: PokerState):
        try:
            self._track_opponent(current_state)
        except Exception as e:
            pass
        
        street = current_state.street

        try:
            if street == 'pre-flop':
                return self._preflop(current_state)
            elif street == 'auction':
                return self._auction(current_state)
            else:
                return self._postflop(current_state, game_info)
        except Exception as e:
            if street == 'auction':
                return ActionBid(1)
            if current_state.can_act(ActionCall):
                return ActionCall()
            if current_state.can_act(ActionCheck):
                return ActionCheck()
            return ActionFold()

    def _preflop(self, state):
        """ULTRA AGGRESSIVE - play with chen >= 2"""
        try:
            chen = self._chen
            cost = state.cost_to_call
            
            # PREMIUM: raise aggressively
            if chen >= 10:
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    amt = min(hi, max(lo, int(3.0 * BIG_BLIND) + state.opp_wager))
                    return ActionRaise(amt)
                elif state.can_act(ActionCall):
                    return ActionCall()
                else:
                    return ActionCheck()
            
            # GOOD: raise and call
            if chen >= 7:
                if state.can_act(ActionRaise) and cost > 0:
                    lo, hi = state.raise_bounds
                    amt = min(hi, max(lo, cost * 2))
                    return ActionRaise(amt)
                elif state.can_act(ActionCall):
                    return ActionCall()
                elif state.can_act(ActionCheck):
                    return ActionCheck()
                else:
                    return ActionFold()
            
            # MEDIUM: almost always call
            if chen >= 3:
                if state.can_act(ActionCall):
                    return ActionCall()
                elif state.can_act(ActionCheck):
                    return ActionCheck()
                else:
                    return ActionFold()
            
            # WEAK: call 50% of the time
            if random.random() < 0.5:
                if state.can_act(ActionCall):
                    return ActionCall()
                elif state.can_act(ActionCheck):
                    return ActionCheck()
            
            if state.can_act(ActionCheck):
                return ActionCheck()
            elif state.can_act(ActionCall):
                return ActionCall()
            else:
                return ActionFold()
        
        except Exception as e:
            if state.can_act(ActionCall):
                return ActionCall()
            elif state.can_act(ActionCheck):
                return ActionCheck()
            else:
                return ActionFold()

    def _auction(self, state):
        try:
            equity = mc_equity(state.my_hand, list(state.board) if state.board else [], [], 40)
        except Exception as e:
            equity = 0.5

        try:
            pot = state.pot
            chips = state.my_chips
            
            if pot <= 0:
                pot = 30
            if chips <= 0:
                chips = 4990
                
            # MORE AGGRESSIVE bidding than sub3
            if equity >= 0.75:
                bid_pct = 0.35
            elif equity >= 0.65:
                bid_pct = 0.25
            elif equity >= 0.55:
                bid_pct = 0.15
            elif equity >= 0.45:
                bid_pct = 0.08
            elif equity >= 0.35:
                bid_pct = 0.04
            else:
                bid_pct = 0.02
            
            base_bid = int(pot * bid_pct)
            capped_bid = min(base_bid, int(chips * 0.20))
            final_bid = max(1, capped_bid, base_bid)
            
            if final_bid < 1:
                final_bid = 1
                
            return ActionBid(final_bid)
            
        except Exception as e:
            return ActionBid(1)

    def _postflop(self, state, game_info):
        """Aggressive postflop - call more often"""
        if game_info.time_bank < 2.0:
            if state.cost_to_call == 0:
                return ActionCheck()
            if state.cost_to_call <= BIG_BLIND and state.can_act(ActionCall):
                return ActionCall()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        rollouts = 35 if state.street == 'flop' else 45
        try:
            opp_revealed = list(state.opp_revealed_cards) if state.opp_revealed_cards else []
            equity = mc_equity(state.my_hand, list(state.board) if state.board else [], opp_revealed, rollouts)
        except:
            equity = 0.5

        pot = state.pot
        cost = state.cost_to_call
        info_multiplier = 1.25 if self._has_opponent_info else 1.0
        po = cost / (pot + cost + 1e-6) if cost > 0 else 0

        # STRONG
        if equity >= 0.80:
            return self._value_bet(state, aggressive=True, multiplier=info_multiplier)

        # GOOD
        if equity >= 0.63:
            return self._value_bet(state, aggressive=False, multiplier=info_multiplier)

        # MODERATE
        if equity >= 0.50:
            if cost == 0:
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    bet = int(pot * 0.45 * info_multiplier)
                    return ActionRaise(min(hi, max(lo, bet)))
                return ActionCheck()
            if equity > po + 0.05:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # MARGINAL
        if equity >= 0.35:
            if cost == 0:
                return ActionCheck()
            if equity > po and cost <= pot * 0.35:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # WEAK - call cheap more often
        if equity >= 0.20:
            if cost == 0:
                if state.can_act(ActionRaise) and random.random() < 0.25:
                    lo, hi = state.raise_bounds
                    bet = int(pot * 0.55)
                    return ActionRaise(min(hi, max(lo, bet)))
                return ActionCheck()
            # Call cheap bets
            if cost <= pot * 0.15 and state.can_act(ActionCall):
                return ActionCall()
            if cost <= BIG_BLIND and state.can_act(ActionCall) and random.random() < 0.5:
                return ActionCall()
            if state.can_act(ActionCheck):
                return ActionCheck()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # BLUFF: call small bets
        if cost <= BIG_BLIND and state.can_act(ActionCall):
            return ActionCall()
        
        return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

    def _value_bet(self, state, aggressive=False, multiplier=1.0):
        pot = state.pot
        cost = state.cost_to_call

        if cost > 0:
            if aggressive and state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                bet = int(pot * 0.70 * multiplier) + state.opp_wager
                return ActionRaise(min(hi, max(lo, bet)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        if state.can_act(ActionRaise):
            lo, hi = state.raise_bounds
            bet_size = (0.75 if aggressive else 0.55) * multiplier
            bet = int(pot * bet_size)
            return ActionRaise(min(hi, max(lo, bet)))

        return ActionCheck()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
