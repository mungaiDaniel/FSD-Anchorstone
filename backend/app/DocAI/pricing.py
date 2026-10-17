"""
What AI calls cost, from the per-model prices in the setting ai.price_table (USD per
million tokens), so prices can change without a code change.

    cost_usd(model, tokens…)        ACTUAL cost of a call, from the token usage the API returned
                                    (cache writes at 1.25×, cache reads at 0.1× the input price)
    estimate_usd(model, pages)      ESTIMATE before a call, from the pages it sends: a fixed
                                    allowance for the prompt and schema plus a per-page allowance
                                    for input and output. Deliberately on the high side (a budget
                                    should refuse a little early rather than overspend). None when
                                    the model has no price: such a call is refused.
"""
from decimal import ROUND_HALF_UP, Decimal

from app.Settings import business

MICRO_USD = Decimal("0.000001")
# Allowances for the estimate (tokens). The fixture readings use 2,900–6,200 input and
# 300–2,300 output tokens per call (tests/fixtures/ai_responses), so these sit above them.
PROMPT_AND_SCHEMA_INPUT = 2500
INPUT_PER_PAGE = 2500
OUTPUT_BASE = 500
OUTPUT_PER_PAGE = 2500


def prices(model: str | None) -> tuple[Decimal, Decimal] | None:
    row = business.get("ai.price_table").get(model or "")
    return (Decimal(row["input"]), Decimal(row["output"])) if row else None


def cost_usd(model: str | None, input_tokens: int, output_tokens: int, cache_read: int = 0,
             cache_write: int = 0) -> Decimal | None:
    p = prices(model)
    if p is None:
        return None
    p_in, p_out = p
    total = (input_tokens * p_in + output_tokens * p_out + cache_write * p_in * Decimal("1.25")
             + cache_read * p_in * Decimal("0.1")) / Decimal(1_000_000)
    return total.quantize(MICRO_USD, rounding=ROUND_HALF_UP)


def estimate_usd(model: str | None, pages: int) -> Decimal | None:
    pages = max(int(pages or 1), 1)
    return cost_usd(model, PROMPT_AND_SCHEMA_INPUT + INPUT_PER_PAGE * pages, OUTPUT_BASE + OUTPUT_PER_PAGE * pages)
