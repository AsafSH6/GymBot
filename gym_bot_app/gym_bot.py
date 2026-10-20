import os
import logging
from logging.handlers import RotatingFileHandler

from telegram.ext import Updater

from gym_bot_app.background_http_server import run_simple_http_server_on_background
from gym_bot_app.commands import (AdminCommand,
                                  MyDaysCommand,
                                  TrainedCommand,
                                  RankingCommand,
                                  SelectDaysCommand,
                                  SetCreatureCommand,
                                  SetMotivationCommand,
                                  MyStatisticsCommand,
                                  BotStatisticsCommand,
                                  MotivationQuotesCommand,
                                  AllTrainingTraineesCommand,
                                  MonthRankingCommand,
                                  YearRankingCommand,
                                  FreshStartCommand)

from gym_bot_app.tasks import (GoToGymTask,
                               WentToGymTask,
                               TaskTypeToInstance,
                               NewWeekSelectDaysTask,
                               DidNotTrainUpdaterTask,
                               MotivationReminderTask)

MSG_TIMEOUT = 20

LOG_DIR = 'logs'
LOG_PATH = os.path.join(LOG_DIR, 'gymbot.log')
LOG_MAX_BYTES = 10 * 1024 * 1024
LOG_BACKUP_COUNT = 3

# The log file is rotated rather than left to grow without bound -- it shares a disk
# with everything else on the host. Note the StreamHandler added in __main__ is what
# puts the logs on stdout (basicConfig with a handler only writes to that handler), so
# it must stay: without it the container produces no visible output at all.
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(handlers=[RotatingFileHandler(LOG_PATH,
                                                  maxBytes=LOG_MAX_BYTES,
                                                  backupCount=LOG_BACKUP_COUNT)],
                    format='%(asctime)s %(levelname)s - [%(module)s:%(funcName)s:%(lineno)d] %(message)s',
                    datefmt='%d-%m-%Y:%H:%M:%S',
                    level=logging.INFO)


def run_gym_bot(token, logger):
    updater = Updater(token=token)

    """ Tasks """
    tasks = [
        GoToGymTask(updater=updater, logger=logger).start(),
        WentToGymTask(updater=updater, logger=logger).start(),
        NewWeekSelectDaysTask(updater=updater, logger=logger).start(),
        DidNotTrainUpdaterTask(updater=updater, logger=logger).start(),
        MotivationReminderTask(updater=updater, logger=logger).start(),
    ]

    task_type_to_instance: TaskTypeToInstance = {
        task.__class__.__name__: task
        for task in tasks
    }

    """ Commands """
    AdminCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    MyDaysCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    TrainedCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    RankingCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    SelectDaysCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    SetCreatureCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    SetMotivationCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    MonthRankingCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    YearRankingCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    FreshStartCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    MyStatisticsCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    BotStatisticsCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    MotivationQuotesCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start()
    AllTrainingTraineesCommand(tasks=task_type_to_instance, updater=updater, logger=logger).start(
        command_name='all_the_botim')

    updater.start_polling(timeout=MSG_TIMEOUT)
    updater.idle()


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        os.environ['BOT_TOKEN'] = os.environ['BOT_TOKEN_TEST']
        os.environ['MONGODB_URL_CON'] = os.environ['MONGODB_URL_CON_TEST']

    token = os.environ['BOT_TOKEN']
    db_con_string = os.environ['MONGODB_URL_CON']
    should_run_simple_http_server = bool(int(os.getenv('RUN_SIMPLE_HTTP_SERVER', '0')))

    from mongoengine import connect

    connect(host=db_con_string)

    logger = logging.getLogger()
    # logger.setLevel(logging.DEBUG)
    logger.addHandler(logging.StreamHandler())

    close_http_server_callback = run_simple_http_server_on_background(logger, should_run_simple_http_server)

    try:
        run_gym_bot(token, logger)
    finally:
        close_http_server_callback()
