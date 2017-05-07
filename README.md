# Project Name

This package implements a Level 2 order book (from a websocket), portfolio manager, and network cycle calculator for the GDAX exchange. Easy plugin extensibility for trading strategies and strong performance on multicore machines.
I have been using it over the past few weeks to manage some of my personal strategies but it still has a number of kinks to be worked out! A sample strategy is provided in SerialTrader; to add your own simply extend BasePortfolioGroup and update PortfolioProcessor accordingly.

## Installation

This package uses redis so you will need to have a redis server running locally. On a mac:

```brew install redis```

```redis-server```

To setup the virtual environment and dependencies simply:

```bin/setup```

You can then run unit tests using:

```bin/test```

## Usage

Please be aware that this software is provided AS IS and you are strongly encouraged to exhaustively read through the source code
before connecting to your GDAX account. Once you are ready edit the `config/secrets` file with your api passphrase, secret, and key.
To start:

```bin/start```

Log files will be written to stdout and to the `logs/` directory. To initiate a shutdown:

```ctrl-c```

Note that as currently configured all standing orders are canceled at shutdown

## Notes

* Project uses the new PEP 484 type hinting (I found it extremely helpful for development).
* The GDAX websocket tends to randomly initiate a shutdown (every few hours or so). I have configured
this package to restart automatically without cancelling orders so it should be seamless.
* This is a pretty computationally intensive process running on four processors (handling Decimal is unfortunately expensive and threading is a nogo because of GIL).
* No visualizer is provided; feel free to contribute one or reach out if you want to know how I built mine.
* The network processor computes some niche things that you may not need (based on median trade size, depth to fill a certain fraction of an order, etc).
If you are placing orders based on best bid/ask this is probably unnecessary.
* As currently configured orders are placed in post-only made (so no taker fee should apply).
* I'll be writing a blog post over the next week or so outlining how the network is computed.
* Using network cycles depends on a strong mean-reversion component; I very much recommend adding short term momentum predictors for your own strategies.
* Two redis db's are used; one to maintain the order book and one for a persistent history of your portfolio size for various currencies.
* Please email me if you want to discuss or are interested in collaborating!

## Contributing

1. Fork it!
2. Create your feature branch: `git checkout -b my-new-feature`
3. Commit your changes: `git commit -am 'Add some feature'`
4. Push to the branch: `git push origin my-new-feature`
5. Submit a pull request
6. Make sure tests pass in travis


