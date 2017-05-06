# from trading_package.portfolio.portfolio import BasePortfolioGroup
# from trading_package.order_book.order import Order
# from trading_package.helper.enums import EdgeType, Currency
# from trading_package.config.constants import EDGE_TYPE, MIN_CYCLE_RETURN
# from typing import List, Dict, Tuple
# from decimal import Decimal
#
#
# class PortfolioGroup(BasePortfolioGroup):
#     # returns {currency: (max_decrease, max_increase)}
#     def get_max_currency_deltas(self) -> Dict[Currency, Tuple[float, float]]:
#         p_balance_usd, total_balance = self.get_valuation()
#         return_deltas = {}
#         if total_balance == 0:
#             return return_deltas
#         for currency, (currency_balance_usd, edge_val) in p_balance_usd.items():
#             if edge_val is None:
#                 continue
#             max_fraction = self.get_portfolio_from_currency(currency).get_max_fraction()
#             min_fraction = self.get_portfolio_from_currency(currency).get_min_fraction()
#             max_increase = ((max_fraction * total_balance) - currency_balance_usd) / edge_val
#             max_increase = max(max_increase, 0.0)
#             max_decrease = (currency_balance_usd - (min_fraction * total_balance)) / edge_val
#             max_decrease = max(max_decrease, 0.0)
#             return_deltas[currency] = (max_decrease, max_increase)
#         return return_deltas
#
#     def get_next_trades(self) -> List[Order]:
#         orders = []
#         available_trade_currencies = self.get_available_currencies_for_trade()
#         if not available_trade_currencies:
#             return orders
#         max_portfolio_deltas = self.get_max_currency_deltas()
#         for currency_to_trade, currency_qty in available_trade_currencies.items():
#             try:
#                 currency_qty = min(Decimal(max_portfolio_deltas[currency_to_trade][0]), currency_qty)
#             except (KeyError, IndexError):
#                 pass
#             cycles_by_cycle_val = self.order_book_manager.network_manager.get_next_nodes_and_avail_qties_by_cycle_value(
#                 EdgeType[EDGE_TYPE],
#                 currency_to_trade)
#             for cycle_val in sorted(cycles_by_cycle_val, reverse=True):
#                 (next_node, edge_val, avail_qty) = cycles_by_cycle_val[cycle_val]
#                 if not (edge_val and avail_qty):
#                     continue
#                 edge_val = Decimal(edge_val)
#                 avail_qty = Decimal(avail_qty)
#                 # avail quantity and edge quantity measure product quantities
#                 remaining_edge_qty = avail_qty - self.order_book.get_edge_qty(currency_to_trade, next_node)
#
#                 if cycle_val <= MIN_CYCLE_RETURN:
#                     break
#                 if remaining_edge_qty > 0:
#                     product = self.order_book.product_manager.get_product_from_currencies(currency_to_trade, next_node)
#                     order_side = product.get_side_from_currency_direction(currency_to_trade, next_node)
#                     # edge_val is already a quote price
#                     quote_price = edge_val
#                     quote_qty = product.get_quote_quantity_from_currency_quantity(currency_to_trade, currency_qty,
#                                                                                   edge_val)
#                     quote_qty = product.round_quantity(min(remaining_edge_qty, quote_qty))
#                     destination_qty = product.get_currency_quantity_from_quote_quantity(next_node, quote_qty,
#                                                                                         edge_val)
#
#                     # account for min and max fraction
#                     try:
#                         max_increase_in_destination_curr = max_portfolio_deltas[next_node][1]
#                         if max_increase_in_destination_curr < destination_qty:
#                             quote_qty = product.get_quote_quantity_from_currency_quantity(next_node,
#                                                                                           max_increase_in_destination_curr,
#                                                                                           edge_val)
#                             quote_qty = product.round_quantity(quote_qty)
#                     except (KeyError, IndexError):
#                         pass
#
#                     order = Order(product.get_product_id(), 0, order_side, quote_qty, quote_price)
#                     if Decimal(order.get_size()) > product.get_base_min_size_dec():
#                         print(
#                             'Trade identified return ({}), source/dest ({}/{}), currency/quote price ({}/{}), currency/quote qty ({}/{})'.format(
#                                 cycle_val,
#                                 currency_to_trade.name,
#                                 next_node,
#                                 edge_val,
#                                 quote_price,
#                                 currency_qty,
#                                 quote_qty
#                             ))
#                         orders += [order]
#                         # only one order per currency please
#                         break
#         return orders
