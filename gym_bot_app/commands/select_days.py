# encoding: utf-8
from __future__ import unicode_literals

from telegram import ParseMode, error
from telegram.ext import CallbackQueryHandler

from gym_bot_app.commands.command import Command
from gym_bot_app.decorators import get_trainee, get_trainee_and_group
from gym_bot_app.keyboards import trainee_select_days_inline_keyboard


class SelectDaysCommand(Command):
    NAME = 'select_days'
    SELECT_DAYS_QUERY_IDENTIFIER = 'select_days'

    def __init__(self, *args, **kwargs):
        super(SelectDaysCommand, self).__init__(*args, **kwargs)
        self.dispatcher.add_handler(
            CallbackQueryHandler(pattern='{identifier}.*'.format(identifier=self.SELECT_DAYS_QUERY_IDENTIFIER),
                                 callback=self.selected_day_callback_query),  # selected training day
        )

    @get_trainee_and_group
    def _handler(self, bot, update, trainee, group):
        self.logger.info('select days command')
        self.logger.info('trainee to select days %s', trainee)
        self.logger.info('the group is %s', group)

        keyboard = trainee_select_days_inline_keyboard(trainee=trainee,
                                                       callback_identifier=self.SELECT_DAYS_QUERY_IDENTIFIER)
        update.message.reply_text('באיזה ימים אתה מתאמן יא בוט?', reply_markup=keyboard)

    @classmethod
    def get_select_days_keyboard_for_trainee(cls, trainee):
        return trainee_select_days_inline_keyboard(trainee=trainee,
                                                   callback_identifier=cls.SELECT_DAYS_QUERY_IDENTIFIER)

    @get_trainee
    def selected_day_callback_query(self, bot, update, trainee):
        self.logger.info('select day')
        self.logger.info('trainee selected %s', trainee)

        query = update.callback_query
        _, trainee_id, selected_day = query.data.split()

        if trainee.id != unicode(trainee_id):  # other trainee tried to select days for this trainee
            self.logger.info('trainee is not allow to choose for others')
            bot.answerCallbackQuery(text='אי אפשר לבחור לאחרים יא בוט',
                                    callback_query_id=update.callback_query.id,
                                    parse_mode=ParseMode.HTML)
            return

        selected_day = trainee.training_days.get(name=selected_day)
        self.logger.info('selected day %s', selected_day)

        if selected_day.selected:
            self.logger.info('already selected day, removing it from the trainee training days')
        else:
            self.logger.info('new selected day, adding it to the trainee training days')
        selected_day.selected = not selected_day.selected
        updated_keyboard = trainee_select_days_inline_keyboard(trainee=trainee,
                                                               callback_identifier=self.SELECT_DAYS_QUERY_IDENTIFIER)

        try:
            bot.edit_message_reply_markup(chat_id=query.message.chat_id,
                                          message_id=query.message.message_id,
                                          reply_markup=updated_keyboard)
            bot.answerCallbackQuery(text='selected {}'.format(selected_day.name.capitalize()),
                                    callback_query_id=update.callback_query.id)
        except error.BadRequest:
            self.logger.debug('The keyboard have not changed probably because the trainee changed it from'
                              ' another keyboard.')
            bot.answerCallbackQuery(text='יא בוט על חלל, כבר שינית את זה במקום אחר...',
                                    callback_query_id=update.callback_query.id)

        trainee.save()  # save to db after the message sent to get better performance
