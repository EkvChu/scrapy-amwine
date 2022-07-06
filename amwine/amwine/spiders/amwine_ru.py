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
        cookies = {
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
        url = response.url
        pr_all_data = response.xpath(XPATH_SCRIPT).re_first(r"window\.productsTotalCount = (.*);")
        pr_all = int(pr_all_data)
        pr_page_data = response.xpath(XPATH_SCRIPT).re_first(r"window\.productsPerServerPage = (.*);")
        pr_on_page = int(pr_page_data)
        pages_count = int(pr_all / pr_on_page)
        page_prefix = "?page="
        for page_count in range(pages_count):
            url_page = f'{url}{page_prefix}{page_count + 1}'
            yield scrapy.Request(url=url_page, callback=self.parse_request)

    def parse_request(self, response):
        json_data = response.xpath(XPATH_SCRIPT).re_first(r"window\.products = (.*);")
        json_obj = json.loads(json_data.replace('\'', '"'))
        urls = [d['link'] for d in json_obj]
        print(len(urls))
        for url in urls:
            url = response.urljoin(url)
            yield scrapy.Request(url, callback=self.parse)

    def get_price_data(self, response):
        current_price = response.xpath(XPATH_CURR_PRICE).get('')
        current_price = current_price.strip()
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
        if sales > 0:
            sales_tag = f"Скидка {sales}%"
        else:
            sales_tag = ""
        return {
                "current": current_price,  # {float} Цена со скидкой, если скидки нет то = original
                "original": original_price,  # {float} Оригинальная цена
                "sale_tag": sales_tag  # {str} Если есть скидка на товар то необходимо вычислить процент скидки и записать формате: "Скидка {}%"
            }

    def get_stock(self, response):
        is_stock = response.xpath(XPATH_STOCK).get()
        current_price = response.xpath(XPATH_CURR_PRICE).get('')
        current_price = current_price.strip()
        if is_stock is not None and len(current_price) < 1:
            stock = False
        else:
            stock = True
        if stock is True:
            count = 1
        else:
            count = 0
        return {
            "in_stock": stock,
            "count": count
        }

    def get_metadata(self, response):
        lst_of_keys = response.xpath(XPATH_FOR_KEYS).getall()
        lst_of_values = response.xpath(XPATH_FOR_VALUES).getall()
        full_keys = []
        for key in lst_of_keys:
            full_keys.append(key.strip())
        full_values = []
        for value in lst_of_values:
            full_values.append(value.strip().replace('  ', ''))
        full_values = [value for value in full_values if value]
        dct = dict(zip(full_keys, full_values))
        description = response.xpath(XPATH_DESCRIPTION).getall()
        try:
            description = description[0].strip()
        except IndexError:
            description = ''
        description_d = {'__description': description}
        article = response.xpath(XPATH_ARTICLE).get('')
        article_d = {'АРТИКУЛ': article}
        dct.update(description_d)
        dct.update(article_d)
        return dct

    def parse(self, response):
        main_image = response.xpath(XPATH_IMAGE).get()
        main_image = response.urljoin(main_image)
        brand = response.xpath(XPATH_BRAND).get('')
        brand = brand.strip()
        title = response.xpath(XPATH_TITLE).get().strip()
        rpc = response.xpath(XPATH_RPC).get()
        section = []
        for sect in response.xpath(XPATH_SECTION).getall():
            section.append(sect)
        if len(section) > 0:
            section = section[-2:]
        section = ";".join(section).replace('\n            ', '').split(";")
        item = {
            "timestamp": int(time.time()),  # Текущее время в формате timestamp
            "RPC": rpc,  # {str} Уникальный код товара
            "url": response.url,  # {str} Ссылка на страницу товара
            "title": title,
            # {str} Заголовок/название товара (если в карточке товара указан цвет или объем, необходимо добавить их в title в формате: "{название}, {цвет}")
            "marketing_tags": [],
            # {list of str} Список тэгов, например: ['Популярный', 'Акция', 'Подарок'], если тэг представлен в виде изображения собирать его не нужно
            "brand": brand,  # {str} Брэнд товара
            "section": section,
            # {list of str} Иерархия разделов, например: ['Игрушки', 'Развивающие и интерактивные игрушки', 'Интерактивные игрушки']
            "price_data": self.get_price_data(response),
            "stock": self.get_stock(response),
            "assets": {
                "main_image": main_image,  # {str} Ссылка на основное изображение товара
                "set_images": [],  # {list of str} Список больших изображений товара
                "view360": [],  # {list of str}
                "video": []  # {list of str}
            },
            "metadata": self.get_metadata(response),
            "variants": 0,
            # {int} Кол-во вариантов у товара в карточке (За вариант считать только цвет или объем/масса. Размер у одежды или обуви варинтами не считаются)
        }
        yield item
