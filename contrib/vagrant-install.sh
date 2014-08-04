
echo `whoami`

sudo apt-get update -y
sudo apt-get upgrade -y
sudo apt-get install -y software-properties-common python-software-properties python g++ make
sudo add-apt-repository -y ppa:chris-lea/node.js
sudo apt-get update -y
sudo apt-get install -y nodejs postgresql python-virtualenv git postgresql-server-dev-9.1 postgresql-contrib python-dev libxml2-dev libxslt1-dev
sudo npm install -g bower less uglify-js

virtualenv /home/vagrant/env
source /home/vagrant/env/bin/activate
pip install -r /vagrant/requirements.txt
pip install honcho
echo "source /home/vagrant/env/bin/activate" >>/home/vagrant/.profile

sudo -u postgres createuser -s vagrant
createdb -T template0 -E utf-8 -O vagrant nomenklatura
psql -d nomenklatura -c "ALTER USER vagrant PASSWORD 'vagrant';"
psql -d nomenklatura -c "CREATE EXTENSION IF NOT EXISTS hstore;"
psql -d nomenklatura -c "CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;"

if [ ! -f /vagrant/vagrant_settings.py ]; then
    touch /vagrant/vagrant_settings.py
    echo "SQLALCHEMY_DATABASE_URI = 'postgresql://vagrant:vagrant@localhost/nomenklatura'" >>/vagrant/vagrant_settings.py
fi
echo "export NOMENKLATURA_SETTINGS=/vagrant/vagrant_settings.py" >>/home/vagrant/.profile
export NOMENKLATURA_SETTINGS=/vagrant/vagrant_settings.py

cd /vagrant 

python setup.py develop
python nomenklatura/manage.py createdb 
