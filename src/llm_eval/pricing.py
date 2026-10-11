"""Model prices, for estimating a run's cost before it is paid for.

USD per million tokens, Anthropic first-party API, as cached on 2026-09-25.
The Message Batches API costs half of these rates. Prices change, so check
them before a large run. An unknown model raises rather than being priced as
free.
"""

from __future__ import annotations

PRICES_USD_PER_MTOK = {           # model: (input, output)
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),      # V1's frozen classifier
    "claude-haiku-4-5": (1.00, 5.00),
}
BATCH_DISCOUNT = 0.5


def cost_usd(model: str, input_tokens: int, output_tokens: int,
             *, batch: bool = True) -> float:
    if model not in PRICES_USD_PER_MTOK:
        raise KeyError(f"no price for {model!r}; add it before running")
    price_in, price_out = PRICES_USD_PER_MTOK[model]
    total = (input_tokens * price_in + output_tokens * price_out) / 1_000_000
    return total * (BATCH_DISCOUNT if batch else 1.0)
