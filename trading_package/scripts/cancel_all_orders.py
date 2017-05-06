from trading_package.client_initializer import *

if __name__ == '__main__':
    print("Cancelling orders")
    products = publicClient.getProducts()
    for product in products:
        authClient.cancelAll(product=product['id'])
    print("Orders Canceled")
