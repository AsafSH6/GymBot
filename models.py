from mongoengine import (Document,
                         StringField,
                         BooleanField,
                         )


class Day(Document):
    name = StringField(required=True, max_length=64)
    selected = BooleanField(default=False)


class Trainee(Document):
    id = StringField(required=True, primary_key=True, unique=True)
    first_name = StringField(required=True)
    training_days =