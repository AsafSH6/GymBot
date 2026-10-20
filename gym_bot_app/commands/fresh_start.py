from collections import defaultdict
from datetime import datetime, time, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import CallbackContext, CallbackQueryHandler, TypeHandler

from gym_bot_app import ALARM_CLOCK_EMOJI, MUSCLE_EMOJI, TROPHY_EMOJI, WEIGHT_LIFTER_EMOJI
from gym_bot_app.commands import Command
from gym_bot_app.commands.ranking import RankingCommand
from gym_bot_app.decorators import get_trainee_and_group
from gym_bot_app.models import FreshStartVote, Group, Trainee
from gym_bot_app.tasks.task import SCHEDULE_TIMEZONE


def fresh_start_deadline(now):
    """When a fresh start vote that opens at the given time closes.

    The vote always closes at a midnight at least 24 hours away. Training is recorded per
    day, so starting a season in the middle of a day would split that day's EXP and
    training days between two seasons.

    Args:
        now(datetime.datetime): when the vote opens, naive local time.

    Returns:
        datetime.datetime. midnight that starts the day after tomorrow, naive local time.

    """
    return datetime.combine(now.date() + timedelta(days=2), time.min)


class CloseFreshStartVote(object):
    """Update the vote closing job puts on the dispatcher's queue.

    Jobs run on their own threads, in parallel to the handlers. A handler that loaded a
    trainee or a group before the reset and saved it after would write its old level over
    the reset one, so the vote is closed by the dispatcher, which handles one update at a
    time, never in parallel to another handler.

    """
    def __init__(self, vote_id):
        self.vote_id = vote_id


class RemindFreshStartVote(object):
    """Update the vote reminder job puts on the dispatcher's queue.

    The dispatcher handles it in turn with the closing of the vote, so a reminder is never
    sent while the vote is being closed, after it already closed.

    """
    def __init__(self, vote_id):
        self.vote_id = vote_id


