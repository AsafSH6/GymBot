# encoding: utf-8
from datetime import datetime, timedelta

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


def trainee_already_marked_training_date(trainee, training_date):
    """Check whether trainee already marked the given training date.

    If trainee already has training day info it means he/she answered marked the given date.

    Args:
        trainee(models.Trainee): trainee instance to check whether already marked the given date.
        training_date(datetime.date): training date to check.

    Returns:
        bool. True if trainee already marked the given date, otherwise False.

    """
    training_info_list = trainee.get_training_info(training_date=training_date)
    return any(info.trained for info in training_info_list)


def get_trainees_that_selected_today_and_did_not_train_yet(group):
    """Get all trainees in group that selected today as training day but did not train yet.

    Args:
        group(models.Group): group instance to filter trainees that selected today as training day and did not
                              train yet.

    Returns:
         list. all trainees in group that selected today as training day but did not train by now.

    """
    today_date = datetime.now().date()
    today_training_trainees = group.get_trainees_of_today()
    did_not_train_yet_trainees = [trainee for trainee in today_training_trainees
                                  if not trainee_already_marked_training_date(trainee=trainee,
                                                                              training_date=today_date)]
    return did_not_train_yet_trainees


def find_instance_in_args(obj, args):
    """find instance of given object type args.

    Args:
        obj(type): type of object to look for.
        args(iterable): arguments to search for the given object type.

    Returns:
        obj. instance of the obj type that found in args.

    """
    return next(filter(lambda arg: isinstance(arg, obj), args))


def get_update_from_args(args):
    """Find bot and update instance in the given args.

    Args:
        args(iterable): arguments to search for the bot and update.

    Returns:
      telegram.Update. instance of update that found in args.

    """
    update = find_instance_in_args(telegram.update.Update, args)
    return update

def get_dates_of_week(date):
    """Returns a list of the dates of the week containing the given day.

    A week begins from Sunday and ends on Saturday.
    
    Args:
        date(datetime): a day from the requested week.
    
    Returns:
      list. a list of datetime objects of dates in the week containing the given day.
    """
    day_idx = (date.weekday() + 1) % 7  # turn sunday into 0, monday into 1, etc.
    sunday = date.date() - timedelta(days=day_idx)
    return [sunday + timedelta(days = i) for i in range(7)]
