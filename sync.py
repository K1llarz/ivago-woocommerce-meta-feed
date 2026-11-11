import csv
import os
import re
from html import unescape

import requests


STORE_URL = os.environ["WC_STORE_URL"].rstrip("/")
CONSUMER_KEY = os.environ["WC_CONSUMER_KEY"]
CONSUMER_SECRET = os.environ["WC_CONSUMER_SECRET"]

session = requests.Session()
session.auth = (CONSUMER_KEY, CONSUMER_SECRET)
session.headers.update({"User-Agent": "IvagoMetaFeed/1.0"})


def fetch_all(endpoint, params=None):
    items = []
    page = 1

    while True:
        query = dict(params or {})
        query.update({"per_page": 100, "page": page})

        response = session.get(
            f"{STORE_URL}/wp-json/wc/v3/{endpoint}",
            params=query,
            timeout=60,
        )
        response.raise_for_status()

        batch = response.json()
        if not isinstance(batch, list):
            raise ValueError("Unexpected WooCommerce API response")

        items.extend(batch)

        if len(batch) < 100:
            break

        page += 1

    return items


def clean(value):
    return re.sub(r"<[^>]+>", " ", unescape(str(value or ""))).strip()


def availability(product):
    stock_status = product.get("stock_status")

    if stock_status == "instock":
        return "in stock"
    if stock_status == "onbackorder":
        return "available for order"
    return "out of stock"


def category_depth(category, categories_by_id):
    depth = 0
    visited = {category["id"]}
    parent_id = category.get("parent")

    while parent_id and parent_id not in visited:
        parent = categories_by_id.get(parent_id)
        if parent is None:
            break

        visited.add(parent_id)
        depth += 1
        parent_id = parent.get("parent")

    return depth


def get_category_label(product, categories_by_id):
    categories = [
        categories_by_id.get(category["id"], category)
        for category in product.get("categories") or []
        if category.get("slug")
    ]

    if not categories:
        return ""

    category = min(
        categories,
        key=lambda item: (
            -category_depth(item, categories_by_id),
            item["id"],
        ),
    )

    return category["slug"]


def make_row(product, category_label, parent=None):
    source = parent or product
    image = (product.get("images") or source.get("images") or [{}])[0]

    price = product.get("price")
    if not price:
        return None

    row = {
        "id": str(product["id"]),
        "title": clean(product.get("name") or source.get("name")),
        "description": clean(
            source.get("description") or source.get("short_description")
        )[:5000],
        "availability": availability(product),
        "condition": "new",
        "price": f"{price} GEL",
        "link": product.get("permalink") or source.get("permalink"),
        "image_link": image.get("src", ""),
        "brand": "Ivago",
        "custom_label_0": category_label,
    }

    if parent:
        row["item_group_id"] = str(parent["id"])

    return row


def main():
    categories = fetch_all("products/categories")
    categories_by_id = {category["id"]: category for category in categories}

    products = fetch_all("products", {"status": "publish"})
    rows = []

    for product in products:
        category_label = get_category_label(product, categories_by_id)

        if product.get("type") == "variable":
            variations = fetch_all(f"products/{product['id']}/variations")

            for variation in variations:
                if variation.get("status") == "publish":
                    row = make_row(variation, category_label, parent=product)
                    if row:
                        rows.append(row)
        else:
            row = make_row(product, category_label)
            if row:
                rows.append(row)

    if not rows:
        raise RuntimeError("No valid products returned; keeping old feed")

    fields = [
        "id",
        "title",
        "description",
        "availability",
        "condition",
        "price",
        "link",
        "image_link",
        "brand",
        "item_group_id",
        "custom_label_0",
    ]

    with open("products.csv.tmp", "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    os.replace("products.csv.tmp", "products.csv")
    print(f"Successfully exported {len(rows)} products")


if __name__ == "__main__":
    main()
