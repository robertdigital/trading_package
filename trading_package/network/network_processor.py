import traceback
from multiprocessing import Process, queues
from multiprocessing import Queue, Event

from trading_package.helper.enums import LogType
from trading_package.order_book.order_book import OrderBookManager


class NetworkProcessor(Process):
    PROCESS_NAME = 'Network Processor'

    def __init__(self, product_manager, logging_queue: Queue, exit_event: Event, ready_event: Event) -> None:
        Process.__init__(self)
        self.products = product_manager
        self.exit = exit_event
        self.ready_event = ready_event
        self.logging_queue = logging_queue
        self.order_book_manager = OrderBookManager(product_manager)

    def run(self) -> None:
        self.on_open()
        first = True
        while not self.exit.is_set():
            try:
                self.order_book_manager.update_network_manager()
                if first:
                    self.ready_event.set()
                    first = False
            except Exception as e:
                self.on_error(e)
        self.on_close()

    def on_open(self) -> None:
        self.log(LogType.info, "-- Process Started! --")

    def on_close(self) -> None:
        self.log(LogType.info, "-- Process Terminated! --")

    def on_error(self, e: Exception) -> None:
        self.log(LogType.error, traceback.format_exc())
        self.log(LogType.error, str(e))

    def log(self, log_type: LogType, msg: str) -> None:
        try:
            self.logging_queue.put({'type': log_type.name, 'msg': msg, 'process': self.PROCESS_NAME})
        except queues.Full:
            print('Log dropped!')
            print(msg)
