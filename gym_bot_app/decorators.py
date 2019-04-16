# encoding: utf-8
from __future__ import unicode_literals

import logging
import functools
import threading

from telegram.error import TimedOut, Unauthorized

from gym_bot_app.models import Group, Trainee
from gym_bot_app.utils import get_bot_and_update_from_args


def get_group(func):
    """Decorator to insert group as argument to the given function.

    Creates new Group if did not exist in DB.
    Appends the group as last argument of the function.

    Notes:
        func has to be used in dispatcher as handler in order to receive the bot and the update arguments.

    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        bot, update = get_bot_and_update_from_args(args)
        group_id = update.message.chat_id if update.message else update.callback_query.message.chat_id
        group = Group.objects.get(id=group_id)

        if group is None:  # new group.
            group = Group.objects.create(id=group_id)

        args_with_group = args + (group, )
        return func(*args_with_group, **kwargs)

    return wrapper


def get_trainee_and_group(func):
    """Decorator to insert trainee and group as arguments to the given function.

    Creates new Trainee if did not exist in DB.
    Creates new Group if did not exist in DB.
    Adds the trainee to the group if it was not part of it.
    Appends the trainee and group as last argument of the function.

    Example:
        @get_trainee_and_group
        def run(bot, update, trainee, group):
            ....

    Notes:
        func has to be used in dispatcher as handler in order to receive the bot and the update arguments.

    """
    @get_group
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        bot, update = get_bot_and_update_from_args(args)

        trainee_id = update.effective_user.id
        trainee = Trainee.objects.get(id=trainee_id)
        if trainee is None:  # new trainee.
            trainee = Trainee.objects.create(id=trainee_id,
                                             first_name=update.effective_user.first_name)

        group = args[-1]
        if trainee not in group.trainees:
            group.add_trainee(new_trainee=trainee)

        args_with_trainee_and_group = args[:-1] + (trainee, group)
        return func(*args_with_trainee_and_group, **kwargs)

    return wrapper


def repeats(every_seconds):
    """Decorator to repeat function.

    Args:
        every_seconds(int): number of seconds to wait between each repeat.

    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            threading.Timer(every_seconds,
                            wrapper,
                            args=args,
                            kwargs=kwargs).start()
            return func(*args, **kwargs)
        return wrapper
    return decorator


def run_for_all_groups(func):
    """Decorator to run function for all existing groups in DB.

    Insert the group to the function as last argument.
    Handles TimedOut exceptions if occurred.

    Example:
        @run_for_all_groups
        def say_hello(group):
            ...

    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = logging.getLogger(func.__module__)
        for group in Group.objects.filter(is_deleted=False):
            try:
                args_with_group = args + (group, )
                func(*args_with_group, **kwargs)
            except TimedOut:
                logger.error('Timeout occurred in module %s with execution func %s',
                             func.__module__,
                             func.func_name)
            except Unauthorized:
                group.delete()
                logger.info('Unauthorized group %s - deleted', group)
            except Exception:
                logger.error('Exception occurred in module %s with execution func %s',
                             func.__module__,
                             func.func_name)

    return wrapper
