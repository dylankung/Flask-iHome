# -*- coding:utf-8 -*-

import random
import re

from flask import request, jsonify, current_app, make_response

from ihome import redis_store, constants
from ihome.models import User
from ihome.tasks.sms import tasks
from ihome.utils.captcha.captcha import captcha
from ihome.utils.response_code import RET
from . import api


@api.route("/imagecode/<image_code_id>", methods=["GET"])
def generate_image_code(image_code_id):
    """图片验证码"""
    # 生成图片验证码
    # name-图片验证码的名字， text-图片验证码的文本， image-图片的二进制数据
    name, text, image = captcha.generate_captcha()
    # 将图片验证码的编号与文本数据保存到redis中，供以后进行验证
    try:
        redis_store.setex("ImageCode_" + image_code_id, constants.IMAGE_CODE_REDIS_EXPIRES, text)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="保存图片验证码失败")
    else:
        response = make_response(image)
        # 设置传回给前端的内容数据是图片格式
        response.headers["Content-Type"] = "image/jpg"
        return response


@api.route("/smscode/<mobile>", methods=["GET"])
def send_sms_code(mobile):
    """发送手机短信验证码"""
    # 获取参数
    image_code = request.args.get("text")  # 用户填写的图片验证码的内容
    image_code_id = request.args.get("id")  # 图片验证码的编号

    # 参数校验
    if not all([mobile, image_code, image_code_id]):
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")

    # 手机号格式校验
    if not re.match(r"^1[34578]\d{9}$", mobile):
        return jsonify(errno=RET.PARAMERR, errmsg="手机号格式错误")

    # 验证图片验证码
    try:
        # 查询redis获取真实的图片验证码
        real_image_code = redis_store.get("ImageCode_" + image_code_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="查询数据异常")

    # 判断验证码是否过期
    if not real_image_code:
        return jsonify(errno=RET.DATAERR, errmsg="图片验证码过期")

    # 删除redis中的图片验证码
    try:
        redis_store.delete("ImageCode_" + image_code_id)
    except Exception as e:
        current_app.logger.error(e)

    # 判断验证码是否正确
    if image_code.lower() != real_image_code.lower():
        return jsonify(errno=RET.DATAERR, errmsg="图片验证码错误")

    # 判断手机号是否注册过
    try:
        user = User.query.filter_by(mobile=mobile).first()
    except Exception as e:
        current_app.logger.error(e)
    else:
        if user is not None:
            return jsonify(errno=RET.DBERR, errmsg="手机号已存在")

    # 判断是否在60秒内重复发送短信
    try:
        send_flag = redis_store.get("SMSCodeSendFlag_" + mobile)
    except Exception as e:
        current_app.logger.error(e)
    else:
        if send_flag:
            return jsonify(errno=RET.REQERR, errmsg="发送次数过于频繁")

    # 生成短信验证码
    sms_code = '%06d' % random.randint(0, 1000000)

    # 在redis中保存短信验证码
    try:
        redis_store.setex("SMSCode_" + mobile, constants.SMS_CODE_REDIS_EXPIRES, sms_code)
        redis_store.setex("SMSCodeSendFlag_" + mobile, constants.SEND_SMS_CODE_INTERVAL, 1)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="保存数据出现错误")

    # 发送短信验证码
    # try:
    #     ccp = sms.CCP()
    #     result = ccp.send_template_sms(mobile, [sms_code, constants.SMS_CODE_REDIS_EXPIRES/60], 1)
    # except Exception as e:
    #     current_app.logger.error(e)
    #     return jsonify(errno=RET.THIRDERR, errmsg="发送短信异常")
    #
    # if 0 == result:
    #     return jsonify(errno=RET.OK, errmsg="发送成功")
    # else:
    #     return jsonify(errno=RET.THIRDERR, errmsg="发送短信失败")

    tasks.send_template_sms.delay(mobile, [sms_code, constants.SMS_CODE_REDIS_EXPIRES / 60], 1)
    return jsonify(errno=RET.OK, errmsg="发送成功")
