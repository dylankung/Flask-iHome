# coding:utf-8

from ihome import create_app
flask_app = create_app("development")

from ihome import db
from ihome.tasks.main import app
from ihome.models import Order
import datetime


@app.task
def save_order(user_id, house_id, start_date_str, end_date_str, price):
    flask_app.app_context().push()
    # 确保用户预订的时间内，房屋没有被别人下单
    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
    end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
    try:
        # 查询时间冲突的订单数
        count = Order.query.filter(Order.house_id == house_id, Order.begin_date <= end_date,
                                   Order.end_date >= start_date).count()
    except Exception as e:
        print(e)
        return -1
    if count > 0:
        return -2

    # 订单总额
    days = (end_date - start_date).days + 1
    amount = days * price

    # 保存订单数据
    order = Order()
    order.house_id = house_id
    order.user_id = user_id
    order.begin_date = start_date
    order.end_date = end_date
    order.days = days
    order.house_price = price
    order.amount = amount
    try:
        db.session.add(order)
        db.session.commit()
    except Exception as e:
        print(e)
        db.session.rollback()
        return -1

    return order.id
