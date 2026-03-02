from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Iterable

import eval7


RANK_ORDER = "23456789TJQKA"


@dataclass(frozen=True)
class EquityEstimate:
    win_rate: float
    tie_rate: float
    loss_rate: float
    iterations: int


def _normalize_cards(cards: Iterable[str] | None) -> list[str]:
    if cards is None:
        return []
    normalized = [card.strip() for card in cards if card and card.strip()]
    return normalized


def _validate_card(card: str) -> None:
    if len(card) != 2:
        raise ValueError(f"Invalid card format: {card}")
    rank, suit = card[0], card[1]
    if rank not in RANK_ORDER or suit not in "cdhs":
        raise ValueError(f"Invalid card: {card}")


def estimate_equity_monte_carlo(
    my_hole_cards: Iterable[str],
    community_cards: Iterable[str] | None = None,
    known_opp_cards: Iterable[str] | None = None,
    *,
    iterations: int = 4000,
    rng_seed: int | None = None,
) -> EquityEstimate:
    my_hole = _normalize_cards(my_hole_cards)
    board = _normalize_cards(community_cards)
    opp_known = _normalize_cards(known_opp_cards)

    if len(my_hole) != 2:
        raise ValueError("my_hole_cards must contain exactly 2 cards")
    if len(board) > 5:
        raise ValueError("community_cards cannot exceed 5 cards")
    if len(opp_known) > 2:
        raise ValueError("known_opp_cards cannot exceed 2 cards")
    if iterations <= 0:
        raise ValueError("iterations must be positive")

    all_known = my_hole + board + opp_known
    for card in all_known:
        _validate_card(card)
    if len(set(all_known)) != len(all_known):
        raise ValueError("Duplicate cards detected across known cards")

    my_cards = [eval7.Card(card) for card in my_hole]
    board_cards = [eval7.Card(card) for card in board]
    opp_known_cards = [eval7.Card(card) for card in opp_known]

    # Construct opponent range string
    if len(opp_known) == 0:
        hr = eval7.HandRange("XX")
    elif len(opp_known) == 1:
        c1 = opp_known[0]
        deck_strs = [v + s for v in "23456789TJQKA" for s in "cdhs"]
        dead_set = set(all_known)
        combos = []
        for c2 in deck_strs:
            if c2 not in dead_set and c2 != c1:
                combos.append(c1 + c2)
        hr = eval7.HandRange(",".join(combos) if combos else "XX")
    elif len(opp_known) == 2:
        hr = eval7.HandRange(opp_known[0] + opp_known[1])
    else:
        hr = eval7.HandRange("XX")
    
    equity = eval7.py_hand_vs_range_monte_carlo(my_cards, hr, board_cards, iterations)
    
    win_rate = float(equity)
    tie_rate = 0.0 # Py_hand_vs_range_monte_carlo lumps win + 0.5*tie into "equity"
    loss_rate = max(0.0, 1.0 - win_rate)

    return EquityEstimate(
        win_rate=win_rate,
        tie_rate=tie_rate,
        loss_rate=loss_rate,
        iterations=iterations,
    )
