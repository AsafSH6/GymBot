from mongoengine import QuerySet, DoesNotExist


class ExtendedQuerySet(QuerySet):
    """Extension of default QuerySet."""

    def get(self, *q_objs, **query):
        """Override method to look for 'id' argument and cast it to unicode.

        If object does not exist catches the exception and returns None.

        """
        try:
            if 'id' in query:
                query['id'] = unicode(query['id'])
            return super(ExtendedQuerySet, self).get(*q_objs, **query)
        except DoesNotExist:
            return None
