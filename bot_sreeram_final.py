#!/usr/bin/env python3
"""
bot_sreeram_final.py - Tournament-Hardened Poker Bot

Philosophy:
- Prioritize safety (no illegal bids) over local optimization
- Use sound poker theory rather than local adaptation
- Conservative but disciplined approach that works against diverse opponents
- Avoid exploitable patterns that real players punish

Key Features:
1. GUARANTEED SAFE auction bidding
2. Principle-based preflop strategy (not overfitted)
3. Strong hand reading with Monte Carlo
4. Position-aware, stack-aware decisions
"""

import random
from collections import namedtuple
from pokerbots.engine.card import Card
from pkbot.actions import ActionCall, ActionRaise, ActionFold, ActionCheck, ActionBid

# Precomputed Chen Score - industry standard for hand strength
CHEN_PAIRS = {
    (0, 0): 16, (0, 1): 15, (0, 2): 13, (0, 3): 12, (0, 4): 11, (0, 5): 11,
    (0, 6): 10, (0, 7): 9, (0, 8): 8, (0, 9): 7, (0, 10): 6, (0, 11): 5, (0, 12): 4,
    (1, 1): 15, (1, 2): 13, (1, 3): 12, (1, 4): 10, (1, 5): 10, (1, 6): 9,
    (1, 7): 8, (1, 8): 7, (1, 9): 6, (1, 10): 5, (1, 11): 4, (1, 12): 3,
    (2, 2): 13, (2, 3): 11, (2, 4): 9, (2, 5): 9, (2, 6): 8, (2, 7): 7,
    (2, 8): 6, (2, 9): 5, (2, 10): 4, (2, 11): 3, (2, 12): 2,
    (3, 3): 12, (3, 4): 10, (3, 5): 9, (3, 6): 8, (3, 7): 7, (3, 8): 6,
    (3, 9): 5, (3, 10): 4, (3, 11): 3, (3, 12): 2,
    (4, 4): 11, (4, 5): 10, (4, 6): 9, (4, 7): 8, (4, 8): 7, (4, 9): 6,
    (4, 10): 5, (4, 11): 4, (4, 12): 3,
    (5, 5): 10, (5, 6): 9, (5, 7): 8, (5, 8): 7, (5, 9): 6, (5, 10): 5, (5, 11): 4,
    (6, 6): 9, (6, 7): 8, (6, 8): 7, (6, 9): 6, (6, 10): 5, (6, 11): 4,
    (7, 7): 8, (7, 8): 7, (7, 9): 6, (7, 10): 5, (7, 11): 4,
    (8, 8): 7, (8, 9): 6, (8, 10): 5, (8, 11): 4,
    (9, 9): 6, (9, 10): 5, (9, 11): 4,
    (10, 10): 5, (10, 11): 4,
    (11, 11): 4,
    (12, 12): 4,
}

def chen_score(card1, card2):
    """Calculate Chen score for hole cards (0-28 scale)."""
    r1, r2 = card1.rank, card2.rank
    original_r1, original_r2 = r1, r2
    
    if r1 > r2:
        r1, r2 = r2, r1
    
    base = CHEN_PAIRS.get((r1, r2), 0)
    if base == 0:
        base = max(r1, r2) + 2
    
    if r1 == r2:
        return base * 2
    
    gap = r2 - r1
    if gap == 1:
        base -= 1
    elif gap >= 2:
        base -= (gap - 1)
    
    if card1.suit == card2.suit:
        base += 2
    
    return max(0, min(28, base))

def monte_carlo_equity(hole_cards, community, num_rollouts=40):
    """Estimate equity vs random opponent with Monte Carlo simulation."""
    deck = [Card(r, s) for r in range(13) for s in range(4)]
    for card in hole_cards + community:
        try:
            deck.remove(card)
        except ValueError:
            pass
    
    if len(deck) < 2:
        return 0.5
    
    wins = 0
    for _ in range(num_rollouts):
        opp_hole = random.sample(deck, 2)
        our_hand = hole_cards + community
        opp_hand = opp_hole + community
        
        our_strength = calculate_hand_strength(our_hand)
        opp_strength = calculate_hand_strength(opp_hand)
        
        if our_strength > opp_strength:
            wins += 1
    
    return wins / num_rollouts if num_rollouts > 0 else 0.5

