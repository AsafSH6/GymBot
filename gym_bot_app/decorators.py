# encoding: utf-8
from __future__ import unicode_literals

import threading

from gym_bot_app.models import Group, Trainee
from gym_bot_app.utils import get_bot_and_update_from_args


def get_trainee(func):
    def wrapper(*args, **kwargs):
        bot, update = get_bot_and_update_from_args(args)
        trainee_id = update.effective_user.id
        trainee = Trainee.objects.get(id=trainee_id)

        if trainee is None:  # new trainee.
            trainee = Trainee.objects.create(id=trainee_id,
                                             first_name=update.effective_user.first_name)

        args_with_trainee = args + (trainee, )
        return func(*args_with_trainee, **kwargs)

    return wrapper


def get_group(func):
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
    @get_trainee
    @get_group
    def wrapper(*args, **kwargs):
        trainee, group = args[-2:]

        if trainee not in group.trainees:
            group.add_trainee(new_trainee=trainee)

        return func(*args, **kwargs)

    return wrapper


def repeats(every_seconds):
    def decorator(func):
        def wrapper(*args, **kwargs):
            threading.Timer(every_seconds,
                            wrapper,
                            args=args,
                            kwargs=kwargs).start()
            return func(*args, **kwargs)
        return wrapper
    return decorator
