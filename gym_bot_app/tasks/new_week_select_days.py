# encoding: utf-8
from __future__ import unicode_literals

from datetime import time, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import CallbackQueryHandler

from gym_bot_app.tasks.task import Task
from gym_bot_app.utils import upper_first_letter
from gym_bot_app.models import Group, Day
from gym_bot_app.decorators import get_trainee_and_group, repeats


class NewWeekSelectDaysTask(Task):
    TARGET_DAY = 'Saturday'
    TARGET_TIME = time(hour=21, minute=30, second=0, microsecond=0)

    def __init__(self, *args, **kwargs):
        super(NewWeekSelectDaysTask, self).__init__(*args, **kwargs)
        self.dispatcher.add_handler(CallbackQueryHandler(pattern='new_week.*',
                                                         callback=self.new_week_selected_day_callback_query))

    def get_start_time(self):
        return self._seconds_until_day_and_time(target_day_name=self.TARGET_DAY,
                                                target_time=self.TARGET_TIME)

    @repeats(every_seconds=timedelta(weeks=1).total_seconds())
    def execute(self):
        self.logger.info('reminding to select days for new week')
        for group in Group.objects:
            self.logger.info('new week remind for %s', group)
            for trainee in group.trainees:
                trainee.unselect_all_days()
            self.logger.info('unselected all days for the trainees in group')

            keyboard = self._generate_inline_keyboard_for_new_week_select_days(group)
            self.updater.bot.send_message(chat_id=group.id,
                                          text='כל הבוטים, מוזמנים למלא את ימי האימון לשבוע הקרוב כדי שתוכלו כבר מעכשיו לחשוב על תירוצים למה לא ללכת',
                                          reply_markup=keyboard)

    @get_trainee_and_group
    def new_week_selected_day_callback_query(self, bot, update, trainee, group):
        self.logger.info('new week selected day')
        self.logger.info('trainee selected %s in group %s', trainee, group)
        query = update.callback_query

        _, selected_day_name = query.data.split()
        self.logger.info('selected day name is %s', selected_day_name)
        selected_day = trainee.training_days.get(name=selected_day_name)
        selected_day.selected = not selected_day.selected
        trainee.save()
        group.reload()

        keyboard = self._generate_inline_keyboard_for_new_week_select_days(group)
        try:
            bot.edit_message_reply_markup(chat_id=group.id,
                                          message_id=query.message.message_id,
                                          reply_markup=keyboard)
            bot.answerCallbackQuery(text="selected {}".format(upper_first_letter(selected_day.name)),
                                    callback_query_id=update.callback_query.id)
        except error.BadRequest:
            self.logger.debug('The keyboard have not changed probably because the trainee changed it from'
                              ' another keyboard.')
            bot.answerCallbackQuery(text='יא בוט על חלל, כבר שינית את זה במקום אחר...',
                                    callback_query_id=update.callback_query.id)

    def _generate_inline_keyboard_for_new_week_select_days(self, group):
        self.logger.info('generation inline keyboard for new week select days for group %s', group)
        keyboard = []
        for day in Day.get_week_days():
            training_in_day = day.name

            trainees = group.get_trainees_in_day(day.name)
            if trainees:
                training_in_day += ': ' + ', '.join(trainee.first_name
                                                    for trainee in trainees)

            callback_data = 'new_week {day_name}'.format(day_name=day.name)
            keyboard.append([InlineKeyboardButton(training_in_day, callback_data=callback_data)])

        return InlineKeyboardMarkup(keyboard)
