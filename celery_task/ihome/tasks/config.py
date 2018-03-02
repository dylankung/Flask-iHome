# coding:utf-8

broker_url = "redis://127.0.0.1:6379/1"
result_backend = "redis://127.0.0.1:6379/2"

task_routes = ({
    'ihome.tasks.sms.tasks.send_template_sms': {'queue': 'sms'},
    'ihome.tasks.orders.tasks.save_order': {'queue': 'orders'}
})
