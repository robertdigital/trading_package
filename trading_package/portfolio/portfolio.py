from datetime import datetime
from decimal import Decimal
from typing import Dict, Tuple, List, Optional

from dateutil import tz
from redis import StrictRedis

from trading_package.config.constants import *
from trading_package.helper.enums import Currency, OrderStatus
from trading_package.order_book.order import Order
from trading_package.order_book.order_book import OrderBookManager
from trading_package.portfolio.portfolio_order_book import PortfolioOrderBook


class PortfolioException(Exception):
    pass


class Portfolio:
    def __init__(self, currency: Currency, qty: str = 0, min_fraction: Optional[str] = None,
                 max_fraction: Optional[str] = None) -> None:
        self.persistent_redis_server = StrictRedis(host='localhost', port=6379, db=1)
        self.currency = currency
        self.qty = Decimal(qty)

        try:
            self.min_fraction = min_fraction or PORTFOLIO_MAKEUP[currency.name][0]
        except (KeyError, IndexError):
            self.min_fraction = '0.0'
        self.min_fraction = Decimal(self.min_fraction)

        try:
            self.max_fraction = max_fraction or PORTFOLIO_MAKEUP[currency.name][1]
        except (KeyError, IndexError):
            self.max_fraction = '1.0'
        self.max_fraction = Decimal(self.max_fraction)

    def get_max_fraction(self) -> Decimal:
        redis_fraction = self.persistent_redis_server.get('portfolio:max_fraction:{}'.format(self.get_currency().name))
        return Decimal(redis_fraction) if redis_fraction else self.max_fraction

    def get_min_fraction(self) -> Decimal:
        redis_fraction = self.persistent_redis_server.get('portfolio:min_fraction:{}'.format(self.get_currency().name))
        return Decimal(redis_fraction) if redis_fraction else self.min_fraction

    def get_currency(self) -> Currency:
        return self.currency

    def get_qty(self) -> Decimal:
        return self.qty

    def validate_portfolio(self, portfolio) -> bool:
        if portfolio.get_currency() != self.get_currency():
            raise PortfolioException(
                'Cannot add portfolios of different currencies: {} {}'.format(portfolio.get_currency(),
                                                                              self.get_currency())
            )
        else:
            return True

    def __add__(self, portfolio) -> Decimal:
        self.validate_portfolio(portfolio)
        self.qty = self.qty + portfolio.get_qty()
        return self.qty

    def __sub__(self, portfolio) -> Decimal:
        self.validate_portfolio(portfolio)
        self.qty = self.qty - portfolio.get_qty()
        return self.qty

    def __str__(self) -> str:
        output = [self.get_currency(), self.get_qty()]
        output = [str(o) for o in output]
        return '-'.join(output)

    def __repr__(self) -> str:
        return self.__str__()


