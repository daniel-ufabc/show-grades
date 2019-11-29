import sys
sys.path.insert(0, '/var/www/show')

import os

from show import app as application

application.secret_key = os.urandom(24)

