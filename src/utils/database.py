#!/usr/bin/env python
# -*- coding: utf-8 -*-

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from src import config

"""
How to use scoped sessions, please see here 
https://docs.sqlalchemy.org/en/13/orm/contextual.html?highlight=
scoped_session#sqlalchemy.orm.scoping.scoped_session
"""

__author__ = "Yashpal Meena <yashpal.meena@screen-magic.com>"
__copyright__ = "Copyright 2022 Screen Magic Mobile Pvt Ltd"

db_url = config.SQLALCHEMY_DATABASE_URI
options = {'pool_recycle': 3600, 'echo': False}
engine = create_engine(db_url, **options)
session = scoped_session(sessionmaker(bind=engine))