def calculate_hand_strength(cards):
    """Evaluate 5+ card poker hand strength."""
    if len(cards) < 5:
        return tuple(c.rank for c in sorted(cards, key=lambda x: x.rank, reverse=True))
    
    ranks = [c.rank for c in cards]
    suits = [c.suit for c in cards]
    
    rank_counts = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    
    has_pair = 2 in rank_counts.values()
    has_trips = 3 in rank_counts.values()
    has_quads = 4 in rank_counts.values()
    has_flush = any(suits.count(s) >= 5 for s in set(suits))
    has_straight = check_straight(sorted(set(ranks)))
    
    if has_quads:
        return (8, 0, 0, 0)
    elif has_trips and has_pair:
        return (7, 0, 0, 0)
    elif has_flush:
        return (6, max(ranks), 0, 0)
    elif has_straight:
        return (5, max(ranks), 0, 0)
    elif has_trips:
        return (4, 0, 0, 0)
    elif has_pair:
        return (2, max(ranks), 0, 0)
    else:
        return (1, max(ranks), 0, 0)

def check_straight(unique_ranks):
    """Check if cards contain a straight."""
    for i in range(len(unique_ranks) - 4):
        if unique_ranks[i+4] - unique_ranks[i] == 4:
            return True
    return False

class Bot:
    def __init__(self):
        self.bankroll = 0
    
    def handle_new_game(self, game_state):
        self.bankroll = game_state.bankroll
    
    def handle_game_complete(self, game_state):
        self.bankroll = game_state.bankroll
    
    def get_action(self, game_state, round_state, active):
        """Main decision logic."""
        legal_actions = round_state.legal_actions
        street = round_state.street
        
        if street == 0:  # Auction round
            return self._auction_action(legal_actions, game_state, round_state)
        elif street == 1:  # Preflop
            return self._preflop_action(legal_actions, game_state, round_state)
        else:  # Postflop (streets 2-4)
            return self._postflop_action(legal_actions, game_state, round_state, street)
    
    def _auction_action(self, legal_actions, game_state, round_state):
        """Auction bidding (GUARANTEED SAFE)."""
        # Determine our hand
        is_button = game_state.button_status
        if is_button:
            our_hand = game_state.button_hand
            our_chips = game_state.stacks[0]
        else:
            our_hand = round_state.hands[0]
            our_chips = game_state.stacks[1]
        
        if not our_hand or len(our_hand) != 2:
            # No hand, bid 0
            bid_actions = [a for a in legal_actions if type(a).__name__ == 'ActionBid']
            if bid_actions:
                return next((a for a in bid_actions if a.amount == 0), bid_actions[0])
            return legal_actions[0]
        
        # Calculate hand strength (Chen score)
        equity = chen_score(our_hand[0], our_hand[1]) / 28.0
        
        # Determine bid percentage based on equity
        # Conservative: 5-30% of pot
        bid_percentage = 0.05 + (equity * 0.25)  # 0.05 to 0.30
        pot = game_state.pot
        calculated_bid = int(pot * bid_percentage)
        
        # SAFETY CRITICAL: Hard cap at 15% of remaining chips
        # This is the most conservative limit to prevent any illegal bids
        max_safe_bid = max(1, int(our_chips * 0.15))
        
        # Final bid is minimum of calculated and safe maximum
        final_bid = min(calculated_bid, max_safe_bid)
        
        # Find all legal bid actions
        bid_actions = [a for a in legal_actions if type(a).__name__ == 'ActionBid']
        if not bid_actions:
            return legal_actions[0]
        
        # Get all available bid amounts
        legal_bids = [a.amount for a in bid_actions]
        
        # Find best bid: exact match or closest lower bid
        valid_bids = [b for b in legal_bids if b <= final_bid]
        if valid_bids:
            best_bid = max(valid_bids)
        else:
            best_bid = min(legal_bids)
        
        return next(a for a in bid_actions if a.amount == best_bid)
    
    def _preflop_action(self, legal_actions, game_state, round_state):
        """Preflop decisions based on position and hand strength."""
        is_button = game_state.button_status
        our_hand = game_state.button_hand if is_button else round_state.hands[0]
        
        if len(our_hand) != 2:
            return next((a for a in legal_actions if type(a).__name__ == 'ActionFold'), legal_actions[0])
        
        chen = chen_score(our_hand[0], our_hand[1])
        
        # Stack depth modification
        our_chips = game_state.stacks[0] if is_button else game_state.stacks[1]
        if our_chips < 2500:  # Short stack
            chen -= 3
        elif our_chips > 7500:  # Deep stack
            chen += 1
        
        # Determine situation: what are we facing?
        has_raise = any(type(a).__name__ == 'ActionRaise' for a in legal_actions)
        has_call = any(type(a).__name__ == 'ActionCall' for a in legal_actions)
        
        if has_call and has_raise:
            # Someone already bet/raised
            if chen >= 8:  # Premium hand
                if has_raise:
                    return next((a for a in legal_actions if type(a).__name__ == 'ActionRaise'),
                               next((a for a in legal_actions if type(a).__name__ == 'ActionCall'),
                                    next(a for a in legal_actions if type(a).__name__ == 'ActionFold')))
                else:
                    return next((a for a in legal_actions if type(a).__name__ == 'ActionCall'),
                               next(a for a in legal_actions if type(a).__name__ == 'ActionFold'))
            elif chen >= 5:  # Decent hand
                return next((a for a in legal_actions if type(a).__name__ == 'ActionCall'),
                           next(a for a in legal_actions if type(a).__name__ == 'ActionFold'))
            else:  # Weak hand
                return next(a for a in legal_actions if type(a).__name__ == 'ActionFold')
        else:
            # No bet yet, we can check or raise
            if chen >= 9:  # Very strong
                if has_raise:
                    return next((a for a in legal_actions if type(a).__name__ == 'ActionRaise'),
                               next(a for a in legal_actions if type(a).__name__ == 'ActionCheck'))
                else:
                    return next(a for a in legal_actions if type(a).__name__ == 'ActionCheck')
            elif chen >= 6:  # Strong
                if random.random() < 0.35:
                    if has_raise:
                        return next((a for a in legal_actions if type(a).__name__ == 'ActionRaise'),
                                   next(a for a in legal_actions if type(a).__name__ == 'ActionCheck'))
                    else:
                        return next(a for a in legal_actions if type(a).__name__ == 'ActionCheck')
                else:
                    return next(a for a in legal_actions if type(a).__name__ == 'ActionCheck')
            else:  # Weak
                return next(a for a in legal_actions if type(a).__name__ == 'ActionCheck')
    
    def _postflop_action(self, legal_actions, game_state, round_state, street):
        """Postflop play (flop, turn, river)."""
        is_button = game_state.button_status
        our_hand = game_state.button_hand if is_button else round_state.hands[0]
        community = round_state.community
        
        if len(our_hand) < 2 or len(community) < 3:
            return next((a for a in legal_actions if type(a).__name__ == 'ActionCheck'),
                       next(a for a in legal_actions if type(a).__name__ == 'ActionFold'))
        
        # Calculate equity
        num_rollouts = 35 if street == 2 else 50
        equity = monte_carlo_equity(our_hand, community, num_rollouts)
        
        # Determine what we're facing
        has_call = any(type(a).__name__ == 'ActionCall' for a in legal_actions)
        has_raise = any(type(a).__name__ == 'ActionRaise' for a in legal_actions)
        has_check = any(type(a).__name__ == 'ActionCheck' for a in legal_actions)
        
        pot = game_state.pot
        
        if has_call and not has_check:
            # Someone bet at us (can call or raise/fold)
            call_action = next(a for a in legal_actions if type(a).__name__ == 'ActionCall')
            # Estimate bet amount - not directly available, use pot heuristic
            bet_amount = pot // 2  # Conservative estimate
            pot_odds = bet_amount / (pot + bet_amount) if (pot + bet_amount) > 0 else 0.5
            
            # Only call/raise if our equity clearly beats pot odds
            min_equity = pot_odds + 0.08  # 8% safety margin
            
            if equity > min_equity + 0.15:  # Strong hand
                if has_raise:
                    return next((a for a in legal_actions if type(a).__name__ == 'ActionRaise'),
                               next((a for a in legal_actions if type(a).__name__ == 'ActionCall'),
                                    next(a for a in legal_actions if type(a).__name__ == 'ActionFold')))
                else:
                    return next((a for a in legal_actions if type(a).__name__ == 'ActionCall'),
                               next(a for a in legal_actions if type(a).__name__ == 'ActionFold'))
            elif equity > min_equity:  # Marginally profitable
                return next((a for a in legal_actions if type(a).__name__ == 'ActionCall'),
                           next(a for a in legal_actions if type(a).__name__ == 'ActionFold'))
            else:  # Unprofitable
                return next(a for a in legal_actions if type(a).__name__ == 'ActionFold')
        else:
            # No bet yet, check or bet
            if equity > 0.70:  # Very strong
                if has_raise:
                    return next((a for a in legal_actions if type(a).__name__ == 'ActionRaise'),
                               next(a for a in legal_actions if type(a).__name__ == 'ActionCheck'))
                else:
                    return next(a for a in legal_actions if type(a).__name__ == 'ActionCheck')
            elif equity > 0.60:  # Strong
                if random.random() < 0.3:
                    if has_raise:
                        return next((a for a in legal_actions if type(a).__name__ == 'ActionRaise'),
                                   next(a for a in legal_actions if type(a).__name__ == 'ActionCheck'))
                    else:
                        return next(a for a in legal_actions if type(a).__name__ == 'ActionCheck')
                else:
                    return next(a for a in legal_actions if type(a).__name__ == 'ActionCheck')
            else:  # Marginal/weak
                return next(a for a in legal_actions if type(a).__name__ == 'ActionCheck')


bot = Bot()
