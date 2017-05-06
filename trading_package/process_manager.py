import logging
from datetime import datetime
from multiprocessing import Event, Queue, queues
from signal import getsignal, signal, SIGINT, SIG_IGN

from redis import StrictRedis
from redis.exceptions import ConnectionError

from trading_package.client_initializer import *
from trading_package.exchange_websocket.exchange_websocket import ExchangeWebsocket
from trading_package.helper.enums import LogType, Currency
from trading_package.network.network_processor import NetworkProcessor
from trading_package.order_book.order_book_processor import OrderBookProcessor
from trading_package.portfolio.portfolio_processor import PortfolioProcessor
from trading_package.portfolio.product import ProductManager, Product

logger = logging.getLogger('MainLogger')
logger.setLevel(logging.INFO)
fh = logging.FileHandler(datetime.now().strftime('logs/process_%d_%m_%Y.log'))
fh.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(levelname)s:%(asctime)s:%(message)s')
ch.setFormatter(formatter)
fh.setFormatter(formatter)
# add the handlers to logger
logger.addHandler(ch)
logger.addHandler(fh)
logger.propagate = False

def get_product_manager() -> ProductManager:
    pm = ProductManager()
    excluded_product_ids = {'BTC-GBP', 'BTC-EUR'}
    currencies = publicClient.getCurrencies()
    [pm.set_currency(Currency[currency['id']], currency['min_size']) for currency in currencies if
     currency['id'] not in ['GBP', 'EUR']]
    for raw_product in publicClient.getProducts():
        if raw_product['id'] not in excluded_product_ids:
            pm + Product(product_id=raw_product['id'], quote_currency=Currency[raw_product['quote_currency']],
                         base_currency=Currency[raw_product['base_currency']],
                         quote_increment=raw_product['quote_increment'],
                         base_min_size=raw_product['base_min_size'])
    return pm


def log(q: Queue(), batch_size: int = 1) -> None:
    count = 0
    while not q.empty():
        if count >= batch_size:
            break
        try:
            raw_msg = q.get(block=False)
            process_name = raw_msg['process'] if 'process' in raw_msg else ''
            msg = '{}:{}'.format(process_name, raw_msg['msg'])
            logger.log(LogType[raw_msg['type']].value, msg)
            count = count + 1
        except (KeyError, queues.Empty) as e:
            print(e)
            break


def main() -> bool:
    default_handler = getsignal(SIGINT)
    signal(SIGINT, SIG_IGN)
    restart_event_bool = False

    exit_event = Event()
    ready_events = [Event() for _ in range(3)]
    comm_queues = [Queue() for _ in range(3)]
    logger_queue = comm_queues[2]
    product_manager = get_product_manager()
    processes = [ExchangeWebsocket(product_manager, comm_queues[0], comm_queues[1], ready_events[0], exit_event),
                 OrderBookProcessor(product_manager, comm_queues[1], logger_queue, exit_event, ready_events[1]),
                 PortfolioProcessor(product_manager, comm_queues[0], logger_queue, exit_event, ready_events),
                 NetworkProcessor(product_manager, logger_queue, exit_event, ready_events[2])]
    try:
        # clear out redis at the beginning
        try:
            redis_server = StrictRedis(host='localhost', port=6379, db=0)
            redis_server.flushdb()
        except ConnectionError as e:
            print("Redis server not running: exiting")
            print(e)
            exit()
        for process in processes:
            logger.log(LogType.info.value, 'Starting process {}'.format(process.PROCESS_NAME))
            process.daemon = True
            process.start()
        logger.log(LogType.info.value, 'All Processes Started!')
        signal(SIGINT, default_handler)
        # a subprocess may set the exit event
        while not exit_event.is_set():
            log(logger_queue)
        logger.log(LogType.info.value, 'Restart Event Set')
        restart_event_bool = True
    except KeyboardInterrupt as e:
        exit_event.set()
        logger.log(LogType.info.value, 'Exit Event Set Via KeyboardInterrupt {}'.format(e))
    except Exception as e:
        logger.log(LogType.info.value, 'Exit Event Set via {}'.format(e))
        exit_event.set()
        logger.log(LogType.info.value, 'Restart Event Set')
        restart_event_bool = True
    finally:
        # flush logs
        logger.log(LogType.info.value, 'Exit Process Initiated')
        logger.log(LogType.info.value, 'Shutting Down Gracefully')
        while not logger_queue.empty():
            log(logger_queue, batch_size=100)
        # flush queues just in case
        for queue in comm_queues:
            while not queue.empty():
                try:
                    queue.get(block=False)
                except queues.Empty:
                    pass
        for process in processes:
            logger.log(LogType.info.value, 'Joining Process {}'.format(process.PROCESS_NAME))
            process.join()
            logger.log(LogType.info.value, 'Process {} Joined!'.format(process.PROCESS_NAME))
        logger.log(LogType.info.value, 'All Processes Joined')
        return restart_event_bool


if __name__ == '__main__':
    while True:
        reset = main()
        print('Reset: {}'.format(reset))
        if not reset:
            exit()
