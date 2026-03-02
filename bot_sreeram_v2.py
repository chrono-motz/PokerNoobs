'''
Bot Sreeram v2 — Major Improvements
Fixed critical bugs from submission:
  - Auction bidding: Now bids aggressively (5-25% of pot)
  - Preflop: MUCH wider ranges (Chen >= 2 from position)
  - Post-flop: More aggressive value betting and bluffing
  - Error handling: Fallback strategies if MC equity fails
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
    Enhanced poker bot with aggressive auction bidding and wider preflop ranges.
    """
    def __init__(self):
        # Opponent action tracking
        self.opp_folds = 0
        self.opp_raises = 0
        self.opp_calls = 0
        self.opp_actions = 0
        
        # Hand-specific tracking
        self._chen = 0.0

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        """Initialize hand variables."""
        self._chen = chen_score(current_state.my_hand[0], current_state.my_hand[1])

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        """Learn from hand results."""
        pass

    @property
    def fold_rate(self):
        """Opponent's fold rate."""
        if self.opp_actions < 10:
            return 0.35
        return self.opp_folds / max(1, self.opp_actions)

    def get_move(self, game_info: GameInfo, current_state: PokerState):
        """Core decision logic."""
        street = current_state.street

        if street == 'pre-flop':
            return self._preflop(current_state)
        elif street == 'auction':
            return self._auction(current_state)
        else:
            return self._postflop(current_state, game_info)

    # ────────────────────────────────────────────────────────────────────────
    # PREFLOP STRATEGY - MUCH WIDER
    # ────────────────────────────────────────────────────────────────────────

    def _preflop(self, state):
        """Preflop: aggressive wide ranges with position awareness."""
        chen = self._chen
        cost = state.cost_to_call
        is_sb = not state.is_bb

        # Premium hands (10+): Always raise
        if chen >= 10:
            if state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                return ActionRaise(min(hi, max(lo, int(4.0 * BIG_BLIND) + state.opp_wager)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Strong hands (7-10): Raise most positions
        if chen >= 7:
            if state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                return ActionRaise(min(hi, max(lo, int(3.0 * BIG_BLIND) + state.opp_wager)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Good hands (5-7): Call wider
        if chen >= 5:
            if cost <= 4 * BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # Medium hands (3-5): Position-dependent play
        if chen >= 3:
            if is_sb:
                # SB: steal wide
                if cost <= BIG_BLIND:
                    if state.can_act(ActionRaise) and random.random() < 0.55:
                        lo, hi = state.raise_bounds
                        return ActionRaise(min(hi, max(lo, int(2.5 * BIG_BLIND))))
                    return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            else:
                # BB: defend very wide
                if cost <= 2 * BIG_BLIND:
                    return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # Weak hands (2-3): Play from position
        if chen >= 2:
            if not is_sb and cost <= BIG_BLIND:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
        
        return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

    # ────────────────────────────────────────────────────────────────────────
    # AUCTION STRATEGY - AGGRESSIVE BIDDING
    # ────────────────────────────────────────────────────────────────────────

    def _auction(self, state):
        """Aggressive auction bidding - critical to not bid 0."""
        pot = state.pot
        my_chips = state.my_chips
        
        try:
            # MC equity evaluation on the flop
            board = list(state.board) if state.board else []
            equity = mc_equity(state.my_hand, board, [], 40)
        except Exception:
            # Fallback: use Chen score as equity proxy
            equity = min(0.85, self._chen / 20.0)
        
        # Uncertainty metric
        uncertainty = 1.0 - abs(equity - 0.5) * 2
        
        # Aggressive bidding - ALWAYS bid something meaningful
        if equity >= 0.80:
            # Strong hand: bid 20-25% of pot
            bid_pct = 0.24
        elif equity >= 0.70:
            # Very good hand: bid 18% of pot
            bid_pct = 0.18
        elif equity >= 0.60:
            # Good hand: bid 15% of pot
            bid_pct = 0.15
        elif equity >= 0.50:
            # Slight edge: bid 12% of pot
            bid_pct = 0.12
        elif equity >= 0.40:
            # Marginal: bid 10% of pot
            bid_pct = 0.10
        else:
            # Weak: still bid 7% (don't give away auctions)
            bid_pct = 0.07
        
        # Uncertainty boost for marginal hands
        if 0.35 < equity < 0.65:
            bid_pct *= (1.0 + uncertainty * 0.4)
        
        bid = int(pot * bid_pct)
        
        # Cap at 15% of chips
        bid = min(bid, int(my_chips * 0.15))
        
        # CRITICAL: Always bid at least 3
        bid = max(3, bid)
        
        return ActionBid(bid)

    # ────────────────────────────────────────────────────────────────────────
    # POST-FLOP STRATEGY - AGGRESSIVE VALUE BETTING
    # ────────────────────────────────────────────────────────────────────────

    def _postflop(self, state, game_info):
        """Post-flop: aggressive equity-based play."""
        # Time check
        if game_info.time_bank < 2.0:
            if state.cost_to_call == 0:
                return ActionCheck()
            if state.cost_to_call <= BIG_BLIND and state.can_act(ActionCall):
                return ActionCall()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # MC equity calculation with error handling
        rollouts = 35 if state.street == 'flop' else 45
        try:
            board = list(state.board) if state.board else []
            opp_cards = list(state.opp_revealed_cards) if state.opp_revealed_cards else []
            equity = mc_equity(state.my_hand, board, opp_cards, rollouts)
        except Exception:
            # Fallback: estimate from Chen score
            equity = min(0.90, self._chen / 18.0)

        pot = state.pot
        cost = state.cost_to_call
        po = cost / (pot + cost + 1e-6) if cost > 0 else 0

        # ─ VERY STRONG (77%+): Aggressive value betting ─
        if equity >= 0.77:
            return self._value_bet(state, aggressive=True, overbet=True)

        # ─ STRONG (60-77%): Strong value betting ─
        if equity >= 0.60:
            return self._value_bet(state, aggressive=True, overbet=False)

        # ─ MODERATE (45-60%): Betting draws ─
        if equity >= 0.45:
            if cost == 0:
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    bet = int(pot * 0.55)
                    return ActionRaise(min(hi, max(lo, bet)))
                return ActionCheck()
            if equity > po + 0.01:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

        # ─ BLUFF EQUITY (25-45%): Bluff when opponent folds often ─
        if equity >= 0.25:
            if cost == 0 and self.fold_rate > 0.25 and random.random() < 0.30:
                if state.can_act(ActionRaise):
                    lo, hi = state.raise_bounds
                    bet = int(pot * 0.55)
                    return ActionRaise(min(hi, max(lo, bet)))
            if cost == 0:
                return ActionCheck()
            # Call reasonable bets with bluff catchers
            if cost <= pot * 0.33 and random.random() < 0.35:
                return ActionCall() if state.can_act(ActionCall) else ActionCheck()
            return ActionFold() if state.can_act(ActionFold) else ActionCheck()

        # ─ WEAK (<25%): Rare bluffs only ─
        if cost == 0 and self.fold_rate > 0.40 and random.random() < 0.15:
            if state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                bet = int(pot * 0.60)
                return ActionRaise(min(hi, max(lo, bet)))
        
        return ActionCheck() if state.can_act(ActionCheck) else ActionFold()

    def _value_bet(self, state, aggressive=False, overbet=False):
        """Aggressive value betting."""
        pot = state.pot
        cost = state.cost_to_call

        if cost > 0:
            # Raise/call when facing opposition
            if aggressive and state.can_act(ActionRaise):
                lo, hi = state.raise_bounds
                bet = int(pot * 0.90) + state.opp_wager
                return ActionRaise(min(hi, max(lo, bet)))
            return ActionCall() if state.can_act(ActionCall) else ActionCheck()

        # Bet for value with strong sizing
        if state.can_act(ActionRaise):
            lo, hi = state.raise_bounds
            if overbet:
                bet_size = pot * 1.10  # Overbet premium hands
            elif aggressive:
                bet_size = pot * 0.90  # Bet big
            else:
                bet_size = pot * 0.70  # Bet medium
            return ActionRaise(min(hi, max(lo, int(bet_size))))
        
        return ActionCheck()


if __name__ == '__main__':
    run_bot(Player(), parse_args())
