from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from app.cache import Cache
from app.models import Item, ItemCreate, ItemUpdate, ItemsResponse
from app.storage import Storage
from app.tasks import start_background_refresh, stop_background_refresh

app = FastAPI(title="Inventory API")
cache = Cache()
storage = Storage()


@app.on_event("startup")
async def startup():
    await storage.connect()
    start_background_refresh(cache, storage)


@app.on_event("shutdown")
async def shutdown():
    stop_background_refresh()
    await storage.disconnect()


@app.get("/items", response_model=ItemsResponse)
async def list_items(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    cache_key = f"items:list:{page}:{page_size}"
    cached = await cache.get(cache_key)
    if cached:
        return ItemsResponse(**cached)

    offset = (page - 1) * page_size
    rows = storage.query("SELECT * FROM items LIMIT ? OFFSET ?", page_size, offset)
    count_row = storage.query("SELECT COUNT(*) AS cnt FROM items")
    total = count_row[0]["cnt"] if count_row else 0

    result = ItemsResponse(
        items=[Item(**row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
    await cache.set(cache_key, result.model_dump())
    return result


@app.get("/items/search", response_model=ItemsResponse)
async def search_items(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    cache_key = f"items:search:{q}:{page}:{page_size}"
    cached = await cache.get(cache_key)
    if cached:
        return ItemsResponse(**cached)

    offset = (page - 1) * page_size
    like_pattern = f"%{q}%"
    rows = storage.query(
        "SELECT * FROM items WHERE name LIKE ? LIMIT ? OFFSET ?",
        like_pattern, page_size, offset,
    )
    count_row = storage.query(
        "SELECT COUNT(*) AS cnt FROM items WHERE name LIKE ?",
        like_pattern,
    )
    total = count_row[0]["cnt"] if count_row else 0

    result = ItemsResponse(
        items=[Item(**row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
    await cache.set(cache_key, result.model_dump())
    return result


@app.get("/items/{item_id}", response_model=Item)
async def get_item(item_id: int):
    cache_key = f"items:{item_id}"
    cached = await cache.get(cache_key)
    if cached:
        return Item(**cached)

    rows = storage.query("SELECT * FROM items WHERE id = ?", item_id)
    if not rows:
        raise HTTPException(status_code=404, detail="Item not found")
    item = Item(**rows[0])
    await cache.set(cache_key, item.model_dump())
    return item


@app.post("/items", response_model=Item, status_code=201)
async def create_item(item: ItemCreate) -> Item:
    row = storage.query(
        "INSERT INTO items (name, price, quantity) VALUES (?, ?, ?) RETURNING *",
        item.name, item.price, item.quantity,
    )
    new_item = Item(**row[0])
    await cache.invalidate_prefix("items:list:")
    await cache.invalidate_prefix("items:search:")
    return new_item


@app.patch("/items/{item_id}", response_model=Item)
async def update_item(item_id: int, item: ItemUpdate) -> Item:
    updates: List[str] = []
    params: List = []
    if item.name is not None:
        updates.append("name = ?")
        params.append(item.name)
    if item.price is not None:
        updates.append("price = ?")
        params.append(item.price)
    if item.quantity is not None:
        updates.append("quantity = ?")
        params.append(item.quantity)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(item_id)
    row = storage.query(
        f"UPDATE items SET {', '.join(updates)} WHERE id = ? RETURNING *",
        *params,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")

    await cache.invalidate_prefix("items:list:")
    await cache.invalidate_prefix("items:search:")
    await cache.delete(f"items:{item_id}")
    return Item(**row[0])


@app.delete("/items/{item_id}", status_code=204)
async def delete_item(item_id: int):
    row = storage.query("DELETE FROM items WHERE id = ? RETURNING id", item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    await cache.invalidate_prefix("items:list:")
    await cache.invalidate_prefix("items:search:")
    await cache.delete(f"items:{item_id}")
