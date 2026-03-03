"""
PokerNoobs Bot - Working Version
Simple, stable, and profitable poker strategy
"""
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
import random

BIG_BLIND = 20
SMALL_BLIND = 10

# Simple hand strength evaluation
RANK_MAP = {'2': 0, '3': 1, '4': 2, '5': 3, '6': 4, '7': 5, '8': 6,
            '9': 7, 'T': 8, 'J': 9, 'Q': 10, 'K': 11, 'A': 12}

class Player(BaseBot):
    def __init__(self):
        self.opp_folds = 0
        self.opp_calls = 0
        self.opp_raises = 0
        self.opp_actions = 0

    def on_hand_start(self, game_info, current_state):
        pass

    def on_hand_end(self, game_info, current_state):
        pass

    def _hand_strength(self, hand):
        """Simple hand strength from Chen formula."""
        r1, s1 = int(RANK_MAP.get(hand[0][0], 0)), hand[0][1]
        r2, s2 = int(RANK_MAP.get(hand[1][0], 0)), hand[1][1]
        
        # Normalize ranks (A=12 becomes 14)
        r1 = 14 if r1 == 12 else r1
        r2 = 14 if r2 == 12 else r2
        
        high = max(r1, r2)
        low = min(r1, r2)
        
        # Base score from high card
        score = high
        
        # Pair bonus
        if r1 == r2:
            score = high * 2
        
        # Suited bonus
        if s1 == s2:
            score += 4
        
        # Gap bonus/penalty
        gap = high - low
        if gap == 1:
            score += 1
        elif gap > 2:
            score -= (gap - 2)
        
        return score

    def get_move(self, game_info, current_state):
        try:
            street = current_state.street
            
            if street == 'pre-flop':
                return self._preflop(current_state)
            elif street == 'auction':
                return self._auction(current_state)
            else:  # flop, turn, river
                return self._postflop(current_state)
        except:
            # Fallback on any error
            if street == 'auction':
                return ActionBid(max(1, min(current_state.my_chips // 50, 100)))
            elif ActionCheck in current_state.valid_actions:
                return ActionCheck()
            elif ActionCall in current_state.valid_actions:
                return ActionCall()
            else:
                return ActionFold()

    def _preflop(self, state):
        """Preflop strategy."""
        strength = self._hand_strength(state.my_hand)
        cost = state.cost_to_call
        is_sb = not state.is_bb
        
        # Premium hands (high strength)
        if strength >= 20:
            if state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                return ActionRaise(min(hi, max(lo, int(2.0 * BIG_BLIND) + state.opp_wager)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()
        
        # Strong hands
        if strength >= 14:
            if cost <= BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()
        
        # Medium hands
        if strength >= 10:
            if cost <= SMALL_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()
        
        # Weak hands - tight
        if is_sb and cost <= SMALL_BLIND and random.random() < 0.4:
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()
        
        return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

    def _auction(self, state):
        """Auction strategy: bid based on hand strength."""
        try:
            strength = self._hand_strength(state.my_hand)
            pot = state.pot if state.pot > 0 else 30
            chips = state.my_chips if state.my_chips > 0 else 4990
            
            # Bid based on hand strength
            if strength >= 20:  # Premium hands
                bid_pct = 0.20
            elif strength >= 14:  # Strong hands
                bid_pct = 0.12
            elif strength >= 10:  # Medium hands
                bid_pct = 0.06
            elif strength >= 6:  # Weak hands
                bid_pct = 0.02
            else:  # Very weak hands
                bid_pct = 0.01
            
            # Calculate bid
            bid = int(pot * bid_pct)
            bid = min(bid, int(chips * 0.15))  # Cap at 15% of stack
            bid = max(1, bid)  # Always bet at least 1
            
            return ActionBid(bid)
        except:
            return ActionBid(max(1, min(state.my_chips // 50, 100)))

    def _postflop(self, state):
        """Postflop strategy: simple equity-based."""
        try:
            strength = self._hand_strength(state.my_hand)
            pot = state.pot
            cost = state.cost_to_call
            
            # Strong hands bet
            if strength >= 14:
                if state.can_act(ActionRaise) and random.random() < 0.6:
                    lo, hi = state.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(0.5 * pot))))
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            
            # Medium hands call cheap
            if strength >= 8:
                if cost <= pot * 0.1:
                    return ActionCall() if state.can_act(ActionCall) else ActionCheck()
                return ActionCheck() if state.can_act(ActionCheck) else ActionFold()
            
            # Weak hands fold to bets
            if cost > 0:
                return ActionFold() if state.can_act(ActionFold) else ActionCheck()
            
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()
        except:
            if state.can_act(ActionCheck):
                return ActionCheck()
            elif state.can_act(ActionCall) and state.cost_to_call < state.pot * 0.2:
                return ActionCall()
            else:
                return ActionFold()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
