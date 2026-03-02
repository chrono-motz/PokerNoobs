from pkbot.actions import ActionFold, ActionCall, ActionCheck, ActionRaise, ActionBid
from pkbot.states import GameInfo, PokerState
from pkbot.base import BaseBot

class Player(BaseBot):
    """
    IIT Pokerbots 2026 Sneak Peek Hold'em Bot
    """
    def __init__(self) -> None:
        """
        Called exactly once when a new game starts.
        Initialize persistent tracking variables here to maintain O(1) loop speed
        and stay well within the 20-second cumulative time limit.
        """
        self.hand_strength = 0
        
        # --- Auction Tracking Variables ---
        self.pot_pre_auction = 0
        self.auction_pot_increase = 0
        self.my_bid = 0
        
        # --- Opponent Profiling Dictionary ---
        # We will populate this to find patterns in their playstyle.
        self.opp_profile = {
            'High': [],
            'Low': []
        }

    def on_hand_start(self, game_info: GameInfo, current_state: PokerState) -> None:
        """
        Called at the start of each round. Resets round-specific variables.
        """
        self.hand_strength = self._calculate_chen_score(current_state.my_hand)
        
        self.pot_pre_auction = 0
        self.auction_pot_increase = 0
        self.my_bid = 0

    def get_move(self, game_info: GameInfo, current_state: PokerState):
        """
        Core decision engine. Must return an Action object within microseconds.
        """
        street = current_state.street
        cost_to_call = getattr(current_state, 'cost_to_call', 0)
        current_pot = getattr(current_state, 'pot', 0)

        # =====================================================================
        # 1. PRE-FLOP PHASE
        # =====================================================================
        if street == 'preflop':
            if self.hand_strength >= 10:
                # Raise premium hands to thin the field and lower the SPR
                raise_amount = current_pot + cost_to_call
                return ActionRaise(int(raise_amount))
            elif self.hand_strength >= 6:
                # Call small raises with decent hands
                if cost_to_call <= 40: 
                    return ActionCall()
            
            # Default to checking or folding weak hands
            return ActionCheck() if cost_to_call == 0 else ActionFold()

        # =====================================================================
        # 2. THE AUCTION PHASE
        # =====================================================================
        if street == 'auction':
            # Record the exact pot size before bids are submitted
            self.pot_pre_auction = current_pot
            
            # Decide bid based on how marginal/uncertain our hand is.
            # Hands with a Chen score of 8-12 often face tough post-flop decisions,
            # so information is highly valuable.
            if 8 <= self.hand_strength <= 12:
                # Bid 10% of the pot, but cap it so we don't bleed chips
                self.my_bid = max(2, self.pot_pre_auction // 10) 
            else:
                # If we have the absolute nuts or total trash, info doesn't change our play.
                self.my_bid = 2 
                
            return ActionBid(int(self.my_bid))

        # =====================================================================
        # 3. POST-FLOP PHASES (Flop, Turn, River)
        # =====================================================================
        if street == 'flop':
            # The first time we act on the flop AFTER the auction, calculate the dead money.
            if self.pot_pre_auction > 0 and self.auction_pot_increase == 0:
                self.auction_pot_increase = current_pot - self.pot_pre_auction

        # Basic Post-Flop Fallback Logic (To be upgraded with C++ evaluator later)
        if cost_to_call == 0:
            return ActionCheck()
        elif cost_to_call < 50 and self.hand_strength >= 8:
            return ActionCall()
        else:
            return ActionFold()

    def on_hand_end(self, game_info: GameInfo, current_state: PokerState) -> None:
        """
        Called when the round finishes. Profile the opponent's bidding 
        strategy against their actual showdown hands.
        """
        opp_bid = None
        
        # Mathematically deduce the opponent's exact bid based on second-price mechanics
        if self.my_bid > self.auction_pot_increase:
            # We won. The pot increased by exactly the opponent's lower bid.
            opp_bid = self.auction_pot_increase
            
        elif self.auction_pot_increase == (2 * self.my_bid) and self.my_bid > 0:
            # We tied. Both players paid their identical bids into the pot.
            opp_bid = self.my_bid
            
        # Note: If self.my_bid == self.auction_pot_increase, we lost the auction. 
        # The opponent paid OUR bid. We know their bid was higher, but we cannot 
        # know the exact amount. Thus, opp_bid remains None.

        opp_cards = getattr(current_state, 'opp_hand', None)
        
        # Only log data if we successfully deduced their bid AND saw their cards at showdown
        if opp_bid is not None and opp_cards is not None:
            
            # Dynamic Threshold: A bid is "High" if it's > 33% of the pre-auction pot,
            # with an absolute floor of 40 chips (2 Big Blinds).
            high_bid_threshold = max(self.pot_pre_auction // 3, 40)
            
            bid_category = "High" if opp_bid > high_bid_threshold else "Low"
            
            # Store the profile data for future exploitation
            self.opp_profile[bid_category].append({
                'cards': opp_cards,
                'board': getattr(current_state, 'board', []),
                'bid_amount': opp_bid,
                'pot_size': self.pot_pre_auction
            })

    # =========================================================================
    # Heuristics & Helpers
    # =========================================================================
    def _calculate_chen_score(self, cards):
        """
        Calculates a fast O(1) heuristic for pre-flop hand strength.
        Cards are represented as two-character strings (e.g., 'Ah', 'Kd').
        """
        if not cards or len(cards) < 2:
            return 0
            
        rank_values = {'A': 10, 'K': 8, 'Q': 7, 'J': 6, 'T': 5, '9': 4.5, 
                       '8': 4, '7': 3.5, '6': 3, '5': 2.5, '4': 2, '3': 1.5, '2': 1}
        
        c1_rank, c1_suit = cards[0][0], cards[0][1]
        c2_rank, c2_suit = cards[1][0], cards[1][1]
        
        v1 = rank_values.get(c1_rank, 0)
        v2 = rank_values.get(c2_rank, 0)
        
        score = max(v1, v2)
        
        # Pairs
        if c1_rank == c2_rank:
            score = max(5, score * 2)
            
        # Suited
        if c1_suit == c2_suit:
            score += 2
            
        # Gaps
        gap = abs(v1 - v2)
        if gap == 1: score -= 1
        elif gap == 2: score -= 2
        elif gap == 3: score -= 4
        elif gap >= 4: score -= 5
        
        return score