#!/usr/bin/env python3
import sys
sys.path.insert(0, '/Users/sreeramma/Documents/PokerBots/PokerNoobs')

from poker_utils import mc_equity

# Test mc_equity with parameters from Round #7
my_hand = ['7h', '5h']
board = ['4s', '8d', '7s']
opp_known = []
rollouts = 40

print(f"Testing mc_equity:")
print(f"  Hand: {my_hand}")
print(f"  Board: {board}")
print(f"  Opp known: {opp_known}")
print(f"  Rollouts: {rollouts}")

try:
    equity = mc_equity(my_hand, board, opp_known, rollouts)
    print(f"\nResult: equity = {equity:.4f}")
    
    # Now test the bidding logic
    pot = 30  # SB=10 + BB=20
    if equity >= 0.75:
        bid_pct = 0.20
    elif equity >= 0.65:
        bid_pct = 0.15
    elif equity >= 0.55:
        bid_pct = 0.10
    elif equity >= 0.45:
        bid_pct = 0.06
    elif equity >= 0.35:
        bid_pct = 0.03
    else:
        bid_pct = 0.01
    
    bid = int(pot * bid_pct)
    chips = 4980
    bid = min(bid, int(chips * 0.15))
    final_bid = max(1, bid)
    
    print(f"\nBidding calculation:")
    print(f"  Pot: {pot}")
    print(f"  Bid %: {bid_pct}")
    print(f"  Raw bid: {bid}")
    print(f"  Final bid: {final_bid}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
