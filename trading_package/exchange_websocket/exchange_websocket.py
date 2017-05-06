import multiprocessing
import signal
from twisted.python import log
import traceback
import json
from twisted.internet import reactor
from twisted.internet.protocol import ReconnectingClientFactory
from autobahn.twisted.websocket import WebSocketClientProtocol, WebSocketClientFactory, connectWS
from datetime import datetime
from trading_package.portfolio.product import ProductManager
from multiprocessing import Queue, Event


class MyClientProtocol(WebSocketClientProtocol):
    PROCESS_NAME = 'Autobahn Websocket Client'

    def onConnect(self, response) -> None:
        self.factory.resetDelay()
        self.log.info("Server connected: {0}".format(response.peer))

    def onOpen(self) -> None:
        self.log.info("-- Process Started! --")
        self.log.info('Product ids: {}'.format(self.products))
        sub_params = json.dumps({"type": "subscribe", "product_ids": self.products}).encode('utf-8')
        self.sendMessage(sub_params)
        self.ready_event.set()

    def onMessage(self, payload, is_binary) -> None:
        if self.state == self.STATE_CLOSING:
            return
        elif self.exit.wait(0):
            self.log.error("Exit event set, closing protocol")
            self.sendClose()
            return
        raw_msg = payload.decode('utf8')
        raw_msg = json.loads(raw_msg)
        this_sequence_id = int(raw_msg['sequence'])
        product_id = raw_msg['product_id']
        if product_id in self.last_sequence_id and this_sequence_id != self.last_sequence_id[product_id] + 1:
            error_msg = 'Sequence ids out of order ({}:{}, {})'.format(product_id, this_sequence_id, self.last_sequence_id)
            self.log.error(error_msg)
            self.exit.set()
            self.sendClose()
            return
        self.last_sequence_id[product_id] = this_sequence_id
        try:
            if raw_msg['type'] in ['received', 'open', 'done', 'match', 'change']:
                self.result_queue.put(raw_msg, False)
                self.task_queue.put(raw_msg, False)
            elif raw_msg['type'] == 'heartbeat':
                pass
            else:
                self.log.info('msg: {} ignored\n'.format(raw_msg))
        except multiprocessing.queues.Full as e:
            self.log.error(traceback.format_exc())
            self.log.error(str(e))

    def onClose(self, wasClean, code, reason) -> None:
        self.log.info("-- Process Terminated! --")


class MyClientFactory(WebSocketClientFactory, ReconnectingClientFactory):
    PROCESS_NAME = 'Autobahn Websocket Client'
    maxDelay = 1
    initialDelay = 0

    def clientConnectionFailed(self, connector, reason) -> None:
        self.log.error('Connection Failed with reason {}'.format(reason))
        if not self.protocol.exit.wait(0):
            self.protocol.exit.set()
        reactor.stop()

    def clientConnectionLost(self, connector, reason) -> None:
        self.log.error('Connection Lost with reason {}'.format(reason))
        if not self.protocol.exit.wait(0):
            self.protocol.exit.set()
        reactor.stop()


# this maintains a websocket and sends messages to a result queue
# an order book manager will read off the result queue to maintain
# the current state
class ExchangeWebsocket(multiprocessing.Process):
    PROCESS_NAME = 'Exchange Websocket'
    URL = 'wss://ws-feed.gdax.com'

    def __init__(self, pm: ProductManager, task_queue: Queue, result_queue: Queue, ready_event: Event, exit_event: Event) -> None:
        multiprocessing.Process.__init__(self)
        protocol = MyClientProtocol
        protocol.products = pm.get_product_ids()
        protocol.task_queue = task_queue
        protocol.result_queue = result_queue
        protocol.last_sequence_id = {}
        protocol.exit = exit_event
        protocol.ready_event = ready_event
        self.protocol = protocol

    def run(self) -> None:
        log.startLogging(open(datetime.now().strftime('logs/websocket_%d_%m_%Y.log'), 'a'))
        factory = MyClientFactory(self.URL)
        factory.protocol = self.protocol
        connectWS(factory)

        default_handler = signal.getsignal(signal.SIGINT)

        signal.signal(signal.SIGINT, signal.SIG_IGN)
        reactor.run()
        signal.signal(signal.SIGINT, default_handler)
        if reactor.running:
            reactor.stop()


def main():
    from trading_package.process_manager import get_product_manager
    import time

    exit_event = multiprocessing.Event()
    task_queue = multiprocessing.Queue()
    ready_event = multiprocessing.Event()
    result_queue = multiprocessing.Queue()
    queues = [task_queue, result_queue]
    wsClient = ExchangeWebsocket(get_product_manager(), task_queue, result_queue, ready_event,
                                 exit_event)
    wsClient.daemon = True
    wsClient.start()
    print("Waiting for a while")
    try:
        time.sleep(10)
    except:
        print('exception')
        time.sleep(10)
    print("Finished waiting")
    exit_event.set()
    for queue in queues:
        while not queue.empty():
            queue.get(False)
    print('queues emptied')
    print('joining process')
    wsClient.join(timeout=1)


if __name__ == "__main__":
    main()
