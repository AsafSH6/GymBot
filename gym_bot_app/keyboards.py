# encoding: utf-8
from __future__ import unicode_literals

from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from gym_bot_app.models import Day


def all_group_participants_select_days_inline_keyboard(group, callback_identifier):
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


def yes_or_no_inline_keyboard(callback_identifier):
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