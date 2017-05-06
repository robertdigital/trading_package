import GDAX
from trading_package.config.secrets import *

authClient = GDAX.AuthenticatedClient(KEY, B64_SECRET, PASS_PHRASE, product_id='')
publicClient = GDAX.PublicClient(product_id='')
