import datetime
import httpx
import json
import os
import sys
from mcp.server.fastmcp import FastMCP

# ── 配置（从环境变量读取）────────────────────────────────────
SAP_BASE_URL      = os.environ.get("SAP_BASE_URL", "")
SAP_PO_BASE_URL   = os.environ.get("SAP_PO_BASE_URL", "")
SAP_PROD_BASE_URL = os.environ.get("SAP_PROD_BASE_URL", "")
SAP_USERNAME      = os.environ.get("SAP_USERNAME", "")
SAP_PASSWORD      = os.environ.get("SAP_PASSWORD", "")
TEAMS_FLOW_URL    = os.environ.get("TEAMS_FLOW_URL", "")

mcp = FastMCP("SAP MCP Server", stateless_http=True)


def send_teams_notification(title: str, message: str, color: str = "0076D7") -> str:
    """通过 Power Automate Flow 发送 Teams 消息，返回推送结果描述。"""
    if not TEAMS_FLOW_URL:
        return "（Teams通知跳过：未配置 TEAMS_FLOW_URL）"
    payload = {"title": title, "message": message, "color": color}
    try:
        resp = httpx.post(TEAMS_FLOW_URL, json=payload, timeout=10)
        if resp.status_code in (200, 202):
            return "✅ Teams通知已发送"
        return f"⚠️ Teams通知返回异常: HTTP {resp.status_code} - {resp.text[:200]}"
    except Exception as e:
        return f"⚠️ Teams通知发送失败: {str(e)}"


def get_auth():
    return (SAP_USERNAME, SAP_PASSWORD)


def odata_get(path: str, params: dict = None) -> dict:
    url = f"{SAP_BASE_URL}{path}"
    headers = {"Accept": "application/json"}
    if params is None:
        params = {}
    params["$format"] = "json"
    response = httpx.get(url, auth=get_auth(), headers=headers, params=params, verify=True)
    response.raise_for_status()
    return response.json()


def get_csrf_token() -> tuple[str, dict]:
    url = f"{SAP_BASE_URL}/"
    headers = {"x-csrf-token": "Fetch", "Accept": "application/json"}
    response = httpx.get(url, auth=get_auth(), headers=headers, verify=True)
    token = response.headers.get("x-csrf-token", "")
    cookies = dict(response.cookies)
    return token, cookies


def odata_post(path: str, payload: dict) -> dict:
    token, cookies = get_csrf_token()
    url = f"{SAP_BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-csrf-token": token,
    }
    response = httpx.post(url, auth=get_auth(), headers=headers, json=payload, cookies=cookies, verify=True)
    if not response.is_success:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise Exception(f"HTTP {response.status_code}: {json.dumps(err, ensure_ascii=False)}")
    return response.json()


def odata_patch(path: str, payload: dict) -> bool:
    token, cookies = get_csrf_token()
    url = f"{SAP_BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-csrf-token": token,
        "If-Match": "*",
    }
    response = httpx.patch(url, auth=get_auth(), headers=headers, json=payload, cookies=cookies, verify=True)
    if not response.is_success:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise Exception(f"HTTP {response.status_code}: {json.dumps(err, ensure_ascii=False)}")
    return True


def to_date_str(date_str: str) -> str:
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    ms = int(dt.timestamp() * 1000)
    return f"/Date({ms})/"


# ── 查询工具 ────────────────────────────────────────────────

