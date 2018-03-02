# coding:utf-8


from celery import Celery


app = Celery("ihome")
app.config_from_object("ihome.tasks.config")

app.autodiscover_tasks(["ihome.tasks.sms", "ihome.tasks.orders"])