'''
Bot Sreeram v5 — Ultra-Precision Edition
Uses eval7 for accurate equity calculations:
  - Auction: Smart bidding calibrated to true win rate potential
  - Preflop: Position-aware with Chen scoring
  - Postflop: eval7-powered equity decisions, not approximations
  - Information: Exploit revealed cards with precise equity
'''
from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot
from pkbot.runner import parse_args, run_bot
from equity import estimate_equity_monte_carlo
from poker_utils import chen_score, RANK_MAP
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
    # Equity Calculation using eval7
    # ────────────────────────────────────────────────────────────────────────

    def _estimate_equity(self, my_hand, board, opp_known, iterations=2000):
        """Calculate equity using eval7 for precision."""
        try:
            estimate = estimate_equity_monte_carlo(
                my_hole_cards=my_hand,
                community_cards=board if board else [],
                known_opp_cards=opp_known,
                iterations=iterations,
            )
            # Combine win rate with tie rate
            equity = estimate.win_rate + 0.5 * estimate.tie_rate
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
    # AUCTION STRATEGY - EVAL7 POWERED
    # ────────────────────────────────────────────────────────────────────────

    def _auction(self, state):
        """Smart auction bidding using eval7 equity."""
        # Use eval7 for more precise equity calculation
        opp_known = list(state.opp_revealed_cards[:1]) if state.opp_revealed_cards else []
        equity = self._estimate_equity(state.my_hand, state.board, opp_known, iterations=1500)
        
        # Store for postflop reference
        self._last_equity = equity
        
        # Smart bidding: bid more when equity significantly exceeds 0.5
        # Inspired by example_bot: target_fraction = max(0.0, min(0.35, equity - 0.45))
        target_fraction = max(0.0, min(0.30, equity - 0.45))
        bid = int(target_fraction * state.my_chips)
        
        # Minimum bid 1 chip
        return ActionBid(max(1, bid))

    # ────────────────────────────────────────────────────────────────────────
    # POST-FLOP STRATEGY - EVAL7 POWERED
    # ────────────────────────────────────────────────────────────────────────

    def _postflop(self, state, game_info):
        """Post-flop using eval7 equity with revealed cards."""
        # Time management
        if game_info.time_bank < 2.0:
            if state.cost_to_call == 0:
                return ActionCheck()
            if state.cost_to_call <= BIG_BLIND and state.can_act(ActionCall):
                return ActionCall()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # Calculate precise equity using eval7
        opp_known = list(state.opp_revealed_cards) if state.opp_revealed_cards else []
        iterations = 1500 if state.street == 'flop' else 2000
        equity = self._estimate_equity(state.my_hand, state.board, opp_known, iterations=iterations)

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

        # ─ BLUFF EQUITY (20-35%) ─
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
