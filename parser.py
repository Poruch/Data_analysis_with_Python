import requests
import pandas as pd
import time
import random
import re
from datetime import datetime

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
}

def parse_release_date(date_str):
    """Преобразует русскоязычную дату из Steam API в объект datetime"""
    if not date_str or date_str in ["N/A", "Скоро", "Coming Soon", "TBA"]:
        return pd.NaT
    
    clean_str = date_str.replace(" г.", "").strip()
    month_map = {
        "янв.": "Jan", "фев.": "Feb", "мар.": "Mar", "апр.": "Apr",
        "мая": "May", "май": "May", 
        "июн.": "Jun", "июл.": "Jul", "авг.": "Aug",
        "сен.": "Sep", "окт.": "Oct", "ноя.": "Nov", "дек.": "Dec"
    }
    
    for ru, en in month_map.items():
        if ru in clean_str:
            clean_str = clean_str.replace(ru, en)
            break
            
    try:
        return datetime.strptime(clean_str, "%d %b %Y")
    except ValueError:
        return pd.NaT

def get_steamspy_data(appid):
    """Источник данных SteamSpy: владельцы, теги, жанры, языки, CCU"""
    try:
        url = f"https://steamspy.com/api.php?request=appdetails&appid={appid}"
        r = requests.get(url, headers=HEADERS, timeout=10)
        
        if "application/json" not in r.headers.get("Content-Type", ""):
            return None
            
        data = r.json()
        if data.get("appid") == 999999:
            return None
            
        owners_avg = "N/A"
        owners_str = data.get("owners", "0 .. 0")
        m = re.search(r"([\d,]+)\s*\.\.\s*([\d,]+)", owners_str)
        if m:
            avg = (int(m.group(1).replace(",","")) + int(m.group(2).replace(",",""))) // 2
            owners_avg = f"{avg:,}".replace(",", " ")
            
        tags_list = []
        tags_raw = data.get("tags", {})
        if isinstance(tags_raw, dict):
            sorted_tags = sorted(tags_raw.items(), key=lambda x: x[1], reverse=True)
            tags_list = [tag[0] for tag in sorted_tags[:20]]
            
        genre_raw = data.get("genre", "")
        if isinstance(genre_raw, str) and genre_raw:
            genres_list = [g.strip() for g in genre_raw.split(",") if g.strip()]
        elif isinstance(genre_raw, list):
            genres_list = genre_raw
        else:
            genres_list = []

        languages_raw = data.get("languages")
        if isinstance(languages_raw, list):
            lang_count = len(languages_raw)
        elif isinstance(languages_raw, str) and languages_raw.strip():
            lang_count = len([x.strip() for x in languages_raw.split(",")])
        else:
            lang_count = 0
            
        return {
            "Игра": data.get("name", "N/A"),
            "Разработчик": data.get("developer", "N/A"),
            "Издатель": data.get("publisher", "N/A"),
            "Примерное кол-во владельцев (среднее)": owners_avg,
            "Популярные теги (20)": ", ".join(tags_list) if tags_list else "N/A",
            "Жанры": ", ".join(genres_list) if genres_list else "N/A",
            "Количество языков": lang_count,
            "Пиковый онлайн вчера (CCU)": f"{data.get('ccu', 0):,}".replace(",", " ")
        }
    except Exception:
        return None


def get_steam_api_data(appid):
    """Платформы, особенности, метакритик, дата выхода, локализованная цена"""
    try:
        url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=russian"
        r = requests.get(url, headers=HEADERS, timeout=10)
        data = r.json().get(str(appid), {})
        
        if not data.get("success"):
            return {}
            
        app = data["data"]
        categories = [cat["description"].lower() for cat in app.get("categories", [])]
        
        def check(kws): 
            return any(k in " ".join(categories) for k in kws)
            
        if app.get("is_free"):
            price = "Бесплатно"
        elif "price_overview" in app:
            price = app["price_overview"].get("final_formatted", "N/A")
        else:
            price = "N/A"
            
        raw_date = app.get("release_date", {}).get("date", "N/A")
        parsed_date = parse_release_date(raw_date)
            
        return {
            "Игра": app.get("name", "N/A"),
            "Разработчик": ", ".join(app.get("developers", ["N/A"])),
            "Издатель": ", ".join(app.get("publishers", ["N/A"])),
            "Дата выхода": parsed_date,
            "Ранний доступ": "Ранний доступ" in app.get("name", "") or app.get("release_date", {}).get("coming_soon", False),
            "Цена": price,
            "Windows": app.get("platforms", {}).get("windows", False),
            "MacOS": app.get("platforms", {}).get("mac", False),
            "Linux": app.get("platforms", {}).get("linux", False),
            "Одиночная игра": check(["для одного игрока", "single-player"]),
            "Мультиплеерная игра": check(["многопользовательская", "multi-player", "coop"]),
            "Облако": check(["облачные сохранения", "cloud"]),
            "Достижения": check(["достижения", "achievements"]),
            "Family Share": check(["семейный доступ", "family sharing"]),
            "VR": check(["vr"]),
            "SteamDeck": check(["steam deck", "deck verified"]),
            "Рейтинг Metacritic": f"{app.get('metacritic', {}).get('score', 'N/A')}/100" if "metacritic" in app else "N/A"
        }
    except Exception:
        return {}

