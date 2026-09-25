# gbinsureapi 医保智能结算 API 网关

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:19935/health
```

gbinsureapi 为医院信息系统提供标准化医保结算接口，覆盖身份核验、费用批次上传、预结算、正式结算、冲正、结算单查询和日终对账。

## 主要功能

- 参保人身份核验：基于身份证号和医保卡号返回参保状态、参保地、医保类型和账户余额。
- 费用批次上传：费用上传独立保存批次、明细和就诊号，生成批次号；同一批次内不允许重复项目编码。
- 服务端预结算：HIS 只提交批次号与参保地，服务端读取已保存明细核算金额并生成预结算凭证，金额不由 HIS 修改。
- 正式结算：只认预结算凭证号；网络重试返回同一结算单，同一凭证不能重复成功生成两张结算单。
- 全额冲正：冲正后来源批次和历史结算单保留，同一就诊号可重新上传费用批次。
- 结算单管理：列表返回凭证号、来源批次号、就诊号和冲正时间，支持按单号、参保人、就诊号和日期查询。
- 日终对账：汇总当日成功金额和笔数，已冲正金额不纳入有效结算金额。
- API 文档与权限：Swagger UI、API Key + JWT 双重认证、调用审计日志。

## 快速启动（Docker）

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:19935/health
```

停止服务：

```bash
docker compose down
```

如需同时清除数据库卷：

```bash
docker compose down -v
```

## 访问地址

- 健康检查：<http://localhost:19935/health>
- Swagger 文档：<http://localhost:19935/docs>
- OpenAPI JSON：<http://localhost:19935/openapi.json>

## 结算链路 API 示例

先获取 JWT：

```bash
TOKEN=$(curl -s -X POST http://localhost:19935/api/auth/token \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-api-key" \
  -d '{"client_id":"his-demo","scopes":["settlement:write","settlement:read"]}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
```

### 1. 上传费用批次

```bash
curl -s -X POST http://localhost:19935/api/settlements/expenses \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-api-key" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "insured_id": "P0001",
    "visit_no": "V202609250001",
    "items": [
      {
        "item_code": "YP0001",
        "name": "示例药品",
        "category": "药品",
        "catalog_class": "甲类",
        "unit_price": "25.00",
        "quantity": "2",
        "amount": "50.00",
        "self_pay_ratio": "0.00"
      }
    ]
  }'
```

响应中的 `batch_no` 是后续预结算的唯一费用依据。

### 2. 创建预结算凭证

```bash
curl -s -X POST http://localhost:19935/api/settlements/pre-settle \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-api-key" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"batch_no":"替换为批次号","insured_region":"北京市"}'
```

服务端读取批次明细并核算，返回 `voucher_no` 与各分项金额。

### 3. 正式结算

```bash
curl -s -X POST http://localhost:19935/api/settlements/confirm \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-api-key" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"voucher_no":"替换为预结算凭证号"}'
```

使用相同 `voucher_no` 重试不会产生第二张结算单，服务端返回已生成的结算单。

### 4. 当日冲正与查询

```bash
curl -s -X POST http://localhost:19935/api/settlements/替换为结算单号/reverse \
  -H "X-API-Key: demo-api-key" \
  -H "Authorization: Bearer $TOKEN"

curl -s "http://localhost:19935/api/settlements?visit_no=V202609250001" \
  -H "X-API-Key: demo-api-key" \
  -H "Authorization: Bearer $TOKEN"

curl -s "http://localhost:19935/api/reconciliation/daily?day=2026-09-25" \
  -H "X-API-Key: demo-api-key" \
  -H "Authorization: Bearer $TOKEN"
```

## 身份核验示例

```bash
curl -s http://localhost:19935/api/insured/verify \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-api-key" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"id_card":"110101199001010012","medical_card_no":"YB00010001"}'
```

## 技术栈

| 分类 | 技术 |
| --- | --- |
| 后端框架 | FastAPI + Python 3.11 |
| 数据库 | PostgreSQL 16 |
| ORM | SQLAlchemy 2 |
| 迁移 | Alembic 依赖预留；容器初始化使用 `database/init.sql` |
| 校验 | Pydantic v2 |
| 认证 | API Key + JWT |
| 文档 | Swagger UI / OpenAPI |

## 项目目录结构

```text
.
├── docker-compose.yml
├── .env.example
├── .env
├── README.md
├── backend
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app
│       ├── api
│       ├── core
│       ├── db
│       ├── models
│       ├── schemas
│       └── services
└── database
    └── init.sql
```

## 环境变量

| 变量 | 说明 |
| --- | --- |
| COMPOSE_PROJECT_NAME | Docker Compose 项目名，固定为 `gbinsureapi` |
| DB_NAME | PostgreSQL 数据库名 |
| DB_USER | PostgreSQL 用户名 |
| DB_PASSWORD | PostgreSQL 密码 |
| JWT_SECRET | JWT 签名密钥 |
| API_KEY_SECRET | API Key 校验密钥 |
| BACKEND_PORT | 后端宿主机端口，默认 19935 |

## 本地开发（备选）

先启动 PostgreSQL，然后：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 19935
```

也可以使用 Python `requests` 调用：

```python
import requests

base_url = "http://localhost:19935"
headers = {"X-API-Key": "demo-api-key"}
token = requests.post(
    f"{base_url}/api/auth/token",
    json={"client_id": "his-demo", "scopes": ["settlement:write", "settlement:read"]},
    headers=headers,
).json()["access_token"]
headers["Authorization"] = f"Bearer {token}"

uploaded = requests.post(
    f"{base_url}/api/settlements/expenses",
    json={
        "insured_id": "P0001",
        "visit_no": "V202609250001",
        "items": [
            {
                "item_code": "YP0001",
                "name": "示例药品",
                "category": "药品",
                "catalog_class": "甲类",
                "unit_price": "25.00",
                "quantity": "2",
                "amount": "50.00",
                "self_pay_ratio": "0.00",
            }
        ],
    },
    headers=headers,
).json()

voucher = requests.post(
    f"{base_url}/api/settlements/pre-settle",
    json={"batch_no": uploaded["batch_no"], "insured_region": "北京市"},
    headers=headers,
).json()

settlement = requests.post(
    f"{base_url}/api/settlements/confirm",
    json={"voucher_no": voucher["voucher_no"]},
    headers=headers,
).json()
print(settlement)
```

## 数据一致性约束

- 未完成批次：同一就诊号同时只能存在一个 `UPLOADED` 或 `PRE_SETTLED` 批次。
- 冲正后重传：冲正不会删除原批次或结算单，原批次标记为 `REVERSED`，该就诊号可上传新批次。
- 凭证幂等：正式结算仅接收 `voucher_no`，数据库对凭证结算记录建立唯一约束。
- 日终口径：`total_amount`、`reimbursed_amount` 等有效金额只统计未冲正结算；`reversed_amount` 单独展示冲正金额。

## License

MIT
