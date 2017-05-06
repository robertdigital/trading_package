from datetime import datetime
from decimal import Decimal
from dateutil import tz
from trading_package.helper.enums import *
from typing import Dict, Union, Optional


class OrderException(Exception):
    pass


class Order:
    def __init__(self, product_id: str, sequence_id: int, order_side: OrderSide, size: str, price: str,
                 status: OrderStatus = OrderStatus.open, order_id: str = None, order_type: OrderType = OrderType.limit,
                 created_at: Optional[datetime] = None, historical: bool = False, confirmed: bool = False):
        self.product_id = product_id
        self.order_side = order_side
        self.order_type = order_type
        self.status = status
        self.sequence_id = int(sequence_id)
        self.size = size
        self.filled_size = '0'
        self.price = str(price)
        self.order_id = order_id
        if created_at is None:
            self.created_at = datetime.now(tz.tzutc())
        else:
            # orders cannot be created in the future please
            self.created_at = min(datetime.now(tz.tzutc()), created_at)
        self.historical = historical
        self.confirmed = confirmed
        if float(self.size) < 0:
            raise OrderException('Order size must be positive {}'.format(self.size))

    def get_historical(self) -> bool:
        return self.historical

    def get_confirmed(self) -> bool:
        return self.confirmed

    def set_confirmed(self, confirmed: bool) -> bool:
        self.confirmed = confirmed
        return self.confirmed

    def get_created_at(self) -> datetime:
        return self.created_at

    def get_unix_timestamp(self) -> str:
        return self.created_at.strftime('%s')

    def get_created_at_seconds_ago(self, now_time=None) -> int:
        now_time = datetime.now(tz.tzutc()) if now_time is None else now_time
        created_at_seconds_ago = (now_time - self.get_created_at()).seconds
        return created_at_seconds_ago

    def get_order_type(self) -> OrderType:
        return self.order_type

    def get_filled_size(self) -> str:
        return self.filled_size

    def add_filled_size(self, qty: str) -> str:
        self.filled_size = str(Decimal(self.filled_size) + Decimal(qty))
        return self.filled_size

    def get_remaining_size(self) -> str:
        return str(Decimal(self.size) - Decimal(self.filled_size))

    def get_sequence_id(self) -> int:
        return self.sequence_id

    def get_order_id(self) -> str:
        return self.order_id

    def get_status(self) -> OrderStatus:
        return self.status

    def update_status(self, status: OrderStatus) -> OrderStatus:
        self.status = status
        return self.get_status()

    def get_product_id(self) -> str:
        return self.product_id

    def get_price(self) -> str:
        return self.price

    def get_order_side(self) -> OrderSide:
        return self.order_side

    def get_size(self) -> str:
        return self.size

    def get_gdax_order_params(self) -> Dict[str, Union[bool, str]]:
        return {
            'price': str(self.get_price()),
            'size': str(self.get_size()),
            'product_id': str(self.get_product_id()),
            'time_in_force': 'GTC',
            'post_only': True
        }

    def __str__(self) -> str:
        return '{}-{}-{}-{}-{}-{}'.format(
            self.get_product_id(), self.get_size(), self.get_order_side(), self.get_price(), self.get_order_type(),
            self.get_status()
        )

    def __repr__(self) -> str:
        return self.__str__()
