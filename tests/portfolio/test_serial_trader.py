# from trading_package.portfolio.product import Product, ProductManager
# from trading_package.order_book.order import Order
# from trading_package.portfolio.portfolio import Portfolio
# from trading_package.portfolio.serial_trader import PortfolioGroup
# from trading_package.portfolio.portfolio_order_book import PortfolioOrderBook
# from trading_package.order_book.order_book import OrderBookManager
# from trading_package.helper.enums import Currency, OrderSide, OrderType, QuoteType, EdgeType
# import unittest
#
#
# def generate_objects(product_manager):
#     order_book = PortfolioOrderBook(product_manager)
#     portfolio_group = PortfolioGroup(order_book)
#     for currency in product_manager.get_currencies():
#         portfolio = Portfolio(currency, '100')
#         portfolio_group + portfolio
#     return order_book, portfolio_group
#
#
# class PortfolioTestCase(unittest.TestCase):
#     product_a = Product(product_id='BTC-USD', quote_currency=Currency.USD, base_currency=Currency.BTC,
#                         quote_increment='0.01',
#                         base_min_size='0.01')
#     product_b = Product(product_id='LTC-BTC', quote_currency=Currency.BTC, base_currency=Currency.LTC,
#                         quote_increment='0.0001',
#                         base_min_size='0.0001')
#     product_c = Product(product_id='LTC-USD', quote_currency=Currency.USD, base_currency=Currency.LTC,
#                         quote_increment='0.01',
#                         base_min_size='0.01')
#     product_manager = ProductManager()
#     product_manager + product_a
#     product_manager + product_b
#     product_manager + product_c
#
#     def test_get_orders(self):
#         order_book, portfolio_group = generate_objects(self.product_manager)
#         portfolio_group.get_portfolio_from_currency(Currency.BTC) - Portfolio(Currency.BTC, '99.9')
#         portfolio_group.get_portfolio_from_currency(Currency.LTC) - Portfolio(Currency.LTC, '90')
#         ob = OrderBookManager(self.product_manager)
#
#         # add current best bid and ask
#         ob + Order('BTC-USD', 0, OrderSide.bid, '10', '1009.0')
#         ob + Order('BTC-USD', 0, OrderSide.ask, '10', '1010.0')
#         ob + Order('LTC-USD', 0, OrderSide.bid, '10', '10.1')
#         ob + Order('LTC-USD', 0, OrderSide.ask, '10', '10.2')
#         ob + Order('LTC-BTC', 0, OrderSide.bid, '10', '0.01')
#         ob + Order('LTC-BTC', 0, OrderSide.ask, '10', '0.011')
#
#         # add historical orders
#         ob + Order('BTC-USD', 0, OrderSide.bid, '1', '1009.0', order_type=OrderType.match, historical=True)
#         ob + Order('BTC-USD', 0, OrderSide.ask, '1', '1010.0', order_type=OrderType.match, historical=True)
#         ob + Order('LTC-USD', 0, OrderSide.bid, '1', '10.1', order_type=OrderType.match, historical=True)
#         ob + Order('LTC-USD', 0, OrderSide.ask, '1', '10.2', order_type=OrderType.match, historical=True)
#         ob + Order('LTC-BTC', 0, OrderSide.bid, '1', '0.01', order_type=OrderType.match, historical=True)
#         ob + Order('LTC-BTC', 0, OrderSide.ask, '1', '0.011', order_type=OrderType.match, historical=True)
#
#         ob.update_network_manager()
#         cycles_by_val = ob.get_network_manager().get_cycles_for_currency_by_value(EdgeType.median, QuoteType.currency,
#                                                                                   Currency.USD)
#         orders = portfolio_group.get_next_trades()
#         orders_str = set(map(str, orders))
#         print(orders_str)
#         # assert orders_str == ['LTC-USD-1.00-OrderSide.ask-10.19-OrderType.limit-OrderStatus.open', 'BTC-USD-0.02-OrderSide.ask-1009.99-OrderType.limit-OrderStatus.open']
#         assert orders_str == {'LTC-BTC-1.0000-OrderSide.ask-0.0109-OrderType.limit-OrderStatus.open',
#                               'LTC-USD-1.00-OrderSide.bid-10.11-OrderType.limit-OrderStatus.open',
#                               'BTC-USD-0.10-OrderSide.ask-1009.99-OrderType.limit-OrderStatus.open'}
#
#
# if __name__ == '__main__':
#     unittest.main()
