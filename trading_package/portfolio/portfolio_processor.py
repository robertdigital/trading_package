import traceback
from multiprocessing import Queue, Event, Process, queues
from typing import Dict, List, Optional

from dateutil import parser
from requests import RequestException

from trading_package.client_initializer import *
from trading_package.config.constants import STALE_OPEN_ORDERS, ORDER_CONFIRMATION_TIME
from trading_package.helper.enums import *
from trading_package.order_book.order import Order
from trading_package.portfolio.portfolio import BasePortfolioGroup
from trading_package.portfolio.portfolio import Portfolio
from trading_package.portfolio.portfolio_order_book import PortfolioOrderBook
from trading_package.portfolio.product import ProductManager


class ApiError(Exception):
    pass


class PortfolioProcessor(Process):
    PROCESS_NAME: str = 'Portfolio Processor'
    DEBUG: bool = True
    BATCH_SIZE: int = 100

    def __init__(self, product_manager: ProductManager, websocket_feed_queue: Queue, logging_queue: Queue,
                 exit_event: Event, ready_events: List[Event]) -> None:
        Process.__init__(self)
        self.websocket_feed_queue = websocket_feed_queue
        self.logging_queue = logging_queue
        self.exit = exit_event
        self.product_manager = product_manager
        self.order_book = PortfolioOrderBook(self.product_manager)
        self.portfolio = BasePortfolioGroup(self.order_book)
        self.ready_events = ready_events
        self.registered_orders = []

    def run(self) -> None:
        self.on_open()
        self.register_orders([order_id for order_id, order in self.order_book.get_orders(OrderStatus.open).items()])
        all_processes_ready = False
        while not self.exit.is_set():
            self.process_websocket_message()
            # self.remove_unconfirmed_orders_if_needed()
            # self.cancel_orders_if_needed()

            # wait until all processes are ready to go
            if not all_processes_ready:
                all_processes_ready = all([re.is_set() for re in self.ready_events])
            else:
                self.create_orders_if_needed()
        while not self.websocket_feed_queue.empty():
            self.websocket_feed_queue.get(block=False)
        self.on_close()

    def register_orders(self, order_ids: List[str]) -> None:
        self.registered_orders.extend(order_ids)

    def de_register_orders(self, order_ids: List[str]) -> None:
        [self.registered_orders.remove(order_id) for order_id in order_ids]

    def cancel_all_orders(self) -> None:
        if self.DEBUG:
            return
        for product_id in self.product_manager.get_product_ids():
            authClient.cancelAll(product=product_id)
        self.log(LogType.info, 'All remaining orders canceled')

    def remove_unconfirmed_orders_if_needed(self) -> List[str]:
        order_ids_to_remove = self.order_book.get_expired_unconfirmed_orders(ORDER_CONFIRMATION_TIME)
        if len(order_ids_to_remove) > 0:
            self.log(LogType.error, 'Would have removed orders: {}'.format(order_ids_to_remove))
        return order_ids_to_remove

    def cancel_orders_if_needed(self) -> List[str]:
        order_ids_to_cancel = self.order_book.get_stale_open_orders(STALE_OPEN_ORDERS)
        if len(order_ids_to_cancel) > 0:
            self.log(LogType.info, 'Decided to cancel orders: {}'.format(order_ids_to_cancel))
        for order_id in order_ids_to_cancel:
            self.cancel_order(order_id)
        return order_ids_to_cancel

    def create_orders_if_needed(self) -> None:
        orders = self.portfolio.get_next_trades()
        if self.DEBUG:
            return
        created_order_ids = []
        for order in orders:
            order_json = order.get_gdax_order_params()
            try:
                if order.get_order_side() is OrderSide.bid:
                    self.log(LogType.info, 'Placing buy order: {}'.format(order))
                    gdax_response = authClient.buy(order_json)
                else:
                    self.log(LogType.info, 'Placing sell order: {}'.format(order))
                    gdax_response = authClient.sell(order_json)
                self.validate_gdax_response(gdax_response)
            except (RequestException, ApiError) as e:
                self.on_error(e)
                for order_id in created_order_ids:
                    self.cancel_order(order_id)
                break
            else:
                order = self.parse_gdax_json_to_order(gdax_response)
                self.register_orders([order.get_order_id()])
                created_order_ids.append(order.get_order_id())
                order.set_confirmed(False)
                self.order_book + order

    @staticmethod
    def validate_gdax_response(gdax_response: Dict) -> bool:
        if 'message' in gdax_response:
            raise ApiError(gdax_response['message'])
        elif 'status' in gdax_response and gdax_response['status'] == 'rejected':
            raise ApiError(
                'Order {} Rejected'.format(gdax_response))
        else:
            return True

    def cancel_order(self, order_id: str) -> Optional[Order]:
        if self.DEBUG:
            return
        try:
            gdax_response = authClient.cancelOrder(order_id)
            self.validate_gdax_response(gdax_response)
            # we set the order status to canceled so it does not get canceled again
            # but we are still waiting on official confirmation to come through websocket
            order, order_status = self.order_book.get_order_and_status_by_id(order_id)
            order.update_status(OrderStatus.canceled)
            return order
        except ApiError as e:
            self.on_error(e)
            return None

    def process_websocket_message(self) -> None:
        try:
            order_count = 0
            while not self.websocket_feed_queue.empty():
                order = self.websocket_feed_queue.get(block=False)
                if order is None:
                    continue
                elif 'order_id' in order:
                    order_id = order['order_id']
                elif 'maker_order_id' in order:
                    order_id = order['maker_order_id']
                else:
                    continue
                if order_id in self.registered_orders:
                    self.update_order_status(order)
                    order_count = order_count + 1
                    if order_count >= self.BATCH_SIZE:
                        return
        except queues.Empty:
            return None
        except Exception as e:
            self.on_error(e)
            return None

    def update_order_status(self, order) -> None:
        if order['type'] == 'done':
            self.log(LogType.info, 'Order {} done with reason {} for size {}'.format(order['order_id'],
                                                                                     order['reason'],
                                                                                     order['remaining_size']))
            self.handle_done_order(order)
        elif order['type'] == 'match':
            self.log(LogType.info, 'Order {} matched for size {}'.format(order['maker_order_id'],
                                                                         order['size']))
            self.handle_match_order(order)
        elif order['type'] == 'received':
            self.order_book.confirm_order(order['order_id'])
            self.log(LogType.info, 'Order {} received by order book for size {}'.format(order['order_id'],
                                                                                        order['size']))
        elif order['type'] == 'open':
            self.order_book.confirm_order(order['order_id'])
            self.log(LogType.info, 'Order {} open confirmed by order book for size {}'.format(order['order_id'],
                                                                                              order['remaining_size']))
        elif order['type'] == 'change':
            self.log(LogType.error, 'ERROR - Order {} CHANGED {}'.format(order['order_id'], order))
        else:
            self.log(LogType.error, 'ERROR - Order response type not recognized {}'.format(order))

    def handle_match_order(self, raw_order: Dict) -> str:
        order_id = self.portfolio.handle_match_order(raw_order['maker_order_id'], raw_order['size'])
        return order_id

    def handle_done_order(self, order: Dict) -> None:
        order_status = OrderStatus.filled if order['reason'] == 'filled' else OrderStatus.canceled
        order_id = self.portfolio.handle_done_order(order['order_id'], order_status)
        self.de_register_orders([order_id])

    def parse_gdax_json_to_order(self, raw_order: Dict) -> Order:
        product_id, side, size, price, order_id, filled_size = raw_order['product_id'], raw_order[
            'side'], raw_order['size'], raw_order['price'], raw_order['id'], raw_order[
                                                                   'filled_size']
        created_at = parser.parse(raw_order['created_at'])
        side = 'bid' if side == 'buy' else 'ask'
        order = Order(product_id, 0, OrderSide[side], size, price, OrderStatus.open, order_id, created_at=created_at)
        order.add_filled_size(filled_size)
        self.log(LogType.info,
                 'Order id {} created {} seconds ago'.format(order.get_order_id(), order.get_created_at_seconds_ago()))
        return order

    def on_open(self) -> None:
        self.log(LogType.info, "-- Process Started! --")
        currencies = self.product_manager.get_currencies()
        for account in authClient.getAccounts():
            p = Portfolio(Currency[account['currency']], account['balance'])
            if p.get_currency() in currencies:
                self.portfolio + p
        orders = authClient.getOrders()[0]
        for raw_order in orders:
            order = self.parse_gdax_json_to_order(raw_order)
            order.set_confirmed(True)
            if order.get_product_id() in self.product_manager.get_product_ids():
                self.order_book + order

    def on_error(self, e: Exception) -> None:
        self.log(LogType.error, traceback.format_exc())
        self.log(LogType.error, str(e))

    def on_close(self) -> None:
        self.log(LogType.info, "-- Process Terminated! --")

    def log(self, log_type: LogType, msg: str) -> None:
        try:
            self.logging_queue.put(
                {'type': log_type.name, 'msg': str(msg), 'process': self.PROCESS_NAME})
        except queues.Full:
            print('Log dropped!')
            print(msg)

