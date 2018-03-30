from gym_bot_app.db.models import Group, Trainee, Day
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
        group_id = update.effective_user.id
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