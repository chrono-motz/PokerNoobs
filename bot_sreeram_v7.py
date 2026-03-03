#!/usr/bin/env python3
"""
bot_sreeram_v7.py - Balanced Poker Bot
Combines safety from v6 with measured aggression.

Key Features:
1. SAFE auction bidding - never exceeds available chips
2. BALANCED preflop - more aggressive than v6, safer than advanced
3. Smart aggression - position-aware, stack-aware
4. Pot odds discipline - only calls with positive EV
"""

import random
from collections import namedtuple
from pokerbots.engine.card import Card

# Precomputed Chen Score data
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

def estimate_equity_rollout(hole_cards, community, num_rollouts=50):
    """Monte Carlo equity estimation."""
    deck = [Card(r, s) for r in range(13) for s in range(4)]
    for card in hole_cards + community:
        deck.remove(card)
    
    wins = 0
    for _ in range(num_rollouts):
        sample = random.sample(deck, 2)
        our_best = best_poker_hand(hole_cards + community + sample)
        opp_best = best_poker_hand(sample + community + sample)
        if our_best > opp_best:
            wins += 1
    
    return wins / num_rollouts if num_rollouts > 0 else 0.5

def best_poker_hand(cards):
    """Simple hand strength evaluator."""
    if len(cards) < 5:
        return (0, max(c.rank for c in cards))
    
    high_card = max(c.rank for c in cards)
    pair = sum(1 for c in cards if sum(1 for other in cards if other.rank == c.rank) >= 2)
    flush = max((sum(1 for c in cards if c.suit == s) for s in range(4)), default=0)
    straight = 1 if has_straight(cards) else 0
    
    return (straight, flush, pair, high_card)

def has_straight(cards):
    """Check if cards contain a straight."""
    ranks = sorted(set(c.rank for c in cards))
    for i in range(len(ranks) - 4):
        if ranks[i+4] - ranks[i] == 4:
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
        
        pot = game_state.pot
        active_player = game_state.button
        button_state = game_state.button_status
        
        if street == 0:  # Auctions
            return self._handle_auction(legal_actions, game_state, round_state)
        elif street == 1:  # Preflop
            return self._handle_preflop(legal_actions, game_state, round_state)
        else:  # Postflop (streets 2-4)
            return self._handle_postflop(legal_actions, game_state, round_state)
    
    def _handle_auction(self, legal_actions, game_state, round_state):
        """Safe auction bidding."""
        our_hand = game_state.button_hand if game_state.button_status else round_state.hands[0]
        chips = game_state.stacks[0] if game_state.button_status else game_state.stacks[1]
        pot = game_state.pot
        
        # Calculate equity using Chen score
        if len(our_hand) == 2:
            equity = chen_score(our_hand[0], our_hand[1]) / 28.0
        else:
            equity = 0.5
        
        # Determine bid amount
        bid_pct = min(0.35, 0.10 + equity * 0.25)  # 10-35% based on equity
        pot_bid = int(pot * bid_pct)
        
        # SAFETY: Never exceed 25% of remaining chips (v7 vs v6's 20%)
        max_safe_bid = max(1, int(chips * 0.25))
        final_bid = min(pot_bid, max_safe_bid)
        
        # Find closest legal bid
        for action in legal_actions:
            if action.amount == final_bid:
                return action
        
        # Fallback to closest legal bid
        bids = [a.amount for a in legal_actions if a.amount > 0]
        if bids:
            closest = min(bids, key=lambda x: abs(x - final_bid))
            return next(a for a in legal_actions if a.amount == closest)
        
        # No legal bid, fold
        return next(a for a in legal_actions if a.is_fold)
    
    def _handle_preflop(self, legal_actions, game_state, round_state):
        """Preflop decision."""
        our_hand = game_state.button_hand if game_state.button_status else round_state.hands[0]
        chen = chen_score(our_hand[0], our_hand[1])
        
        # Stack depth adjustment (v7: more aggressive than v6)
        us_stack = game_state.stacks[0] if game_state.button_status else game_state.stacks[1]
        if us_stack < 2500:  # Short stack
            chen -= 2
        elif us_stack > 7500:  # Deep stack
            chen += 1
        
        # Check what actions are available and what we're facing
        facing_bet = False
        for action in legal_actions:
            if action.is_call and not action.is_check:
                facing_bet = True
                break
        
        # v7: Balanced aggression
        if facing_bet:
            # Facing a bet - be moderately aggressive
            if chen >= 9:  # Strong hand
                return next((a for a in legal_actions if a.is_raise), 
                           next((a for a in legal_actions if a.is_call), 
                                next(a for a in legal_actions if a.is_fold)))
            elif chen >= 6:  # Medium hand - call more, raise less
                if random.random() < 0.3:
                    return next((a for a in legal_actions if a.is_raise),
                               next((a for a in legal_actions if a.is_call),
                                    next(a for a in legal_actions if a.is_fold)))
                else:
                    return next((a for a in legal_actions if a.is_call),
                               next((a for a in legal_actions if a.is_fold)))
            else:
                return next(a for a in legal_actions if a.is_fold)
        else:
            # No bet faced - check/raise decision
            if chen >= 8:
                return next((a for a in legal_actions if a.is_raise),
                           next(a for a in legal_actions if a.is_check))
            elif chen >= 5:
                if random.random() < 0.4:
                    return next((a for a in legal_actions if a.is_raise),
                               next(a for a in legal_actions if a.is_check))
                else:
                    return next(a for a in legal_actions if a.is_check)
            else:
                return next(a for a in legal_actions if a.is_check)
    
    def _handle_postflop(self, legal_actions, game_state, round_state):
        """Postflop (flop, turn, river) play."""
        our_hand = game_state.button_hand if game_state.button_status else round_state.hands[0]
        community = round_state.community
        
        street = round_state.street
        rollouts = 40 if street == 2 else 50  # Fewer rollouts on flop
        
        equity = estimate_equity_rollout(our_hand, community, rollouts)
        
        # Check what we're facing
        facing_bet = False
        bet_amount = 0
        for action in legal_actions:
            if action.is_call and not action.is_check:
                facing_bet = True
                bet_amount = action.amount
                break
        
        pot = game_state.pot
        
        if facing_bet:
            pot_odds = bet_amount / (pot + bet_amount)
            min_equity = pot_odds + 0.05  # 5% safety margin
            
            if equity > min_equity + 0.15:  # Strong equity
                return next((a for a in legal_actions if a.is_raise),
                           next((a for a in legal_actions if a.is_call),
                                next(a for a in legal_actions if a.is_fold)))
            elif equity > min_equity:  # Adequate equity
                return next((a for a in legal_actions if a.is_call),
                           next(a for a in legal_actions if a.is_fold))
            else:
                return next(a for a in legal_actions if a.is_fold)
        else:
            # No bet faced - check/bet decision
            if equity > 0.65:
                bet_amt = int(pot * 0.65)
                for action in legal_actions:
                    if action.is_raise and action.amount >= bet_amt:
                        return action
                return next((a for a in legal_actions if a.is_raise),
                           next(a for a in legal_actions if a.is_check))
            elif equity > 0.55:
                if random.random() < 0.4:
                    return next((a for a in legal_actions if a.is_raise),
                               next(a for a in legal_actions if a.is_check))
                else:
                    return next(a for a in legal_actions if a.is_check)
            else:
                return next(a for a in legal_actions if a.is_check)


bot = Bot()
