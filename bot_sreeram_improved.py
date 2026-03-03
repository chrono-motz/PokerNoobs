#!/usr/bin/env python3
"""
Improved poker bot with:
1. More aggressive auction bidding strategy
2. Position-aware preflop ranges
3. Pot odds aware postflop play
4. Faster, safer equity calculation (no timeouts)
"""

from pkbot.base import BaseBot
from pkbot.states import GameInfo, PokerState
from pkbot.actions import ActionBid, ActionRaise, ActionFold, ActionCall, ActionCheck
import random

class SreeramImprovedBot(BaseBot):
    """
    Improved bot with key enhancements:
    - Auction bidding: bid based on hand strength and pot odds
    - Aggressive hand selection
    - Postflop pot odds discipline
    - Fast hand evaluation (no mc_equity)
    """
    
    def __init__(self):
        super().__init__()
        self.hand_chen_scores = {}
        self._init_chen_scores()
    
    def _init_chen_scores(self):
        """Initialize Chen formula scores for all hands"""
        ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
        for i, r1 in enumerate(ranks):
            for r2 in enumerate(ranks):
                key = f"{r1}{r2}"
                self.hand_chen_scores[key] = self._calculate_chen(r1, r2)
    
    def _calculate_chen(self, r1, r2):
        """Chen formula for hand strength (0-28 scale)"""
        # Using simplified version based on hand strength  
        ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
        rank_vals = {r: (14-i) for i, r in enumerate(ranks)}
        
        v1, v2 = rank_vals[r1], rank_vals[r2]
        
        # High card points
        score = max(v1, v2) * 2
        
        # Gap penalty
        gap = abs(v1 - v2) - 1
        if gap > 0:
            score -= gap
        
        # Pair bonus
        if r1 == r2:
            score += 16
        
        # Suited bonus
        # (Assuming no suits for this exercise)
        
        return max(0, min(28, score // 2.5))
    
    def _hand_strength(self, my_cards):
        """Evaluate hand strength 0-28"""
        r1, r2 = my_cards[0][0], my_cards[1][0]
        
        # Simple hand strength without suit consideration
        ranks = {'A': 14, 'K': 13, 'Q': 12, 'J': 11, 'T': 10,
                 '9': 9, '8': 8, '7': 7, '6': 6, '5': 5, '4': 4, '3': 3, '2': 2}
        
        v1, v2 = ranks[r1], ranks[r2]
        high = max(v1, v2)
        low = min(v1, v2)
        
        # Base score
        score = 0
        
        if r1 == r2:  # Pair
            score = low + 16
        else:
            # High card value
            score = high
            
            # Connected is strong
            gap = high - low
            if gap == 1:
                score += 6  # Connected
            elif gap == 2:
                score += 4  # Gap 1
            elif gap == 3:
                score += 3  # Gap 2
            elif gap <= 5:
                score += 1  # Semi-connected
        
        return min(28, max(0, score))
    
    def _preflop_action(self, game: GameInfo, state: PokerState, strength: int):
        """Determine preflop action based on hand strength and position"""
        my_cards = state.my_cards
        my_chips = state.my_chips
        current_bet = state.current_bet
        blind_size = game.button_blind
        big_blind = blind_size * 2
        
        # Determine position (approximate)
        # Tighter early position, wider late position
        is_button = state.dealer == game.my_player
        is_big_blind = state.big_blind == game.my_player
        
        # Position multiplier (wider ranges on button/late position)
        pos_mult = 1.0
        if is_button or (state.dealer + 1) % 2 == game.my_player:
            pos_mult = 1.3  # Wider
        elif is_big_blind:
            pos_mult = 0.9
        else:
            pos_mult = 0.8  # Tighter early
        
        adjusted_strength = strength * pos_mult
        
        # Aggression thresholds
        if adjusted_strength >= 20:
            # Premium hand: raise
            if current_bet == 0:
                raise_to = max(blind_size * 3, my_chips // 10)
                return ActionRaise(min(raise_to, my_chips))
            else:
                # Reraise if strength is very high
                if strength >= 22:
                    return ActionRaise(min(current_bet * 2, my_chips))
                return ActionCall()
        
        elif adjusted_strength >= 14:
            # Good hand: call/raise based on position
            if current_bet == 0:
                raise_to = blind_size * 2.5 if pos_mult > 1 else blind_size * 2
                return ActionRaise(min(int(raise_to), my_chips))
            else:
                return ActionCall()
        
        elif adjusted_strength >= 10:
            # Marginal hand: call if cheap
            if current_bet <= blind_size * 1.5:
                return ActionCall()
            else:
                return ActionFold()
        
        else:
            # Weak hand: fold
            return ActionFold()
    
    def _auction_action(self, game: GameInfo, state: PokerState, strength: int):
        """
        Enhanced auction bidding:
        - Bid more with strong hands
        - Consider pot odds
        - More aggressive than conservative bot
        """
        my_chips = state.my_chips
        pot = state.pot_before_auction
        current_high_bid = state.auction_high_bid
        
        # Minimum and maximum bid
        min_bid = 1
        max_bid = min(my_chips, pot)
        
        if strength >= 20:
            # Premium hand: bid 25-30% of pot
            bid_amount = int(pot * 0.25)
        elif strength >= 16:
            # Good hand: bid 15-20% of pot
            bid_amount = int(pot * 0.17)
        elif strength >= 12:
            # Decent hand: bid 8-12% of pot
            bid_amount = int(pot * 0.10)
        elif strength >= 8:
            # Marginal: bid 3-5% of pot
            bid_amount = int(pot * 0.04)
        else:
            # Weak: minimum bid
            bid_amount = min_bid
        
        # Ensure valid bid
        bid_amount = max(min_bid, min(bid_amount, max_bid))
        
        # Never bid 0
        bid_amount = max(1, bid_amount)
        
        try:
            return ActionBid(bid_amount)
        except Exception:
            return ActionBid(max(1, min(my_chips // 50, 100)))
    
    def _postflop_action(self, game: GameInfo, state: PokerState, strength: int):
        """
        Postflop play with pot odds consideration
        """
        my_chips = state.my_chips
        current_bet = state.current_bet
        pot = state.pot
        my_bet = state.my_bet
        
        if current_bet == 0:
            # Check or bet
            if strength >= 16:
                # Strong: bet 50-70% pot
                bet_amount = int(pot * 0.6)
                return ActionRaise(min(bet_amount, my_chips))
            elif strength >= 10:
                # Decent: bet 30-40% pot
                bet_amount = int(pot * 0.35)
                return ActionRaise(min(bet_amount, my_chips))
            else:
                # Weak: check
                return ActionCheck()
        
        else:
            # Someone bet - decide whether to call/raise/fold
            # Pot odds: what % of pot to call?
            odds = current_bet / (pot + current_bet)
            min_equity_needed = odds
            
            # Estimate equity needed
            hand_equity = strength / 28.0  # Rough estimate
            
            if hand_equity > min_equity_needed * 1.5:
                # Good equity: raise
                if strength >= 18:
                    raise_amount = current_bet * 2
                    return ActionRaise(min(int(raise_amount), my_chips))
                else:
                    return ActionCall()
            
            elif hand_equity > min_equity_needed * 1.1:
                # Marginally good: call
                return ActionCall()
            
            elif hand_equity > min_equity_needed * 0.8:
                # Borderline: call if cheap
                if current_bet <= pot * 0.2:
                    return ActionCall()
                else:
                    return ActionFold()
            
            else:
                # Bad equity: fold
                return ActionFold()
    
    def step(self, game: GameInfo, state: PokerState) -> ActionBid | ActionRaise | ActionFold | ActionCall | ActionCheck:
        """Main decision logic"""
        
        try:
            # Evaluate hand strength
            strength = self._hand_strength(state.my_cards)
            
            # Street detection
            if state.street == 'PREFLOP':
                return self._preflop_action(game, state, int(strength))
            
            elif state.street == 'AUCTION':
                return self._auction_action(game, state, int(strength))
            
            elif state.street in ['FLOP', 'TURN', 'RIVER']:
                return self._postflop_action(game, state, int(strength))
            
            # Fallback
            return ActionCheck()
        
        except Exception as e:
            # Safety fallback
            try:
                if state.current_bet == 0:
                    return ActionCheck()
                else:
                    return ActionCall()
            except:
                return ActionFold()
