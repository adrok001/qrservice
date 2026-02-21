"""
PoC: Ответ на отзыв Яндекс Карт через внутренний API Яндекс Бизнеса.

Использование:
    python yandex_reply_poc.py

Скрипт:
1. Загружает страницу отзывов Яндекс Бизнеса (с cookies)
2. Парсит review ID и CSRF-токены из HTML
3. Отправляет ответ на выбранный отзыв
"""

import json
import re
import sys

import requests

# === НАСТРОЙКИ ===

COMPANY_ID = "120057269196"

COOKIES = {
    "Session_id": "3:1771690030.5.0.1762511050377:NvXJVA:3044.1.2:1|2282285924.0.2.3:1762511050.6:2148328969.7:1764851991|3:11736001.733279.Cv3ImrEEXOV1QEAd7ZKWG6ZAELo",
    "sessionid2": "3:1771690030.5.0.1762511050377:NvXJVA:3044.1.2:1|2282285924.0.2.3:1762511050.6:2148328969.7:1764851991|3:11736001.733279.fakesign0000000000000000000",
    "yandexuid": "8769848311762351740",
    "i": "9j06mns9K2/R3EeH7gP6+EyQpYXGF/1uxCzodY9gdKUC1c5k6Ffg0TzJrWqhiU8z2fv89hnkjiHa0b5WpVJMpB9fyFg=",
    "L": "WTNdQQQESUpnDA0JQ01TBVYARHpIQXJgPAYICQh5UwQOHQ==.1762511050.1360481.348675.4e4fa40b9445a83e1618e5e13c48d88f",
    "yandex_login": "TopNaKarte",
    "sessar": "1.1719226.CiCUhpRTpHu2ryIpzk5GZNmkPJuT3zjij9UFpzIoW4eTzw.LyU1PV3LAGOHC3M8DEjWLLImgoQQT43HTkRdGs60f68",
    "skid": "6574592251770713238",
    "is_gdpr": "1",
    "is_gdpr_b": "CMzOaRDx8wIYASgC",
    "gdpr": "0",
    "yuidss": "8769848311762351740",
    "_yasc": "gDa3/BGmNGS5TufYhkIS9fZyqT6ni/zgrZLPUgRq/VvRMJq7dhX5um103jJZMlQBXa9ISjWmQnBswki6tktJww==",
    "bh": "EkEiTm90OkEtQnJhbmQiO3Y9Ijk5IiwgIkdvb2dsZSBDaHJvbWUiO3Y9IjE0NSIsICJDaHJvbWl1bSI7dj0iMTQ1IhoFIng4NiIiDyIxNDUuMC43NjMyLjc3IioCPzAyAiIiOgkiV2luZG93cyJCCCIxMC4wLjAiSgQiNjQiUlsiTm90OkEtQnJhbmQiO3Y9Ijk5LjAuMC4wIiwgIkdvb2dsZSBDaHJvbWUiO3Y9IjE0NS4wLjc2MzIuNzciLCAiQ2hyb21pdW0iO3Y9IjE0NS4wLjc2MzIuNzciWgI/MGD5uOfMBmoe3Mrh/wiS2KGxA5/P4eoD+/rw5w3r//32D52nzIcI",
}

HEADERS = {
    "accept": "application/json; charset=UTF-8",
    "content-type": "application/json; charset=UTF-8",
    "origin": "https://yandex.ru",
    "x-requested-with": "XMLHttpRequest",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}


def fetch_reviews_page(session: requests.Session, page: int = 1) -> str:
    """Загрузить HTML страницы отзывов."""
    url = f"https://yandex.ru/sprav/{COMPANY_ID}/p/edit/reviews/"
    params = {"ranking": "by_time", "page": page, "type": "company"}
    resp = session.get(url, params=params, headers={"user-agent": HEADERS["user-agent"]})
    resp.raise_for_status()
    return resp.text


def decode_unicode_escapes(s: str) -> str:
    """Декодировать \\u002F и подобные escape-последовательности."""
    return s.encode().decode("unicode_escape")


