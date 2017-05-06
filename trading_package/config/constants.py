NETWORK_LOOKBACK = 24*60*30 # 24 hour lookback


STALE_OPEN_ORDERS = 5*60 # 1 minute stale order cancellation


EDGE_TYPE = 'mean'


MIN_CYCLE_RETURN = 1.005 # 0.5%


# I want to be able to fill a
# x% mean order
# and fill at the better part of the price
# quantity filled = x% * mean at price p(1 - x%)
# This will round such that I may fill more than x% but not less
# if at all possible
QTY_MULTIPLIER = 0.5


# Orders must be confirmed within 1 minutes or they are taken
# off the order book. We don't cancel unconfirmed orders
# note that this actually does happen quite a lot
ORDER_CONFIRMATION_TIME = 600


# consider all orders within the same second to be the same
ORDER_AGGREGATION_TIME = 1


# Really try to restrict exposure
# Note that these defaults are subsidiary to redis
PORTFOLIO_MAKEUP = {
    'LTC': ('0', '1.0'),
    'BTC': ('0', '1.0'),
    'USD': ('0', '1.0'),
    'ETH': ('0', '1.0')
}