@mcp.tool()
def list_sales_orders(top: int = 10, filter: str = "") -> str:
    """查询销售订单列表。top 为返回数量，filter 为 OData 过滤条件（可选）"""
    params = {"$top": top, "$select": "SalesOrder,SalesOrderType,SoldToParty,TotalNetAmount,TransactionCurrency,SalesOrderDate,RequestedDeliveryDate,PurchaseOrderByCustomer"}
    if filter:
        params["$filter"] = filter
    data = odata_get("/A_SalesOrder", params)
    orders = data.get("d", {}).get("results", [])
    if not orders:
        return "没有找到销售订单。"
    lines = []
    for o in orders:
        lines.append(
            f"订单号: {o.get('SalesOrder')} | 类型: {o.get('SalesOrderType')} | "
            f"客户: {o.get('SoldToParty')} | 金额: {o.get('TotalNetAmount')} {o.get('TransactionCurrency')} | "
            f"客户参考: {o.get('PurchaseOrderByCustomer')} | 日期: {o.get('SalesOrderDate', '')[:10]}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_sales_order(sales_order: str) -> str:
    """根据销售订单号获取详细信息"""
    data = odata_get(f"/A_SalesOrder('{sales_order}')")
    order = data.get("d", {})
    if not order:
        return f"找不到订单 {sales_order}。"
    return json.dumps(order, ensure_ascii=False, indent=2)


@mcp.tool()
def list_sales_order_items(sales_order: str) -> str:
    """查询某个销售订单的行项目"""
    params = {
        "$filter": f"SalesOrder eq '{sales_order}'",
        "$select": "SalesOrder,SalesOrderItem,Material,RequestedQuantity,RequestedQuantityUnit,NetAmount,TransactionCurrency,ItemBillingBlockReason,SalesDocumentRjcnReason",
    }
    data = odata_get("/A_SalesOrderItem", params)
    items = data.get("d", {}).get("results", [])
    if not items:
        return f"订单 {sales_order} 没有行项目。"
    lines = []
    for i in items:
        lines.append(
            f"行项目: {i.get('SalesOrderItem')} | 物料: {i.get('Material')} | "
            f"数量: {i.get('RequestedQuantity')} {i.get('RequestedQuantityUnit')} | "
            f"金额: {i.get('NetAmount')} {i.get('TransactionCurrency')} | "
            f"开票冻结: {i.get('ItemBillingBlockReason')} | 拒绝原因: {i.get('SalesDocumentRjcnReason')}"
        )
    return "\n".join(lines)


# ── 创建工具 ────────────────────────────────────────────────

@mcp.tool()
def create_sales_order(
    sales_order_type: str,
    sold_to_party: str,
    sales_organization: str,
    distribution_channel: str,
    material: str,
    order_quantity: str,
    quantity_unit: str = "PC",
    request_date: str = "",
    customer_po: str = "",
) -> str:
    """创建销售订单。
    sales_order_type: 订单类型（如 OR）
    sold_to_party: 售达方客户编号
    sales_organization: 销售组织
    distribution_channel: 分销渠道
    material: 物料编号
    order_quantity: 订单数量（如 "1"）
    quantity_unit: 数量单位（如 PC、EA、KG，默认 PC）
    request_date: 请求交货日期 YYYY-MM-DD（不填则用当天）
    customer_po: 客户参考号（可选）
    """
    if request_date:
        date_str = to_date_str(request_date)
    else:
        dt = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        date_str = f"/Date({int(dt.timestamp() * 1000)})/"

    payload = {
        "SalesOrderType": sales_order_type,
        "SoldToParty": sold_to_party,
        "SalesOrganization": sales_organization,
        "DistributionChannel": distribution_channel,
        "RequestedDeliveryDate": date_str,
        "to_Item": {
            "results": [
                {
                    "Material": material,
                    "RequestedQuantity": order_quantity,
                    "RequestedQuantityUnit": quantity_unit,
                }
            ]
        },
    }
    if customer_po:
        payload["PurchaseOrderByCustomer"] = customer_po
    try:
        data = odata_post("/A_SalesOrder", payload)
    except Exception as e:
        return f"创建失败，错误详情：{str(e)}"
    order = data.get("d", {})
    if not order:
        return "创建失败，未返回订单数据。"
    so_number = order.get('SalesOrder')
    notify = send_teams_notification("📋 销售订单已创建", f"订单号: {so_number} | 客户: {sold_to_party} | 物料: {material} | 数量: {order_quantity}")
    return f"销售订单创建成功！订单号: {so_number}  {notify}"


# ── 修改工具 ────────────────────────────────────────────────

@mcp.tool()
def update_sales_order(
    sales_order: str,
    customer_po: str = "",
    request_date: str = "",
    payment_terms: str = "",
    billing_block: str = "",
    delivery_block: str = "",
    shipping_condition: str = "",
) -> str:
    """修改销售订单头部信息。
    sales_order: 销售订单号
    customer_po: 客户参考号（可选）
    request_date: 请求交货日期 YYYY-MM-DD（可选）
    payment_terms: 付款条件，如 0001/0004（可选）
    billing_block: 开票冻结原因，填 "" 解除冻结（可选）
    delivery_block: 交货冻结原因，填 "" 解除冻结（可选）
    shipping_condition: 装运条件，如 01/02（可选）
    """
    payload = {}
    if customer_po:
        payload["PurchaseOrderByCustomer"] = customer_po
    if request_date:
        payload["RequestedDeliveryDate"] = to_date_str(request_date)
    if payment_terms:
        payload["CustomerPaymentTerms"] = payment_terms
    if billing_block is not None and billing_block != "":
        payload["HeaderBillingBlockReason"] = billing_block
    if delivery_block is not None and delivery_block != "":
        payload["DeliveryBlockReason"] = delivery_block
    if shipping_condition:
        payload["ShippingCondition"] = shipping_condition
    if not payload:
        return "没有提供任何要修改的字段。"
    try:
        odata_patch(f"/A_SalesOrder('{sales_order}')", payload)
    except Exception as e:
        return f"修改失败，错误详情：{str(e)}"
    return f"销售订单 {sales_order} 修改成功！"


@mcp.tool()
def update_sales_order_item(
    sales_order: str,
    sales_order_item: str,
    order_quantity: str = "",
    billing_block: str = "",
    rejection_reason: str = "",
) -> str:
    """修改销售订单行项目。
    sales_order: 销售订单号
    sales_order_item: 行项目号（如 10、20）
    order_quantity: 新的订单数量（可选）
    billing_block: 开票冻结原因，填 "" 解除冻结（可选）
    rejection_reason: 拒绝原因，填 "" 取消拒绝（可选）
    """
    payload = {}
    if order_quantity:
        payload["RequestedQuantity"] = order_quantity
    if billing_block is not None and billing_block != "":
        payload["ItemBillingBlockReason"] = billing_block
    if rejection_reason is not None and rejection_reason != "":
        payload["SalesDocumentRjcnReason"] = rejection_reason
    if not payload:
        return "没有提供任何要修改的字段。"
    try:
        odata_patch(f"/A_SalesOrderItem(SalesOrder='{sales_order}',SalesOrderItem='{sales_order_item}')", payload)
    except Exception as e:
        return f"修改失败，错误详情：{str(e)}"
    return f"销售订单 {sales_order} 行项目 {sales_order_item} 修改成功！"


def odata_v4_get(path: str, params: dict = None) -> dict:
    url = f"{SAP_PO_BASE_URL}{path}"
    headers = {"Accept": "application/json"}
    if params is None:
        params = {}
    response = httpx.get(url, auth=get_auth(), headers=headers, params=params, verify=True)
    response.raise_for_status()
    return response.json()


def get_csrf_token_v4() -> tuple[str, dict]:
    url = f"{SAP_PO_BASE_URL}/"
    headers = {"x-csrf-token": "Fetch", "Accept": "application/json"}
    response = httpx.get(url, auth=get_auth(), headers=headers, verify=True)
    token = response.headers.get("x-csrf-token", "")
    cookies = dict(response.cookies)
    return token, cookies


def odata_v4_post(path: str, payload: dict) -> dict:
    token, cookies = get_csrf_token_v4()
    url = f"{SAP_PO_BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-csrf-token": token,
    }
    response = httpx.post(url, auth=get_auth(), headers=headers, json=payload, cookies=cookies, verify=True)
    if not response.is_success:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise Exception(f"HTTP {response.status_code}: {json.dumps(err, ensure_ascii=False)}")
    return response.json()


