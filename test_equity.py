from equity import estimate_equity_monte_carlo

# Test with hands from the game log
my_hand = ['Tc', '2c']  # from Round #2
board = ['2d', 'Ah', '7d']  # flop
opp_known = ['7s']  # revealed card

print('Testing v5 auction equity calc:')
print(f'My hand: {my_hand}')
print(f'Board: {board}')
print(f'Opponent known: {opp_known}')

try:
    result = estimate_equity_monte_carlo(my_hand, board, opp_known, iterations=500)
    combined_equity = result.win_rate + 0.5 * result.tie_rate
    target_fraction = max(0.0, min(0.30, combined_equity - 0.45))
    bid = int(target_fraction * 5000)
    print(f'\nEquity calculation result:')
    print(f'  Win rate: {result.win_rate:.4f}')
    print(f'  Tie rate: {result.tie_rate:.4f}')
    print(f'  Combined equity: {combined_equity:.4f}')
    print(f'  Target fraction: {target_fraction:.4f}')
    print(f'  Bid amount: {bid} chips')
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
