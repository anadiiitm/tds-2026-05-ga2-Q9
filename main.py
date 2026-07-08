import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allow browser-based grader
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
# Fixed catalog (IDs 1..42)
# -------------------------
catalog = [
    {
        "id": i,
        "item": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# -------------------------
# Idempotency storage
# -------------------------
idempotency_store = {}

# -------------------------
# Rate limiting storage
# -------------------------
client_requests = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request, call_next):
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

        return Response(
            status_code=429,
            headers={
                "Retry-After": str(retry)
            }
        )

    bucket.append(now)

    return await call_next(request)


# -----------------------------------
# Idempotent POST /orders
# -----------------------------------

@app.post("/orders", status_code=201)
def create_order(
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key")
):
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4())
    }

    idempotency_store[idempotency_key] = order

    return order


# -----------------------------------
# Cursor pagination
# -----------------------------------

@app.get("/orders")
def list_orders(limit: int = 10, cursor: str | None = None):

    start = int(cursor) if cursor else 0

    items = catalog[start:start + limit]

    next_cursor = None

    if start + limit < len(catalog):
        next_cursor = str(start + limit)

    return {
        "items": items,
        "next_cursor": next_cursor
    }
