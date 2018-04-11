# encoding: utf-8
from __future__ import unicode_literals
from datetime import datetime

import telegram

from gym_bot_app import DAYS_NAME


def day_name_to_day_idx(day_name):
    """Convert day name to day index.

    Args:
        day_name(str): name of the day to convert.

    Returns:
        int. index of the given day.

    """
    return DAYS_NAME.index(day_name.capitalize())


def number_of_days_until_next_day(target_day_name):
    """Calculate the number of days until the next occurrence of target day.

    Args:
        target_day_name(str): name of the target day.

    Returns:
        int. number of days until the target day.

    """
    today = datetime.today().strftime('%A')
    return (DAYS_NAME.index(target_day_name.capitalize()) - DAYS_NAME.index(today)) % len(DAYS_NAME)


def find_instance_in_args(obj, args):
    """find instance of given object type args.

    Args:
        obj(type): type of object to look for.
        args(iterable): arguments to search for the given object type.

    Returns:
        obj. instance of the obj type that found in args.

    """
    return filter(lambda arg: isinstance(arg, obj), args)[0]


def get_bot_and_update_from_args(args):
    """Find bot and update instance in the given args.

    Args:
        args(iterable): arguments to search for the bot and update.

    Returns:
        tuple.
          telegram.Bot. instance of bot that found in args.
          telegram.Upate. instance of update that found in args.

    """
    bot = find_instance_in_args(telegram.bot.Bot, args)
    update = find_instance_in_args(telegram.update.Update, args)
    return bot, update
