import time
import uuid
from collections import defaultdict, deque
from typing import Optional

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI()

# -------------------------
# CORS
# -------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 42
RATE_LIMIT = 16
WINDOW = 10  # seconds

# -------------------------
# Fixed catalog
# -------------------------
catalog = [
    {
        "id": i,
        "item": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# -------------------------
# Stores
# -------------------------
idempotency_store = {}

client_requests = defaultdict(deque)


# -------------------------
# Request body
# -------------------------
class OrderRequest(BaseModel):
    item: Optional[str] = None


# -------------------------
# Rate Limiting Middleware
# -------------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):

    # Never rate-limit CORS preflight
    if request.method == "OPTIONS":
        return await call_next(request)

    client = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()

    bucket = client_requests[client]

    # Remove expired timestamps
    while bucket and now - bucket[0] > WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:
        retry = max(1, int(WINDOW - (now - bucket[0])))

        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded"
            },
            headers={
                "Retry-After": str(retry)
            },
        )

    bucket.append(now)

    return await call_next(request)


# -------------------------
# Idempotent POST /orders
# -------------------------
@app.post("/orders", status_code=201)
def create_order(
    order: OrderRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
):

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    created_order = {
        "id": str(uuid.uuid4()),
        "item": order.item,
    }

    idempotency_store[idempotency_key] = created_order

    return created_order


# -------------------------
# Cursor Pagination
# -------------------------
@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
):

    start = int(cursor) if cursor else 0

    items = catalog[start:start + limit]

    next_cursor = None

    if start + limit < TOTAL_ORDERS:
        next_cursor = str(start + limit)

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
