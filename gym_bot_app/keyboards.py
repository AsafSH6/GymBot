from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from gym_bot_app import WEIGHT_LIFTER_EMOJI
from gym_bot_app.models import Day


YES_RESPONSE = 'yes'
NO_RESPONSE = 'no'
DATE_FORMAT = '%d/%m/%Y'


def all_group_participants_select_days_inline_keyboard(group, callback_identifier):
    """Select days inline keyboard for all participants in the given group.

    callback_data is in form of (callback identifier, selected day name)

    Args:
        group(models.Group): group to generate keyboard for.
        callback_identifier(str): identifier of the callback handler which will be executed once keyboard is used.

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

    callback_data is in form of (callback identifier, selected trainee id, selected day name)

    Args:
        trainee(models.Trainee): trainee to generate keyboard for.
        callback_identifier(str): identifier of the callback handler which will be executed once keyboard is used.

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


def yes_or_no_inline_keyboard(callback_identifier,
                              yes_option=YES_RESPONSE,
                              no_option=NO_RESPONSE,
                              date_format=DATE_FORMAT):
    """yes or no inline keyboard.

    callback_data is in form of (callback identifier, selected response, selected day date)

    Args:
        callback_identifier(str): identifier of the callback handler which will be executed once keyboard is used.
        yes_option (str): button yes option text.
        no_option (str): button no option text.
        date_format (str): format of date in callback data.

    Returns:
        InlineKeyboardMarkup. inline yes or no keyboard.

    """
    today_date = datetime.now().date().strftime(date_format)
    yes_response_callback_data = '{callback_identifier} {yes_response} {date}'.format(callback_identifier=callback_identifier,
                                                                                      yes_response=YES_RESPONSE,
                                                                                      date=today_date)
    no_response_callback_data = '{callback_identifier} {no_response} {date}'.format(callback_identifier=callback_identifier,
                                                                                    no_response=NO_RESPONSE,
                                                                                    date=today_date)

    keyboard = [[InlineKeyboardButton(yes_option,
                                      callback_data=yes_response_callback_data),
                 InlineKeyboardButton(no_option,
                                      callback_data=no_response_callback_data)]]

    return InlineKeyboardMarkup(keyboard)