# encoding: utf-8
from __future__ import unicode_literals

import telegram

from gym_bot_app import DAYS_NAME


def upper_first_letter(name):
    return name[0].upper() + name[1:].lower()


def day_name_to_day_idx(day_name):
    return DAYS_NAME.index(upper_first_letter(day_name))


def find_instance_in_args(obj, args):
    return filter(lambda arg: isinstance(arg, obj), args)[0]


def get_bot_and_update_from_args(args):
    bot = find_instance_in_args(telegram.bot.Bot, args)
    update = find_instance_in_args(telegram.update.Update, args)
    return bot, update
