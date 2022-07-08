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
        url = response.url  # TODO: объяви её поближе к месту использования
        # сохраняем в products_all данные о количестве всех имеющихся продуктов в категории  # TODO: название переменной "все продукты", значит тут лежат все продукты?
        products_all = response.xpath(XPATH_SCRIPT).re_first(r"window\.productsTotalCount = (.*);")  # TODO: комментарий лишний, можно назвать переменную иначе, например total_products_count (любое название, чтобы в имени было count/number)
        products_all = int(products_all)
        # сохраняем в products_on_page данные о количестве продуктов на каждой из страниц
        products_on_page = response.xpath(XPATH_SCRIPT).re_first(r"window\.productsPerServerPage = (.*);")
        products_on_page = int(products_on_page)
        pages_count = int(products_all / products_on_page)
        page_prefix = "?page="
        for page_count in range(pages_count):
            url_page = f'{url}{page_prefix}{page_count + 1}'
            yield scrapy.Request(url=url_page, callback=self.parse_request)

    def parse_request(self, response):  # TODO: название функции - парсим реквест? какой реквест мы парсим? мы парсим категорийную страницу
        json_data = response.xpath(XPATH_SCRIPT).re_first(r"window\.products = (.*);")
        json_obj = json.loads(json_data.replace('\'', '"'))
        urls = [d['link'] for d in json_obj]
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

        sales_tag = ''  # TODO: отступ между try-except у sales и этим блоком необязателен, т.к. эта логика всё ещё к sales относится (но не принципиально)
        sales_tag = f"Скидка {sales}%" if sales > 0 else sales_tag

        return {  # TODO: лучше возвращай переменную, а не дикт в таком виде, будет более читаемо (по всему коду - аналогично, здесь я бы сделал price_data, т.к. функция так называется
                "current": current_price,  # {float} Цена со скидкой, если скидки нет то = original
                "original": original_price,  # {float} Оригинальная цена
                "sale_tag": sales_tag  # {str} Если есть скидка на товар то необходимо вычислить процент скидки и записать формате: "Скидка {}%"
            }

    def get_stock(self, response):
        not_stock = response.xpath(XPATH_STOCK).get()
        current_price = response.xpath(XPATH_CURR_PRICE).get()
        if not_stock and not current_price:  # TODO: гораздо лучше, правда для человека не в контексте есть противоречие, т.е. если цена есть, то и сток есть (это правда, но я бы оставил коммент, что у товара не в стоке нет цены)
            stock = False
        else:
            stock = True
        count = 0
        count += 1 if stock else count
        return {
            "in_stock": stock,
            "count": count
        }

    def get_metadata(self, response):
        list_keys = response.xpath(XPATH_FOR_KEYS).getall()  # TODO: можно и без list было, просто keys / values, множественное число в названии указывает на то, что объект итерируемый
        list_values = response.xpath(XPATH_FOR_VALUES).getall()
        full_keys = [key.strip() for key in list_keys]  # TODO: не бойся возвращать результат в те же переменные, откуда их взяла - list_keys звучит лучше, чем full_keys (почему фулл? а до этого они не фулл были?)
        full_values = [value.strip().replace('  ', '') for value in list_values]  # TODO: аналогично
        full_values = [value for value in full_values if value]
        dct_metadata = dict(zip(full_keys, full_values))  # TODO: не очень нравится эти dct/lst в названии, можно было просто metadata назвать
        description = response.xpath(XPATH_DESCRIPTION).getall()

        try:
            description = description[0].strip()  # TODO: если берёшь нулевой элемент, то почему бы просто не взять .get() с дефолтом, а не .getall()?
        except IndexError:
            description = ''

        description_d = {'__description': description}  # TODO: если в конце всё равно наполняешь дикт с метадатой, то можно было просто сделать metadata['__description': description]
        article = response.xpath(XPATH_ARTICLE).get('')
        article = {'АРТИКУЛ': article}
        dct_metadata.update(description_d)
        dct_metadata.update(article)
        return dct_metadata  # TODO: тут молодец, возвращаешь переменную, которая ссылается на дикт, а не сам дикт

    def parse(self, response):
        main_image = response.xpath(XPATH_IMAGE).get()
        main_image = response.urljoin(main_image)
        brand = response.xpath(XPATH_BRAND).get('')
        brand = brand.strip()
        title = response.xpath(XPATH_TITLE).get().strip()  # TODO: а если title будет None? Укажи дефолт перед стрипом
        rpc = response.xpath(XPATH_RPC).get()
        section = response.xpath(XPATH_SECTION).getall()  # TODO: тут список секций (sections, а переменная в единственном числе)
        section = [sect.strip() for sect in section]
        if section:
            section = section[2:]

        item = {  # TODO: укажи комменты справа от строк с диктами, т.к. ниже они выглядят просто как закомменченные строки
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
                "set_images": [main_image],  # {list of str} Список больших изображений товара
                "view360": [],  # {list of str}
                "video": []  # {list of str}
            },
            "metadata": self.get_metadata(response),
            "variants": 0,
            # {int} Кол-во вариантов у товара в карточке (За вариант считать только цвет или объем/масса. Размер у одежды или обуви варинтами не считаются)
        }
        yield item
