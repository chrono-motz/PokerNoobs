#!/usr/bin/env python3
"""
SIMPLE TEST: Determine if bot can bid > 0 with minimal code
"""
from pkbot.actions import ActionBid

# Test 1: Direct ActionBid
bid1 = ActionBid(5)
print(f"ActionBid(5).amount = {bid1.amount}")

# Test 2: Dynamic amount
amount = 10
bid2 = ActionBid(amount)
print(f"ActionBid({amount}).amount = {bid2.amount}")

# Test 3: max() function
bid_result = max(1, int(30 * 0.02))
bid3 = ActionBid(bid_result)
print(f"ActionBid(max(1, int(30*0.02))).amount = {bid3.amount}")

# Test 4: The way the server might serialize this
import sys
code = 'A' + str(bid3.amount)
print(f"Socket message: {code}")
amount_from_socket = int(code[1:])
print(f"Parsed amount: {amount_from_socket}")
