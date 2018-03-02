# coding:utf-8

from ihome.tasks.main import app
from ihome.libs.yuntongxun.sms import CCP


@app.task
def send_template_sms(to, datas, temp_id):
    """发送短信"""
    ccp = CCP()
    ccp.send_template_sms(to, datas, temp_id)

