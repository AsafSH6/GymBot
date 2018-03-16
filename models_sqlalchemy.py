# encoding: utf-8
from __future__ import unicode_literals

import os

from sqlalchemy.orm import relationship, sessionmaker, Query
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (Table,
                        Column,
                        ForeignKey,
                        String,
                        event,
                        create_engine)
Base = declarative_base()
engine = create_engine(os.environ['POSTGRES_URL_CON'])


user_and_days_association_table = Table('user_and_days', Base.metadata,
    Column('day', String, ForeignKey('day.name'),  primary_key=True),
    Column('user', String, ForeignKey('user.id'),  primary_key=True)
)

user_and_groups_association_table = Table('user_and_groups', Base.metadata,
    Column('group', String, ForeignKey('group.id')),
    Column('user', String, ForeignKey('user.id'))
)


class ExtendedQuery(Query):
    def get(self, ident):
        return super(ExtendedQuery, self).get(str(ident))


class Day(Base):
    __tablename__ = 'day'
    name = Column(String(255), primary_key=True)
    users = relationship('User', secondary=user_and_days_association_table, backref='days')

    def __repr__(self):
        return '{name}'.format(name=self.name)

    def __unicode__(self):
        return repr(self)

    def __str__(self):
        return repr(self)


@event.listens_for(Day.__table__, 'after_create', once=True)
def insert_initial_values(*args, **kwargs):
    from utils import DAYS_NAME
    Base.metadata.bind = engine
    session = sessionmaker(bind=engine)()
    session.add_all([Day(name=day_name) for day_name in DAYS_NAME])
    session.commit()
    session.close()


class User(Base):
    __tablename__ = 'user'
    id = Column(String(255), primary_key=True)
    first_name = Column(String(255), nullable=True)

    def __repr__(self):
        return "<User(id='%s', first name='%s')>" % (self.id, self.first_name)

    def __unicode__(self):
        return repr(self)

    def __str__(self):
        return repr(self)


class Group(Base):
    __tablename__ = 'group'
    id = Column(String(255), primary_key=True)
    users = relationship('User', secondary=user_and_groups_association_table, backref='group')

    def __repr__(self):
        return "<Group(id='%s')>" % self.id

    def __unicode__(self):
        return repr(self)

    def __str__(self):
        return repr(self)


# Create all tables in the engine. This is equivalent to "Create Table"
# statements in raw SQL.
Base.metadata.create_all(engine)