def odata_v4_patch(path: str, payload: dict) -> bool:
    token, cookies = get_csrf_token_v4()
    url = f"{SAP_PO_BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-csrf-token": token,
        "If-Match": "*",
    }
    response = httpx.patch(url, auth=get_auth(), headers=headers, json=payload, cookies=cookies, verify=True)
    if not response.is_success:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise Exception(f"HTTP {response.status_code}: {json.dumps(err, ensure_ascii=False)}")
    return True


# ── 采购订单工具 ────────────────────────────────────────────

@mcp.tool()
def list_purchase_orders(top: int = 10, filter: str = "") -> str:
    """查询采购订单列表。top 为返回数量，filter 为 OData 过滤条件（可选）"""
    params = {
        "$top": top,
        "$select": "PurchaseOrder,PurchaseOrderType,Supplier,CompanyCode,PurchaseOrderDate,DocumentCurrency,NetPaymentDays,CreatedByUser,PurchasingGroup,PurchasingOrganization",
    }
    if filter:
        params["$filter"] = filter
    data = odata_v4_get("/PurchaseOrder", params)
    orders = data.get("value", [])
    if not orders:
        return "没有找到采购订单。"
    lines = []
    for o in orders:
        lines.append(
            f"订单号: {o.get('PurchaseOrder')} | 类型: {o.get('PurchaseOrderType')} | "
            f"供应商: {o.get('Supplier')} | 公司代码: {o.get('CompanyCode')} | "
            f"创建人: {o.get('CreatedByUser')} | 日期: {o.get('PurchaseOrderDate', '')[:10]}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_purchase_order(purchase_order: str) -> str:
    """根据采购订单号获取详细信息"""
    data = odata_v4_get(f"/PurchaseOrder/{purchase_order}")
    order = data
    if not order or "PurchaseOrder" not in order:
        return f"找不到采购订单 {purchase_order}。"
    keys = ["PurchaseOrder","PurchaseOrderType","Supplier","CompanyCode","PurchaseOrderDate",
            "DocumentCurrency","PaymentTerms","IncotermsClassification","PurchasingGroup",
            "PurchasingOrganization","SupplierRespSalesPersonName"]
    result = {k: order.get(k, "") for k in keys if k in order}
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_purchase_order_items(purchase_order: str) -> str:
    """查询采购订单的行项目"""
    params = {
        "$filter": f"PurchaseOrder eq '{purchase_order}'",
        "$select": "PurchaseOrder,PurchaseOrderItem,Material,PurchaseOrderItemText,OrderQuantity,PurchaseOrderQuantityUnit,NetPriceAmount,DocumentCurrency,Plant,StorageLocation",
    }
    data = odata_v4_get("/PurchaseOrderItem", params)
    items = data.get("value", [])
    if not items:
        return f"采购订单 {purchase_order} 没有行项目。"
    lines = []
    for i in items:
        lines.append(
            f"行项目: {i.get('PurchaseOrderItem')} | 物料: {i.get('Material')} | "
            f"描述: {i.get('PurchaseOrderItemText')} | "
            f"数量: {i.get('OrderQuantity')} {i.get('PurchaseOrderQuantityUnit')} | "
            f"单价: {i.get('NetPriceAmount')} {i.get('DocumentCurrency')} | "
            f"工厂: {i.get('Plant')} | 交货日期: {i.get('ItemDeliveryDate', '')[:10]}"
        )
    return "\n".join(lines)


@mcp.tool()
def create_purchase_order(
    supplier: str,
    company_code: str,
    purchasing_organization: str,
    purchasing_group: str,
    material: str,
    plant: str,
    order_quantity: float,
    quantity_unit: str,
    net_price: float,
    currency: str = "CNY",
    delivery_date: str = "",
    po_type: str = "NB",
) -> str:
    """创建采购订单。
    supplier: 供应商编号
    company_code: 公司代码
    purchasing_organization: 采购组织
    purchasing_group: 采购组
    material: 物料编号
    plant: 工厂
    order_quantity: 订单数量
    quantity_unit: 数量单位（如 PC、KG）
    net_price: 净价
    currency: 货币（默认 CNY）
    delivery_date: 交货日期 YYYY-MM-DD（可选）
    po_type: 采购订单类型（默认 NB）
    """
    payload = {
        "PurchaseOrderType": po_type,
        "Supplier": supplier,
        "CompanyCode": company_code,
        "PurchasingOrganization": purchasing_organization,
        "PurchasingGroup": purchasing_group,
        "DocumentCurrency": currency,
        "_PurchaseOrderItem": [
            {
                "PurchaseOrderItem": "10",
                "Material": material,
                "Plant": plant,
                "OrderQuantity": int(order_quantity),
                "PurchaseOrderQuantityUnit": quantity_unit,
                "NetPriceAmount": float(net_price),
                "DocumentCurrency": currency,
            }
        ],
    }
    try:
        data = odata_v4_post("/PurchaseOrder", payload)
    except Exception as e:
        return f"创建失败，错误详情：{str(e)}"
    po_number = data.get("PurchaseOrder")
    if not po_number:
        return "创建失败，未返回订单号。"
    if delivery_date:
        try:
            odata_v4_patch(f"/PurchaseOrderScheduleLine/{po_number}/10/1", {"ScheduleLineDeliveryDate": delivery_date})
        except Exception as e:
            return f"采购订单 {po_number} 创建成功，但交货日期设置失败：{str(e)}"
    result = f"采购订单创建成功！订单号: {po_number}" + (f"，交货日期已设置为 {delivery_date}" if delivery_date else "")
    notify = send_teams_notification("🛒 采购订单已创建", f"订单号: {po_number} | 供应商: {supplier} | 物料: {material} | 数量: {order_quantity} | 工厂: {plant}")
    return f"{result}  {notify}"


@mcp.tool()
def update_purchase_order(
    purchase_order: str,
    payment_terms: str = "",
    incoterms: str = "",
    purchasing_group: str = "",
) -> str:
    """修改采购订单头部信息。
    purchase_order: 采购订单号
    payment_terms: 付款条件（可选）
    incoterms: 国际贸易条款，如 EXW/CIF（可选）
    purchasing_group: 采购组（可选）
    """
    payload = {}
    if payment_terms:
        payload["PaymentTerms"] = payment_terms
    if incoterms:
        payload["IncotermsClassification"] = incoterms
    if purchasing_group:
        payload["PurchasingGroup"] = purchasing_group
    if not payload:
        return "没有提供任何要修改的字段。"
    try:
        odata_v4_patch(f"/PurchaseOrder/{purchase_order}", payload)
    except Exception as e:
        return f"修改失败，错误详情：{str(e)}"
    return f"采购订单 {purchase_order} 修改成功！"


@mcp.tool()
def update_purchase_order_item(
    purchase_order: str,
    purchase_order_item: str,
    order_quantity: str = "",
    quantity_unit: str = "",
    delivery_date: str = "",
    net_price: str = "",
    currency: str = "",
) -> str:
    """修改采购订单行项目。
    purchase_order: 采购订单号
    purchase_order_item: 行项目号（如 10、20）
    order_quantity: 新的订单数量（修改数量时必须同时提供 quantity_unit）
    quantity_unit: 数量单位（修改数量时必填）
    delivery_date: 新的交货日期 YYYY-MM-DD（可选）
    net_price: 新的净价（修改净价时必须同时提供 currency）
    currency: 货币（修改净价时必填）
    """
    results = []
    item_payload = {}
    if order_quantity:
        if not quantity_unit:
            return "修改数量时必须同时提供 quantity_unit（数量单位）。"
        item_payload["OrderQuantity"] = int(order_quantity)
        item_payload["PurchaseOrderQuantityUnit"] = quantity_unit
    if net_price:
        if not currency:
            return "修改净价时必须同时提供 currency（货币）。"
        item_payload["NetPriceAmount"] = float(net_price)
        item_payload["DocumentCurrency"] = currency
    if item_payload:
        try:
            odata_v4_patch(f"/PurchaseOrderItem/{purchase_order}/{purchase_order_item}", item_payload)
            results.append("数量/净价修改成功")
        except Exception as e:
            results.append(f"数量/净价修改失败：{str(e)}")
    if delivery_date:
        try:
            odata_v4_patch(f"/PurchaseOrderScheduleLine/{purchase_order}/{purchase_order_item}/1", {"ScheduleLineDeliveryDate": delivery_date})
            results.append(f"交货日期已设置为 {delivery_date}")
        except Exception as e:
            results.append(f"交货日期修改失败：{str(e)}")
    if not results:
        return "没有提供任何要修改的字段。"
    return f"采购订单 {purchase_order} 行项目 {purchase_order_item}：" + "；".join(results)


def prod_odata_get(path: str, params: dict = None) -> dict:
    if params is None:
        params = {}
    params["$format"] = "json"
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{SAP_PROD_BASE_URL}{path}?{query_string}"
    headers = {"Accept": "application/json"}
    response = httpx.get(url, auth=get_auth(), headers=headers, verify=True)
    response.raise_for_status()
    return response.json()


def get_csrf_token_prod() -> tuple[str, dict]:
    url = f"{SAP_PROD_BASE_URL}/"
    headers = {"x-csrf-token": "Fetch", "Accept": "application/json"}
    response = httpx.get(url, auth=get_auth(), headers=headers, verify=True)
    token = response.headers.get("x-csrf-token", "")
    cookies = dict(response.cookies)
    return token, cookies


def prod_odata_post(path: str, payload: dict) -> dict:
    token, cookies = get_csrf_token_prod()
    url = f"{SAP_PROD_BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-csrf-token": token,
    }
    response = httpx.post(url, auth=get_auth(), headers=headers, json=payload, cookies=cookies, verify=True)
    if not response.is_success:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise Exception(f"HTTP {response.status_code}: {json.dumps(err, ensure_ascii=False)}")
    return response.json()


