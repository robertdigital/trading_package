import curses


def init_curses():
    curses.start_color()
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)


def get_order_attributes(df):
    attrs = {}
    return attrs


def get_fill_attributes(df):
    attrs = {}
    return attrs


def get_portfolio_attributes(df):
    attrs = {}
    return attrs


def get_cycle_attributes(df):
    attrs = {}
    for i in list(df.query('cycle_return < 1').index):
        attrs[i] = curses.color_pair(3)
    for i in list(df.query('cycle_return > 1.01').index):
        attrs[i] = curses.color_pair(2)
    return attrs


def format_columns(window, cols, row_id, n_cols=None, attr=0):
    n_cols = n_cols or len(cols)
    (max_y, max_x) = window.getmaxyx()
    if row_id >= max_y:
        return None
    attr = attr or 0
    col_idx = 0
    col_width = int((max_x + 0.0) / n_cols)
    for col in cols:
        window.addstr(row_id, col_idx, str(col), attr)
        col_idx += col_width


def formatter(x):
    if isinstance(x, float):
        return '{:.4f}'.format(x)
    elif isinstance(x, int):
        return str(x)
    else:
        return x


def display_df(window, title, df, idx_attr_map, start_idx=0):
    header = list(df)
    format_columns(window, [title], start_idx, attr=curses.A_BOLD)
    format_columns(window, header, start_idx + 1, attr=curses.A_UNDERLINE)
    start_idx += 2
    for idx, pf in df.iterrows():
        row = pf.values
        f_row = map(formatter, row)
        attribute = idx_attr_map[idx] if idx in idx_attr_map else 0
        format_columns(window, f_row, idx + start_idx, attr=attribute)
    window.refresh()
    return start_idx + len(df)
