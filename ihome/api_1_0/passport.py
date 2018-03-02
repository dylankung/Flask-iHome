# -*- coding:utf-8 -*-

import re

from flask import jsonify, request, current_app, session
from ihome.models import User
from ihome.utils.response_code import RET
from ihome import db, redis_store, constants
from ihome.utils.commons import login_required
from . import api


@api.route("/users", methods=["POST"])
def register():
    """用户注册"""
    # 从json中获取参数
    user_data = request.get_json()
    if not user_data:
        return jsonify(errno=RET.PARAMERR, errmsg="参数不完整")

    mobile = user_data.get("mobile")  # 手机号
    sms_code = user_data.get("sms_code")  # 短信验证码
    password = user_data.get("password")  # 密码

    # 检查参数
    if not all([mobile, sms_code, password]):
        return jsonify(errno=RET.PARAMERR, errmsg="参数不完整")

    # 手机号格式校验
    if not re.match(r"1[34578]\d{9}$", mobile):
        return jsonify(errno=RET.PARAMERR, errmsg="手机号格式不正确")

    # 检查短信验证码
    # 从redis中读取真实的短信验证码
    try:
        real_sms_code = redis_store.get("SMSCode_" + mobile)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="读取验证码异常")

    # 判断验证码是否过期
    if not real_sms_code:
        return jsonify(errno=RET.DATAERR, errmsg="短信验证码过期")

    # 判断用户输入的验证码的正确性
    if real_sms_code != str(sms_code):
        return jsonify(errno=RET.DATAERR, errmsg="短信验证码无效")

    # 已经进行过短信验证码的对比校验，所以删除redis中的smscode
    try:
        redis_store.delete("SMSCode_" + mobile)
    except Exception as e:
        current_app.logger.error(e)

    # 保存用户信息
    user = User(name=mobile, mobile=mobile)
    # 通过设置user模型的password属性，实际调用了设置密码的方法，对密码进行了加密
    user.password = password
    try:
        db.session.add(user)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DATAEXIST, errmsg="手机号已存在")

    # 保存用户的session数据
    session["user_id"] = user.id
    session["name"] = mobile
    session["mobile"] = mobile

    return jsonify(errno=RET.OK, errmsg="OK", data=user.to_dict())


@api.route("/sessions", methods=["POST"])
def login():
    """用户登录"""
    # 获取参数
    req_data = request.get_json()
    if not req_data:
        return jsonify(errno=RET.PARAMERR, errmsg="参数不完整")

    mobile = req_data.get("mobile")
    password = req_data.get("password")

    # 检查参数
    if not all([mobile, password]):
        return jsonify(errno=RET.PARAMERR, errmsg="参数不完整")

    # 手机号格式校验
    if not re.match(r"^1[34578]\d{9}$", mobile):
        return jsonify(errno=RET.PARAMERR, errmsg="手机号格式错误")

    # 判断访问次数是否超过限制
    try:
        access_count = redis_store.get("access_%s" % request.remote_addr)
    except Exception as e:
        current_app.logger.error(e)
    else:
        if access_count is not None and int(access_count) >= constants.LOGIN_ERROR_MAX_NUM:
            return jsonify(errno=RET.REQERR, errmsg="请求过于频繁")

    # 检查密码是否正确
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="数据库异常")
    # 调用user模型中实现的检验用户密码的方法
    if user is None or not user.check_password(password):
        try:
            redis_store.incr("access_%s" % request.remote_addr)
            redis_store.expire("access_%s" % request.remote_addr, constants.LOGIN_ERROR_LOCKED_TIME)
        except Exception as e:
            current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR, errmsg="手机号或密码错误")

    # 删除访问次数记录
    try:
        redis_store.delete("access_%s" % request.remote_addr)
    except Exception as e:
        current_app.logger.error(e)

    # 用户验证成功，保存用户的session数据
    session["user_id"] = user.id
    session["name"] = user.name
    session["mobile"] = user.mobile

    return jsonify(errno=RET.OK, errmsg="登录成功", data={"user_id": user.id})


@api.route("/session", methods=["GET"])
def check_login():
    """检查登陆状态"""
    # 尝试从session中获取用户的名字
    name = session.get("name")
    # 如果session中数据name名字存在，则表示用户已登录，否则未登录
    if name is not None:
        return jsonify(errno=RET.OK, errmsg="true", data={"name": name})
    else:
        return jsonify(errno=RET.SESSIONERR, errmsg="false")


@api.route("/session", methods=["DELETE"])
@login_required
def logout():
    """登出"""
    # 清除session数据
    csrf_token = session.get("csrf_token")
    session.clear()
    session["csrf_token"] = csrf_token
    return jsonify(errno=RET.OK, errmsg="OK")
