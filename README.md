# gbinsureapi 医保智能结算 API 网关

```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:19935/health
```

gbinsureapi 为医院信息系统提供标准化医保结算接口，覆盖身份核验、费用上传、预结算、正式结算、冲正、查询和日终对账。

## 主要功能

- 参保人身份核验：基于身份证号和医保卡号返回参保状态、参保地、医保类型和账户余额。
- 费用明细上传：校验药品、诊疗、耗材、检查明细（金额须等于单价×数量），生成上传批次号并持久化批次、明细与就诊号；同一就诊号只允许存在一个未冲正批次。
- 预结算计算：只提交批次号与参保地，服务端基于已冻结的批次明细核算并生成预结算凭证，支持多次预结算比对（旧凭证自动作废）。
- 正式结算与冲正：正式结算只认凭证号，同一凭证不能重复成功（网络重试幂等返回原单）；支持当日全额冲正，冲正后原批次保留、同一就诊号可重新上传。
- 结算单查询与对账：按结算单号、参保人、来源批次、就诊号和日期范围查询，返回来源批次与冲正时间；日终汇总排除已冲正金额。
- API 文档与权限：Swagger UI、API Key + JWT 双重认证、调用审计日志。

## 访问地址

- 健康检查：<http://localhost:19935/health>
- Swagger 文档：<http://localhost:19935/docs>

## API 调用示例

```bash
TOKEN=$(curl -s -X POST http://localhost:19935/api/auth/token \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-api-key" \
  -d '{"client_id":"his-demo","scopes":["settlement:write","settlement:read"]}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:19935/api/insured/verify \
  -H "Content-Type: application/json" \
  -H "X-API-Key: demo-api-key" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"id_card":"110101199001010012","medical_card_no":"YB00010001"}'
```

### 以费用批次为准的结算链路

```bash
# 1) 费用上传：保存批次、明细与就诊号，金额此后冻结
BATCH=$(curl -s -X POST http://localhost:19935/api/settlements/expenses \
  -H "Content-Type: application/json" -H "X-API-Key: demo-api-key" -H "Authorization: Bearer $TOKEN" \
  -d '{"insured_id":"INS010012","visit_no":"V20260925001","items":[
        {"item_code":"A0001","name":"诊查费","category":"诊疗","catalog_class":"甲类",
         "unit_price":"20.00","quantity":1,"amount":"20.00","self_pay_ratio":0}]}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['batch_no'])")

# 2) 预结算：只提交批次号与参保地，服务端核算并返回凭证号
VOUCHER=$(curl -s -X POST http://localhost:19935/api/settlements/pre-settle \
  -H "Content-Type: application/json" -H "X-API-Key: demo-api-key" -H "Authorization: Bearer $TOKEN" \
  -d "{\"batch_no\":\"$BATCH\",\"region\":\"北京市\"}" \
  | python -c "import sys,json;print(json.load(sys.stdin)['voucher_no'])")

# 3) 正式结算：只认凭证号；重复/重试调用幂等返回同一张结算单
curl -s -X POST http://localhost:19935/api/settlements/confirm \
  -H "Content-Type: application/json" -H "X-API-Key: demo-api-key" -H "Authorization: Bearer $TOKEN" \
  -d "{\"voucher_no\":\"$VOUCHER\"}"

# 4) 当日冲正：原批次保留并标记 REVERSED，同一就诊号可重新上传
curl -s -X POST http://localhost:19935/api/settlements/<settlement_no>/reverse \
  -H "X-API-Key: demo-api-key" -H "Authorization: Bearer $TOKEN"

# 5) 结算列表（带来源批次 batch_no 与冲正时间 reversed_at），日终汇总排除已冲正金额
curl -s "http://localhost:19935/api/settlements?visit_no=V20260925001" \
  -H "X-API-Key: demo-api-key" -H "Authorization: Bearer $TOKEN"
curl -s "http://localhost:19935/api/reconciliation/daily?day=2026-09-25" \
  -H "X-API-Key: demo-api-key" -H "Authorization: Bearer $TOKEN"
```

## 技术栈

| 分类 | 技术 |
| --- | --- |
| 后端框架 | FastAPI + Python 3.11 |
| 数据库 | PostgreSQL |
| ORM | SQLAlchemy |
| 迁移 | Alembic 目录预留 |
| 校验 | Pydantic |
| 认证 | API Key + JWT |
| 文档 | Swagger UI / OpenAPI |

## 目录结构

```text
.
├── docker-compose.yml
├── .env.example
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
| COMPOSE_PROJECT_NAME | Docker Compose 项目名 |
| DB_NAME / DB_USER / DB_PASSWORD | PostgreSQL 数据库配置 |
| JWT_SECRET | JWT 签名密钥 |
| API_KEY_SECRET | API Key 校验密钥 |
| BACKEND_PORT | 后端宿主机端口，默认 19935 |

## 本地开发

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 19935
```

## License

MIT
