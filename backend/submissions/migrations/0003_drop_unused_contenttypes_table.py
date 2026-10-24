"""Remove the django_content_type table.

`django.contrib.contenttypes` was in INSTALLED_APPS out of habit — it ships in
Django's default project template. It exists so that other Django features can
refer to "a row in any model", which is what the admin's permission system and
generic foreign keys need.

This project uses none of that: no admin, no generic relations, no Django
permissions (roles live in app_profile). The table it created held three rows
naming our own models, and nothing ever read them.

On a fresh database the table is never created, because the app is no longer
installed. On an existing one this removes it. IF EXISTS covers both.
"""

from django.db import migrations

DROP = "DROP TABLE IF EXISTS public.django_content_type;"

# Not reversible in any useful sense: re-creating an empty table that nothing
# reads would restore clutter, not behaviour. Reinstalling the app would
# rebuild it properly if it were ever genuinely needed.
NOOP = migrations.RunSQL.noop


class Migration(migrations.Migration):
    dependencies = [("submissions", "0002_lock_down_data_api")]

    operations = [migrations.RunSQL(DROP, reverse_sql=NOOP)]