def get_reviews(appid):
    """Возвращает долю положительных отзывов как float от 0.0 до 1.0"""
    res = {"Недавние отзывы": 0.0, "Все отзывы": 0.0, "Количество отзывов": "0"}
    try:
        url_recent = f"https://store.steampowered.com/appreviews/{appid}?json=1&filter=all&language=all&day_range=30&num_per_page=1"
        r_recent = requests.get(url_recent, headers=HEADERS, timeout=10).json()
        
        url_all = f"https://store.steampowered.com/appreviews/{appid}?json=1&filter=all&language=all&day_range=all&num_per_page=1"
        r_all = requests.get(url_all, headers=HEADERS, timeout=10).json()
        
        if r_recent.get("success") == 1 and "query_summary" in r_recent:
            q = r_recent["query_summary"]
            total = q.get("total_reviews", 0)
            pos = q.get("total_positive", 0)
            # Дробное число от 0 до 1
            res["Недавние отзывы"] = round(pos / total, 4) if total > 0 else 0.0
            res["Количество отзывов"] = f"{total:,}".replace(",", " ")
            
        if r_all.get("success") == 1 and "query_summary" in r_all:
            q = r_all["query_summary"]
            total = q.get("total_reviews", 0)
            pos = q.get("total_positive", 0)
            # Дробное число от 0 до 1
            res["Все отзывы"] = round(pos / total, 4) if total > 0 else 0.0
            
    except Exception:
        pass
    return res


def get_last_update(appid):
    """Возвращает дату последнего обновления как объект datetime"""
    try:
        url = f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid={appid}&count=1&maxlength=50&format=json"
        r = requests.get(url, headers=HEADERS, timeout=10).json()
        if "appnews" in r and "newsitems" in r["appnews"] and r["appnews"]["newsitems"]:
            ts = r["appnews"]["newsitems"][0]["date"]
            return datetime.fromtimestamp(ts) # Возвращаем datetime, а не строку
        return pd.NaT
    except Exception:
        return pd.NaT

def parse_game(appid):
    print(f"📥 AppID {appid}...", end=" ")
    
    spy_data = get_steamspy_data(appid)
    api_data = get_steam_api_data(appid)
    
    if not spy_data and not api_data:
        print("❌ Недоступна")
        return None
        
    if not spy_data:
        spy_data = {
            "Игра": api_data.get("Игра", "N/A"),
            "Разработчик": api_data.get("Разработчик", "N/A"),
            "Издатель": api_data.get("Издатель", "N/A"),
            "Примерное кол-во владельцев (среднее)": "N/A (Блок)",
            "Популярные теги (20)": "N/A",
            "Жанры": "N/A (Блок)",
            "Количество языков": "N/A",
            "Пиковый онлайн вчера (CCU)": "N/A (Блок)"
        }
        status = "⚠️ (SteamSpy блок)"
    else:
        status = "✅"
        
    reviews_data = get_reviews(appid)
    update_data = {"Дата последнего обновления": get_last_update(appid)}
    
    final_data = {"AppID": appid}
    final_data.update(spy_data)
    final_data.update(api_data)
    final_data.update(reviews_data)
    final_data.update(update_data)
    
    print(status)
    return final_data

def main():
    app_ids = [730, 570, 1091500, 1245620, 413150, 292030]
    
    dataset = []
    print("🚀 Запуск финального парсера...\n")
    
    for appid in app_ids:
        res = parse_game(appid)
        if res: 
            dataset.append(res)
        time.sleep(random.uniform(1.5, 2.5))
        
    if dataset:
        df = pd.DataFrame(dataset)
        
        # Принудительно приводим ОБЕ колонки с датами к единому типу datetime64[ns]
        df["Дата выхода"] = pd.to_datetime(df["Дата выхода"])
        df["Дата последнего обновления"] = pd.to_datetime(df["Дата последнего обновления"])
        
        cols_order = [
            "AppID", "Игра", "Издатель", "Разработчик", "Дата выхода", "Дата последнего обновления",
            "Недавние отзывы", "Все отзывы", "Количество отзывов", "Популярные теги (20)", "Жанры", "Количество языков",
            "Одиночная игра", "Мультиплеерная игра", "Ранний доступ", "Облако", "Достижения", 
            "Family Share", "VR", "Windows", "Linux", "MacOS", "SteamDeck", "Цена", 
            "Примерное кол-во владельцев (среднее)", "Пиковый онлайн вчера (CCU)",
            "Рейтинг Metacritic"
        ]
        
        final_cols = [c for c in cols_order if c in df.columns]
        df = df[final_cols]
        
        filename = "steam_ultimate_dataset.csv"
        df.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"\n🎉 Датасет успешно сохранен в {filename}")
        
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1400)
        print("\n--- Предпросмотр датасета ---")
        print(df.head())
    else:
        print("\n❌ Не удалось собрать данные.")

if __name__ == "__main__":
    main()