def parse_reviews(html: str) -> list[dict]:
    """Извлечь отзывы с токенами из HTML.

    Структура отзыва в JSON:
    {
        "id": "...",                          # = cmnt_entity_id = reviewId
        "author": {"user": "Имя", ...},      # автор
        "snippet": "текст отзыва",            # краткий текст
        "full_text": "текст отзыва",          # полный текст
        "rating": 5,                          # рейтинг 1-5
        "owner_comment": {"text": "..."},     # ответ владельца (если есть)
        "cmnt_entity_id": "...",              # ID отзыва
        "business_answer_csrf_token": "..."   # токен для ответа
    }
    """
    reviews = []

    # Ищем JSON-массив items в HTML
    items_match = re.search(r'"items"\s*:\s*\[', html)
    if not items_match:
        print("  Блок 'items' не найден в HTML!")
        return reviews

    # Парсим каждый отзыв через позицию cmnt_entity_id
    review_ids = re.findall(r'"cmnt_entity_id"\s*:\s*"([^"]+)"', html)
    tokens = re.findall(r'"business_answer_csrf_token"\s*:\s*"([^"]+)"', html)

    print(f"  Найдено отзывов: {len(review_ids)}")
    print(f"  Найдено токенов: {len(tokens)}")

    for rid, token in zip(review_ids, tokens):
        token_decoded = decode_unicode_escapes(token)

        # Находим позицию этого отзыва в HTML
        pos = html.find(f'"cmnt_entity_id":"{rid}"')
        if pos < 0:
            continue

        # Берём контекст: 3000 символов ДО (там весь отзыв)
        start = max(0, pos - 3000)
        chunk = html[start:pos + 100]

        # Автор: "author":{"privacy":"...","user":"ИМЯ",...}
        author = "?"
        author_match = re.search(r'"author"\s*:\s*\{[^}]*"user"\s*:\s*"([^"]+)"', chunk)
        if author_match:
            author = author_match.group(1)

        # Текст отзыва: "snippet":"..."
        review_text = ""
        snippet_match = re.search(r'"snippet"\s*:\s*"((?:[^"\\]|\\.)*)"', chunk)
        if snippet_match:
            review_text = snippet_match.group(1)[:120]
            review_text = review_text.replace("\\n", " ").strip()

        # Рейтинг: "rating":5
        rating = "?"
        rating_match = re.search(r'"rating"\s*:\s*(\d)', chunk)
        if rating_match:
            rating = rating_match.group(1)

        # Есть ли ответ владельца: "owner_comment":{"time_created":...,"text":"..."}
        has_answer = False
        oc_match = re.search(r'"owner_comment"\s*:\s*\{[^}]*"text"\s*:\s*"([^"]*)"', chunk)
        if oc_match and oc_match.group(1):
            has_answer = True

        reviews.append({
            "reviewId": rid,
            "answerCsrfToken": token_decoded,
            "author": author,
            "text": review_text,
            "rating": rating,
            "hasAnswer": has_answer,
        })

    return reviews


def find_csrf_tokens(html: str) -> dict:
    """Найти все CSRF-токены на странице."""
    tokens = {}

    # x-csrf-token — поле "csrf" в HTML (формат: hash:timestamp)
    csrf_match = re.search(r'"csrf"\s*:\s*"([a-f0-9]+:[0-9]+)"', html)
    if csrf_match:
        tokens["x-csrf-token"] = csrf_match.group(1)

    # reviewsCsrfToken — поле "csrf_token" в HTML (рядом с pager)
    csrf_token_match = re.search(r'"csrf_token"\s*:\s*"([^"]+)"', html)
    if csrf_token_match:
        raw = csrf_token_match.group(1)
        tokens["reviewsCsrfToken"] = decode_unicode_escapes(raw)

    print(f"  x-csrf-token: {'OK' if 'x-csrf-token' in tokens else 'НЕ НАЙДЕН'}")
    print(f"  reviewsCsrfToken: {'OK' if 'reviewsCsrfToken' in tokens else 'НЕ НАЙДЕН'}")

    return tokens


