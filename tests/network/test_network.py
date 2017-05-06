from trading_package.network.network import NetworkManager
from networkx import get_edge_attributes
from trading_package.order_book.order_book import OrderBook, Order
from trading_package.helper.enums import OrderSide, OrderType, Currency, NetworkType, EdgeType, QuoteType
from trading_package.portfolio.product import Product
import unittest


class NetworkTestCase(unittest.TestCase):
    def test_that_network_correctly_computes_edges(self):
        def get_price(side):
            price = 400 if side == OrderSide.ask else 100
            return str(price)

        def get_worse_price(s, i=0):
            price = float(get_price(s)) + 50 + i if s == OrderSide.ask else float(get_price(s)) - 50 - i
            return str(price)

        def get_better_price(s, i=0):
            price = float(get_price(s)) - 50 - i if s == OrderSide.ask else float(get_price(s)) + 50 + i
            return str(price)

        product_id = 'BTC-USD'
        product = Product(product_id=product_id, quote_currency=Currency.USD, base_currency=Currency.BTC, quote_increment='0.01', base_min_size='0.01')

        ob = OrderBook(product)
        ob.redis_server.flushdb()
        nm = NetworkManager()
        for side in OrderSide:
            # test adding base set of orders
            for idx, price in enumerate([get_price(side), get_better_price(side), get_worse_price(side)]):
                order = Order(product_id, 0, side, '1.0', price, order_id=str(idx))
                ob + order
                order.historical = True
                order.order_type = OrderType.match
                order.size = '0.5'
                ob - order
            assert ob.get_price(side, 0)[1] == float(get_better_price(side))
            assert ob.get_median_trade_size(side, OrderType.match, 100) == 1.5
            assert ob.get_average_trade_size(side, OrderType.match, 100) == 1.5
            nm.update_from_order_book(ob, side)
        # print(get_edge_attributes(nm.get_network(NetworkType.price, quote_type=QuoteType.product, edge_type=EdgeType.mean), 'weight'))
        # print(nm.get_next_nodes_and_avail_qties_by_cycle_value(EdgeType.mean, Currency.USD), {
        #     2.3331111259249386: (Currency.BTC, '150.01', '1.5')})
        assert nm.get_next_nodes_and_avail_qties_by_cycle_value(EdgeType.mean, Currency.USD) == {
            2.3331111259249386: (Currency.BTC, '150.01', '1.5')}
        assert nm.get_next_nodes_and_avail_qties_by_cycle_value(EdgeType.mean, Currency.BTC) == {
            2.3331111259249386: (Currency.USD, '349.99', '1.5')}

if __name__ == '__main__':
    unittest.main()