"""
Pure Python eval7 shim — provides compatible Card, Deck, and evaluate()
so the engine.py can run locally without the C-extension eval7 package.

This is NOT shipped to the competition server (which has eval7 installed).
It's for local testing only.
"""
import random
from itertools import combinations

# ─── Rank / Suit mappings ────────────────────────────────────────────────────

RANK_CHARS = '23456789TJQKA'
SUIT_CHARS = 'cdhs'

RANK_INT = {c: i for i, c in enumerate(RANK_CHARS)}   # '2'->0 .. 'A'->12
SUIT_INT = {c: i for i, c in enumerate(SUIT_CHARS)}


# ─── Card ────────────────────────────────────────────────────────────────────

class Card:
    """Minimal eval7-compatible Card."""

    __slots__ = ('rank', 'suit', '_str')

    def __init__(self, s: str):
        self._str = s
        self.rank = RANK_INT[s[0]]
        self.suit = SUIT_INT[s[1]]

    def __repr__(self):
        return self._str

    def __str__(self):
        return self._str

    def __eq__(self, other):
        if isinstance(other, Card):
            return self.rank == other.rank and self.suit == other.suit
        return NotImplemented

    def __hash__(self):
        return hash((self.rank, self.suit))


# ─── Deck ────────────────────────────────────────────────────────────────────

class Deck:
    """Minimal eval7-compatible Deck."""

    def __init__(self):
        self.cards = [Card(r + s) for r in RANK_CHARS for s in SUIT_CHARS]
        self._idx = 0

    def shuffle(self):
        random.shuffle(self.cards)
        self._idx = 0

    def deal(self, n: int) -> list:
        dealt = self.cards[self._idx: self._idx + n]
        self._idx += n
        return dealt

    def peek(self, n: int) -> list:
        return self.cards[self._idx: self._idx + n]


# ─── Hand Evaluator ─────────────────────────────────────────────────────────

def _hand_rank_5(cards_5: list) -> tuple:
    """
    Evaluate a 5-card hand → comparable tuple (higher is better).
    Categories: 8-straight flush … 0-high card.
    """
    ranks = sorted([c.rank for c in cards_5], reverse=True)
    suits = [c.suit for c in cards_5]

    is_flush = len(set(suits)) == 1

    unique = sorted(set(ranks), reverse=True)
    is_straight = False
    straight_high = 0

    if len(unique) == 5:
        if unique[0] - unique[4] == 4:
            is_straight = True
            straight_high = unique[0]
        elif unique == [12, 3, 2, 1, 0]:  # A-2-3-4-5 wheel
            is_straight = True
            straight_high = 3  # 5-high

    # Frequency counts
    freq = {}
    for r in ranks:
        freq[r] = freq.get(r, 0) + 1

    count_rank = sorted(freq.items(), key=lambda x: (x[1], x[0]), reverse=True)
    counts = [c for _, c in count_rank]
    ordered = [r for r, _ in count_rank]

    if is_straight and is_flush:
        return (8, straight_high)
    if counts == [4, 1]:
        return (7, ordered[0], ordered[1])
    if counts == [3, 2]:
        return (6, ordered[0], ordered[1])
    if is_flush:
        return (5,) + tuple(ranks)
    if is_straight:
        return (4, straight_high)
    if counts == [3, 1, 1]:
        return (3, ordered[0], ordered[1], ordered[2])
    if counts == [2, 2, 1]:
        pairs = sorted([r for r, c in count_rank if c == 2], reverse=True)
        kicker = [r for r, c in count_rank if c == 1][0]
        return (2, pairs[0], pairs[1], kicker)
    if counts == [2, 1, 1, 1]:
        pair = ordered[0]
        kickers = sorted([r for r, c in count_rank if c == 1], reverse=True)
        return (1, pair) + tuple(kickers)
    return (0,) + tuple(ranks)


def evaluate(cards) -> int:
    """
    eval7-compatible evaluate(). Accepts a list of 5-7 Card objects.
    Returns an integer score; higher is better.

    We convert the tuple rank to a single int for compatibility with
    engine.py's comparison operators (>, <, ==).
    """
    best = None
    card_list = list(cards)
    for combo in combinations(card_list, 5):
        rank = _hand_rank_5(list(combo))
        if best is None or rank > best:
            best = rank

    # Encode tuple to a single integer for fast comparison
    # Max 6 components, each < 16: pack into base-16 digits
    score = 0
    for v in best:
        score = score * 16 + v
    return score
