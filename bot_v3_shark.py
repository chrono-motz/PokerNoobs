'''Bot v3 — Tight-Shark: top hands only, massive value bets, zero bluffs.'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
from poker_utils import mc_equity, chen_score
import random

BIG_BLIND = 20

class Player(BaseBot):
    def __init__(self):
        self.opp_folds = self.opp_raises = self.opp_calls = self.opp_actions = 0
        self._chen = 0.0; self._po = 0; self._ps = None

    def on_hand_start(self, gi, cs):
        self._chen = chen_score(cs.my_hand[0], cs.my_hand[1])
        self._po = BIG_BLIND if not cs.is_bb else 10
        self._ps = 'pre-flop'

    def on_hand_end(self, gi, cs): pass

    def _track(self, s):
        if s.street != self._ps: self._po = 0; self._ps = s.street
        d = s.opp_wager - self._po
        if d > 0:
            if s.opp_wager > s.my_wager: self.opp_raises += 1
            else: self.opp_calls += 1
            self.opp_actions += 1
        self._po = s.opp_wager

    def get_move(self, gi, cs):
        self._track(cs)
        if cs.street == 'auction': return self._bid(cs)
        if cs.street == 'pre-flop': return self._preflop(cs)
        return self._postflop(cs, gi)

    def _preflop(self, s):
        c, cost = self._chen, s.cost_to_call
        if c >= 11:
            if s.can_act(ActionRaise):
                lo, hi = s.raise_bounds
                return ActionRaise(min(hi, max(lo, int(4.0*BIG_BLIND)+s.opp_wager)))
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()
        if c >= 9:
            if cost <= 4*BIG_BLIND:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(3.0*BIG_BLIND)+s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()
        if c >= 7:
            if cost <= 2*BIG_BLIND: return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _bid(self, s):
        eq = mc_equity(s.my_hand, s.board, [], 40)
        u = 1.0 - abs(eq - 0.5) * 2
        bv = min(s.pot * 0.12 * u, s.my_chips * 0.06)
        return ActionBid(max(0, min(int(bv), s.my_chips)))

    def _postflop(self, s, gi):
        if gi.time_bank < 3.0:
            if s.cost_to_call == 0: return ActionCheck()
            if s.cost_to_call <= BIG_BLIND and s.can_act(ActionCall): return ActionCall()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        eq = mc_equity(s.my_hand, s.board, s.opp_revealed_cards, 50)
        pot, cost = s.pot, s.cost_to_call
        po = cost / (pot + cost) if cost > 0 else 0
        if eq >= 0.82: return self._vb(s, True)
        if eq >= 0.68: return self._vb(s, False)
        if eq >= 0.55:
            if cost == 0:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(pot*0.50))))
                return ActionCheck()
            if eq > po + 0.08: return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        if eq >= 0.40:
            if cost == 0: return ActionCheck()
            if eq > po + 0.05 and cost <= pot*0.25:
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        # No bluffs — just fold/check
        return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _vb(self, s, agg):
        pot, cost = s.pot, s.cost_to_call
        if cost > 0:
            if agg and s.can_act(ActionRaise):
                lo, hi = s.raise_bounds
                return ActionRaise(min(hi, max(lo, int(pot*0.90)+s.opp_wager)))
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()
        if s.can_act(ActionRaise):
            lo, hi = s.raise_bounds
            return ActionRaise(min(hi, max(lo, int(pot*(0.90 if agg else 0.65)))))
        return ActionCheck()

if __name__ == '__main__':
    run_bot(Player(), parse_args())
