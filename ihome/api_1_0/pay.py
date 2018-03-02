# coding:utf-8

from . import api
from ihome.models import Order
from ihome.utils.commons import login_required
from flask import current_app, g, jsonify, request
from ihome.utils.response_code import RET
from alipay import AliPay
from ihome import db
import os


@api.route("/orders/<int:order_id>/payment", methods=["POST"])
@login_required
def order_pay(order_id):
    """订单支付"""
    user_id = g.user_id
    try:
        order = Order.query.filter_by(id=order_id, status="WAIT_PAYMENT", user_id=user_id).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="查询订单信息异常")

    if order is None:
        return jsonify(errno=RET.DATAERR, errmsg="订单数据异常")

    # 构造支付宝支付链接地址
    alipay_client = AliPay(
        appid=current_app.config["ALIPAY_APPID"],
        app_notify_url=None,  # 默认回调url
        app_private_key_path=os.path.join(os.path.dirname(__file__), "keys/app_private_key.pem"),
        alipay_public_key_path=os.path.join(os.path.dirname(__file__), "keys/alipay_public_key.pem"),
        # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
        sign_type="RSA2",  # RSA 或者 RSA2
        debug=True  # 默认False
    )

    order_string = alipay_client.api_alipay_trade_wap_pay(
        out_trade_no=order.id,
        total_amount=str(order.amount/100),
        subject=u"爱家租房%s" % order.id,
        return_url="http://127.0.0.1:5000/payComplete.html",
    )

    alipay_url = current_app.config["ALIPAY_URL"] + "?" + order_string
    return jsonify(errno=RET.OK, errmsg="OK", data={"pay_url": alipay_url})


@api.route("/payment", methods=["POST"])
def set_pay_result():
    """设置支付结果"""
    data = request.form.to_dict()
    signature = data.pop("sign")

    alipay_client = AliPay(
        appid=current_app.config["ALIPAY_APPID"],
        app_notify_url=None,  # 默认回调url
        app_private_key_path=os.path.join(os.path.dirname(__file__), "keys/app_private_key.pem"),
        alipay_public_key_path=os.path.join(os.path.dirname(__file__), "keys/alipay_public_key.pem"),
        # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
        sign_type="RSA2",  # RSA 或者 RSA2
        debug=True  # 默认False
    )

    success = alipay_client.verify(data, signature)

    if success:
        order_id = data.get("out_trade_no")
        trade_no = data.get("trade_no")
        try:
            Order.query.filter_by(id=order_id).update({"status": "WAIT_COMMENT", "trade_no": trade_no})
            db.session.commit()
        except Exception as e:
            current_app.logger.error(e)
            db.session.rollback()
            return jsonify(errno=RET.DBERR, errmsg="更新支付信息失败")
        return jsonify(errno=RET.OK, errmsg="OK")
    else:
        return jsonify(errno=RET.REQERR, errmsg="参数错误")
