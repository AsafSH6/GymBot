import random

# Kept outside gym_bot_app.commands so tasks can use it too: commands/admin.py imports
# gym_bot_app.tasks, so a task importing from gym_bot_app.commands would be circular.

QUOTE_MSG = '"{text}", {author}'

QUOTE_LIST = [
    {'text': 'The last three or four reps is what makes the muscle grow. This area of pain divides a champion from someone who is not a champion.', 'author': 'Arnold Schwarzenegger'},
    {'text': 'Success usually comes to those who are too busy to be looking for it.', 'author': 'Henry David Thoreau'},
    {'text': 'All progress takes place outside the comfort zone', 'author': 'Michael John Bobak'},
    {'text': 'If you think lifting is dangerous, try being weak. Being weak is dangerous.', 'author': 'Bret Contreras'},
    {'text': 'The only place where success comes before work is in the dictionary.', 'author': 'Vidal Sassoon'},
    {'text': 'The clock is ticking. Are you becoming the person you want to be?', 'author': 'Greg Plitt'},
    {'text': 'Whether you think you can, or you think you can’t, you’re right.', 'author': 'Henry Ford'},
    {'text': 'The successful warrior is the average man, with laser-like focus.', 'author': 'Bruce Lee'},
    {'text': 'You must expect great things of yourself before you can do them.', 'author': 'Michael Jordan'},
    {'text': 'Action is the foundational key to all success.', 'author': 'Pablo Picasso'},
    {'text': 'Everyone is a bot', 'author': 'Asaf sh'},
]


def format_quote(quote):
    """Format a quote for sending.

    Args:
        quote(dict): quote from QUOTE_LIST.

    Returns:
        str. the quote text followed by its author.

    """
    return QUOTE_MSG.format(text=quote['text'], author=quote['author'])


def random_quote():
    """Pick a random quote.

    Returns:
        dict. quote from QUOTE_LIST.

    """
    return random.choice(QUOTE_LIST)


def _cycle_order(cycle):
    """Order in which the quotes are used during the given cycle.

    Args:
        cycle(int): number of the cycle, each cycle is len(QUOTE_LIST) days long.

    Returns:
        list. of int, a permutation of the QUOTE_LIST indexes.

    """
    return random.Random(cycle).sample(range(len(QUOTE_LIST)), len(QUOTE_LIST))


def quote_of_the_day(day):
    """Pick the quote of the given day.

    The days are split into cycles of len(QUOTE_LIST) days, and each cycle uses every
    quote exactly once in a shuffled order. The order is seeded by the cycle number, so
    the same day always gets the same quote -- no matter which group asks or whether the
    bot restarted in between.

    Args:
        day(datetime.date): day to pick the quote for.

    Returns:
        dict. quote from QUOTE_LIST.

    """
    cycle, position = divmod(day.toordinal(), len(QUOTE_LIST))
    order = _cycle_order(cycle)

    if order[0] == _cycle_order(cycle - 1)[-1]:
        # Don't open the cycle with yesterday's quote. Swapping the first two never
        # touches the last slot, which is what the next cycle compares against.
        order[0], order[1] = order[1], order[0]

    return QUOTE_LIST[order[position]]
