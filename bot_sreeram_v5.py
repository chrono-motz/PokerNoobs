'''
Bot Sreeram v5 — Championship Refinement
Builds on v4's champion strategy with:
  - More aggressive auction bidding (higher equity % bid)
  - Better postflop aggression with draws
  - Improved river bluffing based on board texture
  - Tighter bankroll management for long-term edge
'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
from poker_utils import chen_score, mc_equity, RANK_MAP
import random

BIG_BLIND = 20
SMALL_BLIND = 10

class Player(BaseBot):
    """Ultra-precise bot using eval7 for equity calculations."""
    
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
        self._last_equity = 0.5

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        """Initialize hand variables."""
        self._chen = chen_score(current_state.my_hand[0], current_state.my_hand[1])
        self._po = BIG_BLIND if not current_state.is_bb else SMALL_BLIND
        self._ps = 'pre-flop'
        self._has_opponent_info = False
        self._last_equity = 0.5

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
    # Equity Calculation using poker_utils MC
    # ────────────────────────────────────────────────────────────────────────

    def _estimate_equity(self, my_hand, board, opp_known, rollouts=50):
        """Calculate equity using poker_utils Monte Carlo."""
        try:
            equity = mc_equity(my_hand, board, opp_known, rollouts)
            return min(1.0, max(0.0, equity))
        except:
            return 0.5

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

        # Premium hands
        if chen >= 10:
            if state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                return ActionRaise(min(hi, max(lo, int(4.0 * BIG_BLIND) + state.opp_wager)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Strong hands
        if chen >= 8:
            if cost <= 5 * BIG_BLIND:
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    return ActionRaise(min(hi, max(lo, int(2.5 * BIG_BLIND) + state.opp_wager)))
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Medium hands
        if chen >= 6:
            if cost <= 2 * BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # Lower medium
        if chen >= 4:
            if cost <= BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # Weak hands with position
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
    # AUCTION STRATEGY - MORE AGGRESSIVE THAN v4
    # ────────────────────────────────────────────────────────────────────────

    def _auction(self, state):
        """Aggressive auction bidding calibrated to equity strength."""
        # Use poker_utils for equity calculation
        opp_known = list(state.opp_revealed_cards[:1]) if state.opp_revealed_cards else []
        equity = self._estimate_equity(state.my_hand, state.board, opp_known, rollouts=60)
        
        # Store for postflop reference
        self._last_equity = equity
        
        # v5: More aggressive bidding than v4
        pot = state.pot
        if equity >= 0.78:
            bid = int(pot * 0.25)
        elif equity >= 0.68:
            bid = int(pot * 0.18)
        elif equity >= 0.58:
            bid = int(pot * 0.12)
        elif equity >= 0.48:
            bid = int(pot * 0.07)
        elif equity >= 0.38:
            bid = int(pot * 0.03)
        else:
            bid = max(1, int(pot * 0.01))
        
        return ActionBid(bid)

    # ────────────────────────────────────────────────────────────────────────
    # POST-FLOP STRATEGY - EVAL7 POWERED
    # ────────────────────────────────────────────────────────────────────────

    def _postflop(self, state, game_info):
        """Post-flop strategy: more aggressive value betting and draw play."""
        # Time management
        if game_info.time_bank < 2.0:
            if state.cost_to_call == 0:
                return ActionCheck()
            if state.cost_to_call <= BIG_BLIND and state.can_act(ActionCall):
                return ActionCall()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # Calculate precise equity
        opp_known = list(state.opp_revealed_cards) if state.opp_revealed_cards else []
        rollouts = 60 if state.street == 'flop' else 80
        equity = self._estimate_equity(state.my_hand, state.board, opp_known, rollouts=rollouts)

        pot = state.pot
        cost = state.cost_to_call

        # Information multiplier - exploit revealed cards more
        info_multiplier = 1.35 if self._has_opponent_info else 1.0

        # Pot odds
        po = cost / (pot + cost + 1e-6) if cost > 0 else 0

        # ─ PREMIUM EQUITY (85%+) ─
        if equity >= 0.85:
            return self._value_bet(state, aggressive=True, multiplier=info_multiplier)

        # ─ STRONG EQUITY (70%+) ─
        if equity >= 0.70:
            return self._value_bet(state, aggressive=True, multiplier=1.15)

        # ─ GOOD EQUITY (58%+) ─
        if equity >= 0.58:
            return self._value_bet(state, aggressive=False, multiplier=info_multiplier)

        # ─ MODERATE EQUITY (45%+) ─
        if equity >= 0.45:
            if cost == 0:
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    bet = int(pot * 0.40 * info_multiplier)
                    return ActionRaise(min(hi, max(lo, bet)))
                return ActionCheck()
            if equity > po + 0.05:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            if state.street == 'river' and equity > 0.45:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # ─ DRAW EQUITY (30-45%) ─
        if equity >= 0.30:
            if cost == 0:
                # More aggressive on turn/river with draws
                if state.street in ['turn', 'river']:
                    if random.random() < 0.35 and state.can_act(ActionRaise):
                        lo, hi = state.raise_bounds
                        return ActionRaise(min(hi, max(lo, int(pot * 0.40))))
                return ActionCheck()
            # Draws: call if pot odds support it
            if equity > po - 0.05:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # ─ BLUFF EQUITY (15-30%) ─
        if equity >= 0.15 and self._has_opponent_info and cost == 0:
            try:
                opp_rank = RANK_MAP.get(state.opp_revealed_cards[0][0], 0)
                # Bluff more aggressively on turn/river
                if opp_rank <= 7:
                    bluff_freq = 0.30 if state.street == 'river' else 0.15
                    if random.random() < bluff_freq and state.can_act(ActionRaise):
                        lo, hi = state.raise_bounds
                        bet = int(pot * 0.65)
                        return ActionRaise(min(hi, max(lo, bet)))
            except:
                pass
            return ActionCheck()

        # Default
        return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

    def _value_bet(self, state, aggressive=False, multiplier=1.0):
        """Value betting with multiplier."""
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
