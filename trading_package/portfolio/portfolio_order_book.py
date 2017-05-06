import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Tuple, Set

from dateutil import tz

from trading_package.helper.enums import OrderStatus, Currency
from trading_package.order_book.order import Order
from trading_package.portfolio.product import ProductManager

logger = logging.getLogger('PortfolioOrderBookLogger')
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)s:%(asctime)s:%(message)s')
ch.setFormatter(formatter)
# add the handlers to logger
logger.addHandler(ch)
logger.propagate = False


class PortfolioOrderBookException(Exception):
    pass


class PortfolioOrderBook:
    def __init__(self, product_manager: ProductManager) -> None:
        self.orders = {status: {} for status in OrderStatus}
        self.product_manager = product_manager

    def get_product_manager(self) -> ProductManager:
        return self.product_manager

    def get_product_ids(self) -> List[str]:
        return self.get_product_manager().get_product_ids()

    def get_orders(self, status: OrderStatus) -> Dict[str, Order]:
        return self.orders[status]

    def get_stale_open_orders(self, seconds_ago) -> List[str]:
        now_time = datetime.now(tz.tzutc())
        order_ids = []
        for order_id, order in self.get_orders(OrderStatus.open).items():
            if order.get_created_at_seconds_ago(
                    now_time) > seconds_ago and order.get_status() == OrderStatus.open and order.get_confirmed():
                order_ids.append(order_id)
        return order_ids

    def get_expired_unconfirmed_orders(self, seconds_ago: int) -> List[str]:
        now_time = datetime.now(tz.tzutc())
        order_ids = []
        for order_id, order in self.get_orders(OrderStatus.open).items():
            if order.get_created_at_seconds_ago(
                    now_time) > seconds_ago and order.get_status() == OrderStatus.open and order.get_confirmed() is False:
                order_ids.append(order_id)
        return order_ids

    def get_order_and_status_by_id(self, order_id: str) -> Tuple[Order, OrderStatus]:
        order = None
        order_status = None
        for status, orders_by_id in self.orders.items():
            if order_id in orders_by_id:
                order = orders_by_id[order_id]
                order_status = status
                break
        return order, order_status

    def update_order_status(self, order_id: str, status: OrderStatus) -> Order:
        order, order_status = self.get_order_and_status_by_id(order_id)
        self.orders[order_status].pop(order.get_order_id())
        order.update_status(status)
        self.orders[status][order_id] = order
        return order

    # NOTE THAT THIS RETURNS PRODUCT QTY NOT SOURCE QTY
    def get_edge_qty(self, source_currency: Currency, destination_currency: Currency) -> Decimal:
        currency_set = {source_currency, destination_currency}
        qty = 0
        for order_id, order in self.get_orders(OrderStatus.open).items():
            product = self.product_manager.get_product(order.get_product_id())
            if product.get_currency_set() == currency_set:
                qty = qty + Decimal(order.get_remaining_size())
        return qty

    def any_open_orders(self) -> bool:
        return True if self.get_orders(OrderStatus.open) else False

    def get_edges_with_open_orders(self) -> Set[Tuple[Currency, Currency]]:
        out = set()
        for order in self.get_orders(OrderStatus.open).values():
            product = self.product_manager.get_product(order.get_product_id())
            side = order.get_order_side()
            source_currency = product.get_source_currency(side)
            dest_currency = product.get_destination_currency(side)
            out.add((source_currency, dest_currency))
        return out

    def get_hold_qty(self, currency: Currency) -> Decimal:
        qty = 0
        for order_id, order in self.get_orders(OrderStatus.open).items():
            product = self.product_manager.get_product(order.get_product_id())
            if currency == product.get_source_currency(order.get_order_side()):
                this_qty = product.get_currency_quantity_from_quote_quantity(currency, order.get_remaining_size(),
                                                                             order.get_price())
                qty = qty + Decimal(this_qty)
        return qty

    def match_order(self, order_id: str, qty: str) -> Order:
        logger.info('Order {} matched for qty {}'.format(order_id, qty))
        order, order_status = self.get_order_and_status_by_id(order_id)
        order.add_filled_size(qty)
        return order

    def fill_order(self, order_id: str) -> Order:
        logger.info('Order {} filled'.format(order_id))
        return self.update_order_status(order_id, OrderStatus.filled)

    def cancel_order(self, order_id: str) -> Order:
        logger.info('Order {} cancelled'.format(order_id))
        return self.update_order_status(order_id, OrderStatus.canceled)

    def confirm_order(self, order_id: str) -> Order:
        logger.info('Order {} confirmed'.format(order_id))
        order, order_status = self.get_order_and_status_by_id(order_id)
        order.set_confirmed(True)
        return order

    def get_currencies(self) -> Set[Currency]:
        return self.product_manager.get_currencies()

    # allow addition of order to order book
    # this should be used for new orders
    def __add__(self, order: Order) -> Order:
        logger.info('Order {} added'.format(order.get_order_id()))
        self.orders[order.get_status()][order.get_order_id()] = order
        return order

    def __sub__(self, order_id: str) -> Order:
        logger.info('Order {} removed'.format(order_id))
        order, order_status = self.get_order_and_status_by_id(order_id)
        return self.orders[order.get_status()].pop(order_id)
