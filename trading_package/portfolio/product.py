from decimal import Decimal, ROUND_DOWN, ROUND_HALF_EVEN
from typing import Set, List, Dict, Optional

from trading_package.helper.enums import *


class ProductException(Exception):
    pass


class Product:
    def __init__(self, product_id: str, quote_currency: Currency, base_currency: Currency, quote_increment: str,
                 base_min_size: str) -> None:
        self.product_id = product_id
        self.quote_currency = quote_currency
        self.base_currency = base_currency
        self.quote_increment = Decimal(quote_increment)
        self.base_min_size = Decimal(base_min_size)
        self.currency_pair = {
            OrderSide.bid: {
                'source': self.quote_currency,
                'destination': self.base_currency
            },
            OrderSide.ask: {
                'source': self.base_currency,
                'destination': self.quote_currency
            }
        }

    def get_base_min_size_str(self) -> str:
        return str(self.base_min_size)

    def get_base_min_size_dec(self) -> str:
        return self.base_min_size

    def get_quote_increment(self) -> str:
        return str(self.quote_increment)

    def get_currency_set(self) -> Set[Currency]:
        return {self.quote_currency, self.base_currency}

    def has_currency(self, currency: Currency) -> bool:
        return currency in self.get_currency_set()

    def get_product_id(self) -> str:
        return self.product_id

    def get_currency_pair(self) -> Dict[OrderSide, Dict[str, Currency]]:
        return self.currency_pair

    def get_source_currency(self, order_side: OrderSide) -> Currency:
        return self.currency_pair[order_side]['source']

    def get_destination_currency(self, order_side: OrderSide) -> Currency:
        return self.currency_pair[order_side]['destination']

    def get_quote_price_currency(self) -> Currency:
        return self.quote_currency

    def get_quote_quantity_currency(self) -> Currency:
        return self.base_currency

    def get_side_from_currency_direction(self, source_currency: Currency,
                                         destination_currency: Currency) -> Optional[OrderSide]:
        if not self.get_currency_set() == {source_currency, destination_currency}:
            return None
        for side in OrderSide:
            if self.get_source_currency(side) == source_currency:
                return side

    def convert_currency_price_to_quote_price(self, currency: Currency, price: float) -> float:
        return self.convert_quote_price_to_currency_price(currency, price)

    def convert_quote_price_to_currency_price(self, currency: Currency, price: float) -> float:
        if self.get_quote_price_currency() == currency:
            return price
        else:
            return 1.0 / price

    def get_lower_price(self, price: str) -> Decimal:
        lower_price = Decimal(price).quantize(self.quote_increment, rounding=ROUND_HALF_EVEN) - self.quote_increment
        return lower_price

    def get_higher_price(self, price: str) -> Decimal:
        higher_price = Decimal(price).quantize(self.quote_increment, rounding=ROUND_HALF_EVEN) + self.quote_increment
        return higher_price

    # Note that this rounds down
    def round_quantity(self, quantity: str, rounding=ROUND_DOWN) -> Decimal:
        return Decimal(quantity).quantize(self.base_min_size, rounding=rounding)

    def round_price(self, price: str) -> Decimal:
        return Decimal(price).quantize(self.quote_increment, rounding=ROUND_HALF_EVEN)

    def get_quote_quantity_from_currency_quantity(self, currency: Currency, quantity: str, quote_price: str) -> Decimal:
        if self.get_quote_quantity_currency() == currency:
            return Decimal(quantity)
        else:
            return Decimal(quantity) / Decimal(quote_price)

    def get_currency_quantity_from_quote_quantity(self, currency: Currency, quantity: str, quote_price: str) -> Decimal:
        if self.get_quote_quantity_currency() == currency:
            return Decimal(quantity)
        else:
            return Decimal(quantity) * Decimal(quote_price)


class ProductManager:
    def __init__(self) -> None:
        self.product_by_product_id = {}
        self.currencies = {}

    def get_product(self, product_id: str) -> Optional[Product]:
        try:
            return self.product_by_product_id[product_id]
        except KeyError:
            return None

    def get_product_ids(self) -> List[str]:
        return list(self.product_by_product_id.keys())

    def get_product_from_currencies(self, source_currency: Currency, destination_currency: Currency) -> Optional[
        Product]:
        currency_set = {source_currency, destination_currency}
        for product_id, product in self.product_by_product_id.items():
            if product.get_currency_set() == currency_set:
                return product
        # this means there was no match and should never happen
        return None

    def get_side_from_currency_direction(self, source_currency: Currency, destination_currency: Currency) -> OrderSide:
        product = self.get_product_from_currencies(source_currency, destination_currency)
        return product.get_side_from_currency_direction(source_currency, destination_currency)

    def get_currencies(self) -> Set[Currency]:
        currencies = set()
        for product in self.product_by_product_id.values():
            currencies |= product.get_currency_set()
        return currencies

    def __add__(self, product: Product) -> None:
        self.product_by_product_id[product.get_product_id()] = product

    def __sub__(self, product: Product) -> None:
        try:
            del self.product_by_product_id[product.get_product_id()]
        except KeyError:
            pass

    def set_currency(self, currency: Currency, min_size: str) -> None:
        self.currencies[currency] = Decimal(min_size)

    def get_min_size(self, currency: Currency) -> Optional[Decimal]:
        if currency in self.currencies:
            return self.currencies[currency]
        else:
            return None

