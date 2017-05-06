from enum import Enum
# make sure not to import helper constants
# or you will have a circular import


class OrderBookRequestType(Enum):
    valuation = 1
    best_bid_ask = 2
    network_manager = 3
    volume = 4
    register_order = 5
    deregister_order = 6
    order_update = 7


class OrderBookResponseStatus(Enum):
    success = 1
    failure = 2


class NetworkType(Enum):
    price = 1
    quantity = 2


class EdgeType(Enum):
    best = 1
    median = 2
    mean = 3
    custom = 4


# Note that the values are important here
# as they are used when sorting by volatility!
# We prefer to hold $ when possible
class Currency(Enum):
    LTC = 1
    ETH = 2
    BTC = 3
    USD = 4


class OrderSide(Enum):
    bid = 1
    ask = 2


class OrderType(Enum):
    match = 1
    limit = 2
    change = 3
    cancel = 4


class OrderStatus(Enum):
    open = 1
    filled = 2
    canceled = 3
    unconfirmed = 4


class QuoteType(Enum):
    product = 1
    currency = 2


class LogType(Enum):
    info = 20
    debug = 10
    error = 40
