from datetime import datetime
from statistics import mean, median, mode, StatisticsError
from typing import List, Tuple, Optional

from dateutil import tz
from redis import StrictRedis

from trading_package.helper.enums import *
from trading_package.network.network import NetworkManager
from trading_package.order_book.order import Order
from trading_package.portfolio.product import ProductManager, Product


class SequenceException(Exception):
    def __init__(self, value) -> None:
        self.parameter = value

    def __str__(self) -> str:
        return repr(self.parameter)


class OrderBookException(Exception):
    pass


class OrderBook:
    # not that sequence ids will be cast to integers
    # order book is also maintained in redis
    def __init__(self, product: Product, sequence_id: int = 0) -> None:
        self.redis_server = StrictRedis(host='localhost', port=6379, db=0, encoding="utf-8", decode_responses=True)
        self.product = product
        self.sequence_id = int(sequence_id)
        self.order_book = {side: {} for side in OrderSide}
        self.trades = {side: {order_type: {} for order_type in OrderType} for side in OrderSide}
        self.orders_added = 0
        self.orders_subtracted = 0

    def get_product_id(self) -> str:
        return self.get_product().get_product_id()

    def get_product(self) -> Product:
        return self.product

    def get_sequence_id(self) -> int:
        return self.sequence_id

    # this method determines the best maker price at which to place an order
    # so as to fill AT least quantity
    def get_network_price(self, side: OrderSide, total_quantity: float, desired_quantity: float = 0,
                          allow_exceed_best: bool = True) -> Tuple[Optional[str], Optional[float]]:
        if total_quantity is None:
            raise OrderBookException('Total quantity cannot be none in get_price: {}'.format(total_quantity))

        # this is how much approximately we need to fill first to get best possible price
        other_quantity = total_quantity - desired_quantity
        best_price, worst_price, total_price, error, worst_qty = self.get_price(side=side, depth=other_quantity)
        # prices haven't loaded yet
        if worst_price is None or best_price is None:
            return None, None
        # this means we can optimally place at the back of the queue within an error of the minimum quote size
        # we do all comparisons as floats to save time at the cost of accuracy here
        elif error <= float(self.get_product().get_base_min_size_str()):
            return str(worst_price), desired_quantity
        # best bid and best ask are separated by the minimum spread so there is nowhere else for me to go
        # return available qty of 0 at best price
        elif best_price == worst_price and (self.spread_locked() or not allow_exceed_best):
            return str(best_price), 0.

        # take a slightly worse price but in exchange fill more quantity
        if side == OrderSide.bid:
            new_price = self.get_product().get_higher_price(str(worst_price))
        else:
            new_price = self.get_product().get_lower_price(str(worst_price))

        return str(new_price), desired_quantity + worst_qty - error

    def spread_locked(self) -> bool:
        best_bid, best_ask = self.get_best_bid_ask(0)
        if best_bid and best_ask:
            if self.get_product().get_higher_price(str(best_bid)) == self.get_product().round_price(str(best_ask)):
                return True
        return False

    # this returns
    # (best price, worst price, total price for depth, excess quantity above depth, filled qty at worst price)
    # in product quote currency
    def get_price(self, side: OrderSide, depth: float = 0) -> Tuple[float, float, float, float, float]:
        if depth is None:
            raise OrderBookException('depth cannot by none in get_price: {}'.format(depth))

        total_price = 0.
        total_qty = 0.
        best_price = None
        worst_price = None
        excess_qty = 0.
        worst_qty = 0.
        reverse_order_sort = True if side is OrderSide.bid else False
        counter = 0
        iter_count = 10
        keep_going = True
        while keep_going:
            price_keys = self.redis_server.zrange(self.__get_ob_order_set_redis_key(side), counter,
                                                  counter + iter_count - 1, withscores=True, desc=reverse_order_sort)
            if len(price_keys) == 0:
                break
            sizes = self.redis_server.mget(map(lambda x: x[0], price_keys))
            for idx, (_, price) in enumerate(price_keys):
                if best_price is None:
                    best_price = price
                worst_price = price
                if sizes[idx] is None:
                    continue
                size = float(sizes[idx])
                qty = min(size, depth - total_qty)
                excess_qty = size - qty
                worst_qty = size

                total_price = total_price + (price * qty)
                total_qty = total_qty + qty
                if total_qty >= depth:
                    keep_going = False
                    break

            counter = counter + iter_count
        return best_price, worst_price, total_price, excess_qty, worst_qty

    def get_best_bid(self, depth: float = 0) -> float:
        return self.get_price(OrderSide.bid, depth)[1]

    def get_best_ask(self, depth: float = 0) -> float:
        return self.get_price(OrderSide.ask, depth)[1]

    def get_best_bid_ask(self, depth=0) -> Tuple[float, float]:
        return self.get_best_bid(depth), self.get_best_ask(depth)

    def get_best(self, side: OrderSide, depth: float = 0) -> float:
        if side == OrderSide.bid:
            return self.get_best_bid(depth)
        else:
            return self.get_best_ask(depth)

    def validate_order(self, order: Order) -> bool:
        if isinstance(order, Order):
            if order.get_product_id() != self.get_product_id():
                raise OrderBookException(
                    'You can only add orders with the same product id {} {}'.format(self.get_product_id(),
                                                                                    order.get_product_id())
                )
            elif order.get_sequence_id() < self.get_sequence_id():
                raise SequenceException(
                    'You cannot add orders with a lower sequence id {} {}'.format(self.get_sequence_id(),
                                                                                  order.get_sequence_id())
                )
            else:
                return True
        else:
            raise OrderBookException(
                'You can only add orders of type Order to an order book {}'.format(str(type(order)))
            )

    # optimize so that this is way faster
    def validate(self) -> None:
        try:
            max_bid, min_ask = self.get_best_bid_ask()
            if max_bid and min_ask and max_bid > min_ask:
                raise OrderBookException(
                    'Max bid ({}) exceeds Min ask ({}) for product {}'.format(max_bid, min_ask, self.get_product_id())
                )
        except ValueError:
            pass

    # we need this to round to the nearest group by period!
    # group_by_period = None means no grouping at all
    # 1) Sort orders by created_at_time (first is most recent)
    # 2) For each created_at_time get rounded seconds ago created
    # 3) If same as previous order the increment array element
    # 4) Else append array element
    def get_trade_quantities(self, side: OrderSide, order_type: OrderType, seconds_ago: int,
                             group_by_period: int = None) -> List[float]:
        now_time = float(datetime.now(tz.tzutc()).strftime('%s'))
        first_time = now_time - seconds_ago
        quantities = []
        last_created_at = None
        # this gets all relevant keys
        size_key_by_timestamp = self.redis_server.zrangebyscore(self.__get_th_order_set_redis_key(order_type, side),
                                                                first_time,
                                                                now_time, withscores=True)
        if len(size_key_by_timestamp) == 0:
            return []
        sizes = self.redis_server.mget(map(lambda x: x[0], size_key_by_timestamp))
        for idx, (_, timestamp) in enumerate(size_key_by_timestamp):
            size = sizes[idx]
            if size is None:
                continue
            else:
                size = float(sizes[idx])
            created_at = int(timestamp)
            quantity = 0
            if group_by_period is None:
                r_created_at = created_at
            else:
                r_created_at = (created_at / group_by_period) * group_by_period
            quantity = quantity + size
            if r_created_at == last_created_at:
                quantities[-1] = quantities[-1] + quantity
            else:
                quantities.append(quantity)
            last_created_at = r_created_at
        return quantities

    def get_volume(self, side: OrderSide, order_type: OrderType, seconds_ago: int) -> float:
        order_quantities = self.get_trade_quantities(side, order_type, seconds_ago)
        return sum(order_quantities)

    def get_edge_trade_size(self, side: OrderSide, order_type: OrderType, seconds_ago: int, edge_type: EdgeType,
                            group_by_period: Optional[int] = None) -> float:
        qty = None
        if edge_type == EdgeType.best:
            qty = 0.
        elif edge_type == EdgeType.mean:
            qty = self.get_average_trade_size(side, order_type, seconds_ago, group_by_period)
        elif edge_type == EdgeType.median:
            qty = self.get_median_trade_size(side, order_type, seconds_ago, group_by_period)
        elif edge_type == EdgeType.custom:
            qty = self.get_average_trade_size(side, order_type, seconds_ago, group_by_period)
            if qty is not None:
                qty = qty / 10.
        return qty

    def get_average_trade_size(self, side: OrderSide, order_type: OrderType, seconds_ago: int,
                               group_by_period: Optional[int] = None) -> Optional[float]:
        order_quantities = self.get_trade_quantities(side, order_type, seconds_ago, group_by_period)
        if len(order_quantities) == 0:
            return None
        return mean(order_quantities)

    def get_median_trade_size(self, side: OrderSide, order_type: OrderType, seconds_ago: int,
                              group_by_period: Optional[int] = None) -> Optional[float]:
        order_quantities = self.get_trade_quantities(side, order_type, seconds_ago, group_by_period)
        if len(order_quantities) == 0:
            return None
        return median(order_quantities)

    def get_mode_trade_size(self, side: OrderSide, order_type: OrderType, seconds_ago: int,
                            group_by_period: Optional[int] = None) -> Optional[float]:
        order_quantities = self.get_trade_quantities(side, order_type, seconds_ago, group_by_period)
        if len(order_quantities) == 0:
            return None
        try:
            return mode(order_quantities)
        except StatisticsError:
            return None

    def __get_root_ob_redis_key(self, side: OrderSide) -> str:
        return 'order_book:book:{}:{}'.format(self.get_product_id(), side.name)

    # this key points to a hash of order_id => size
    def __get_ob_order_hash_redis_key(self, side: OrderSide, price: str) -> str:
        return '{}:{:.5f}:order_list'.format(self.__get_root_ob_redis_key(side), float(price))

    # this key points to the sum of orders at this price
    def __get_ob_sum_size_redis_key(self, side: OrderSide, price: str) -> str:
        return '{}:{:.5f}:order_size_sum'.format(self.__get_root_ob_redis_key(side), float(price))

    # this key points to a set with price keys and score of price to facilitate getting a range
    def __get_ob_order_set_redis_key(self, side: OrderSide) -> str:
        return '{}'.format(self.__get_root_ob_redis_key(side))

    # redis key for trade history
    def __get_th_order_set_redis_key(self, order_type: OrderType, side: OrderSide) -> str:
        return 'order_book:history:trades:{}:{}:{}'.format(self.get_product_id(),
                                                           side.name,
                                                           order_type.name)

    # redis key for trade history
    def __get_th_redis_key(self, order_type: OrderType, side: OrderSide, timestamp: str) -> str:
        return 'order_book:history:trades:{}:{}:{}:{}'.format(self.get_product_id(),
                                                              side.name,
                                                              order_type.name,
                                                              timestamp)

    @staticmethod
    def __get_pr_redis_key(side: OrderSide) -> str:
        return 'order_book:changed_products:{}'.format(side.name)

    def __add_trade_to_trade_history(self, order: Order) -> None:
        th_set_key = self.__get_th_order_set_redis_key(order.get_order_type(), order.get_order_side())
        th_order_size_key = self.__get_th_redis_key(order.get_order_type(), order.get_order_side(),
                                                    order.get_unix_timestamp())
        self.redis_server.zadd(th_set_key, order.get_unix_timestamp(), th_order_size_key)
        self.redis_server.incrbyfloat(th_order_size_key, order.get_size())

    def __update_sequence_id(self, sequence_id: int) -> None:
        if sequence_id > self.sequence_id:
            self.sequence_id = sequence_id

    def __remove_order(self, order: Order) -> None:
        price = order.get_price()
        side = order.get_order_side()
        order_key = self.__get_ob_order_hash_redis_key(side, price)
        size_key = self.__get_ob_sum_size_redis_key(side, price)
        self.redis_server.hdel(order_key, order.get_order_id())
        if self.redis_server.hlen(order_key) == 0:
            # why bother deleting here?
            self.redis_server.delete(order_key)
            self.redis_server.delete(size_key)
            self.redis_server.zrem(self.__get_ob_order_set_redis_key(side),
                                   self.__get_ob_sum_size_redis_key(side, price))
        else:
            self.redis_server.incrbyfloat(size_key, '-' + order.get_size())

    def __change_order(self, order: Order) -> None:
        price = order.get_price()
        order_id = order.get_order_id()
        side = order.get_order_side()
        new_order_size = order.get_filled_size()
        order_key = self.__get_ob_order_hash_redis_key(side, price)
        size_key = self.__get_ob_sum_size_redis_key(side, price)
        if self.redis_server.hexists(order_key, order_id):
            self.redis_server.hset(order_key, order_id, new_order_size)
            self.redis_server.incrbyfloat(size_key, '-' + order.get_remaining_size())

    def __match_order(self, order: Order) -> None:
        price = order.get_price()
        order_id = order.get_order_id()
        side = order.get_order_side()
        order_key = self.__get_ob_order_hash_redis_key(side, price)
        size_key = self.__get_ob_sum_size_redis_key(side, price)
        self.redis_server.hincrbyfloat(order_key, order_id, '-' + order.get_size())
        self.redis_server.incrbyfloat(size_key, '-' + order.get_size())

    def __register_product_change(self, side) -> None:
        self.redis_server.sadd(self.__get_pr_redis_key(side), self.get_product_id())

    # allow addition of order to order book
    # this should be used for new orders
    def __add__(self, order: Order) -> None:
        self.validate_order(order)
        self.__update_sequence_id(order.get_sequence_id())
        price = order.get_price()
        side = order.get_order_side()
        if not order.get_historical():
            # This marks that we have live orders at this price
            self.redis_server.zadd(self.__get_ob_order_set_redis_key(side), price,
                                   self.__get_ob_sum_size_redis_key(side, price))
            # This adds the order to a list of orders keyed off price
            self.redis_server.hset(self.__get_ob_order_hash_redis_key(side, price), order.get_order_id(),
                                   order.get_size())
            self.redis_server.incrbyfloat(self.__get_ob_sum_size_redis_key(side, price), order.get_size())

        self.__register_product_change(order.get_order_side())
        self.orders_added = self.orders_added + 1
        # if self.orders_added % 1000 == 1:
        # print('Heartbeat {} orders added to {}'.format(self.orders_added, self.get_product_id()))
        self.__add_trade_to_trade_history(order)

    # allow subtraction of order from order book
    def __sub__(self, order: Order) -> None:
        self.validate_order(order)
        self.__update_sequence_id(order.get_sequence_id())
        if not order.get_historical():
            if order.get_status() in [OrderStatus.filled, OrderStatus.canceled]:
                self.__remove_order(order)
            elif order.get_order_type() == OrderType.change:
                self.__change_order(order)
            else:
                self.__match_order(order)

        self.__register_product_change(order.get_order_side())
        self.orders_subtracted = self.orders_subtracted + 1
        # if self.orders_subtracted % 1000 == 1:
        #     print('Heartbeat {} orders removed from {}'.format(self.orders_subtracted, self.get_product_id()))
        self.__add_trade_to_trade_history(order)


