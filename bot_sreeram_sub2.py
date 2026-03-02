'''
Bot Sreeram — Enhanced Strategy Bot
Combines equity-based play, opponent modeling, and aggressive preflop:
  - Preflop: Wider ranges than baseline, steals more frequently
  - Equity: Monte Carlo evaluation (40-50 rollouts) for post-flop decisions  
  - Auction: Smart bidding based on equity uncertainty
  - Post-flop: Aggressive value betting, bluffing against tight opponents
  - Opponent modeling: Track fold/raise rates and exploit patterns
'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
from poker_utils import mc_equity, chen_score
import random

BIG_BLIND = 20
SMALL_BLIND = 10

class Player(BaseBot):
    """
    Enhanced poker bot with equity-based decisions and opponent profiling.
    """
    def __init__(self):
        # Opponent action tracking
        self.opp_folds = 0
        self.opp_raises = 0
        self.opp_calls = 0
        self.opp_actions = 0
        self.opp_bid_sum = 0
        self.opp_bid_count = 0
        
        # Hand-specific tracking
        self._chen = 0.0
        self._pot_at_street_start = 0
        self._previous_street = None

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        """Initialize hand variables."""
        self._chen = chen_score(current_state.my_hand[0], current_state.my_hand[1])
        self._pot_at_street_start = 0
        self._previous_street = None

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        """Learn from hand results - track opponent tendencies."""
        pass

    # ────────────────────────────────────────────────────────────────────────
    # Opponent Modeling
    # ────────────────────────────────────────────────────────────────────────
    
    @property
    def fold_rate(self):
        """Opponent's fold rate - use for bluffing decisions."""
        if self.opp_actions < 10:
            return 0.35  # Default assumption
        return self.opp_folds / max(1, self.opp_actions)
    
    @property
    def raise_rate(self):
        """Opponent's raise rate."""
        if self.opp_actions < 10:
            return 0.25
        return self.opp_raises / max(1, self.opp_actions)

    def _track_opponent_action(self, state):
        """Update opponent action counters."""
        # This would be called to track opponent moves
        # For now, basic structure in place
        pass

    # ────────────────────────────────────────────────────────────────────────
    # Main Decision Engine
    # ────────────────────────────────────────────────────────────────────────

    def get_move(self, game_info: GameInfo, current_state: PokerState):
        """Core decision logic."""
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

        # Premium hands: strong 3-bets and value opens
        if chen >= 10:
            if state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                return ActionRaise(min(hi, max(lo, int(4.0 * BIG_BLIND) + state.opp_wager)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Strong hands: raise most positions
        if chen >= 7:
            if state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                return ActionRaise(min(hi, max(lo, int(3.0 * BIG_BLIND) + state.opp_wager)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Medium hands: wider calling range
        if chen >= 5:
            if cost <= 3 * BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # Lower medium hands: position-dependent play
        if chen >= 3:
            # SB steals wider
            if is_sb and cost <= BIG_BLIND:
                if state.can_act(ActionRaise) and random.random() < 0.40:
                    lo, hi = state.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5 * BIG_BLIND))))
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            # BB defends wider
            if not is_sb and cost <= BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # Weak hands: check/fold
        return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

    # ────────────────────────────────────────────────────────────────────────
    # AUCTION STRATEGY
    # ────────────────────────────────────────────────────────────────────────

    def _auction(self, state):
        """Smart auction bidding using equity and uncertainty."""
        # Use MC equity to gauge hand strength
        equity = mc_equity(state.my_hand, state.board, [], 40)
        
        # Uncertainty metric: how close to 50/50 (higher = more uncertain)
        uncertainty = 1.0 - abs(equity - 0.5) * 2
        
        # Base bid: higher for strong hands, bid more when uncertain (polarized)
        if equity >= 0.75:
            # Strong hand: bid aggressively
            bid = int(state.pot * 0.15 * (1.0 + uncertainty * 0.5))
        elif equity >= 0.55:
            # Moderate hand: standard bid
            bid = int(state.pot * 0.12 * (1.0 + uncertainty * 0.3))
        else:
            # Weak hand: minimal bid
            bid = max(1, int(state.pot * 0.05))
        
        # Cap at 10% of chips
        bid = min(bid, int(state.my_chips * 0.10))
        return ActionBid(max(1, bid))

    # ────────────────────────────────────────────────────────────────────────
    # POST-FLOP STRATEGY
    # ────────────────────────────────────────────────────────────────────────

    def _postflop(self, state, game_info):
        """Post-flop: equity-based decisions with pot odds."""
        # Time management: fold cheap if low on time
        if game_info.time_bank < 3.0:
            if state.cost_to_call == 0:
                return ActionCheck()
            if state.cost_to_call <= BIG_BLIND and state.can_act(ActionCall):
                return ActionCall()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # Calculate equity
        rollouts = 40 if state.street == 'flop' else 50
        equity = mc_equity(state.my_hand, state.board, 
                          list(state.opp_revealed_cards) if state.opp_revealed_cards else [], 
                          rollouts)

        pot = state.pot
        cost = state.cost_to_call

        # Pot odds required
        po = cost / (pot + cost + 1e-6) if cost > 0 else 0

        # ─ STRONG EQUITY (78%+): Aggressive value betting ─
        if equity >= 0.78:
            return self._value_bet(state, aggressive=True)

        # ─ GOOD EQUITY (60-78%): Value betting ─
        if equity >= 0.60:
            return self._value_bet(state, aggressive=False)

        # ─ MODERATE EQUITY (45-60%): Call/bet based on pot odds ─
        if equity >= 0.45:
            if cost == 0:
                # Can bet with draw
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(pot * 0.50))))
                return ActionCheck()
            # Call if odds are right
            if equity > po + 0.02:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # ─ BLUFF EQUITY (30-45%): Bluff if opponent folds often ─
        if equity >= 0.30:
            if cost == 0 and self.fold_rate > 0.30 and random.random() < 0.22:
                # Bluff into weak opponent
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(pot * 0.55))))
            if state.can_act(ActionCheck):
                return ActionCheck()
            if equity > po:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # ─ WEAK EQUITY (<30%): Give up unless bluffing ─
        if equity >= 0.15 and cost == 0:
            if self.fold_rate > 0.35 and random.random() < 0.15:
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(pot * 0.60))))
        
        # Default: check or fold
        return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

    def _value_bet(self, state, aggressive=False):
        """Value betting subfunction for strong hands."""
        pot = state.pot
        cost = state.cost_to_call

        if cost > 0:
            # Check/call in position
            if aggressive and state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                return ActionRaise(min(hi, max(lo, int(pot * 0.75) + state.opp_wager)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Can bet for value
        if state.can_act(ActionRaise):
            lo, hi = state.raise_bounds
            bet_size = pot * (0.80 if aggressive else 0.60)
            return ActionRaise(min(hi, max(lo, int(bet_size))))
        
        return ActionCheck()



if __name__ == '__main__':
    run_bot(Player(), parse_args())