class FreshStartCommand(Command):
    """Telegram gym bot fresh start command.

    Opens a vote in the group. Every trainee who joins it before it closes starts a new
    season from level 1, with the statistics counting from the new season.

    """
    DEFAULT_COMMAND_NAME = 'fresh_start'
    FRESH_START_QUERY_IDENTIFIER = 'fresh_start'
    JOIN_RESPONSE = 'join'
    LEAVE_RESPONSE = 'leave'
    DEADLINE_FORMAT = '%d/%m'
    REMINDER_BEFORE_CLOSING = timedelta(hours=2)
    RETRY_DELAY = timedelta(minutes=5)

    JOIN_BUTTON_TEXT = 'אני בפנים ' + MUSCLE_EMOJI
    LEAVE_BUTTON_TEXT = 'התחרטתי'
    VOTE_MSG = ('מתחילים מחדש? ' + WEIGHT_LIFTER_EMOJI + '\n'
                'מי שלוחץ "אני בפנים" עד {deadline} בשעה 00:00 מתחיל עונה חדשה מרמה 1.\n'
                'הרמה, ה-EXP והסטטיסטיקות מתאפסים בכל הקבוצות, וגם הרמה שלי בקבוצה הזאת.\n'
                'העונה הנוכחית נשמרת ב-/my_statistics.\n'
                '\n'
                'בפנים: {participants}')
    NO_PARTICIPANTS_YET = 'אף אחד עדיין'
    VOTE_ALREADY_OPEN_MSG = 'כבר יש הצבעה פתוחה יא בוט'
    JOINED_MSG = 'בפנים! ' + MUSCLE_EMOJI
    LEFT_MSG = 'יצאת, נשארת בעונה הנוכחית'
    ALREADY_JOINED_MSG = 'כבר בפנים יא בוט'
    NOT_JOINED_MSG = 'לא היית בפנים יא בוט'
    VOTE_CLOSED_MSG = 'ההצבעה כבר נסגרה'
    JOINED_NOTIFICATION_MSG = '{trainee} בפנים לעונה החדשה ' + MUSCLE_EMOJI + '\nבפנים: {participants}'
    LEFT_NOTIFICATION_MSG = '{trainee} כבר לא בפנים\nבפנים: {participants}'
    # Says "tonight" rather than "in two hours", which a reminder sent late, after the bot
    # was down, would get wrong. It is never sent after midnight.
    REMINDER_MSG = ('תזכורת ' + ALARM_CLOCK_EMOJI + ' ההצבעה נסגרת הלילה בחצות.\n'
                    'מי שבפנים מתחיל עונה חדשה מרמה 1.\n'
                    'בפנים: {participants}')
    NOBODY_JOINED_MSG = 'אף אחד לא נכנס, ממשיכים בעונה הנוכחית'
    RANKING_BEFORE_RESET_MSG = 'הדירוג לפני האיפוס ' + TROPHY_EMOJI + '\n{ranking}'
    NEW_SEASON_MSG = ('עונה חדשה מרמה 1 בשביל: {trainees}\n'
                      'גם אני מתחיל מחדש. בהצלחה יא בוטים ' + MUSCLE_EMOJI)
    NEW_SEASON_MSG_TO_OTHER_GROUPS = 'עונה חדשה מרמה 1 בשביל: {trainees}'

    def __init__(self, *args, **kwargs):
        super(FreshStartCommand, self).__init__(*args, **kwargs)
        self.updater.dispatcher.add_handler(
            CallbackQueryHandler(pattern='{identifier}.*'.format(identifier=self.FRESH_START_QUERY_IDENTIFIER),
                                 callback=self.fresh_start_callback_query)
        )
        # run_async=False explicitly: closing in parallel to other handlers is the race the
        # dispatcher is used to avoid, so a default of run_async=True must not apply here.
        self.updater.dispatcher.add_handler(TypeHandler(type=CloseFreshStartVote,
                                                        callback=self._close_vote,
                                                        run_async=False))
        self.updater.dispatcher.add_handler(TypeHandler(type=RemindFreshStartVote,
                                                        callback=self._remind_vote,
                                                        run_async=False))

    def start(self, *args, **kwargs):
        """Override method to also schedule the closing and reminders of the votes that are not closed yet.

        The job queue lives in memory, so the votes that were open when the bot went down,
        or that a crash left half closed, are scheduled again. Overdue votes close as soon
        as the bot starts, and a reminder the bot was down for is sent as soon as it starts,
        if the vote is not overdue yet.

        """
        super(FreshStartCommand, self).start(*args, **kwargs)
        self._schedule_unfinished_votes()

    def _schedule_unfinished_votes(self, context: CallbackContext = None):
        """Schedule the closing and reminders of the votes that are not closed yet.

        Retries later if the DB is unreachable, instead of keeping the bot from starting.
        Runs as a job when retried, which is safe since it only reads votes.

        """
        try:
            votes = list(FreshStartVote.objects.get_unfinished())
        except Exception:
            self.logger.exception('Failed to load the unfinished fresh start votes, retrying in %s', self.RETRY_DELAY)
            self.updater.job_queue.run_once(callback=self._schedule_unfinished_votes,
                                            when=self.RETRY_DELAY,
                                            job_kwargs={'misfire_grace_time': None})
            return

        for vote in votes:
            self._schedule_vote_closing(vote)
            self._schedule_vote_reminder(vote)

    @get_trainee_and_group
    def _handler(self, update: Update, context: CallbackContext, trainee: Trainee, group: Group):
        """Override method to handle fresh start command.

        Opens a fresh start vote, unless the group already has one that is not closed yet.

        """
        self.logger.info('Fresh start command with %s in %s', trainee, group)

        open_vote = FreshStartVote.objects.get_unfinished(group).first()
        if open_vote is not None:
            self.logger.debug('Group already has an open vote %s', open_vote)
            context.bot.send_message(chat_id=group.id,
                                     text=self.VOTE_ALREADY_OPEN_MSG,
                                     reply_to_message_id=open_vote.message_id,
                                     allow_sending_without_reply=True)
            return

        vote = FreshStartVote.objects.create(group=group.pk,
                                             created_by=trainee.id,
                                             executes_at=fresh_start_deadline(datetime.now()))
        self._schedule_vote_closing(vote)
        self._schedule_vote_reminder(vote)
        try:
            message = update.message.reply_text(quote=False,
                                                text=self._get_vote_msg(vote),
                                                reply_markup=self._get_vote_keyboard(vote))
        except Exception:
            # Nobody can join a vote without its message, and it would block opening another.
            vote.cancel()
            raise

        vote.message_id = message.message_id
        vote.save()
        self.logger.info('Opened %s', vote)

    @get_trainee_and_group
    def fresh_start_callback_query(self, update: Update, context: CallbackContext, trainee: Trainee, group: Group):
        """Response handler of the fresh start vote.

        Adds or removes the trainee from the vote, updates the vote message and tells the
        group.

        """
        query = update.callback_query
        _, vote_id, response = query.data.split()
        self.logger.info('Fresh start callback query with %s in %s answered %s', trainee, group, response)

        vote = FreshStartVote.objects.get(id=vote_id)
        if vote is None or vote.status != FreshStartVote.PENDING:
            answer = self.VOTE_CLOSED_MSG
        elif response == self.JOIN_RESPONSE:
            if trainee.id in vote.participants:
                answer = self.ALREADY_JOINED_MSG
            elif vote.add_participant(trainee):
                answer = self.JOINED_MSG
            else:
                answer = self.VOTE_CLOSED_MSG
        else:
            if trainee.id not in vote.participants:
                answer = self.NOT_JOINED_MSG
            elif vote.remove_participant(trainee):
                answer = self.LEFT_MSG
            else:
                answer = self.VOTE_CLOSED_MSG

        # The vote is already recorded, so a failure to answer the tap or to update the vote
        # message must not keep the group from hearing of it. E.g. a tap made while the bot was
        # down is too old to answer, and when many tap at once Telegram limits the bot. The
        # next tap updates the message.
        try:
            context.bot.answerCallbackQuery(text=answer, callback_query_id=query.id)
        except TelegramError:
            self.logger.exception('Failed to answer the fresh start callback query of %s', trainee)

        if answer in (self.JOINED_MSG, self.LEFT_MSG):
            try:
                query.edit_message_text(text=self._get_vote_msg(vote),
                                        reply_markup=self._get_vote_keyboard(vote))
            except TelegramError:
                self.logger.exception('Failed to update the message of %s', vote)

            notification_msg = self.JOINED_NOTIFICATION_MSG if answer == self.JOINED_MSG else self.LEFT_NOTIFICATION_MSG
            self._send_message(context,
                               chat_id=group.id,
                               text=notification_msg.format(trainee=trainee.first_name,
                                                            participants=self._get_participants_names(vote)),
                               reply_to_message_id=vote.message_id,
                               allow_sending_without_reply=True)

    def _schedule_vote_closing(self, vote: FreshStartVote):
        # Dates in the DB are naive local time, but the job queue runs in UTC, so a naive
        # deadline would close the vote hours late.
        self._run_job(callback=self._queue_vote_closing,
                      vote_id=vote.id,
                      when=SCHEDULE_TIMEZONE.localize(vote.executes_at))
        self.logger.info('Scheduled closing of %s', vote)

    def _schedule_vote_reminder(self, vote: FreshStartVote):
        """Schedule the reminder of an open vote, unless it was already sent or the vote is overdue."""
        if vote.status != FreshStartVote.PENDING or vote.reminded or datetime.now() >= vote.executes_at:
            return

        self._run_job(callback=self._queue_vote_reminder,
                      vote_id=vote.id,
                      when=SCHEDULE_TIMEZONE.localize(vote.executes_at - self.REMINDER_BEFORE_CLOSING))
        self.logger.info('Scheduled reminder of %s', vote)

    def _run_job(self, callback, vote_id, when):
        self.updater.job_queue.run_once(
            callback=callback,
            when=when,
            context=str(vote_id),
            name='{name}{callback}_{vote_id}'.format(name=self.__class__.__name__,
                                                     callback=callback.__name__,
                                                     vote_id=vote_id),
            # APScheduler skips runs that are more than a second late by default, which would
            # leave the vote open forever. None lets it run however late it is.
            job_kwargs={'misfire_grace_time': None},
        )

    def _queue_vote_closing(self, context: CallbackContext):
        """Job callback, puts the closing of the vote on the dispatcher's queue."""
        self.updater.dispatcher.update_queue.put(CloseFreshStartVote(vote_id=context.job.context))

    def _queue_vote_reminder(self, context: CallbackContext):
        """Job callback, puts the reminder of the vote on the dispatcher's queue."""
        self.updater.dispatcher.update_queue.put(RemindFreshStartVote(vote_id=context.job.context))

    def _remind_vote(self, update: RemindFreshStartVote, context: CallbackContext):
        """Remind the group that the vote closes soon, retrying later if that fails."""
        try:
            self._remind_vote_now(vote_id=update.vote_id, context=context)
        except Exception:
            self.logger.exception('Failed to remind fresh start vote %s, retrying in %s',
                                  update.vote_id, self.RETRY_DELAY)
            self._run_job(callback=self._queue_vote_reminder, vote_id=update.vote_id, when=self.RETRY_DELAY)

    def _remind_vote_now(self, vote_id, context: CallbackContext):
        """Remind the group that the vote closes soon, quoting the vote message.

        The vote is marked as reminded before the reminder is sent, so a group is never
        reminded twice, even by a bot that restarts right after sending it. Everything that
        can fail on the DB is done before it, so a retry is never left with a vote marked
        as reminded that was not.

        """
        vote = FreshStartVote.objects.get(id=vote_id)
        if vote is None or datetime.now() >= vote.executes_at:
            self.logger.info('Fresh start vote %s was already closed', vote_id)
            return

        reminder_msg = self.REMINDER_MSG.format(participants=self._get_participants_names(vote))
        if not vote.mark_reminded():
            self.logger.info('Fresh start vote %s was already closed or reminded', vote_id)
            return

        self._send_message(context,
                           chat_id=vote.group.pk,
                           text=reminder_msg,
                           reply_to_message_id=vote.message_id,
                           allow_sending_without_reply=True)
        self.logger.info('Reminded %s', vote)

    def _close_vote(self, update: CloseFreshStartVote, context: CallbackContext):
        """Close the vote and start the new seasons, retrying later if that fails.

        A failure, e.g. the DB being unreachable, leaves the vote open or half closed. Each
        step of closing is recorded on the vote, so the retry finishes it without doing any
        step twice. Until then the group cannot open another vote.

        """
        try:
            self._close_vote_now(vote_id=update.vote_id, context=context)
        except Exception:
            self.logger.exception('Failed to close fresh start vote %s, retrying in %s',
                                  update.vote_id, self.RETRY_DELAY)
            self._run_job(callback=self._queue_vote_closing, vote_id=update.vote_id, when=self.RETRY_DELAY)

    def _close_vote_now(self, vote_id, context: CallbackContext):
        """Close the vote and start the new seasons.

        The ranking message is generated before the reset, and every message is sent after
        it, so a failure to send one never leaves the reset half done or late.

        """
        vote = FreshStartVote.objects.get(id=vote_id)
        if vote is None or not vote.close():
            self.logger.info('Fresh start vote %s was already closed or cancelled', vote_id)
            return

        self.logger.info('Closing %s', vote)
        group = Group.objects.get(id=vote.group.pk)

        if vote.status == FreshStartVote.CANCELLED:
            self._remove_vote_keyboard(context, vote)
            self._send_message(context, chat_id=group.id, text=self.NOBODY_JOINED_MSG)
            return

        ranking_msg = RankingCommand.get_ranking_msg(group)
        trainees = vote.start_new_seasons()
        self.logger.info('Started new seasons for %s', trainees)

        self._remove_vote_keyboard(context, vote)
        trainees_names = ', '.join(trainee.first_name for trainee in trainees)
        self._send_message(context, chat_id=group.id, text=self.RANKING_BEFORE_RESET_MSG.format(ranking=ranking_msg))
        self._send_message(context, chat_id=group.id, text=self.NEW_SEASON_MSG.format(trainees=trainees_names))

        # Notify other groups.
        other_groups_trainees_names = defaultdict(list)
        for trainee in trainees:
            for other_group in trainee.groups:
                if other_group != group:
                    other_groups_trainees_names[other_group.id].append(trainee.first_name)

        for other_group_id, names in other_groups_trainees_names.items():
            self._send_message(context,
                               chat_id=other_group_id,
                               text=self.NEW_SEASON_MSG_TO_OTHER_GROUPS.format(trainees=', '.join(names)))

    def _send_message(self, context: CallbackContext, chat_id, text, **kwargs):
        """Send a message, logging a failure instead of raising it."""
        try:
            context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except TelegramError:
            self.logger.exception('Failed to send fresh start message to %s', chat_id)

    def _remove_vote_keyboard(self, context: CallbackContext, vote: FreshStartVote):
        """Remove the buttons of the vote message, logging a failure instead of raising it."""
        try:
            context.bot.edit_message_reply_markup(chat_id=vote.group.pk,
                                                  message_id=vote.message_id,
                                                  reply_markup=None)
        except TelegramError:
            self.logger.exception('Failed to remove the keyboard of %s', vote)

    def _get_participants_names(self, vote: FreshStartVote):
        participants = Trainee.objects.filter(id__in=vote.participants)
        return ', '.join(trainee.first_name for trainee in participants) or self.NO_PARTICIPANTS_YET

    def _get_vote_msg(self, vote: FreshStartVote):
        return self.VOTE_MSG.format(deadline=vote.executes_at.strftime(self.DEADLINE_FORMAT),
                                    participants=self._get_participants_names(vote))

    def _get_vote_keyboard(self, vote: FreshStartVote):
        callback_data = '{identifier} {vote_id} {{response}}'.format(identifier=self.FRESH_START_QUERY_IDENTIFIER,
                                                                     vote_id=vote.id)

        return InlineKeyboardMarkup([[
            InlineKeyboardButton(self.JOIN_BUTTON_TEXT, callback_data=callback_data.format(response=self.JOIN_RESPONSE)),
            InlineKeyboardButton(self.LEAVE_BUTTON_TEXT, callback_data=callback_data.format(response=self.LEAVE_RESPONSE)),
        ]])
