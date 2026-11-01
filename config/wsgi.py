"""
WSGI config for backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

# Limit glibc memory arena fragmentation on 512MB RAM Linux hosts
os.environ.setdefault('MALLOC_ARENA_MAX', '2')
os.environ.setdefault('PYTHONUNBUFFERED', '1')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
