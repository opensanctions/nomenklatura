#!/bin/bash

mkdir -p nomenklatura/static/vendor
bower install --allow-root
/env/bin/python nomenklatura/manage.py createdb
/env/bin/python nomenklatura/manage.py runserver -p 8080 -t 0.0.0.0