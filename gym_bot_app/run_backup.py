import os
import sys
import datetime as dt

from mongoengine import connect
from gym_bot_app.models import *


BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backups/')

MODELS_TO_BACKUP = (
    Trainee,
    Group,
    Admin,
    TrainingDayInfo,
    FreshStartVote,
    PersonalMotivationQuote
)


def backup(con_url):
    connect(host=con_url)

    os.makedirs(BACKUP_DIR, exist_ok=True)

    for ModelToBackUp in MODELS_TO_BACKUP:
        data = ModelToBackUp.objects.to_json()
        filename = '{model_name}.{date}.json'.format(model_name=ModelToBackUp.__name__,
                                                     date=dt.date.today().strftime('%d.%m.%Y'))
        with open(os.path.join(BACKUP_DIR, filename), 'w') as f:
            f.write(data)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        os.environ['MONGODB_URL_CON'] = os.environ['MONGODB_URL_CON_TEST']

    db_con_string = os.environ['MONGODB_URL_CON']
    backup(db_con_string)
