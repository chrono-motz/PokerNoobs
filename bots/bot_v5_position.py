'''
Bot v5 — Position-Aware
Plays differently as SB vs BB. SB steals wider, BB defends tighter.
Uses different bet sizing in/out of position.
'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
import random
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from bot import mc_equity, chen_score, MC_ITERS_AUCTION, MC_ITERS_POSTFLOP

STARTING_STACK = 5000
BIG_BLIND = 20
SMALL_BLIND = 10

class Player(BaseBot):
    def __init__(self):
        self.opp_folds = 0
        self.opp_raises = 0
        self.opp_calls = 0
        self.opp_actions = 0
        self._chen = 0.0
        self._prev_opp_wager = 0
        self._prev_street = None

    def on_hand_start(self, gi, cs):
        self._chen = chen_score(cs.my_hand[0], cs.my_hand[1])
        self._prev_opp_wager = BIG_BLIND if not cs.is_bb else SMALL_BLIND
        self._prev_street = 'pre-flop'

    def on_hand_end(self, gi, cs): pass

    @property
    def fold_rate(self):
        return self.opp_folds / max(1, self.opp_actions) if self.opp_actions >= 10 else 0.3

    def _track(self, s):
        if s.street != self._prev_street:
            self._prev_opp_wager = 0
            self._prev_street = s.street
        delta = s.opp_wager - self._prev_opp_wager
        if delta > 0:
            if s.opp_wager > s.my_wager: self.opp_raises += 1
            else: self.opp_calls += 1
            self.opp_actions += 1
        self._prev_opp_wager = s.opp_wager

    def get_move(self, gi, cs):
        self._track(cs)
        if cs.street == 'auction': return self._bid(cs)
        if cs.street == 'pre-flop': return self._preflop(cs)
        return self._postflop(cs, gi)

    # ── POSITION-AWARE PREFLOP ──
    def _preflop(self, s):
        chen = self._chen
        cost = s.cost_to_call
        is_sb = not s.is_bb  # SB acts first preflop

        if is_sb:
            # SB: steal wider, open-raise more hands
            if chen >= 10:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(3.5*BIG_BLIND) + s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if chen >= 7:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5*BIG_BLIND) + s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if chen >= 5:
                # Steal attempt
                if s.can_act(ActionRaise) and random.random() < 0.30:
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5*BIG_BLIND))))
                if cost <= BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            if chen >= 3 and random.random() < 0.15:
                # Occasional steal with marginal
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5*BIG_BLIND))))
            if s.can_act(ActionCheck): return ActionCheck()
            return ActionFold()
        else:
            # BB: defend tighter, 3-bet premium
            if chen >= 10:
                if s.can_act(ActionRaise) and cost > 0:
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(3.5*cost) + s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            if chen >= 8:
                if cost <= 3*BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                if cost <= 5*BIG_BLIND and random.random() < 0.4:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            if chen >= 6:
                if cost <= 2*BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            if chen >= 4:
                if cost <= BIG_BLIND:
                    return ActionCall() if s.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _bid(self, s):
        eq = mc_equity(s.my_hand, s.board, [], MC_ITERS_AUCTION)
        pot = s.pot
        chips = s.my_chips
        uncertainty = 1.0 - abs(eq - 0.5) * 2
        bid_value = pot * 0.20 * uncertainty
        bid_value = min(bid_value, chips * 0.10)
        return ActionBid(max(0, min(int(bid_value), chips)))

    # ── POSITION-AWARE POSTFLOP ──
    def _postflop(self, s, gi):
        if gi.time_bank < 3.0:
            if s.cost_to_call == 0: return ActionCheck()
            if s.cost_to_call <= BIG_BLIND and s.can_act(ActionCall): return ActionCall()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

        eq = mc_equity(s.my_hand, s.board, s.opp_revealed_cards, MC_ITERS_POSTFLOP)
        pot, cost = s.pot, s.cost_to_call
        po = cost / (pot + cost) if cost > 0 else 0
        # Post-flop: BB acts first (is "out of position")
        oop = s.is_bb

        if eq >= 0.80:
            if oop and eq >= 0.85:
                # Check-raise trap OOP with monsters
                if cost == 0 and random.random() < 0.35:
                    return ActionCheck()
            return self._vbet(s, True)
        if eq >= 0.65:
            return self._vbet(s, False)
        if eq >= 0.50:
            if cost == 0:
                # IP: c-bet more; OOP: check more
                bet_freq = 0.70 if not oop else 0.45
                if random.random() < bet_freq and s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    frac = 0.50 if not oop else 0.40
                    return ActionRaise(min(hi, max(lo, int(pot*frac))))
                return ActionCheck()
            if eq > po + 0.05: return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        if eq >= 0.35:
            if cost == 0: return ActionCheck()
            if eq > po and cost <= pot*0.35:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        if eq >= 0.20:
            if cost == 0:
                if not oop and self.fold_rate > 0.4 and random.random() < 0.15:
                    if s.can_act(ActionRaise):
                        lo, hi = s.raise_bounds
                        return ActionRaise(min(hi, max(lo, int(pot*0.55))))
                return ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _vbet(self, s, agg):
        pot, cost = s.pot, s.cost_to_call
        if cost > 0:
            if agg and s.can_act(ActionRaise):
                lo, hi = s.raise_bounds
                return ActionRaise(min(hi, max(lo, int(pot*0.65) + s.opp_wager)))
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()
        if s.can_act(ActionRaise):
            lo, hi = s.raise_bounds
            f = 0.70 if agg else 0.50
            return ActionRaise(min(hi, max(lo, int(pot*f))))
        return ActionCheck()

if __name__ == '__main__':
    run_bot(Player(), parse_args())