class OrderBookManager:
    BATCH_SIZE = 10

    def __init__(self, product_manager: ProductManager) -> None:
        self.product_manager = product_manager
        self.order_books = {product_id: OrderBook(product_manager.get_product(product_id)) for product_id in
                            self.product_manager.get_product_ids()}
        self.network_manager = NetworkManager()
        self.redis_server = StrictRedis(host='localhost', port=6379, db=0, encoding="utf-8", decode_responses=True)

    def get_order_book(self, product_id: str) -> OrderBook:
        return self.order_books[product_id]

    def get_network_manager(self) -> NetworkManager:
        return self.network_manager

    def update_network_manager(self) -> NetworkManager:
        for side in OrderSide:
            products = self.redis_server.execute_command('SPOP', self.__get_pr_redis_key(side), self.BATCH_SIZE)
            for next_product in products:
                self.network_manager.update_from_order_book(self.get_order_book(next_product), side)
        return self.get_network_manager()

    @staticmethod
    def __get_pr_redis_key(side: OrderSide) -> str:
        return 'order_book:changed_products:{}'.format(side.name)

    def __add__(self, order: Order) -> OrderBook:
        order_book = self.get_order_book(order.get_product_id())
        val = order_book + order
        return val

    # allow subtraction of order to order book
    # this should be used for cancellation
    def __sub__(self, order: Order) -> OrderBook:
        order_book = self.get_order_book(order.get_product_id())
        val = order_book - order
        return val
