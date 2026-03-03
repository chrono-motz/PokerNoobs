#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sreeramma/Documents/PokerBots/PokerNoobs')

from bot_sreeram_sub3 import Player
from pkbot.states import GameState, PokerState, GameInfo

# Simulate Round #9 from the logs
# Flop [9c Qd 4c], both players have 20 in pot
# Both players have been in blinds: SB=10, BB=20
# Poker_Noobs has [7c, 6h], in big blind position

# Create a minimal game state for auction
test_state = GameState(
    dealer=1,  # Poker_Noobs (active player needs to bid)
    street=3,  # flop
    auction=True,
    bids=[None, None],  # no one has bid yet
    wagers=[10, 20],  # SB=10, BB=20
    chips=[4990, 4980],  # both have 5000 - their blinds
    hands=[['7c', '6h'], ['9c', 'Qd']],  # Poker_Noobs hand vs opponent
    opp_hands=[['9c', 'Qd'], ['7c', '6h']],  # Revealed to opponent
    community_cards=['9c', 'Qd', '4c'],  # Flop
    parent_state=None
)

# Create Poker State for Poker_Noobs (player 0, the big blind)
game_info = GameInfo(bankroll=-140, time_bank=30.0, round_num=9)
poker_state = PokerState(test_state, 1)  # Player 1 is the one acting (dealer=1)

print(f"GameState preparation:")
print(f"  Dealer index: {test_state.dealer}")
print(f"  My hand (player 1): {poker_state.my_hand}")
print(f"  Opponent hand: (hidden)")
print(f"  Board: {poker_state.board}")
print(f"  My chips: {poker_state.my_chips}")
print(f"  My wager: {poker_state.my_wager}")
print(f"  Opp wager: {poker_state.opp_wager}")
print(f"  Pot: {poker_state.pot}")
print(f"  Street: {poker_state.street}")

player = Player()
player.on_hand_start(game_info, poker_state)

try:
    action = player.get_move(game_info, poker_state)
    print(f"\n🎯 Bot action: {action}")
    if hasattr(action, 'amount'):
        print(f"   Bid amount: {action.amount}")
    else:
        print(f"   Action type: {type(action)}")
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
