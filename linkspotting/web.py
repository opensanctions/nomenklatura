from flask import render_template

from linkspotting.core import app, db

@app.route('/')
def index():
    return render_template('index.html')
