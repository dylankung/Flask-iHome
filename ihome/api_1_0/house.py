# -*- coding:utf-8 -*-

import json
import datetime

from flask import current_app, request, jsonify, g, session
from ihome import db, redis_store, constants
from ihome.utils.response_code import RET
from ihome.utils.commons import login_required
from ihome.utils.image_storage import storage
from ihome.models import Area, House, Facility, HouseImage, User, Order
from . import api


@api.route("/areas", methods=["GET"])
def get_areas_info():
    """提供房屋区域信息"""
    # 先查询redis获取缓存数据
    try:
        areas = redis_store.get("area_info")
    except Exception as e:
        current_app.logger.error(e)
        areas = None

    # 如果redis中存在，直接将数据返回
    if areas:
        current_app.logger.info("hit area info redis")
        # 因为redis中保存的是json字符串，所以直接进行字符串拼接返回
        return '{"errno":0, "errmsg":"OK", "data":%s}' % areas

    # 如果redis中不存在，查询数据库
    # 查询数据库，获取城区信息
    try:
        areas = Area.query.all()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="获取城区信息失败")

    # 将areas对象列表中的对象转换为字典
    areas_list = []
    for area in areas:
        areas_list.append(area.to_dict())

    # 将areas_list转换为json字符串
    json_areas = json.dumps(areas_list)

    # 将数据保存到redis作为缓存
    try:
        redis_store.setex("area_info", constants.AREA_INFO_REDIS_EXPIRES, json_areas)
    except Exception as e:
        current_app.logger.error(e)

    resp = '{"errno":"0", "errmsg":"OK", "data":%s}' % json_areas
    return resp


@api.route("/houses", methods=["POST"])
@login_required
def save_new_house():
    """
    房东发布房源信息
    前端发送过来的json数据
    {
        "title":"",
        "price":"",
        "area_id":"1",
        "address":"",
        "room_count":"",
        "acreage":"",
        "unit":"",
        "capacity":"",
        "beds":"",
        "deposit":"",
        "min_days":"",
        "max_days":"",
        "facility":["7","8"]
    }
    """
    user_id = g.user_id  # 用户编号

    # 获取参数
    house_data = request.get_json()
    if house_data is None:
        return jsonify(errno=RET.PARAMERR, errmsg="参数缺失")

    title = house_data.get("title")  # 房屋名称标题
    price = house_data.get("price")  # 房屋单价
    area_id = house_data.get("area_id")  # 房屋所属城区的编号
    address = house_data.get("address")  # 房屋地址
    room_count = house_data.get("room_count")  # 房屋包含的房间数目
    acreage = house_data.get("acreage")  # 房屋面积
    unit = house_data.get("unit")  # 房屋布局（几室几厅)
    capacity = house_data.get("capacity")  # 房屋容纳人数
    beds = house_data.get("beds")  # 房屋卧床数目
    deposit = house_data.get("deposit")  # 押金
    min_days = house_data.get("min_days")  # 最小入住天数
    max_days = house_data.get("max_days")  # 最大入住天数

    # 校验传入数据
    if not all((title, price, area_id, address, room_count, acreage, unit, capacity, beds, deposit, min_days,
                max_days)):
        return jsonify(errno=RET.PARAMERR, errmsg="参数缺失")

    # 前端传过来的单价和押金是以元为单位，转换为分
    try:
        price = int(float(price) * 100)
        deposit = int(float(deposit) * 100)
    except Exception as e:
        return jsonify(errno=RET.PARAMERR, errmsg="参数错误")

    # 保存房屋基本信息数据到数据库
    house = House()
    house.user_id = user_id
    house.area_id = area_id
    house.title = title
    house.price = price
    house.address = address
    house.room_count = room_count
    house.acreage = acreage
    house.unit = unit
    house.capacity = capacity
    house.beds = beds
    house.deposit = deposit
    house.min_days = min_days
    house.max_days = max_days

    # 处理房屋的设施编号
    facility = house_data.get("facility")
    if facility:
        # 过滤用户发送的设施信息，查找出真实存在的设施，过滤掉错误的设施编号
        facilities = Facility.query.filter(Facility.id.in_(facility)).all()
        house.facilities = facilities
    try:
        db.session.add(house)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg="保存房屋数据失败")

    return jsonify(errno=RET.OK, errmsg="OK", data={"house_id": house.id})


