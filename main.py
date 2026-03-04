import csv
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://books.toscrape.com/"

# Output structure
OUTPUT_ROOT = "output"
DATA_DIR = os.path.join(OUTPUT_ROOT, "data")
IMAGES_DIR = os.path.join(OUTPUT_ROOT, "images")


def slugify(text: str) -> str:
    """
    Convert text into a safe filename part.
    Example: "A Light in the Attic" -> "a_light_in_the_attic"
    """
    return (
        text.strip()
        .lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("'", "")
        .replace("&", "and")
    )


def parse_number_available(availability_text: str) -> int:
    """
    Extract the available quantity from:
    "In stock (22 available)"
    """
    match = re.search(r"(\d+)\s+available", availability_text)
    return int(match.group(1)) if match else 0


def parse_review_rating(soup: BeautifulSoup) -> str:
    """
    Extract the review rating from a CSS class.
    Example: <p class="star-rating Three"> -> "Three"
    """
    rating_tag = soup.find("p", class_="star-rating")
    if not rating_tag:
        return ""
    classes = rating_tag.get("class", [])
    return classes[1] if len(classes) > 1 else ""


def get_product_table_data(soup: BeautifulSoup) -> dict:
    """
    Extract key/value pairs from the product information table.
    """
    data = {}
    table = soup.find("table", class_="table table-striped")
    if not table:
        return data

    for row in table.find_all("tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td:
            key = th.get_text(strip=True)
            value = td.get_text(strip=True)
            data[key] = value

    return data


def scrape_book(url: str) -> dict:
    """
    Scrape one product page and return a dict with the required fields.
    """
    response = requests.get(url)
    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    title = soup.find("h1").get_text(strip=True)

    # Category from breadcrumb: Home > Books > Category > Book
    category = ""
    breadcrumb_links = soup.select("ul.breadcrumb li a")
    if len(breadcrumb_links) >= 3:
        category = breadcrumb_links[2].get_text(strip=True)

    # Description (optional)
    product_description = ""
    description_header = soup.find("div", id="product_description")
    if description_header:
        description_paragraph = description_header.find_next_sibling("p")
        if description_paragraph:
            product_description = description_paragraph.get_text(strip=True)

    # Image URL (absolute)
    image_url = ""
    image_tag = soup.find("div", class_="item active")
    if image_tag and image_tag.find("img"):
        src = image_tag.find("img").get("src", "")
        image_url = urljoin(url, src)

    review_rating = parse_review_rating(soup)

    product_table = get_product_table_data(soup)
    upc = product_table.get("UPC", "")
    price_including_tax = product_table.get("Price (incl. tax)", "")
    price_excluding_tax = product_table.get("Price (excl. tax)", "")

    availability_text = soup.find("p", class_="instock availability").get_text(strip=True)
    number_available = parse_number_available(availability_text)

    return {
        "product_page_url": url,
        "universal_product_code": upc,
        "title": title,
        "price_including_tax": price_including_tax,
        "price_excluding_tax": price_excluding_tax,
        "number_available": number_available,
        "product_description": product_description,
        "category": category,
        "review_rating": review_rating,
        "image_url": image_url,
    }


def get_book_urls_from_category(category_url: str) -> list[str]:
    """
    Retrieve all book URLs from a category (with pagination).
    """
    book_urls = []
    next_page_url = category_url

    while next_page_url:
        response = requests.get(next_page_url)
        soup = BeautifulSoup(response.text, "html.parser")

        articles = soup.find_all("article", class_="product_pod")
        for article in articles:
            relative_url = article.find("a")["href"]
            absolute_url = urljoin(next_page_url, relative_url)
            book_urls.append(absolute_url)

        next_link = soup.find("li", class_="next")
        if next_link:
            next_href = next_link.find("a")["href"]
            next_page_url = urljoin(next_page_url, next_href)
        else:
            next_page_url = None

    return book_urls


def get_category_urls() -> list[str]:
    """
    Retrieve all category URLs from the homepage sidebar.
    """
    response = requests.get(BASE_URL)
    soup = BeautifulSoup(response.text, "html.parser")

    category_urls = []
    links = soup.select("div.side_categories ul li ul li a")
    for link in links:
        href = link["href"]
        category_urls.append(urljoin(BASE_URL, href))

    return category_urls


def get_category_name(category_url: str) -> str:
    """
    Retrieve the category name from its page (<h1>).
    """
    response = requests.get(category_url)
    soup = BeautifulSoup(response.text, "html.parser")
    return soup.find("h1").get_text(strip=True)


def save_to_csv(rows: list[dict], csv_path: str) -> None:
    """
    Save book data to a CSV file.
    """
    fieldnames = [
        "product_page_url",
        "universal_product_code",
        "title",
        "price_including_tax",
        "price_excluding_tax",
        "number_available",
        "product_description",
        "category",
        "review_rating",
        "image_url",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def download_image(image_url: str, dest_path: str) -> bool:
    """
    Download an image from image_url and save it to dest_path.
    """
    response = requests.get(image_url, stream=True)
    response.raise_for_status()

    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
            else:
                return False
        return True

def get_image_extension(image_url: str) -> str:
    """
    Try to infer the file extension from the image URL.
    Defaults to '.jpg' if not found.
    """
    path = urlparse(image_url).path
    _, ext = os.path.splitext(path)
    return ext if ext else ".jpg"


def main() -> None:
    """
    Main orchestration:
    - create output folders
    - loop through categories
    - for each category:
        - collect book URLs (pagination)
        - scrape each book
        - save one CSV per category
        - download images into images/<category_slug>/
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    category_urls = get_category_urls()
    print(f"Found {len(category_urls)} categories")

    for category_url in category_urls:
        category_name = get_category_name(category_url)
        category_slug = slugify(category_name)

        category_images_dir = os.path.join(IMAGES_DIR, category_slug) 
        os.makedirs(category_images_dir, exist_ok=True)

        book_urls = get_book_urls_from_category(category_url)

        rows = []
        for book_url in book_urls:
            book = scrape_book(book_url)
            rows.append(book)

            # Download the image for this book
            if book["image_url"]:
                ext = get_image_extension(book["image_url"])
                image_filename = f"{slugify(book['title'])}{ext}"
                image_path = os.path.join(category_images_dir, image_filename)

                # Avoid re-downloading if already exists
                if not os.path.exists(image_path):
                    try:
                        download_image(book["image_url"], image_path)
                    except Exception as e:
                        print(f"Image download failed: {book['image_url']} ({e})")

        csv_filename = f"{category_slug}.csv"
        csv_path = os.path.join(DATA_DIR, csv_filename)

        save_to_csv(rows, csv_path)
        print(f"Saved {len(rows)} rows to {csv_path}")


if __name__ == "__main__":
    main()