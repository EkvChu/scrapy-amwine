import scrapy
import json
import time
from .constants.amwine import *


class AmwineSpider(scrapy.Spider):
    name = 'amwine_ru'
    allowed_domains = ["amwine.ru"]
    start_urls = [
        "https://amwine.ru/catalog/pivo/light/",
        # "https://amwine.ru/catalog/krepkie_napitki/liker/"
    ]

    def start_requests(self):
        cookies = {  # город Ростов-на-дону, магазин по адресу: Космонавтов пр-т, д. 9
            'AMWINE__IS_ADULT': 'Y',
            'AMWINE__REGION_CODE': 'rostov-na-donu',
            'AMWINE__REGION_ELEMENT_XML_ID': '61',
            'AMWINE__REGION_ELEMENT_ID': '182688',
            'AMWINE__CITY_SALE_LOCATION_ID': '1249',
            'AMWINE__CITY_NAME': '%D0%A0%D0%BE%D1%81%D1%82%D0%BE%D0%B2-%D0%BD%D0%B0-%D0%94%D0%BE%D0%BD%D1%83',
            'AMWINE__shop_id': '6311'
        }
        for url in self.start_urls:
            yield scrapy.Request(url=url, cookies=cookies, callback=self.parse_pages)

    def parse_pages(self, response):
        products_category_count = response.xpath(XPATH_SCRIPT).re_first(r"window\.productsTotalCount = (.*);")
        products_category_count = int(products_category_count)
        products_on_page = response.xpath(XPATH_SCRIPT).re_first(r"window\.productsPerServerPage = (.*);")
        products_on_page = int(products_on_page)
        pages_count = int(products_category_count / products_on_page)
        page_prefix = "?page="
        url = response.url
        for page_count in range(pages_count):
            url_page = f'{url}{page_prefix}{page_count + 1}'
            yield scrapy.Request(url=url_page, callback=self.parse_category_page)

    def parse_category_page(self, response):
        json_data = response.xpath(XPATH_SCRIPT).re_first(r"window\.products = (.*);")
        json_obj = json.loads(json_data.replace('\'', '"'))
        urls = [d['link'] for d in json_obj]
        for url in urls:
            url = response.urljoin(url)
            yield scrapy.Request(url, callback=self.parse)

    def get_price_data(self, response):
        current_price = response.xpath(XPATH_CURR_PRICE).getall()
        current_price = [price.strip() for price in current_price]
        current_price = [price for price in current_price if price]
        current_price = ''.join(current_price)
        try:
            current_price = float(current_price)
        except ValueError:
            current_price = 0.0

        original_price = response.xpath(XPATH_ORIG_PRICE).get('')
        original_price = original_price.strip()
        try:
            original_price = float(original_price)
        except ValueError:
            original_price = current_price

        try:
            sales = int(100 - (current_price / original_price * 100))
        except ZeroDivisionError:
            sales = 0
        sales_tag = ''
        sales_tag = f"Скидка {sales}%" if sales > 0 else sales_tag
        price_data = {"current": current_price, "original": original_price, "sale_tag": sales_tag}
        return price_data

    def get_stock(self, response):
        not_stock = response.xpath(XPATH_STOCK).get()
        # у товаров, которые не в наличии, на странице появляется специальный элемент с текстом "Нет в наличии"
        # у товаров в наличии ничего подобного нет
        if not_stock:
            stock = False
        else:
            stock = True
        count = 1 if stock else 0
        stock = {"in_stock": stock, "count": count}
        return stock

    def get_metadata(self, response):
        keys = response.xpath(XPATH_FOR_KEYS).getall()
        values = response.xpath(XPATH_FOR_VALUES).getall()
        keys = [key.strip() for key in keys]
        values = [value.strip().replace('  ', '') for value in values]
        values = [value for value in values if value]
        metadata = dict(zip(keys, values))
        description = response.xpath(XPATH_DESCRIPTION).get('')
        try:
            description = description.strip()
        except IndexError:
            description = ''

        article = response.xpath(XPATH_ARTICLE).get('')
        metadata['__description'] = description
        metadata['АРТИКУЛ'] = article

        return metadata

    def parse(self, response):
        main_image = response.xpath(XPATH_IMAGE).get()
        main_image = response.urljoin(main_image)
        brand = response.xpath(XPATH_BRAND).get('')
        brand = brand.strip()
        title = response.xpath(XPATH_TITLE).get('').strip()
        rpc = response.xpath(XPATH_RPC).get()
        sections = response.xpath(XPATH_SECTION).getall()
        sections = [sect.strip() for sect in sections]
        if sections:
            sections = sections[2:]

        item = {
            "timestamp": int(time.time()),  # Текущее время в формате timestamp
            "RPC": rpc,  # {str} Уникальный код товара
            "url": response.url,  # {str} Ссылка на страницу товара
            "title": title, # {str} Заголовок/название товара (если в карточке товара указан цвет или объем, необходимо добавить их в title в формате: "{название}, {цвет}")
            "marketing_tags": [], # {list of str} Список тэгов, например: ['Популярный', 'Акция', 'Подарок'], если тэг представлен в виде изображения собирать его не нужно
            "brand": brand,  # {str} Бренд товара
            "section": sections, # {list of str} Иерархия разделов, например: ['Игрушки', 'Развивающие и интерактивные игрушки', 'Интерактивные игрушки']
            "price_data": self.get_price_data(response),
            "stock": self.get_stock(response),
            "assets": {
                "main_image": main_image,  # {str} Ссылка на основное изображение товара
                "set_images": [main_image],  # {list of str} Список больших изображений товара
                "view360": [],  # {list of str}
                "video": []  # {list of str}
            },
            "metadata": self.get_metadata(response),
            "variants": 0,  # {int} Кол-во вариантов у товара в карточке (За вариант считать только цвет или объем/масса. Размер у одежды или обуви варинтами не считаются)
        }
        yield item
