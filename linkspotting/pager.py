import math

from flask import url_for, request
from sqlalchemy.orm.query import Query

class Pager(object):

    def __init__(self, query, route, limit=20, **kwargs):
        self.args = dict(request.args.items())
        self.args.update(kwargs)
        self.route = route 
        self.query = query
        try:
            self.page = int(self.args.get('page'))
        except:
            self.page = 1
        try:
            self.limit = min(int(args.get('limit')), 200)
        except:
            self.limit = limit

    @property
    def offset(self):
        return (self.page-1)*self.limit

    @property
    def pages(self):
        return int(math.ceil(len(self)/float(self.limit)))

    @property
    def has_next(self):
        return self.page < self.pages

    @property
    def has_prev(self):
        return self.page > 1

    @property
    def next_url(self):
        return self.page_url(self.page + 1) if self.has_next \
               else self.page_url(self.page)

    @property
    def prev_url(self):
        return self.page_url(self.page - 1) if self.has_prev \
               else self.page_url(self.page)

    @property
    def params(self):
        return [(k, unicode(v).encode('utf-8')) for k, v in self.args.items() \
                if k != 'page']

    def page_url(self, page):
        return url_for(self.route, page=page, **dict(self.params))

    def __iter__(self):
        if isinstance(self.query, Query):
            query = self.query.limit(self.limit)
            query = query.offset(self.offset)
            return query.all().__iter__()
        return iter(self.query[self.offset:self.limit+self.offset])

    def __len__(self):
        if isinstance(self.query, Query):
            return self.query.count()
        return len(self.query)