class BasePortfolioGroup:
    def __init__(self, order_book: PortfolioOrderBook) -> None:
        self.redis_server = StrictRedis(host='localhost', port=6379, db=0)
        # persistent db is not cleared
        self.persistent_redis_server = StrictRedis(host='localhost', port=6379, db=1)
        # this is just the portfolio order book (my orders)
        self.order_book = order_book
        self.portfolios = {currency: Portfolio(currency) for currency in self.order_book.get_currencies()}
        # this is the actual order book
        self.order_book_manager = OrderBookManager(self.order_book.product_manager)

    def get_balance_qty(self, currency: Currency) -> Decimal:
        return self.get_portfolio_from_currency(currency).get_qty()

    def get_available_qty(self, currency: Currency) -> Decimal:
        total_qty = self.portfolios[currency].get_qty()
        hold_qty = self.order_book.get_hold_qty(currency)

        available_qty = total_qty - hold_qty
        self.redis_server.set('portfolio:available:{}'.format(currency.name), available_qty)
        return available_qty

    def get_balances(self) -> Dict[Currency, Decimal]:
        quantities_by_currency = {}
        for currency, portfolio in self.portfolios.items():
            balance_qty = self.get_balance_qty(currency)
            quantities_by_currency[currency] = balance_qty
        return quantities_by_currency

    def get_valuation(self) -> Tuple[Dict[Currency, Tuple[Decimal, Decimal]], Decimal]:
        balances = self.get_balances()
        return self.order_book_manager.network_manager.value_portfolio(balances, Currency.USD)

    def get_available_currencies_for_trade(self) -> Dict[Currency, Decimal]:
        quantities_by_currency = {}
        for currency, portfolio in self.portfolios.items():
            avail_qty = self.get_available_qty(currency)
            min_qty = self.order_book.product_manager.get_min_size(currency)
            if min_qty is None or avail_qty >= min_qty:
                quantities_by_currency[currency] = avail_qty
            else:
                quantities_by_currency[currency] = Decimal('0.')
        return quantities_by_currency

    def get_portfolio_from_currency(self, currency: Currency) -> Portfolio:
        return self.portfolios[currency]

    def get_next_trades(self) -> List[Order]:
        raise PortfolioException('Not Implemented')

    def handle_match_order(self, order_id: str, fill_qty: str) -> str:
        order, status = self.order_book.get_order_and_status_by_id(order_id)
        side = order.get_order_side()
        # this increments the order fill size
        self.order_book.match_order(order.get_order_id(), fill_qty)

        product = self.order_book.product_manager.get_product(order.get_product_id())
        source_currency = product.get_source_currency(side)
        destination_currency = product.get_destination_currency(side)
        source_qty = product.get_currency_quantity_from_quote_quantity(source_currency,
                                                                       fill_qty,
                                                                       order.get_price())
        destination_qty = product.get_currency_quantity_from_quote_quantity(destination_currency,
                                                                            fill_qty,
                                                                            order.get_price())
        # this adds destination currency and removes source currency
        destination_portfolio = Portfolio(destination_currency,
                                          destination_qty)
        source_portfolio = Portfolio(source_currency,
                                     source_qty)
        self + destination_portfolio
        self - source_portfolio
        return order_id

    def handle_done_order(self, order_id: str, order_status: OrderStatus):
        if order_status == OrderStatus.filled:
            self.order_book.fill_order(order_id)
        elif order_status == OrderStatus.canceled:
            self.order_book.cancel_order(order_id)
        else:
            raise PortfolioException('Done order must have status filled or canceled: {}'.format(order_status))
        return order_id

    def __add__(self, other_portfolio: Portfolio) -> Decimal:
        portfolio = self.get_portfolio_from_currency(other_portfolio.get_currency())
        portfolio + other_portfolio
        self.redis_server.set('portfolio:balance:{}'.format(portfolio.get_currency().name), portfolio.get_qty())
        self.persistent_redis_server.zadd('portfolio:balance:{}'.format(portfolio.get_currency().name),
                                          datetime.now(tz.tzutc()).strftime('%s'), portfolio.get_qty())
        return portfolio.get_qty()

    def __sub__(self, other_portfolio: Portfolio) -> Decimal:
        portfolio = self.get_portfolio_from_currency(other_portfolio.get_currency())
        portfolio - other_portfolio
        self.redis_server.set('portfolio:balance:{}'.format(portfolio.get_currency().name), portfolio.get_qty())
        self.persistent_redis_server.zadd('portfolio:balance:{}'.format(portfolio.get_currency().name),
                                          datetime.now(tz.tzutc()).strftime('%s'), portfolio.get_qty())
        return portfolio.get_qty()

    def __str__(self) -> str:
        portfolio_strings = []
        for currency, portfolio in self.portfolios.items():
            portfolio_o = [portfolio, self.get_available_qty(portfolio.get_currency())]
            portfolio_o = [str(o) for o in portfolio_o]
            portfolio_strings.append('-'.join(portfolio_o))
        return '\n'.join(portfolio_strings)

    def __repr__(self) -> str:
        return self.__str__()
