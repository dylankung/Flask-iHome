# -*- coding:utf-8 -*-

from flask import jsonify
from flask_wtf.csrf import CSRFError
from ihome.utils.response_code import RET
from . import api


# flask对于错误默认返回给前端网页，自定义处理400错误返回json的信息
@api.app_errorhandler(400)
def error_400(reason):
    # 如果对于400错误reason是抛出的CSRF缺失的异常，则以json格式返回提示信息
    if isinstance(reason, CSRFError):
        return jsonify(
            errno=RET.REQERR,
            errmsg="The CSRF token is missing."
        ), 400
    # 如果reason是字符串，则直接以json格式返回
    elif isinstance(reason, str):
        return jsonify(
            errno=RET.REQERR,
            errmsg=reason
        ), 400
    # 如果reason是其他类型，则返回未知错误
    else:
        return jsonify(
            errno=RET.REQERR,
            errmsg="unknown"
        ), 400


