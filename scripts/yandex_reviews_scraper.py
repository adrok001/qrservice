#!/usr/bin/env python3
"""
Yandex Maps Reviews Scraper - Full Version
Uses DJB2 hash to compute the 's' signature parameter.
Collects up to 600 reviews per sort order, merges all unique.
"""

import requests
import json
import csv
import time
import re
import sys
from urllib.parse import urlencode


def djb2_hash(params: dict) -> str:
    """Compute Yandex Maps 's' parameter using DJB2 hash."""
    sorted_params = dict(sorted(params.items()))
    query_string = urlencode(sorted_params)
    n = 5381
    for char in query_string:
        n = (33 * n) ^ ord(char)
    return str(n & 0xFFFFFFFF)


def get_csrf_token(session):
    """Get CSRF token from Yandex Maps API error response."""
    resp = session.get(
        "https://yandex.ru/maps/api/business/fetchReviews",
        params={"ajax": "1"}
    )
    try:
        data = resp.json()
        return data.get("csrfToken", "")
    except:
        return ""


def get_tokens_from_page(session, business_id):
    """Load the business page and extract tokens."""
    url = f"https://yandex.ru/maps/org/concept/{business_id}/reviews/"
    resp = session.get(url)

    csrf = ""
    session_id = ""
    req_id = ""

    csrf_match = re.search(r'"csrfToken"\s*:\s*"([^"]+)"', resp.text)
    session_match = re.search(r'"sessionId"\s*:\s*"([^"]+)"', resp.text)
    req_match = re.search(r'"reqId"\s*:\s*"([^"]+)"', resp.text)

    if csrf_match:
        csrf = csrf_match.group(1)
    if session_match:
        session_id = session_match.group(1)
    if req_match:
        req_id = req_match.group(1)

    return csrf, session_id, req_id


def fetch_reviews_page(session, business_id, csrf_token, session_id, req_id,
                        page, ranking="by_time"):
    """Fetch a single page of reviews."""
    params = {
        "ajax": "1",
        "businessId": business_id,
        "csrfToken": csrf_token,
        "locale": "ru_RU",
        "page": str(page),
        "pageSize": "50",
        "ranking": ranking,
    }

    if req_id:
        params["reqId"] = req_id
    if session_id:
        params["sessionId"] = session_id

    # Compute signature
    params["s"] = djb2_hash(params)

    resp = session.get(
        "https://yandex.ru/maps/api/business/fetchReviews",
        params=params
    )

    if resp.status_code != 200:
        # Try to get new CSRF token from error response
        try:
            err_data = resp.json()
            new_csrf = err_data.get("csrfToken", "")
            if new_csrf:
                params["csrfToken"] = new_csrf
                del params["s"]
                params["s"] = djb2_hash(params)
                resp = session.get(
                    "https://yandex.ru/maps/api/business/fetchReviews",
                    params=params
                )
                if resp.status_code == 200:
                    return resp.json(), new_csrf
        except:
            pass
        return None, csrf_token

    return resp.json(), csrf_token


def collect_all_reviews(business_id):
    """Collect reviews using all available sort orders."""

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "ru,en;q=0.9",
        "Referer": f"https://yandex.ru/maps/org/concept/{business_id}/reviews/",
    })

    print("Загружаю страницу для получения токенов...")
    csrf_token, session_id, req_id = get_tokens_from_page(session, business_id)

    if not csrf_token:
        print("Не удалось получить csrfToken из страницы, пробую через API...")
        csrf_token = get_csrf_token(session)

    if not csrf_token:
        print("ОШИБКА: Не удалось получить csrfToken!")
        return []

    print(f"csrfToken: {csrf_token[:30]}...")
    print(f"sessionId: {session_id[:30] if session_id else 'нет'}...")
    print(f"reqId: {req_id[:30] if req_id else 'нет'}...")

    # All known sort orders
    rankings = [
        "by_time",
        "by_relevance_org",
        "by_rating_asc",
        "by_rating_desc",
    ]

    all_reviews = {}  # id -> review data

    for ranking in rankings:
        print(f"\n{'='*50}")
        print(f"Сортировка: {ranking}")
        print(f"{'='*50}")

        page_count = 0

        for page in range(1, 13):  # Max 12 pages
            data, csrf_token = fetch_reviews_page(
                session, business_id, csrf_token, session_id, req_id,
                page, ranking
            )

            if not data:
                print(f"  Стр.{page}: ошибка запроса")
                break

            reviews_data = None
            if isinstance(data, dict):
                if "data" in data and "reviews" in data.get("data", {}):
                    reviews_data = data["data"]["reviews"]
                    total = data["data"].get("params", {}).get("count", "?")
                    total_pages = data["data"].get("params", {}).get("totalPages", "?")
                elif "reviews" in data:
                    reviews_data = data["reviews"]
                    total = "?"
                    total_pages = "?"

            if not reviews_data:
                print(f"  Стр.{page}: нет отзывов в ответе")
                if data and "csrfToken" in data:
                    csrf_token = data["csrfToken"]
                    print(f"  Обновлён csrfToken, повторяю...")
                    # Retry with new token
                    data, csrf_token = fetch_reviews_page(
                        session, business_id, csrf_token, session_id, req_id,
                        page, ranking
                    )
                    if data and "data" in data and "reviews" in data.get("data", {}):
                        reviews_data = data["data"]["reviews"]
                        total = data["data"].get("params", {}).get("count", "?")
                        total_pages = data["data"].get("params", {}).get("totalPages", "?")
                    else:
                        break
                else:
                    break

            new_count = 0
            for rv in reviews_data:
                rid = rv.get("reviewId", "")
                if rid and rid not in all_reviews:
                    bc = rv.get("businessComment") or {}
                    all_reviews[rid] = {
                        "id": rid,
                        "author": (rv.get("author") or {}).get("name", ""),
                        "rating": rv.get("rating", 0),
                        "text": rv.get("text", ""),
                        "date": rv.get("updatedTime", ""),
                        "reply": bc.get("text", ""),
                        "replyDate": bc.get("updatedTime", ""),
                    }
                    new_count += 1

            page_count += 1
            print(f"  Стр.{page}/{total_pages}: +{new_count} новых "
                  f"(всего уникальных: {len(all_reviews)}/{total})")

            if page >= int(total_pages) if str(total_pages).isdigit() else False:
                break

            time.sleep(0.3)

        print(f"Собрано со всех страниц {ranking}: {page_count} стр.")
        time.sleep(1)

    return list(all_reviews.values())


def main():
    business_id = "45519323612"

    print(f"Yandex Maps Reviews Scraper")
    print(f"Business ID: {business_id}")
    print()

    reviews = collect_all_reviews(business_id)

    print(f"\n{'='*50}")
    print(f"ИТОГО: {len(reviews)} уникальных отзывов")

    # Stats
    ratings = [r["rating"] for r in reviews if r["rating"]]
    for star in [5, 4, 3, 2, 1]:
        cnt = sum(1 for r in ratings if r == star)
        print(f"  {star} звёзд: {cnt}")

    with_text = sum(1 for r in reviews if r["text"])
    with_reply = sum(1 for r in reviews if r["reply"])
    print(f"  С текстом: {with_text}")
    print(f"  С ответом бизнеса: {with_reply}")

    # Save JSON
    json_path = "/home/konstantin/reviews_FINAL.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)
    print(f"\nJSON: {json_path}")

    # Save CSV
    csv_path = "/home/konstantin/reviews_FINAL.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "author", "rating", "text", "date", "reply", "replyDate"],
            delimiter=";"
        )
        writer.writeheader()
        for r in reviews:
            writer.writerow(r)
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
