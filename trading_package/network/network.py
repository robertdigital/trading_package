from decimal import Decimal
from typing import Dict, Tuple, List, Optional

from networkx import DiGraph, simple_cycles, get_edge_attributes
from numpy import prod
from redis import StrictRedis

from trading_package.config.constants import *
from trading_package.helper.enums import *


class NetworkManager:
    def __init__(self):
        self.redis_server = StrictRedis(host='localhost', port=6379, db=0, encoding="utf-8", decode_responses=True)

    def get_network(self, network_type: NetworkType, edge_type: EdgeType, quote_type: QuoteType) -> DiGraph:
        network_keys = self.redis_server.keys(self.get_redis_key(network_type, edge_type, quote_type) + '*')
        pipe = self.redis_server.pipeline()
        for network_key in network_keys:
            pipe.hgetall(network_key)
        res = pipe.execute()
        dg = DiGraph()
        for idx, val in enumerate(network_keys):
            start_currency = val.split(':')[-1]
            for end_currency, weight in res[idx].items():
                edge_weight = weight
                end_currency = end_currency
                dg.add_edge(start_currency, end_currency, weight=edge_weight)
        return dg

    # Portfolio hash is {currency_enum: currency_qty}
    # Return is ({currency_enum: (final_currency_qty, edge_val)}, total_qty)
    def value_portfolio(self, portfolio_hash: Dict[Currency, Decimal], final_currency: Currency) -> Tuple[
        Dict[Currency, Tuple[Decimal, Decimal]], Decimal]:
        fc = final_currency.name
        dg = self.get_network(NetworkType.price, EdgeType.best, QuoteType.currency)
        return_hash = {}
        total_qty = Decimal('0')
        for currency, qty in portfolio_hash.items():
            c = currency.name
            if c == fc:
                total_qty = total_qty + qty
                return_hash[currency] = (qty, Decimal(1.0))
                continue
            try:
                edge_val = Decimal(dg[c][fc]['weight'])
                final_qty = edge_val * qty
                return_hash[currency] = (final_qty, edge_val)
                total_qty = total_qty + final_qty
            except KeyError:
                pass
        return return_hash, total_qty

    def add_edge(self, edge_type: EdgeType, quote_type: QuoteType, start_currency: Currency, end_currency: Currency,
                 weight: float,
                 qty: float = 1e9) -> None:
        price_key_val = self.get_redis_key(NetworkType.price, edge_type, quote_type, start_currency)
        self.redis_server.hset(price_key_val, end_currency.name, weight)
        qty_key_val = self.get_redis_key(NetworkType.quantity, edge_type, quote_type, start_currency)
        self.redis_server.hset(qty_key_val, end_currency.name, qty)

    # TODO maybe dont index by cycle value because they will overwrite on another. Should at the least
    # be a list
    def get_cycles_by_value(self, edge_type: EdgeType, quote_type: QuoteType) -> Dict[float, List[str]]:
        dg = self.get_network(NetworkType.price, edge_type, quote_type)
        weights = get_edge_attributes(dg, 'weight')
        cycle_vals = {}
        for cycle in simple_cycles(dg):
            # sort the currencies in cycle for long term sanity
            best_curr = max(cycle, key=lambda x: Currency[x].value)
            best_curr_ind = cycle.index(best_curr)
            cycle = [cycle[best_curr_ind]] + cycle[(best_curr_ind + 1):] + cycle[:best_curr_ind]
            cycle.append(cycle[0])
            prodw = [float(weights[(cycle[i], cycle[i + 1])]) for i in range(len(cycle) - 1)]
            prodw = prod(prodw)
            cycle_vals[prodw] = cycle
        return cycle_vals

    def get_cycles_for_currency_by_value(self, edge_type: EdgeType, quote_type: QuoteType, start_currency: Currency) -> \
            Dict[float, List[str]]:
        cycles_by_val = self.get_cycles_by_value(edge_type, quote_type)
        output = {}
        for cycle_val, cycle in cycles_by_val.items():
            if start_currency.name not in cycle:
                continue
            output[cycle_val] = cycle
        return output

    @staticmethod
    def get_next_node_in_cycle(cycle: List[str], start_currency: Currency) -> Currency:
        return Currency[cycle[cycle.index(start_currency.name) + 1]]

    @staticmethod
    def get_redis_key(network_type: NetworkType, edge_type: EdgeType, quote_type: QuoteType,
                      start_currency: Optional[Currency] = None) -> str:
        currency = '' if start_currency is None else start_currency.name
        return ':'.join(
            ['network', network_type.name, edge_type.name,
             quote_type.name, currency])

    def get_edge_weight(self, edge_type: EdgeType, quote_type: QuoteType, start_currency: Currency,
                        destination_currency: Currency,
                        network_type: NetworkType = NetworkType.price) -> Optional[float]:
        key_val = self.get_redis_key(network_type, edge_type, quote_type, start_currency)
        edge_weight = self.redis_server.hget(key_val, destination_currency.name)
        if edge_weight is None:
            return None
        return edge_weight

    # this return {[cycle_value]: (next_node, edge_weight_product, edge_qty_product)}
    def get_next_nodes_and_avail_qties_by_cycle_value(self, edge_type: EdgeType, start_currency: Currency) -> Dict[
        float, Tuple[Currency, float, float]]:
        cycles = self.get_cycles_for_currency_by_value(edge_type, QuoteType.currency, start_currency)
        output = {}
        for cycle_val in sorted(cycles):
            cycle = cycles[cycle_val]
            next_node = self.get_next_node_in_cycle(cycle, start_currency)
            edge_weight = self.get_edge_weight(edge_type, QuoteType.product, start_currency, next_node,
                                               NetworkType.price)
            avail_qty = self.get_edge_weight(edge_type, QuoteType.product, start_currency, next_node,
                                             NetworkType.quantity)
            output[cycle_val] = (next_node, edge_weight, avail_qty)
        return output

    def update_edge_type(self, order_book, side: OrderSide, edge_type: EdgeType) -> None:
        product = order_book.product
        source_currency = product.get_source_currency(side)
        destination_currency = product.get_destination_currency(side)
        if edge_type is EdgeType.best:
            price = order_book.get_best(side)
            if price is not None:
                product_price = float(price)
                currency_price = order_book.product.convert_quote_price_to_currency_price(destination_currency,
                                                                                          product_price)
                self.add_edge(edge_type, QuoteType.currency, source_currency, destination_currency, currency_price)
                self.add_edge(edge_type, QuoteType.product, source_currency, destination_currency, product_price)
        else:
            product_qty = order_book.get_edge_trade_size(side, OrderType.match, NETWORK_LOOKBACK, edge_type,
                                                         ORDER_AGGREGATION_TIME)
            if product_qty is not None:
                assert product_qty >= 0, 'Edge trade size is negative! {}, {}, {}'.format(source_currency.name,
                                                                                          destination_currency.name,
                                                                                          product_qty)
                my_desired_qty = product_qty * QTY_MULTIPLIER

                # note that custom strategy does not allow exceeding best bid
                allow_exceed_best = edge_type != EdgeType.custom
                price, avail_qty = order_book.get_network_price(side, product_qty, my_desired_qty,
                                                                allow_exceed_best=allow_exceed_best)
                if price is not None:
                    product_price = float(price)
                    currency_price = order_book.product.convert_quote_price_to_currency_price(destination_currency,
                                                                                              product_price)
                    currency_qty = order_book.product.get_currency_quantity_from_quote_quantity(destination_currency,
                                                                                                avail_qty,
                                                                                                product_price)
                    self.add_edge(edge_type, QuoteType.currency, source_currency, destination_currency, currency_price,
                                  currency_qty)
                    self.add_edge(edge_type, QuoteType.product, source_currency, destination_currency, product_price,
                                  avail_qty)

    def update_from_order_book(self, order_book, side: OrderSide) -> None:
        for edge_type in EdgeType:
            self.update_edge_type(order_book, side, edge_type)
