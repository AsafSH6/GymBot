# encoding: utf-8
from __future__ import unicode_literals

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from gym_bot_app import WEIGHT_LIFTER_EMOJI
from gym_bot_app.models import Day


def all_group_participants_select_days_inline_keyboard(group, callback_identifier):
    """Select days inline keyboard for all participants in the given group.

    Args:
        group(models.Group): group to generate keyboard for.
        callback_identifier(str | unicode): identifier of the callback handler which will be executed once keyboard is used.

    Returns:
        InlineKeyboardMarkup. inline keyboard for all participants in group.

    """
    keyboard = []
    for day in Day.get_week_days():
        training_in_day = day.name

        trainees = group.get_trainees_in_day(day.name)
        if trainees:
            training_in_day += ': ' + ', '.join(trainee.first_name
                                                for trainee in trainees)

        callback_data = '{callback_identifier} {day_name}'.format(callback_identifier=callback_identifier,
                                                                  day_name=day.name)
        keyboard.append([InlineKeyboardButton(training_in_day, callback_data=callback_data)])

    return InlineKeyboardMarkup(keyboard)


def trainee_select_days_inline_keyboard(trainee, callback_identifier):
    """Select days inline keyboard for specific trainee.

    Args:
        trainee(models.Trainee): trainee to generate keyboard for.
        callback_identifier(str | unicode): identifier of the callback handler which will be executed once keyboard is used.

    Returns:
        InlineKeyboardMarkup. inline keyboard for specific trainee.

    """
    keyboard = []
    for day in trainee.training_days:
        training_day = day.name

        if day.selected:
            training_day += ' ' + WEIGHT_LIFTER_EMOJI

        callback_data = '{callback_identifier} {id} {day_name}'.format(id=trainee.id,
                                                                       day_name=day.name,
                                                                       callback_identifier=callback_identifier)
        keyboard.append([InlineKeyboardButton(training_day, callback_data=callback_data)])

    return InlineKeyboardMarkup(keyboard)


def yes_or_no_inline_keyboard(callback_identifier):
    """yes or no inline keyboard.

    Args:
        callback_identifier(str | unicode): identifier of the callback handler which will be executed once keyboard is used.

    Returns:
        InlineKeyboardMarkup. inline yes or no keyboard.

    """
    today_name = datetime.now().strftime('%A')
    yes_response_callback_data = '{callback_identifier} yes {today}'.format(callback_identifier=callback_identifier,
                                                                            today=today_name)
    no_response_callback_data = '{callback_identifier} no {today}'.format(callback_identifier=callback_identifier,
                                                                          today=today_name)

    keyboard = [[InlineKeyboardButton('כן',
                                      callback_data=yes_response_callback_data),
                 InlineKeyboardButton('אני אפס',
                                      callback_data=no_response_callback_data)]]

    return InlineKeyboardMarkup(keyboard)