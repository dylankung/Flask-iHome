# -*- coding:utf-8 -*-

from flask import Blueprint, current_app, make_response, session
from flask_wtf import csrf

html = Blueprint("html", __name__)


@html.route("/<regex('.*'):file_name>")
def html_file(file_name):
    """根据用户请求的静态html文件名file_name，提供静态html文件资源"""
    # 如果未指明文件名，则默认返回index.html主页
    if not file_name:
        file_name = "index.html"

    # 如果请求的是不是网站logo图标favicon.ico，则固定从html目录中寻找html文件
    if file_name != "favicon.ico":
        file_name = "html/" + file_name

    # 为客户端设置csrf_token
    # 先生成csrf_token 数据
    csrf_token = csrf.generate_csrf()
    response = make_response(current_app.send_static_file(file_name))
    # 将csrf_token数据设置到用户的cookie中
    response.set_cookie("csrf_token", csrf_token)

    return response

