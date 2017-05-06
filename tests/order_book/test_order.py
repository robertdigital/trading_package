from trading_package.helper.enums import OrderSide
from trading_package.order_book.order import Order
import unittest


class OrderTestCase(unittest.TestCase):
    def test_that_orders_work_as_expect(self):
        o = Order('BTC-USD', 0, OrderSide.bid, '0.1', '100')
        assert o.get_product_id() == 'BTC-USD'
        assert o.get_sequence_id() == 0
        assert o.get_order_side() == OrderSide.bid
        assert o.get_size() == '0.1'
        assert o.get_price() == '100'
        o.add_filled_size('0.05')
        assert o.get_remaining_size() == '0.05'

if __name__ == '__main__':
    unittest.main()
