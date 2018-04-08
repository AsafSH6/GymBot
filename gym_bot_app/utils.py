# encoding: utf-8
from __future__ import unicode_literals
from datetime import datetime

import telegram

from gym_bot_app import DAYS_NAME


def day_name_to_day_idx(day_name):
    return DAYS_NAME.index(day_name.capitalize())


def number_of_days_until_next_day(target_day_name):
    today = datetime.today().strftime('%A')
    return (DAYS_NAME.index(target_day_name) - DAYS_NAME.index(today)) % len(DAYS_NAME)


def find_instance_in_args(obj, args):
    return filter(lambda arg: isinstance(arg, obj), args)[0]


def get_bot_and_update_from_args(args):
    bot = find_instance_in_args(telegram.bot.Bot, args)
    update = find_instance_in_args(telegram.update.Update, args)
    return bot, update
