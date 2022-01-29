import argparse
import json
import os
import sys
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
JSON_PATH = ''


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


def parse_book_page(response):
    selector = ".tabs #content"
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
    selector = "table.tabs #content"
    content_block = BeautifulSoup(response.content, 'lxml').select(selector)
    dom = etree.HTML(str(content_block))
    book_bloks = dom.xpath('//*/table[@class="d_book"]')
    books = [{'book_link': ''.join(book.xpath('tr/td/div[@class="bookimage"]/a[starts-with(@href,"/b")]/@href')),
              'img_link': ''.join(book.xpath('tr/td/div[@class="bookimage"]/a/img/@src')),
              }
             for book in book_bloks
             ]
    return {'books': books}


def download_book(book_link, rewrite=False, skip_txt=False, skip_img=False):
    book = parse_book_page(get_response(book_link))
    if not book["text_link"]:
        return {}
    book_filepath = os.path.normcase(os.path.join(LIB_DIR, TEXTS_SUBDIR, sanitize_filename(f'{book["title"]}.txt')))
    if not skip_txt and (not os.path.exists(book_filepath) or not rewrite):
        download_file(f'{ROOT_URL}{book["text_link"]}', book_filepath)
    img_filename = urlparse(ROOT_URL + book['img_link']).path.split('/')[-1]
    img_filepath = os.path.normcase(os.path.join(LIB_DIR, IMAGES_SUBDIR, sanitize_filename(f'{img_filename}')))
    if not skip_img and (not os.path.exists(img_filepath) or not rewrite):
        download_file(f'{ROOT_URL}{book["img_link"]}', img_filepath)
    return {book['book_link']: {
        'title': book['title'],
        'autor': book['autor'],
        'img_src': img_filepath,
        'book_path': book_filepath,
        'comments': book['comments'],
        'genre': book['genre']
    }}


parser = argparse.ArgumentParser()


def arg_dest_folder(path):
    global LIB_DIR
    path = os.path.normcase(path)
    if LIB_DIR != path:
        LIB_DIR = path


def arg_json_path(path):
    global JSON_PATH
    if os.path.splitext(path)[1] != '.json':
        parser.error("тип файла длжен быть .json")
    path = os.path.normcase(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    JSON_PATH = path
    return path


def parser_addargs():
    parser.add_argument('--start_page', type=int, default=1)
    parser.add_argument('--end_page', type=int, default=9999)
    parser.add_argument('--skip_imgs', action='store_true')
    parser.add_argument('--skip_txt', action='store_true')
    parser.add_argument('--dest_folder', type=arg_dest_folder)
    parser.add_argument('--json_path', type=arg_json_path)


def main():
    global JSON_PATH
    url = f'{ROOT_URL}{TARGET_RUBRIC_URL}'
    limits = parse_rubric_limits(get_response(url))
    parser_addargs()
    args = parser.parse_args(sys.argv[1:])
    if args.end_page > limits['max_page_num']:
        args.end_page = limits['max_page_num']
    if args.end_page <= args.start_page:
        args.end_page = args.start_page
        print(f'скачивание книг со страницы {args.start_page}')
    else:
        print(f'скачивание книг со страниц от {args.start_page} до {args.end_page}')
    os.makedirs(os.path.join(LIB_DIR, TEXTS_SUBDIR), exist_ok=True)
    os.makedirs(os.path.join(LIB_DIR, IMAGES_SUBDIR), exist_ok=True)
    if not JSON_PATH:
        JSON_PATH = os.path.join(LIB_DIR, 'catalog.json')
    if os.path.exists(JSON_PATH) and os.path.isfile(JSON_PATH):
        with open(JSON_PATH, 'r') as file:
            catalog = json.load(file)
    else:
        catalog = {}
    start_page = args.start_page
    end_page = args.end_page
    progressbar = tqdm(total=(end_page - start_page + 1) * 25)
    for page in range(start_page, end_page + 1):
        response = get_response(f'{url}{page}')
        for book in parse_rubric_page(response)['books']:
            try:
                catalog.update(
                    download_book(f'{ROOT_URL}{book["book_link"]}',
                                  skip_txt=args.skip_txt,
                                  skip_img=args.skip_imgs)
                )
            except requests.exceptions.HTTPError:
                pass
            progressbar.update(1)
    progressbar.close()
    if len(catalog) > 0:
        with open(JSON_PATH, 'w') as file:
            json.dump(catalog, file, ensure_ascii=False, indent=2)
    print('*** работа завершена ***')


if __name__ == '__main__':
    main()
