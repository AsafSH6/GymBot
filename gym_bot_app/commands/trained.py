# encoding: utf-8
from __future__ import unicode_literals

from datetime import datetime

from gym_bot_app.commands import Command
from gym_bot_app import FACEPALMING_EMOJI, WEIGHT_LIFTER_EMOJI, TROPHY_EMOJI
from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.utils import trainee_already_marked_training_date


class TrainedCommand(Command):
    """Telegram gym bot trained command.

    Allows trainees to report that they trained today.

    """
    DEFAULT_COMMAND_NAME = 'trained'
    TRAINED_TODAY_MSG = '{creature}!\n Earned {gained_exp} EXP.'
    TRAINED_TODAY_MSG_TO_OTHER_GROUPS = '{trainee} ה{creature} התאמן היום\n Earned {gained_exp} EXP.'
    ALREADY_REPORTED_TRAINING_STATUS_MSG = 'כבר אמרת שהתאמנת היום יא בוט {}'.format(FACEPALMING_EMOJI)
    TRAINEE_LEVELED_UP_MSG = 'יא בוט עלית רמה!!\n' + TROPHY_EMOJI + ' {level} ' + TROPHY_EMOJI
    TRAINEE_LEVELED_UP_MSG_OTHER_GROUPS = '{trainee} הבוט עלה רמה!!\n' + TROPHY_EMOJI + ' {level} ' + TROPHY_EMOJI
    GROUP_LEVELED_UP_MSG = 'כולכם בוטים עליתי רמה!!\n' + WEIGHT_LIFTER_EMOJI + ' {level} ' + WEIGHT_LIFTER_EMOJI

    def __init__(self, *args, **kwargs):
        super(TrainedCommand, self).__init__(*args, **kwargs)

    @get_trainee_and_group
    def _handler(self, bot, update, trainee, group):
        """Override method to handle trained command.

        Creates training day info of today.
        Mark the trained day as selected.

        """
        self.logger.info('Trained command with %s in %s', trainee, group)

        today_date = datetime.now().date()
        if trainee_already_marked_training_date(trainee=trainee, training_date=today_date):
            self.logger.debug('Trainee already reported today about training status')
            update.message.reply_text(quote=True, text=self.ALREADY_REPORTED_TRAINING_STATUS_MSG)
        else:
            training_info, trainee_leveled_up = trainee.add_training_info(training_date=today_date, trained=True)
            gained_exp = training_info.gained_exp
            self.logger.info('Trainee gained %s EXP', gained_exp)

            msg = self.TRAINED_TODAY_MSG.format(creature=trainee.personal_configurations.creature,
                                                gained_exp=gained_exp)
            update.message.reply_text(quote=True, text=msg)

            if trainee_leveled_up:
                self.logger.info('Trainee %s leveled up to %s', trainee, trainee.level)
                trainee_leveled_up_msg = self.TRAINEE_LEVELED_UP_MSG.format(level=trainee.level)
                update.message.reply_text(quote=False,
                                          text=trainee_leveled_up_msg)

            group_leveled_up = group.level.gain_exp(exp=gained_exp)
            if group_leveled_up:
                self.logger.info('Group %s leveled up to level %s', group, group.level)
                group_leveled_up_msg = self.GROUP_LEVELED_UP_MSG.format(level=group.level)
                update.message.reply_text(quote=False,
                                          text=group_leveled_up_msg)

            today_training_day = trainee.training_days.get(name=today_date.strftime('%A'))

            if not today_training_day.selected:  # mark today as selected if it was not selected before
                today_training_day.selected = True

            trainee.save()
            group.save()

            # Notify other groups.
            trained_today_msg_to_other_groups = self.TRAINED_TODAY_MSG_TO_OTHER_GROUPS.format(
                trainee=trainee.first_name,
                creature=trainee.personal_configurations.creature,
                gained_exp=gained_exp
            )
            trainee_leveled_up_other_groups = self.TRAINEE_LEVELED_UP_MSG_OTHER_GROUPS.format(trainee=trainee.first_name,
                                                                                              level=trainee.level)
            other_groups = (g for g in trainee.groups if g != group)
            for other_group in other_groups:
                bot.send_message(chat_id=other_group.id,
                                 text=trained_today_msg_to_other_groups)

                if trainee_leveled_up:
                    bot.send_message(chat_id=other_group.id, text=trainee_leveled_up_other_groups)

                group_leveled_up = other_group.level.gain_exp(exp=training_info.gained_exp)
                if group_leveled_up:
                    self.logger.info('Group %s leveled up to level %s', other_group, other_group.level)
                    other_group_leveled_up_msg = self.GROUP_LEVELED_UP_MSG.format(level=other_group.level)
                    bot.send_message(chat_id=other_group.id, text=other_group_leveled_up_msg)

                other_group.save()
