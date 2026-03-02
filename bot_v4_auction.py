'''Bot v4 — Auction-Hunter: aggressive bids, exploit revealed cards.'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
from poker_utils import mc_equity, chen_score, RANK_MAP
import random

BIG_BLIND = 20

class Player(BaseBot):
    def __init__(self):
        self.opp_folds = self.opp_raises = self.opp_calls = self.opp_actions = 0
        self._chen = 0.0; self._po = 0; self._ps = None; self._info = False

    def on_hand_start(self, gi, cs):
        self._chen = chen_score(cs.my_hand[0], cs.my_hand[1])
        self._po = BIG_BLIND if not cs.is_bb else 10
        self._ps = 'pre-flop'; self._info = False

    def on_hand_end(self, gi, cs): pass

    @property
    def fold_rate(self):
        return self.opp_folds / max(1, self.opp_actions) if self.opp_actions >= 10 else 0.3

    def _track(self, s):
        if s.street != self._ps: self._po = 0; self._ps = s.street
        d = s.opp_wager - self._po
        if d > 0:
            if s.opp_wager > s.my_wager: self.opp_raises += 1
            else: self.opp_calls += 1
            self.opp_actions += 1
        self._po = s.opp_wager
        if len(s.opp_revealed_cards) > 0: self._info = True

    def get_move(self, gi, cs):
        self._track(cs)
        if cs.street == 'auction': return self._bid(cs)
        if cs.street == 'pre-flop': return self._preflop(cs)
        return self._postflop(cs, gi)

    def _preflop(self, s):
        c, cost = self._chen, s.cost_to_call
        if c >= 10:
            if s.can_act(ActionRaise):
                lo, hi = s.raise_bounds
                return ActionRaise(min(hi, max(lo, int(3.5*BIG_BLIND)+s.opp_wager)))
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()
        if c >= 8:
            if cost <= 5*BIG_BLIND:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5*BIG_BLIND)+s.opp_wager)))
                return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()
        if c >= 6:
            if cost <= 2*BIG_BLIND: return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        if c >= 4:
            if cost <= BIG_BLIND: return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _bid(self, s):
        eq = mc_equity(s.my_hand, s.board, [], 40)
        pot, chips = s.pot, s.my_chips
        u = 1.0 - abs(eq - 0.5) * 2
        bv = pot * 0.35 * u  # 3.5x baseline bid
        if eq > 0.70: bv = max(bv, pot * 0.15)
        bv = min(bv, chips * 0.18)
        return ActionBid(max(0, min(int(bv), chips)))

    def _postflop(self, s, gi):
        if gi.time_bank < 3.0:
            if s.cost_to_call == 0: return ActionCheck()
            if s.cost_to_call <= BIG_BLIND and s.can_act(ActionCall): return ActionCall()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        eq = mc_equity(s.my_hand, s.board, s.opp_revealed_cards, 50)
        pot, cost = s.pot, s.cost_to_call
        po = cost / (pot + cost) if cost > 0 else 0
        m = 1.25 if self._info else 1.0  # bigger bets with info

        if eq >= 0.80: return self._vb(s, True, m)
        if eq >= 0.63: return self._vb(s, False, m)
        if eq >= 0.50:
            if cost == 0:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(pot*0.45*m))))
                return ActionCheck()
            if eq > po + 0.05: return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        if eq >= 0.35:
            if cost == 0: return ActionCheck()
            if eq > po and cost <= pot*0.35: return ActionCall() if s.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if s.can_act(ActionCheck) else ActionFold()
        if eq >= 0.20 and self._info and cost == 0:
            opp_r = RANK_MAP.get(s.opp_revealed_cards[0][0], 0) if s.opp_revealed_cards else 0
            if opp_r <= 7 and random.random() < 0.20:
                if s.can_act(ActionRaise):
                    lo, hi = s.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(pot*0.55))))
            return ActionCheck()
        return ActionCheck() if s.can_act(ActionCheck) else ActionFold()

    def _vb(self, s, agg, m=1.0):
        pot, cost = s.pot, s.cost_to_call
        if cost > 0:
            if agg and s.can_act(ActionRaise):
                lo, hi = s.raise_bounds
                return ActionRaise(min(hi, max(lo, int(pot*0.70*m)+s.opp_wager)))
            return ActionCall() if s.can_act(ActionCall) else ActionCheck()
        if s.can_act(ActionRaise):
            lo, hi = s.raise_bounds
            f = (0.75 if agg else 0.55) * m
            return ActionRaise(min(hi, max(lo, int(pot*f))))
        return ActionCheck()

if __name__ == '__main__':
    run_bot(Player(), parse_args())
