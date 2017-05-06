from trading_package.portfolio.product import Product, ProductManager
from trading_package.helper.enums import OrderSide, Currency
from decimal import Decimal
import unittest


class ProductTestCase(unittest.TestCase):
    product_id = 'BTC-USD'
    product = Product(product_id=product_id, quote_currency=Currency.USD, base_currency=Currency.BTC,
                      quote_increment='0.01', base_min_size='0.01')
    product_manager = ProductManager()
    product_manager + product

    def test_currency_set(self):
        assert self.product.get_currency_set() == {Currency.USD, Currency.BTC}

    def test_get_source_currency(self):
        assert self.product.get_source_currency(OrderSide.bid) == Currency.USD
        assert self.product.get_source_currency(OrderSide.ask) == Currency.BTC

    def test_get_side_from_currency_direction(self):
        assert self.product.get_side_from_currency_direction(Currency.USD, Currency.BTC) == OrderSide.bid
        assert self.product.get_side_from_currency_direction(Currency.BTC, Currency.USD) == OrderSide.ask

    def test_convert_quote_price_to_currency_price(self):
        assert self.product.convert_quote_price_to_currency_price(Currency.BTC, 1000.0) == 0.001
        assert self.product.convert_quote_price_to_currency_price(Currency.USD, 1000.0) == 1000.0

    def test_get_diff_price(self):
        assert self.product.get_lower_price('1000.0') == Decimal('999.99')
        assert self.product.get_higher_price('1000.0') == Decimal('1000.01')

    def test_round_qty(self):
        assert self.product.round_quantity('10.00000042') == Decimal('10.00')

    def test_convert_qty(self):
        assert self.product.get_quote_quantity_from_currency_quantity(Currency.USD, '1050.01', '1000.0') == Decimal(
            '1.05001')
        assert self.product.get_currency_quantity_from_quote_quantity(Currency.USD, '1.01', '1000.0') == Decimal('1010')

    def test_product_manager(self):
        assert self.product_manager.get_currencies() == {Currency.USD, Currency.BTC}


if __name__ == '__main__':
    unittest.main()
