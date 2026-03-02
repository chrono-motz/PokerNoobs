'''
Bot v6 — Champion
Synthesized from tournament results:
  🥇 v2 Aggro traits: wider preflop, bigger bets, lower equity thresholds
  + v5 Position traits: SB steals, BB defense, check-raise traps
  + v1 Baseline: strong opponent modeling and auction strategy
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
        # Opponent stats
        self.opp_folds = 0
        self.opp_raises = 0
        self.opp_calls = 0
        self.opp_actions = 0
        self.opp_bid_sum = 0
        self.opp_bid_n = 0
        # Per-hand
        self._chen = 0.0
        self._po = 0
        self._ps = None

    def on_hand_start(self, gi, cs):
        self._chen = chen_score(cs.my_hand[0], cs.my_hand[1])
        self._po = BIG_BLIND if not cs.is_bb else SMALL_BLIND
        self._ps = 'pre-flop'

    def on_hand_end(self, gi, cs):
        pass

    # ── Opponent modeling ────────────────────────────────────────────────
    @property
    def fold_rate(self):
        return self.opp_folds / max(1, self.opp_actions) if self.opp_actions >= 10 else 0.3

    @property
    def raise_rate(self):
        return self.opp_raises / max(1, self.opp_actions) if self.opp_actions >= 10 else 0.3

    @property
    def avg_bid(self):
        return self.opp_bid_sum / max(1, self.opp_bid_n) if self.opp_bid_n > 0 else 50

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
        self._po = s.opp_wager

    # ── Main Decision ────────────────────────────────────────────────────
    def get_move(self, gi, cs):
        self._track(cs)
        if cs.street == 'auction':
            return self._bid(cs)
        if cs.street == 'pre-flop':
            return self._preflop(cs)
        return self._postflop(cs, gi)

    # ── PREFLOP: Aggressive + Position-aware (from v2 + v5) ──────────
    def _preflop(self, s):
        chen = self._chen
        cost = s.cost_to_call
        is_sb = not s.is_bb

        if is_sb:
            # --- SB: steal wider, raise aggressively ---
            if chen >= 10:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(4.0 * BIG_BLIND) + s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if chen >= 7:  # v2's wider threshold
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(3.0 * BIG_BLIND) + s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if chen >= 5:
                # Steal attempt from SB (v5 trait)
                if s.can_act(ActionRaise) and random.random() < 0.35:
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5 * BIG_BLIND))))
                if cost <= BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            if chen >= 3:
                # Occasional steal with marginal (v5 trait)
                if s.can_act(ActionRaise) and random.random() < 0.18:
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5 * BIG_BLIND))))
                if cost <= BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        else:
            # --- BB: defend smart, 3-bet premium ---
            if chen >= 10:
                if s.can_act(ActionRaise) and cost > 0:
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(3.5 * cost) + s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if chen >= 7:  # v2's wider threshold
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

    # ── AUCTION: Smart bidding (from v1 baseline) ────────────────────
    def _bid(self, s):
        eq = mc_equity(s.my_hand, s.board, [], 40)
        pot = s.pot
        chips = s.my_chips

        uncertainty = 1.0 - abs(eq - 0.5) * 2
        bid_value = pot * 0.20 * uncertainty
        bid_value = min(bid_value, chips * 0.10)

        # Opponent adaptation
        if self.opp_bid_n > 5:
            opp_avg = self.avg_bid
            if opp_avg > pot * 0.5:
                bid_value = min(bid_value, pot * 0.05)
            elif opp_avg < 20:
                bid_value = max(bid_value, opp_avg + 5)

        return ActionBid(max(0, min(int(bid_value), chips)))

    # ── POSTFLOP: Aggressive + Position-aware (from v2 + v5) ─────────
    def _postflop(self, s, gi):
        if gi.time_bank < 3.0:
            if s.cost_to_call == 0:
                return ActionCheck()
            if s.cost_to_call <= BIG_BLIND and s.can_act(ActionCall):
                return ActionCall()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        eq = mc_equity(s.my_hand, s.board, s.opp_revealed_cards, 50)
        pot = s.pot
        cost = s.cost_to_call
        po = cost / (pot + cost) if cost > 0 else 0
        oop = s.is_bb  # BB is out of position postflop

        # Monster (eq >= 0.78 from v2)
        if eq >= 0.78:
            # Check-raise trap OOP (from v5)
            if oop and eq >= 0.85 and cost == 0 and random.random() < 0.35:
                return ActionCheck()
            return self._vbet(s, aggressive=True)

        # Strong (eq >= 0.60 from v2)
        if eq >= 0.60:
            return self._vbet(s, aggressive=False)

        # Decent — (eq >= 0.45 from v2, position from v5)
        if eq >= 0.45:
            if cost == 0:
                bet_freq = 0.75 if not oop else 0.50
                if random.random() < bet_freq and s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    frac = 0.55 if not oop else 0.45
                    return ActionRaise(min(hi, max(lo, int(pot * frac))))
                return ActionCheck()
            if eq > po + 0.03:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        # Marginal (0.30-0.45 from v2)
        if eq >= 0.30:
            if cost == 0:
                # Bluff more from IP (v2 + v5 combined)
                bluff_rate = 0.22 if not oop else 0.10
                if self.fold_rate > 0.3 and random.random() < bluff_rate:
                    if s.can_act(ActionRaise):
                        lo, hi = s.raise_bounds
                        return ActionRaise(min(hi, max(lo, int(pot * 0.60))))
                return ActionCheck()
            if eq > po and cost <= pot * 0.4:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        # Weak (0.15-0.30 from v2)
        if eq >= 0.15:
            if cost == 0:
                # Occasional IP bluff
                if not oop and self.fold_rate > 0.35 and random.random() < 0.15:
                    if s.can_act(ActionRaise):
                        lo, hi = s.raise_bounds
                        return ActionRaise(min(hi, max(lo, int(pot * 0.65))))
                return ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _vbet(self, s, aggressive):
        pot = s.pot
        cost = s.cost_to_call
        if cost > 0:
            if aggressive and s.can_act(ActionRaise):
                lo, hi = s.raise_bounds
                # v2's big sizing: 0.80x pot
                return ActionRaise(min(hi, max(lo, int(pot * 0.80) + s.opp_wager)))
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()
        if s.can_act(ActionRaise):
            lo, hi = s.raise_bounds
            frac = 0.85 if aggressive else 0.60  # v2 sizing
            return ActionRaise(min(hi, max(lo, int(pot * frac))))
        return ActionCheck()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
