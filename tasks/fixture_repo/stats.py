"""Sales statistics."""


def average_price(prices):
    total = sum(prices)
    return total / len(prices)


def growth(old, new):
    return (new - old) / old * 100
