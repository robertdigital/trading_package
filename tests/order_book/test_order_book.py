from trading_package.order_book.order import Order
from trading_package.order_book.order_book import OrderBook
from trading_package.helper.enums import OrderSide, OrderStatus, OrderType
from trading_package.portfolio.product import Product
from trading_package.helper.enums import Currency
import unittest


class OrderBookTestCase(unittest.TestCase):
    def test_that_order_book_works_as_expected(self):
        product_id = 'BTC-USD'
        product = Product(product_id=product_id, quote_currency=Currency.USD, base_currency=Currency.BTC,
                          quote_increment='0.01', base_min_size='0.01')
        ob = OrderBook(product)
        # test empty order book
        assert (ob.get_product_id() == product_id)
        assert (ob.orders_added == 0)
        assert (ob.orders_subtracted == 0)

        def get_price(side):
            price = 20 if side == OrderSide.ask else 10
            return str(price)

        def get_better_price(s, i=0):
            price = int(get_price(s)) - 1 - i if s == OrderSide.ask else int(get_price(s)) + 1 + i
            return str(price)

        def get_worse_price(s, i=0):
            price = int(get_price(s)) + 1 + i if s == OrderSide.ask else int(get_price(s)) - 1 - i
            return str(price)

        def get_other_side(s):
            return OrderSide.bid if s == OrderSide.ask else OrderSide.ask

        for side in OrderSide:
            ob = OrderBook(product)
            ob.redis_server.flushdb()

            # test adding base set of orders
            order = Order(product_id, 0, get_other_side(side), '1.0', get_price(get_other_side(side)), order_id='0')
            ob + order
            order = Order(product_id, 0, side, '1.0', get_price(side), order_id='1')
            ob + order
            order = Order(product_id, 0, side, '1.0', get_worse_price(side), order_id='2')
            ob + order

            # test matching and filling an order at best price
            order = Order(product_id, 0, side, '1.0', get_price(side), order_type=OrderType.match, order_id='1')
            ob - order
            order = Order(product_id, 0, side, '0', get_price(side), order_type=OrderType.match,
                          status=OrderStatus.filled,
                          order_id='1')
            ob - order
            assert ob.get_best(side) == float(get_worse_price(side))
            assert ob.get_median_trade_size(side, OrderType.match, 10, 1) == 1.

            # test adding an order at a worse price
            order = Order(product_id, 0, side, '1.0', get_worse_price(side, 1), order_id='3')
            ob + order
            assert (ob.get_best(side) == float(get_worse_price(side)))
            assert ob.get_price(side, 2) == (
                float(get_worse_price(side)), float(get_worse_price(side, 1)), float(get_worse_price(side)) + float(get_worse_price(side, 1)), 0.,
                1.)

            # test cancelling order at best price
            order = Order(product_id, 0, side, '1.0', get_worse_price(side), order_id='2', order_type=OrderType.cancel,
                          status=OrderStatus.canceled)
            ob - order
            assert (ob.get_best(side) == float(get_worse_price(side, 1)))

            # test changing order at best price
            order = Order(product_id, 0, side, '1', get_worse_price(side, 1), order_id='3', order_type=OrderType.change)
            order.add_filled_size('0.5')
            ob - order
            assert (ob.get_best(side) == float(get_worse_price(side, 1)))

            # test cancelling order with unrecognized order id
            order = Order(product_id, 0, side, '4', get_worse_price(side), order_id='1e2', order_type=OrderType.cancel,
                          status=OrderStatus.canceled)
            ob - order
            assert (ob.get_best(side) == float(get_worse_price(side, 1)))

            assert (ob.get_best(get_other_side(side)) == float(get_price(get_other_side(side))))


if __name__ == '__main__':
    unittest.main()
