'''
Bot Sreeram v4 — Championship Edition
Fixed auction bidding to avoid overcommitting to weak hands:
  - Auction: Bid based on equity strength, not false uncertainty
  - Postflop: More aggressive with strong hands after auction
  - Information: Rank-based bluffing + revealed card exploitation
'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
from poker_utils import mc_equity, chen_score, RANK_MAP
import random

BIG_BLIND = 20
SMALL_BLIND = 10

class Player(BaseBot):
    """Championship poker bot with fixed auction strategy."""
    
    def __init__(self):
        # Opponent tracking
        self.opp_folds = 0
        self.opp_raises = 0
        self.opp_calls = 0
        self.opp_actions = 0
        
        # Hand state
        self._chen = 0.0
        self._po = 0
        self._ps = None
        self._has_opponent_info = False

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        """Initialize hand variables."""
        self._chen = chen_score(current_state.my_hand[0], current_state.my_hand[1])
        self._po = BIG_BLIND if not current_state.is_bb else SMALL_BLIND
        self._ps = 'pre-flop'
        self._has_opponent_info = False

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        """Learn from hand results."""
        pass

    # ────────────────────────────────────────────────────────────────────────
    # Opponent Modeling
    # ────────────────────────────────────────────────────────────────────────
    
    @property
    def fold_rate(self):
        """Opponent's fold rate."""
        if self.opp_actions < 10:
            return 0.35
        return self.opp_folds / max(1, self.opp_actions)
    
    @property
    def raise_rate(self):
        """Opponent's raise rate."""
        if self.opp_actions < 10:
            return 0.25
        return self.opp_raises / max(1, self.opp_actions)

    def _track_opponent(self, state):
        """Update opponent action counters."""
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

    # ────────────────────────────────────────────────────────────────────────
    # Main Decision Engine
    # ────────────────────────────────────────────────────────────────────────

    def get_move(self, game_info: GameInfo, current_state: PokerState):
        """Core decision logic."""
        self._track_opponent(current_state)
        street = current_state.street

        if street == 'pre-flop':
            return self._preflop(current_state)
        elif street == 'auction':
            return self._auction(current_state)
        else:  # flop, turn, river
            return self._postflop(current_state, game_info)

    # ────────────────────────────────────────────────────────────────────────
    # PREFLOP STRATEGY
    # ────────────────────────────────────────────────────────────────────────

    def _preflop(self, state):
        """Preflop: wide ranges with position awareness."""
        chen = self._chen
        cost = state.cost_to_call
        is_sb = not state.is_bb

        # Premium hands: strong 3-bets
        if chen >= 10:
            if state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                return ActionRaise(min(hi, max(lo, int(4.0 * BIG_BLIND) + state.opp_wager)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Strong hands: raise most positions
        if chen >= 8:
            if cost <= 5 * BIG_BLIND:
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5 * BIG_BLIND) + state.opp_wager)))
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Medium hands: wider calling
        if chen >= 6:
            if cost <= 2 * BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # Lower medium hands: position play
        if chen >= 4:
            if cost <= BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # Weak hands: tight
        if chen >= 2:
            if is_sb and cost <= BIG_BLIND:
                if state.can_act(ActionRaise) and random.random() < 0.50:
                    lo, hi = state.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5 * BIG_BLIND))))
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            if not is_sb and cost <= BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

    # ────────────────────────────────────────────────────────────────────────
    # AUCTION STRATEGY - FIXED (Bid more cautiously on weak hands)
    # ────────────────────────────────────────────────────────────────────────

    def _auction(self, state):
        """Smart auction bidding: bid based on equity strength."""
        try:
            equity = mc_equity(state.my_hand, list(state.board) if state.board else [], [], 40)
        except:
            equity = 0.5

        pot = state.pot
        chips = state.my_chips

        # KEY FIX: Bid based on equity STRENGTH, with caps to avoid overcommitting weak hands
        if equity >= 0.75:
            # Very strong: bid 20% of pot
            bid = int(pot * 0.20)
        elif equity >= 0.65:
            # Strong: bid 15% of pot
            bid = int(pot * 0.15)
        elif equity >= 0.55:
            # Moderate: bid 10% of pot
            bid = int(pot * 0.10)
        elif equity >= 0.45:
            # Marginal: bid 6% of pot (reduced from 0.35x uncertainty formula!)
            bid = int(pot * 0.06)
        elif equity >= 0.35:
            # Weak: bid minimum 3% of pot
            bid = int(pot * 0.03)
        else:
            # Very weak: minimal bid
            bid = int(pot * 0.01)

        # Reduce bid if low on chips
        bid = min(bid, int(chips * 0.15))
        
        return ActionBid(max(1, bid))

    # ────────────────────────────────────────────────────────────────────────
    # POST-FLOP STRATEGY
    # ────────────────────────────────────────────────────────────────────────

    def _postflop(self, state, game_info):
        """Post-flop: equity-based with conviction."""
        # Time management
        if game_info.time_bank < 2.0:
            if state.cost_to_call == 0:
                return ActionCheck()
            if state.cost_to_call <= BIG_BLIND and state.can_act(ActionCall):
                return ActionCall()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # Calculate equity
        rollouts = 35 if state.street == 'flop' else 45
        try:
            opp_revealed = list(state.opp_revealed_cards) if state.opp_revealed_cards else []
            equity = mc_equity(state.my_hand, list(state.board) if state.board else [], opp_revealed, rollouts)
        except:
            equity = 0.5

        pot = state.pot
        cost = state.cost_to_call

        # Information multiplier
        info_multiplier = 1.25 if self._has_opponent_info else 1.0

        # Pot odds
        po = cost / (pot + cost + 1e-6) if cost > 0 else 0

        # ─ STRONG EQUITY (80%+) ─
        if equity >= 0.80:
            return self._value_bet(state, aggressive=True, multiplier=info_multiplier)

        # ─ GOOD EQUITY (63%+) ─
        if equity >= 0.63:
            return self._value_bet(state, aggressive=False, multiplier=info_multiplier)

        # ─ MODERATE EQUITY (50%+) ─
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

        # ─ MARGINAL EQUITY (35-50%) ─
        if equity >= 0.35:
            if cost == 0:
                return ActionCheck()
            if equity > po and cost <= pot * 0.35:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # ─ BLUFF EQUITY (20-35%): Rank-based bluffing ─
        if equity >= 0.20 and self._has_opponent_info and cost == 0:
            try:
                opp_rank = RANK_MAP.get(state.opp_revealed_cards[0][0], 0)
                if opp_rank <= 7 and random.random() < 0.20:
                    if state.can_act(ActionRaise):
                        lo, hi = state.raise_bounds
                        bet = int(pot * 0.55)
                        return ActionRaise(min(hi, max(lo, bet)))
            except:
                pass
            return ActionCheck()

        # Default
        return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

    def _value_bet(self, state, aggressive=False, multiplier=1.0):
        """Value betting with conviction."""
        pot = state.pot
        cost = state.cost_to_call

        if cost > 0:
            # Aggressive when opposed
            if aggressive and state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                bet = int(pot * 0.70 * multiplier) + state.opp_wager
                return ActionRaise(min(hi, max(lo, bet)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Bet for value
        if state.can_act(ActionRaise):
            lo, hi = state.raise_bounds
            bet_size = (0.75 if aggressive else 0.55) * multiplier
            bet = int(pot * bet_size)
            return ActionRaise(min(hi, max(lo, bet)))

        return ActionCheck()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
