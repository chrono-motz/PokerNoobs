#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sreeramma/Documents/PokerBots/PokerNoobs')

from bot_sreeram_sub3 import Player
from pkbot.states import PokerState, GameState, GameInfo
from pkbot.actions import ActionCall, ActionBid

# Create a test game state for Round #7 auction
# Poker_Noobs has [7h 5h], Flop is [4s 8d 7s]

test_game_state = GameState(
    dealer=1,  # Poker_Noobs is button
    street=3,  # flop
    auction=True,  # IN AUCTION
    bids=[None, None],  # both need to bid
    wagers=[20, 20],  # both have 20 in pot (SB=10, BB=20, no pre-flop raises assumed)
    chips=[4980, 4980],  # both have plenty of chips
    hands=[['7h', '5h'], ['Ac', 'Jc']],  # Poker_Noobs vs Quant_paglus
    opp_hands=[['Ac', 'Jc'], ['7h', '5h']],
    community_cards=['4s', '8d', '7s'],
    parent_state=None
)

# Create PokerState wrapper (player 0 is Poker_Noobs)
game_info = GameInfo(bankroll=0, time_bank=100, round_num=7)
poker_state = PokerState(test_game_state, 0)

print(f"Test Auction State:")
print(f"  My hand: {poker_state.my_hand}")
print(f"  Board: {poker_state.board}")
print(f"  My chips: {poker_state.my_chips}")
print(f"  Pot: {poker_state.pot}")
print(f"  Street: {poker_state.street}")

player = Player()
player.on_hand_start(game_info, poker_state)

try:
    action = player.get_move(game_info, poker_state)
    print(f"\nBot action: {action}")
    if hasattr(action, 'amount'):
         print(f"  Bid amount: {action.amount}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
