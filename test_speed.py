#!/usr/bin/env python3
import time
from equity import estimate_equity_monte_carlo

# Test speed of equity calculation
scenarios = [
    (['Ah', 'Kd'], ['2d', '3d', '4d'], ['7s'], 1500, 'Auction (1500)'),
    (['Ah', 'Kd'], ['2d', '3d', '4d'], ['7s'], 5000, 'Postflop (5000)'),
    (['Ah', 'Kd'], ['2d', '3d', '4d', '5d'], ['7s'], 2000, 'Turn (2000)'),
]

for my_hand, board, opp_known, iters, label in scenarios:
    start = time.time()
    result = estimate_equity_monte_carlo(my_hand, board, opp_known, iterations=iters)
    elapsed = time.time() - start
    equity = result.win_rate + 0.5 * result.tie_rate
    print(f'{label:20s} | Equity: {equity:.4f} | Time: {elapsed:.3f}s')