def send_reply(session: requests.Session, review_id: str, text: str,
               answer_csrf_token: str, reviews_csrf_token: str,
               x_csrf_token: str) -> dict:
    """Отправить ответ на отзыв."""
    url = "https://yandex.ru/sprav/api/ugcpub/business-answer"

    headers = {
        **HEADERS,
        "x-csrf-token": x_csrf_token,
        "referer": f"https://yandex.ru/sprav/{COMPANY_ID}/p/edit/reviews/?ranking=by_time&page=1&type=company",
    }

    body = {
        "reviewId": review_id,
        "text": text,
        "answerCsrfToken": answer_csrf_token,
        "reviewsCsrfToken": reviews_csrf_token,
    }

    print(f"\n  URL: {url}")
    print(f"  reviewId: {review_id}")
    print(f"  text: {text[:80]}")
    print(f"  x-csrf-token: {x_csrf_token[:40]}...")

    resp = session.post(url, json=body, headers=headers)

    print(f"\n  HTTP статус: {resp.status_code}")
    try:
        result = resp.json()
        print(f"  Ответ: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return result
    except Exception:
        print(f"  Ответ (текст): {resp.text[:500]}")
        return {"error": resp.text}


def main():
    print("=" * 50)
    print("  PoC: Ответ на отзыв Яндекс Карт")
    print("=" * 50)

    session = requests.Session()
    session.cookies.update(COOKIES)

    # Шаг 1
    print("\n[1/4] Загрузка страницы отзывов...")
    html = fetch_reviews_page(session)
    print(f"  Получено {len(html)} байт")

    # Шаг 2
    print("\n[2/4] Поиск CSRF-токенов...")
    csrf_tokens = find_csrf_tokens(html)

    x_csrf = csrf_tokens.get("x-csrf-token")
    reviews_csrf = csrf_tokens.get("reviewsCsrfToken")

    if not x_csrf or not reviews_csrf:
        print("\n  ОШИБКА: Не все токены найдены. Возможно cookies протухли.")
        print("  Перелогиньтесь в Яндекс Бизнесе и обновите cookies в скрипте.")
        sys.exit(1)

    # Шаг 3
    print("\n[3/4] Парсинг отзывов...")
    reviews = parse_reviews(html)

    if not reviews:
        print("  Отзывы не найдены!")
        sys.exit(1)

    # Показываем отзывы
    print(f"\n  {'#':<4} {'Рейт':<6} {'Автор':<20} {'Ответ':<8} Текст")
    print("  " + "-" * 80)
    for i, r in enumerate(reviews):
        answered = "Да" if r["hasAnswer"] else "—"
        text_preview = r["text"][:40] + "..." if len(r["text"]) > 40 else r["text"]
        print(f"  {i:<4} {'*' * int(r['rating']) if r['rating'].isdigit() else '?':<6} {r['author']:<20} {answered:<8} {text_preview}")

    # Шаг 4
    print(f"\n[4/4] Отправка тестового ответа")
    print("  Введите номер отзыва (или 'q' для выхода):")
    choice = input("  > ").strip()

    if choice.lower() == "q":
        print("\nВыход.")
        return

    idx = int(choice)
    review = reviews[idx]

    print(f"\n  Выбран отзыв #{idx}: {review['author']} ({review['reviewId'][:20]}...)")
    if review["hasAnswer"]:
        print("  ВНИМАНИЕ: на этот отзыв уже есть ответ! Он будет заменён.")

    print("  Введите текст ответа:")
    text = input("  > ").strip()
    if not text:
        print("  Пустой текст, выход.")
        return

    print(f"\n  Отправляю...")
    result = send_reply(
        session=session,
        review_id=review["reviewId"],
        text=text,
        answer_csrf_token=review["answerCsrfToken"],
        reviews_csrf_token=reviews_csrf,
        x_csrf_token=x_csrf,
    )

    status = result.get("status") or result.get("type")
    if result.get("error"):
        print("\n  РЕЗУЛЬТАТ: Ошибка при отправке")
    else:
        print(f"\n  РЕЗУЛЬТАТ: Ответ отправлен!")


if __name__ == "__main__":
    main()
