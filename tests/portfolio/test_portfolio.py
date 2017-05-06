from trading_package.portfolio.product import Product, ProductManager
from trading_package.order_book.order import Order
from trading_package.portfolio.portfolio import Portfolio, BasePortfolioGroup
from trading_package.portfolio.portfolio_order_book import PortfolioOrderBook
from trading_package.order_book.order_book import OrderBookManager
from trading_package.helper.enums import Currency, OrderStatus, OrderSide, OrderType, QuoteType, EdgeType
import unittest


def generate_objects(product_manager):
    order_book = PortfolioOrderBook(product_manager)
    portfolio_group = BasePortfolioGroup(order_book)
    for currency in product_manager.get_currencies():
        portfolio = Portfolio(currency, '100')
        portfolio_group + portfolio
    return order_book, portfolio_group


class PortfolioTestCase(unittest.TestCase):
    product_a = Product(product_id='BTC-USD', quote_currency=Currency.USD, base_currency=Currency.BTC, quote_increment='0.01',
                        base_min_size='0.01')
    product_b = Product(product_id='LTC-BTC', quote_currency=Currency.BTC, base_currency=Currency.LTC, quote_increment='0.0001',
                        base_min_size='0.0001')
    product_c = Product(product_id='LTC-USD', quote_currency=Currency.USD, base_currency=Currency.LTC, quote_increment='0.01',
                        base_min_size='0.01')
    product_manager = ProductManager()
    product_manager + product_a
    product_manager + product_b
    product_manager + product_c

    def test_that_creating_an_order_reduces_available_qty(self):
        order_book, portfolio_group = generate_objects(self.product_manager)
        order = Order('BTC-USD', 0, OrderSide.bid, '1', '10.0', order_id='1')
        order_book + order
        assert portfolio_group.get_available_qty(Currency.USD) == 90
        assert portfolio_group.get_available_qty(Currency.BTC) == 100

    def test_order_match(self):
        order_book, portfolio_group = generate_objects(self.product_manager)
        order = Order('BTC-USD', 0, OrderSide.bid, '1', '10.0', order_id='1')
        order_book + order
        portfolio_group.handle_match_order('1', '0.5')
        assert portfolio_group.get_available_qty(Currency.USD) == 90
        assert portfolio_group.get_available_qty(Currency.BTC) == 100.5

    def test_order_fill(self):
        order_book, portfolio_group = generate_objects(self.product_manager)
        order = Order('BTC-USD', 0, OrderSide.bid, '1', '10.0', order_id='1')
        order_book + order
        portfolio_group.handle_match_order('1', '1')
        portfolio_group.handle_done_order('1', OrderStatus.filled)
        assert portfolio_group.get_available_qty(Currency.USD) == 90
        assert portfolio_group.get_available_qty(Currency.BTC) == 101

    def test_order_cancellation(self):
        order_book, portfolio_group = generate_objects(self.product_manager)
        order = Order('BTC-USD', 0, OrderSide.bid, '1', '10.0', order_id='1')
        order_book + order
        portfolio_group.handle_done_order('1', OrderStatus.canceled)
        assert portfolio_group.get_available_qty(Currency.USD) == 100
        assert portfolio_group.get_available_qty(Currency.BTC) == 100


if __name__ == '__main__':
    unittest.main()