@api.route("/houses/<int:house_id>/images", methods=["POST"])
@login_required
def save_house_image(house_id):
    """房东上传房屋照片"""
    # 获取要保存的房屋id与照片
    image = request.files.get("house_image")
    if not image:
        return jsonify(errno=RET.PARAMERR, errmsg="未传图片")

    # 判断房屋是否存在
    try:
        house = House.query.get(house_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR, errmsg="房屋不存在")

    # 读取上传的文件内容，并上传到七牛
    image_data = image.read()
    try:
        image_name = storage(image_data)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.THIRDERR, errmsg="上传图片失败")

    # 保存房屋图片数据到数据库中，在数据库中仅保存七牛上文件的路径（文件名），不保存七牛的服务器域名
    house_image = HouseImage()
    house_image.house_id = house_id
    house_image.url = image_name
    db.session.add(house_image)

    # 如果房屋的主图片尚未设置，则设置房屋的主图片
    if not house.index_image_url:
        house.index_image_url = image_name
        db.session.add(house)
    try:
        db.session.commit()
    except Exception as e:
        current_app.logger.error(e)
        db.session.rollback()
        return jsonify(errno=RET.DBERR, errmsg="保存房屋图片失败")

    # 将图片路径拼接完整，返回给前端
    img_url = constants.QINIU_DOMIN_PREFIX + image_name
    return jsonify(errno=RET.OK, errmsg="OK", data={"url": img_url})


@api.route("/user/houses", methods=["GET"])
@login_required
def get_user_houses():
    """获取房东发布的房源信息条目"""
    user_id = g.user_id

    try:
        user = User.query.get(user_id)
        houses = user.houses
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="获取数据失败")

    # 将查询到的房屋信息转换为字典存放到列表中
    houses_list = []
    if houses:
        for house in houses:
            houses_list.append(house.to_basic_dict())
    return jsonify(errno=RET.OK, errmsg="OK", data={"houses": houses_list})


@api.route("/houses/index", methods=["GET"])
def get_house_index():
    """获取主页幻灯片展示的房屋基本信息"""
    # 从缓存中尝试获取数据
    try:
        ret = redis_store.get("home_page_data")
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    if ret:
        current_app.logger.info("hit house index info redis")
        # 因为redis中保存的是json字符串，所以直接进行字符串拼接返回
        return '{"errno":0, "errmsg":"OK", "data":%s}' % ret
    else:
        try:
            # 查询数据库，返回房屋订单数目最多的5条数据
            houses = House.query.order_by(House.order_count.desc()).limit(constants.HOME_PAGE_MAX_HOUSES)
        except Exception as e:
            current_app.logger.error(e)
            return jsonify(errno=RET.DBERR, errmsg="查询数据失败")

        if not houses:
            return jsonify(errno=RET.NODATA, errmsg="查询无数据")

        houses_list = []
        for house in houses:
            # 如果房屋未设置主图片，则跳过
            if not house.index_image_url:
                continue
            houses_list.append(house.to_basic_dict())

        # 将数据转换为json，并保存到redis缓存
        json_houses = json.dumps(houses_list)
        try:
            redis_store.setex("home_page_data", constants.HOME_PAGE_DATA_REDIS_EXPIRES, json_houses)
        except Exception as e:
            current_app.logger.error(e)

        return '{"errno":0, "errmsg":"OK", "data":%s}' % json_houses


@api.route("/houses/<int:house_id>", methods=["GET"])
def get_house_detail(house_id):
    """获取房屋详情"""
    # 前端在房屋详情页面展示时，如果浏览页面的用户不是该房屋的房东，则展示预定按钮，否则不展示，
    # 所以需要后端返回登录用户的user_id
    # 尝试获取用户登录的信息，若登录，则返回给前端登录用户的user_id，否则返回user_id=-1
    user_id = session.get("user_id", "-1")

    # 校验参数
    if not house_id:
        return jsonify(errno=RET.PARAMERR, errmsg="参数确实")

    # 先从redis缓存中获取信息
    try:
        ret = redis_store.get("house_info_%s" % house_id)
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    if ret:
        current_app.logger.info("hit house info redis")
        return '{"errno":"0", "errmsg":"OK", "data":{"user_id":%s, "house":%s}}' % (user_id, ret)

    # 查询数据库
    try:
        house = House.query.get(house_id)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="查询数据失败")

    if not house:
        return jsonify(errno=RET.NODATA, errmsg="房屋不存在")

    # 将房屋对象数据转换为字典
    try:
        house_data = house.to_full_dict()
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DATAERR, errmsg="数据出错")

    # 存入到redis中
    json_house = json.dumps(house_data)
    try:
        redis_store.setex("house_info_%s" % house_id, constants.HOUSE_DETAIL_REDIS_EXPIRE_SECOND, json_house)
    except Exception as e:
        current_app.logger.error(e)

    resp = '{"errno":"0", "errmsg":"OK", "data":{"user_id":%s, "house":%s}}' % (user_id, json_house)
    return resp


