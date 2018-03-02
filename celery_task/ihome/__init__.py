# -*- coding:utf-8 -*-
import logging
import redis

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from flask_session import Session
from config import config, Config
from utils.commons import RegexConverter

# 创建数据库对象
db = SQLAlchemy()
# 创建redis对象
redis_store = redis.StrictRedis(host=Config.REDIS_HOST, port=Config.REDIS_PORT)

# 使用wtf提供的csrf保护机制
csrf = CSRFProtect()


def create_app(config_name):
    """创建flask应用app对象"""
    app = Flask(__name__)
    # 从配置对象中为app设置配置信息
    app.config.from_object(config[config_name])

    # 为app中的url路由添加正则表达式匹配
    app.url_map.converters["regex"] = RegexConverter

    # 为app添加CSRF保护
    csrf.init_app(app)

    # 使用flask-session扩展，用redis保存app的session数据
    Session(app)

    # 数据库处理
    db.init_app(app)

    return app