def prod_odata_patch(path: str, payload: dict) -> bool:
    token, cookies = get_csrf_token_prod()
    url = f"{SAP_PROD_BASE_URL}{path}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-csrf-token": token,
        "If-Match": "*",
    }
    response = httpx.patch(url, auth=get_auth(), headers=headers, json=payload, cookies=cookies, verify=True)
    if not response.is_success:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise Exception(f"HTTP {response.status_code}: {json.dumps(err, ensure_ascii=False)}")
    return True


# ── 生产订单工具 ────────────────────────────────────────────

@mcp.tool()
def list_production_orders(top: int = 10, filter: str = "") -> str:
    """查询生产订单列表。top 为返回数量，filter 为 OData 过滤条件（可选）"""
    params = {"$top": top}
    if filter:
        params["$filter"] = filter
    data = prod_odata_get("/A_ProductionOrder_2", params)
    orders = data.get("d", {}).get("results", [])
    if not orders:
        return "没有找到生产订单。"
    lines = []
    for o in orders:
        lines.append(
            f"订单号: {o.get('ManufacturingOrder')} | 类型: {o.get('ManufacturingOrderType')} | "
            f"物料: {o.get('Material')} | 工厂: {o.get('Plant')} | "
            f"数量: {o.get('TotalQuantity')} {o.get('BaseUnit')} | "
            f"创建日期: {o.get('MfgOrderCreationDate', '')[:10]}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_production_order(manufacturing_order: str) -> str:
    """根据生产订单号获取详细信息"""
    data = prod_odata_get(f"/A_ProductionOrder_2('{manufacturing_order}')")
    order = data.get("d", {})
    if not order:
        return f"找不到生产订单 {manufacturing_order}。"
    keys = [
        "ManufacturingOrder", "ManufacturingOrderType", "Material", "Plant",
        "TotalQuantity", "BaseUnit", "MfgOrderCreationDate", "BasicSchedulingType",
        "ProductionVersion", "ManufacturingOrderCategory", "MfgOrderPlannedStartDate",
        "MfgOrderPlannedEndDate", "MfgOrderScheduledStartDate", "MfgOrderScheduledEndDate",
    ]
    result = {k: order.get(k, "") for k in keys if k in order}
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_production_order_components(manufacturing_order: str) -> str:
    """查询生产订单的物料组件需求"""
    params = {"$filter": f"ManufacturingOrder eq '{manufacturing_order}'"}
    data = prod_odata_get("/A_ProductionOrderComponent_2", params)
    items = data.get("d", {}).get("results", [])
    if not items:
        return f"生产订单 {manufacturing_order} 没有物料组件。"
    lines = []
    for i in items:
        lines.append(
            f"预留号: {i.get('Reservation')} | 物料: {i.get('Material')} | "
            f"需求数量: {i.get('RequiredQuantity')} {i.get('BaseUnit')} | "
            f"工厂: {i.get('Plant')} | 库位: {i.get('StorageLocation')}"
        )
    return "\n".join(lines)


@mcp.tool()
def create_production_order(
    material: str,
    plant: str,
    order_type: str,
    total_quantity: float,
    planned_start_date: str = "",
    planned_end_date: str = "",
    production_version: str = "",
) -> str:
    """创建生产订单。
    material: 物料编号
    plant: 工厂
    order_type: 订单类型（如 YBM1）
    total_quantity: 生产数量
    planned_start_date: 计划开始日期 YYYY-MM-DD（可选）
    planned_end_date: 计划结束日期 YYYY-MM-DD（可选）
    production_version: 生产版本（可选）
    """
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    if planned_start_date and planned_end_date:
        scheduling_type = "3"
    elif planned_end_date and not planned_start_date:
        scheduling_type = "2"
        planned_start_date = ""
    elif planned_start_date and not planned_end_date:
        scheduling_type = "1"
    else:
        scheduling_type = "1"
        planned_start_date = today
    payload = {
        "ManufacturingOrderType": order_type,
        "Material": material,
        "ProductionPlant": plant,
        "TotalQuantity": str(total_quantity),
        "BasicSchedulingType": scheduling_type,
    }
    if planned_start_date:
        payload["MfgOrderPlannedStartDate"] = to_date_str(planned_start_date)
    if planned_end_date:
        payload["MfgOrderPlannedEndDate"] = to_date_str(planned_end_date)
    if production_version:
        payload["ProductionVersion"] = production_version
    try:
        data = prod_odata_post("/A_ProductionOrder_2", payload)
    except Exception as e:
        return f"创建失败，错误详情：{str(e)}"
    order = data.get("d", {})
    if not order:
        return "创建失败，未返回订单数据。"
    prod_number = order.get('ManufacturingOrder')
    notify = send_teams_notification("🏭 生产订单已创建", f"订单号: {prod_number} | 物料: {material} | 工厂: {plant} | 数量: {total_quantity}")
    return f"生产订单创建成功！订单号: {prod_number}  {notify}"


@mcp.tool()
def update_production_order(
    manufacturing_order: str,
    total_quantity: str = "",
    planned_start_date: str = "",
    planned_end_date: str = "",
    production_version: str = "",
) -> str:
    """修改生产订单。
    manufacturing_order: 生产订单号
    total_quantity: 新的生产数量（可选）
    planned_start_date: 新的计划开始日期 YYYY-MM-DD（可选）
    planned_end_date: 新的计划结束日期 YYYY-MM-DD（可选）
    production_version: 生产版本（可选）
    """
    payload = {}
    if total_quantity:
        payload["TotalQuantity"] = total_quantity
    if planned_start_date:
        payload["MfgOrderPlannedStartDate"] = to_date_str(planned_start_date)
    if planned_end_date:
        payload["MfgOrderPlannedEndDate"] = to_date_str(planned_end_date)
    if production_version:
        payload["ProductionVersion"] = production_version
    if not payload:
        return "没有提供任何要修改的字段。"
    try:
        prod_odata_patch(f"/A_ProductionOrder_2('{manufacturing_order}')", payload)
    except Exception as e:
        return f"修改失败，错误详情：{str(e)}"
    return f"生产订单 {manufacturing_order} 修改成功！"


@mcp.tool()
def release_production_order(manufacturing_order: str) -> str:
    """对生产订单执行生产下达（Release）操作。"""
    try:
        get_url = f"{SAP_PROD_BASE_URL}/A_ProductionOrder_2('{manufacturing_order}')?$format=json"
        get_resp = httpx.get(get_url, auth=get_auth(), headers={"Accept": "application/json"}, verify=True)
        etag = get_resp.headers.get("ETag", "*")
        token, cookies = get_csrf_token_prod()
        url = f"{SAP_PROD_BASE_URL}/ReleaseOrder?ManufacturingOrder='{manufacturing_order}'&$format=json"
        headers = {"Accept": "application/json", "x-csrf-token": token, "If-Match": etag}
        response = httpx.post(url, auth=get_auth(), headers=headers, cookies=cookies, verify=True)
        if not response.is_success:
            try:
                err = response.json()
            except Exception:
                err = response.text
            raise Exception(f"HTTP {response.status_code}: {json.dumps(err, ensure_ascii=False)}")
    except Exception as e:
        return f"生产下达失败，错误详情：{str(e)}"
    notify = send_teams_notification("✅ 生产订单已下达", f"订单号: {manufacturing_order} 已完成生产下达")
    return f"生产订单 {manufacturing_order} 生产下达成功！  {notify}"


@mcp.tool()
def technically_complete_production_order(manufacturing_order: str) -> str:
    """对生产订单执行技术关闭（Technically Complete）操作。"""
    try:
        get_url = f"{SAP_PROD_BASE_URL}/A_ProductionOrder_2('{manufacturing_order}')?$format=json"
        get_resp = httpx.get(get_url, auth=get_auth(), headers={"Accept": "application/json"}, verify=True)
        etag = get_resp.headers.get("ETag", "*")
        token, cookies = get_csrf_token_prod()
        url = f"{SAP_PROD_BASE_URL}/TechlyCmpltOrder?ManufacturingOrder='{manufacturing_order}'&$format=json"
        headers = {"Accept": "application/json", "x-csrf-token": token, "If-Match": etag}
        response = httpx.post(url, auth=get_auth(), headers=headers, cookies=cookies, verify=True)
        if not response.is_success:
            try:
                err = response.json()
            except Exception:
                err = response.text
            raise Exception(f"HTTP {response.status_code}: {json.dumps(err, ensure_ascii=False)}")
    except Exception as e:
        return f"技术关闭失败，错误详情：{str(e)}"
    notify = send_teams_notification("🔒 生产订单已技术关闭", f"订单号: {manufacturing_order} 已完成技术关闭（TECO）")
    return f"生产订单 {manufacturing_order} 技术关闭成功！  {notify}"


if __name__ == "__main__":
    import uvicorn
    missing = [v for v in ["SAP_BASE_URL", "SAP_PO_BASE_URL", "SAP_PROD_BASE_URL", "SAP_USERNAME", "SAP_PASSWORD"] if not os.environ.get(v)]
    if missing:
        print(f"Error: 以下环境变量未设置: {', '.join(missing)}")
        print("请参考 .env.example 文件配置环境变量后重试。")
        sys.exit(1)
    print("SAP MCP Server starting...")
    app = mcp.streamable_http_app()
    uvicorn.run(app, host="127.0.0.1", port=8000)