@api.route("/houses", methods=["GET"])
def get_houses_list():
    """获取房屋分页数据"""
    # 获取参数
    area_id = request.args.get("aid", "")  # 城区编号
    start_date_str = request.args.get("sd", "")  # 预订的起始时间
    end_date_str = request.args.get("ed", "")  # 预订的结束时间
    sort_key = request.args.get("sk", "new")  # 排序
    page = request.args.get("p", "1")  # 请求的页数

    # 日期格式校验
    try:
        start_date, end_date = None, None
        # 将请求的日期字符串参数转换为datetime类型
        if start_date_str:
            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")

        if end_date_str:
            end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
        # 请求的起始时间应该小于等于终止时间
        if start_date_str and end_date_str:
            assert start_date <= end_date
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR, errmsg="日期格式不正确")

    # 页数格式校验
    try:
        page = int(page)
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.PARAMERR, errmsg="页数格式不正确")

    # 先读取redis缓存数据
    try:
        redis_key = "houses_%s_%s_%s_%s" % (area_id, start_date_str, end_date_str, sort_key)
        # 存放到redis中的数据用的是redis的哈希类型
        ret = redis_store.hget(redis_key, page)
    except Exception as e:
        current_app.logger.error(e)
        ret = None
    if ret:
        current_app.logger.info("hit houses list redis")
        # redis中缓存的就是完整的报文，所以可以直接返回
        return ret

    # 操作数据库，查询数据
    try:
        # 用来存储查询的过滤条件
        filter_params = []

        # 添加城区条件
        if area_id:
            filter_params.append(House.area_id == area_id)

        # 添加预订起始和终止时间条件
        if start_date and end_date:
            # 找出用户请求查询预订的时间与已经存在了订单的时间冲突的，即不能预订的房屋
            conflict_orders = Order.query.filter(Order.begin_date <= end_date, Order.end_date >= start_date).all()
            conflict_houses_ids = [order.house_id for order in conflict_orders]
            # 过滤不在冲突范围内的房屋
            if conflict_houses_ids:
                filter_params.append(House.id.notin_(conflict_houses_ids))
        elif start_date:
            conflict_orders = Order.query.filter(Order.end_date >= start_date).all()
            conflict_houses_ids = [order.house_id for order in conflict_orders]
            if conflict_houses_ids:
                filter_params.append(House.id.notin_(conflict_houses_ids))
        elif end_date:
            conflict_orders = Order.query.filter(Order.begin_date <= end_date).all()
            conflict_houses_ids = [order.house_id for order in conflict_orders]
            if conflict_houses_ids:
                filter_params.append(House.id.notin_(conflict_houses_ids))

        # 添加排序条件
        if "booking" == sort_key:
            # 以订单量最多排序
            houses = House.query.filter(*filter_params).order_by(House.order_count.desc())
        elif "price-inc" == sort_key:
            # 以价格升序排序
            houses = House.query.filter(*filter_params).order_by(House.price.asc())
        elif "price-des" == sort_key:
            # 以价格降序排序
            houses = House.query.filter(*filter_params).order_by(House.price.desc())
        else:
            # 默认以最新发布排序
            houses = House.query.filter(*filter_params).order_by(House.create_time.desc())

        # 查询出该页面的house模型对象列表结果，使用paginate进行分页
        #                             页数，  每页的条目数，                      分页出错是否报错
        houses_page = houses.paginate(page, constants.HOUSE_LIST_PAGE_CAPACITY, False)
        # 拿到分页后该页面的房屋数据
        houses_list = houses_page.items
        # 符合条件的总页数
        total_page = houses_page.pages

        # 将对象转换为字典
        houses_dict_list = []
        for house in houses_list:
            houses_dict_list.append(house.to_basic_dict())
    except Exception as e:
        current_app.logger.error(e)
        return jsonify(errno=RET.DBERR, errmsg="查询数据失败")

    # 组建返回的响应报文
    resp = {"errno": RET.OK, "errmsg": "OK", "data": {"houses": houses_dict_list,
                                                      "total_page": total_page, "current_page": page}}
    # 将返回的数据转换为json
    resp_json = json.dumps(resp)

    # 将数据保存到redis中缓存
    # 用户请求的页数小于总页数，即请求的是有数据的页
    if page <= total_page:
        redis_key = "houses_%s_%s_%s_%s" % (area_id, start_date_str, end_date_str, sort_key)
        # 创建redis的工具pipeline对象，通过该对象可以一次进行多个redis操作
        pipe = redis_store.pipeline()

        try:
            # 开启redis的事务
            pipe.multi()
            # 使用redis的哈希类型保存数据
            pipe.hset(redis_key, page, resp_json)
            # 设置保存的数据的有效期
            pipe.expire(redis_key, constants.HOME_PAGE_DATA_REDIS_EXPIRES)
            # 执行这个事务
            pipe.execute()
        except Exception as e:
            current_app.logger.error(e)

    return resp_json

