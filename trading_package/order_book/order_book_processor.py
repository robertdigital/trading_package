from multiprocessing import Process, queues
from dateutil import parser
from trading_package.client_initializer import *
from trading_package.order_book.order_book import Order, OrderBookManager, OrderBook
from trading_package.helper.enums import *
from multiprocessing import Queue, Event
from trading_package.portfolio.product import ProductManager
import traceback
from typing import Optional, Dict


class OrderBookProcessor(Process):
    PROCESS_NAME = 'Order Book Processor'

    def __init__(self, product_manager: ProductManager, websocket_feed_queue: Queue, logging_queue: Queue,
                 exit_event: Event, ready_event: Event) -> None:
        Process.__init__(self)
        self.websocket_feed_queue = websocket_feed_queue
        self.product_manager = product_manager
        self.exit = exit_event
        self.logging_queue = logging_queue
        self.ready_event = ready_event
        self.order_book_manager = OrderBookManager(self.product_manager)

    def run(self) -> None:
        self.on_open()
        self.ready_event.set()
        while not self.exit.is_set():
            self.process_next_order()
        # flush queues at close
        while not self.websocket_feed_queue.empty():
            self.websocket_feed_queue.get(block=False)
        self.on_close()

    def process_next_order(self) -> Optional[Order]:
        try:
            next_order = self.websocket_feed_queue.get(block=False)
            this_sequence = self.get_sequence_id(next_order['product_id'])
            next_sequence = int(next_order['sequence'])
            if next_sequence <= this_sequence:
                return None
            self.update_order_book(next_order)
            return next_order
        except queues.Empty:
            return None
        except Exception as e:
            self.on_error(e)
            return None

    @staticmethod
    def map_trade_side_to_order_side(trade_side: str) -> OrderSide:
        if trade_side == 'sell':
            return OrderSide.ask
        if trade_side == 'buy':
            return OrderSide.bid
        else:
            raise Exception('Trade side {} not recognized'.format(trade_side))

    def get_sequence_id(self, product_id: str) -> int:
        return self.order_book_manager.get_order_book(product_id).get_sequence_id()

    def get_change_order(self, order: Dict) -> Order:
        product_id = order['product_id']
        sequence_id = order['sequence']
        side = self.map_trade_side_to_order_side(order['side'])
        price = order['price']
        created_at = parser.parse(order['time'])
        order_id = order['order_id']
        old_size = order['old_size']
        new_size = order['new_size']
        order = Order(product_id, sequence_id, side, old_size, price, order_type=OrderType.change,
                      created_at=created_at,
                      order_id=order_id)
        order.add_filled_size(new_size)
        return order

    def get_open_order(self, order: Dict) -> Order:
        qty = order['remaining_size']
        product_id = order['product_id']
        sequence_id = order['sequence']
        side = self.map_trade_side_to_order_side(order['side'])
        price = order['price']
        created_at = parser.parse(order['time'])
        order_id = order['order_id']
        return Order(product_id, sequence_id, side, qty, price, created_at=created_at, order_id=order_id)

    def get_done_order(self, order: Dict) -> Order:
        qty = order['remaining_size']
        product_id = order['product_id']
        sequence_id = order['sequence']
        order_type = OrderType.match if order['reason'] == 'filled' else OrderType.cancel
        order_status = OrderStatus.filled if order['reason'] == 'filled' else OrderStatus.canceled
        side = self.map_trade_side_to_order_side(order['side'])
        price = order['price']
        created_at = parser.parse(order['time'])
        order_id = order['order_id']
        return Order(product_id, sequence_id, side, qty, price, order_type=order_type, created_at=created_at,
                     status=order_status, order_id=order_id)

    def get_match_order(self, order: Dict) -> Order:
        qty = order['size']
        product_id = order['product_id']
        sequence_id = order['sequence']
        side = self.map_trade_side_to_order_side(order['side'])
        price = order['price']
        created_at = parser.parse(order['time'])
        order_id = order['maker_order_id']
        return Order(product_id, sequence_id, side, qty, price, order_type=OrderType.match, created_at=created_at,
                     order_id=order_id)

    def update_order_book(self, order) -> Optional[OrderBook]:
        if order['type'] == 'received':
            return None
        if order['type'] == 'done':
            if 'price' not in order or 'remaining_size' not in order:
                return None
            return self.order_book_manager - self.get_done_order(order)
        elif order['type'] == 'open':
            return self.order_book_manager + self.get_open_order(order)
        elif order['type'] == 'match':
            return self.order_book_manager - self.get_match_order(order)
        elif order['type'] == 'change':
            if 'new_funds' in order or 'price' not in order:
                return None
            return self.order_book_manager - self.get_change_order(order)

    def on_open(self) -> None:
        self.log(LogType.info, "-- Process Started! --")
        for product_id in self.product_manager.get_product_ids():
            order_book = self.order_book_manager.get_order_book(product_id)
            orders = publicClient.getProductOrderBook(product=product_id, level=3)
            sequence_id = orders['sequence']
            for side in ['bids', 'asks']:
                for raw_order in orders[side]:
                    price = raw_order[0]
                    qty = raw_order[1]
                    order_id = raw_order[2]
                    order = Order(product_id, sequence_id, OrderSide[side[:-1]], qty, price, order_id=order_id)
                    order_book + order
            historical_orders = publicClient.getProductTrades(product=product_id)
            for historical_order in historical_orders:
                price = historical_order['price']
                qty = historical_order['size']
                side = self.map_trade_side_to_order_side(historical_order['side'])
                created_at = parser.parse(historical_order['time'])
                order = Order(product_id, sequence_id, side, qty, price, historical=True, order_type=OrderType.match,
                              created_at=created_at)
                order_book + order

    def on_error(self, e: Exception) -> None:
        self.log(LogType.error, traceback.format_exc())
        self.log(LogType.error, str(e))

    def on_close(self) -> None:
        self.log(LogType.info, "-- Process Terminated! --")

    def log(self, log_type: LogType, msg: str) -> None:
        try:
            self.logging_queue.put({'type': log_type.name, 'msg': msg, 'process': self.PROCESS_NAME})
        except queues.Full:
            print('Log dropped!')
            print(msg)
