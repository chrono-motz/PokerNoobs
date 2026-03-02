'''
Bot v7 — Final Champion
Built on v6 + exploitative adjustments based on opponent tendencies:
  - vs tight (fold_rate > 0.4): steal more, bluff less, bet smaller for value
  - vs aggro (raise_rate > 0.35): trap more, call wider, bet bigger for value
  - Adaptive bet sizing based on opponent fold/call tendency
'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
from poker_utils import mc_equity, chen_score
import random

BIG_BLIND = 20
SMALL_BLIND = 10

class Player(BaseBot):
    def __init__(self):
        self.opp_folds = 0
        self.opp_raises = 0
        self.opp_calls = 0
        self.opp_actions = 0
        self.opp_bid_sum = 0
        self.opp_bid_n = 0
        self._chen = 0.0
        self._po = 0
        self._ps = None

    def on_hand_start(self, gi, cs):
        self._chen = chen_score(cs.my_hand[0], cs.my_hand[1])
        self._po = BIG_BLIND if not cs.is_bb else SMALL_BLIND
        self._ps = 'pre-flop'

    def on_hand_end(self, gi, cs): pass

    # ── Opponent modeling ────────────────────────────────────────────────
    @property
    def fold_rate(self):
        return self.opp_folds / max(1, self.opp_actions) if self.opp_actions >= 10 else 0.3

    @property
    def raise_rate(self):
        return self.opp_raises / max(1, self.opp_actions) if self.opp_actions >= 10 else 0.3

    @property
    def call_rate(self):
        return self.opp_calls / max(1, self.opp_actions) if self.opp_actions >= 10 else 0.3

    @property
    def avg_bid(self):
        return self.opp_bid_sum / max(1, self.opp_bid_n) if self.opp_bid_n > 0 else 50

    @property
    def is_tight(self):
        return self.fold_rate > 0.40

    @property
    def is_aggro(self):
        return self.raise_rate > 0.35

    @property
    def is_passive(self):
        return self.call_rate > 0.50

    def _track(self, s):
        if s.street != self._ps:
            self._po = 0
            self._ps = s.street
        d = s.opp_wager - self._po
        if d > 0:
            if s.opp_wager > s.my_wager:
                self.opp_raises += 1
            else:
                self.opp_calls += 1
            self.opp_actions += 1
        elif d == 0 and self._po == s.opp_wager and s.street == self._ps:
            # Opponent checked or folded (no wager change on same street)
            pass
        self._po = s.opp_wager

    # ── Main Decision ────────────────────────────────────────────────────
    def get_move(self, gi, cs):
        self._track(cs)
        if cs.street == 'auction':
            return self._bid(cs)
        if cs.street == 'pre-flop':
            return self._preflop(cs)
        return self._postflop(cs, gi)

    # ── PREFLOP: v2's wider ranges + v5's position awareness + exploit ──
    def _preflop(self, s):
        chen = self._chen
        cost = s.cost_to_call
        is_sb = not s.is_bb

        if is_sb:
            # SB: steal wider, especially vs tight opponents
            steal_boost = 1 if self.is_tight else 0
            if chen >= 10:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(4.0 * BIG_BLIND) + s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if chen >= (6 if self.is_tight else 7):  # wider vs tight
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(3.0 * BIG_BLIND) + s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if chen >= (4 if self.is_tight else 5):
                steal_chance = 0.45 if self.is_tight else 0.30
                if s.can_act(ActionRaise) and random.random() < steal_chance:
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5 * BIG_BLIND))))
                if cost <= BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            if chen >= 3 and self.is_tight and random.random() < 0.20:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5 * BIG_BLIND))))
            if cost <= BIG_BLIND and chen >= 3:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        else:
            # BB: defend vs steals, 3-bet premium vs aggro
            if chen >= 10:
                if s.can_act(ActionRaise) and cost > 0:
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(3.5 * cost) + s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if chen >= 7:
                if cost <= 3 * BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                if cost <= 5 * BIG_BLIND and random.random() < 0.4:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            if chen >= 5:
                if cost <= 2 * BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            if chen >= 3:
                if cost <= BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    # ── AUCTION ─────────────────────────────────────────────────────────
    def _bid(self, s):
        eq = mc_equity(s.my_hand, s.board, [], 40)
        pot = s.pot
        chips = s.my_chips
        uncertainty = 1.0 - abs(eq - 0.5) * 2
        bid_value = pot * 0.20 * uncertainty
        bid_value = min(bid_value, chips * 0.10)
        if self.opp_bid_n > 5:
            opp_avg = self.avg_bid
            if opp_avg > pot * 0.5:
                bid_value = min(bid_value, pot * 0.05)
            elif opp_avg < 20:
                bid_value = max(bid_value, opp_avg + 5)
        return ActionBid(max(0, min(int(bid_value), chips)))

    # ── POSTFLOP: Adaptive bet sizing based on opponent profile ──────
    def _postflop(self, s, gi):
        if gi.time_bank < 3.0:
            if s.cost_to_call == 0: return ActionCheck()
            if s.cost_to_call <= BIG_BLIND and s.can_act(ActionCall): return ActionCall()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        eq = mc_equity(s.my_hand, s.board, s.opp_revealed_cards, 50)
        pot = s.pot
        cost = s.cost_to_call
        po = cost / (pot + cost) if cost > 0 else 0
        oop = s.is_bb

        # --- Adaptive bet sizing ---
        # vs passive/calling station: bet bigger for value, bluff less
        # vs tight: bet smaller to get calls, steal more
        # vs aggro: trap more, check-raise
        if self.is_passive:
            value_size_agg = 0.90  # big value vs calling stations
            value_size_std = 0.70
            bluff_rate = 0.08     # rarely bluff against call-happy
        elif self.is_tight:
            value_size_agg = 0.60  # smaller to induce calls
            value_size_std = 0.45
            bluff_rate = 0.28     # bluff more vs tight
        elif self.is_aggro:
            value_size_agg = 0.85  # big value when they 3-bet into us
            value_size_std = 0.65
            bluff_rate = 0.10     # aggro players call bluffs
        else:
            value_size_agg = 0.80
            value_size_std = 0.60
            bluff_rate = 0.18

        # --- Monster ---
        if eq >= 0.78:
            # Check-raise trap vs aggro OOP
            if oop and (self.is_aggro or eq >= 0.88) and cost == 0 and random.random() < 0.40:
                return ActionCheck()
            return self._vbet(s, value_size_agg)

        # --- Strong ---
        if eq >= 0.60:
            return self._vbet(s, value_size_std)

        # --- Decent ---
        if eq >= 0.45:
            if cost == 0:
                bet_freq = 0.75 if not oop else 0.50
                if random.random() < bet_freq and s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    frac = 0.55 if not oop else 0.40
                    return ActionRaise(min(hi, max(lo, int(pot * frac))))
                return ActionCheck()
            if eq > po + 0.03:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        # --- Marginal ---
        if eq >= 0.30:
            if cost == 0:
                # Bluff with adaptive rate + position
                actual_bluff = bluff_rate * (1.3 if not oop else 0.7)
                if random.random() < actual_bluff:
                    if s.can_act(ActionRaise):
                        lo, hi = s.raise_bounds
                        return ActionRaise(min(hi, max(lo, int(pot * 0.60))))
                return ActionCheck()
            if eq > po and cost <= pot * 0.4:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        # --- Weak ---
        if eq >= 0.15:
            if cost == 0:
                # Only bluff IP vs tight opponents
                if not oop and self.is_tight and random.random() < bluff_rate * 0.6:
                    if s.can_act(ActionRaise):
                        lo, hi = s.raise_bounds
                        return ActionRaise(min(hi, max(lo, int(pot * 0.65))))
                return ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _vbet(self, s, size_frac):
        pot = s.pot
        cost = s.cost_to_call
        if cost > 0:
            if s.can_act(ActionRaise):
                lo, hi = s.raise_bounds
                return ActionRaise(min(hi, max(lo, int(pot * size_frac) + s.opp_wager)))
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()
        if s.can_act(ActionRaise):
            lo, hi = s.raise_bounds
            return ActionRaise(min(hi, max(lo, int(pot * size_frac))))
        return ActionCheck()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
