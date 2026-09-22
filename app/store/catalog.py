# owner: shared / lead
#
# The price list, and the only place prices are allowed to live.
#
# Everything the browser sends is a SKU and a quantity. Nothing that arrives
# in a request is ever treated as an amount, because a hidden form field
# saying "price=1" is the single most common way a checkout gets robbed.
#
# Amounts are integer cents. Never floats: 0.1 + 0.2 is not 0.3, and money
# that is a fraction of a cent out will eventually fail to reconcile against
# Stripe, which also counts in integer cents.

# Prices from the public cost table on the landing page (#cost).
REGISTRATION_CENTS = 2_000  # $20
KIT_CENTS = 10_000  # $100
MICROBIT_CENTS = 2_000  # $20

# Nobody has decided this one yet. None is deliberate and load-bearing: a SKU
# with no price cannot be bought and is not displayed, so the open question
# shows up as a missing item rather than as a silent $0 charge. Set it to an
# integer number of cents and the practice field appears in the store.
PRACTICE_FIELD_CENTS = None


CATALOG = {
    "registration": {
        "label": "Team registration",
        "description": "Per team. Covers the competition fields and the awards.",
        "amount_cents": REGISTRATION_CENTS,
        "shippable": False,
        "max_quantity": 1,
    },
    "kit": {
        "label": "Official kit",
        "description": "A complete, competition-legal robot, and a field to practice on. No micro:bit.",
        "amount_cents": KIT_CENTS,
        "shippable": True,
        "max_quantity": 4,
    },
    "microbit": {
        "label": "micro:bit",
        "description": "Skip it if you already have one.",
        "amount_cents": MICROBIT_CENTS,
        "shippable": True,
        "max_quantity": 4,
    },
    "practice_field": {
        "label": "Practice field",
        "description": "Printed from the same filament as the competition fields.",
        "amount_cents": PRACTICE_FIELD_CENTS,
        "shippable": True,
        "max_quantity": 2,
    },
}


class CatalogError(ValueError):
    """A cart the catalog refuses to price.

    Raised rather than returned so no caller can accidentally carry on with a
    half-priced cart. Every message is safe to show a buyer.
    """


def is_purchasable(sku: str) -> bool:
    item = CATALOG.get(sku)
    return item is not None and item["amount_cents"] is not None


def purchasable_items():
    """The SKUs a store page should offer, in catalog order."""
    return [(sku, item) for sku, item in CATALOG.items() if is_purchasable(sku)]


def price_cart(raw_items):
    """Turn (sku, quantity) pairs into priced line items.

    *raw_items* comes from a request, so every field is hostile until checked:
    the SKU may not exist, the quantity may be a word, a float, negative, or
    ten thousand. Each of those is a CatalogError rather than a 500, and none
    of them can influence the price - that is read from CATALOG by SKU alone.

    Returns a list of dicts carrying a snapshot of the label and unit price,
    so a later price change never rewrites what somebody was charged.
    """
    priced = []
    seen = set()

    for sku, quantity in raw_items:
        item = CATALOG.get(sku)
        if item is None:
            raise CatalogError(f"Unknown item: {sku!r}.")
        if item["amount_cents"] is None:
            raise CatalogError(f"{item['label']} is not on sale yet.")
        if sku in seen:
            raise CatalogError(f"{item['label']} was listed twice.")
        seen.add(sku)

        # int() on a str raises ValueError; on a float it silently truncates,
        # so 1.9 would become 1. Reject anything that is not already an
        # integer rather than guessing which one the buyer meant.
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            try:
                quantity = int(str(quantity).strip())
            except (TypeError, ValueError):
                raise CatalogError(f"Quantity for {item['label']} is not a number.") from None

        if quantity < 1:
            raise CatalogError(f"Quantity for {item['label']} must be at least 1.")
        if quantity > item["max_quantity"]:
            raise CatalogError(
                f"You can order at most {item['max_quantity']} × {item['label']}."  # noqa: RUF001
            )

        priced.append({
            "sku": sku,
            "label": item["label"],
            "unit_amount_cents": item["amount_cents"],
            "quantity": quantity,
        })

    if not priced:
        raise CatalogError("Your cart is empty.")
    return priced


def cart_total_cents(priced_items) -> int:
    return sum(i["unit_amount_cents"] * i["quantity"] for i in priced_items)


def needs_shipping(priced_items) -> bool:
    """True if anything in the cart is a physical object.

    A cart holding only the registration fee must never ask for a shipping
    address - there is nothing to post.
    """
    return any(CATALOG[i["sku"]]["shippable"] for i in priced_items)
