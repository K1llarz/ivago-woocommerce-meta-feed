
import os
import csv
import requests
from html import unescape
from urllib.parse import urlparse

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
    import re
    return re.sub(r"<[^>]+>", " ", unescape(str(value or ""))).strip()


def availability(product):
    if product.get("stock_status") == "instock":
        return "in stock"
    if product.get("stock_status") == "onbackorder":
        return "available for order"
    return "out of stock"


def make_row(product, parent=None):
    source = parent or product
    image = (product.get("images") or source.get("images") or [{}])[0]

    price = product.get("price")
    if not price:
        return None

    currency = "GEL"

    row = {
        "id": str(product["id"]),
        "title": clean(product.get("name") or source.get("name")),
        "description": clean(
            source.get("description") or source.get("short_description")
        )[:5000],
        "availability": availability(product),
        "condition": "new",
        "price": f"{price} {currency}",
        "link": product.get("permalink") or source.get("permalink"),
        "image_link": image.get("src", ""),
        "brand": "Ivago",
    }

    if parent:
        row["item_group_id"] = str(parent["id"])

    return row


def main():
    products = fetch_all("products", {"status": "publish"})
    rows = []

    for product in products:
        if product.get("type") == "variable":
            variations = fetch_all(
                f"products/{product['id']}/variations"
            )
            for variation in variations:
                if variation.get("status") == "publish":
                    row = make_row(variation, product)
                    if row:
                        rows.append(row)
        else:
            row = make_row(product)
            if row:
                rows.append(row)

    if not rows:
        raise RuntimeError("No valid products returned; keeping old feed")

    fields = [
        "id", "title", "description", "availability",
        "condition", "price", "link", "image_link",
        "brand", "item_group_id",
    ]

    with open("products.csv.tmp", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    os.replace("products.csv.tmp", "products.csv")
    print(f"Successfully exported {len(rows)} products")


if __name__ == "__main__":
    main()
