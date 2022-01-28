import json
import os
import sys
import argparse
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from lxml import etree
from pathvalidate import sanitize_filename
from tqdm import tqdm

ROOT_URL = "https://tululu.org"
TARGET_RUBRIC_URL = "/l55/"
LIB_DIR = 'library/'
TEXTS_SUBDIR = 'books/'
IMAGES_SUBDIR = 'images/'


def check_for_redirect(response):
    if response.is_redirect:
        raise requests.HTTPError('вызвано исключение- редирект')


def get_response(url):
    response = requests.get(url, allow_redirects=False)
    response.raise_for_status()
    check_for_redirect(response)
    return response


def download_file(url, filepath):
    response = get_response(url)
    with open(filepath, 'wb') as file:
        file.write(response.content)
    # if 'text/plain' in response.headers['Content-Type']:
    #     # print(filepath,response.headers['Content-Type'])
    #     with open(filepath, 'w') as file:
    #         file.write(response.text)
    # else:
    #     with open(filepath, 'wb') as file:
    #         file.write(response.content)


def parse_book_page(response):
    selector=".tabs #content"
    content_block = BeautifulSoup(response.content, 'lxml').select(selector)
    dom = etree.HTML(str(content_block))
    return {
        'text_link': ''.join(dom.xpath('//*/a[starts-with(@href,"/txt.php")]/@href')),
        'img_link': ''.join(dom.xpath('//*/div[@class="bookimage"]/a/img/@src')),
        'book_link': ''.join(dom.xpath('//*/div[@class="bookimage"]/a/@href')),
        'title': ''.join(dom.xpath('//h1/text()')).replace('::', '  ').strip(),
        'autor': ''.join(dom.xpath('//h1/a/text()')).strip(),
        'comments': dom.xpath('//*/div[@class="texts"]/span[@class="black"]/text()'),
        'genre': dom.xpath('//*/span[@class="d_book"]/a/text()'),
    }


def parse_rubric_limits(response):
    dom = etree.HTML(str(response.content))
    current = ''.join(dom.xpath('//*/div[@id="content"]/*/span[@class="npage_select"]/b/text()'))
    maxnum = ''.join(dom.xpath('//*/div[@id="content"]/*/a[@class="npage"]/text()')[-1:])
    max_page_num = max(int(current), int(maxnum)) if current.isdigit() and maxnum.isdigit() else 1
    books_per_page = len(dom.xpath('//*/div[@id="content"]/*/div[@class="bookimage"]/text()'))
    return {'max_page_num': max_page_num, 'book_per_page': books_per_page}


def parse_rubric_page(response):
    selector="table.tabs #content"
    content_block = BeautifulSoup(response.content, 'lxml').select(selector)
    dom = etree.HTML(str(content_block))
    book_bloks = dom.xpath('//*/table[@class="d_book"]')
    books = [{'book_link': ''.join(book.xpath('tr/td/div[@class="bookimage"]/a[starts-with(@href,"/b")]/@href')),
              'img_link': ''.join(book.xpath('tr/td/div[@class="bookimage"]/a/img/@src')),
              }
             for book in book_bloks
             ]
    return ({'books': books})


def download_book(book_link, rewrite=False):
    book = parse_book_page(get_response(book_link))
    if not book["text_link"]:
        return {}
    book_filepath = os.path.join(LIB_DIR, TEXTS_SUBDIR, sanitize_filename(f'{book["title"]}.txt'))
    if not os.path.exists(book_filepath) or not rewrite:
        download_file(f'{ROOT_URL}{book["text_link"]}', book_filepath)
    img_filename = urlparse(ROOT_URL + book['img_link']).path.split('/')[-1]
    img_filepath = os.path.join(LIB_DIR, IMAGES_SUBDIR, sanitize_filename(f'{img_filename}'))
    if not os.path.exists(img_filepath) or not rewrite:
        download_file(f'{ROOT_URL}{book["img_link"]}', img_filepath)
    return {book['book_link']: {
        'title': book['title'],
        'autor': book['autor'],
        'img_src': img_filepath,
        'book_path': book_filepath,
        'comments': book['comments'],
        'genre': book['genre']
    }}


def create_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('start_page', nargs='?', default=1, type=int)
    parser.add_argument('end_page', nargs='?', default=4, type=int)
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args(sys.argv[1:])
    if args.end_page <= args.start_page:
        args.end_page = args.start_page
        print(f'скачивание книг со страницы {args.start_page}')
    else:
        print(f'скачивание книг со страниц от {args.start_page} до {args.end_page}')
    os.makedirs(os.path.join(LIB_DIR, TEXTS_SUBDIR), exist_ok=True)
    os.makedirs(os.path.join(LIB_DIR, IMAGES_SUBDIR), exist_ok=True)
    url = f'{ROOT_URL}{TARGET_RUBRIC_URL}'
    # url='https://tululu.org/l74/'
    json_path = os.path.join(LIB_DIR, 'catalog.json')
    if os.path.exists(json_path) and os.path.isfile(json_path):
        with open(json_path, 'r') as file:
            catalog = json.load(file)
    else:
        catalog = {}
    start_page = args.start_page
    end_page = args.end_page
    progressbar=tqdm(total=(end_page - start_page + 1) * 25)
    for page in range(start_page, end_page + 1):
        response = get_response(f'{url}{page}')
        for book in parse_rubric_page(response)['books']:
            try:
                catalog.update(download_book(f'{ROOT_URL}{book["book_link"]}'))
            except requests.exceptions.HTTPError:
                pass
            progressbar.update(1)
    progressbar.close()
    if len(catalog) > 0:
        with open(json_path, 'w') as file:
            json.dump(catalog, file, ensure_ascii=False, indent=2)
    print('*** работа завершена ***')

if __name__ == '__main__':
    main()
