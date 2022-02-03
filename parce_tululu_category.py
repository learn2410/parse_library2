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

ROOT_URL = 'https://tululu.org'
TARGET_RUBRIC_URL = '/l55/'
LIB_DIR = 'library'
TEXTS_SUBDIR = 'books'
IMAGES_SUBDIR = 'images'


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
    selector = '.tabs #content'
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
    pag = ''.join(etree.HTML(str(response.content)).xpath('//*/div[@id="content"]/p[@class="center"]//text()')[-1:])
    return int(pag) if pag.isdigit() else 1


def parse_rubric_page(response):
    selector = 'table.tabs #content'
    content_block = BeautifulSoup(response.content, 'lxml').select(selector)
    dom = etree.HTML(str(content_block))
    book_bloks = dom.xpath('//*/table[@class="d_book"]')
    books = [{'book_link': ''.join(book.xpath('tr/td/div[@class="bookimage"]/a[starts-with(@href,"/b")]/@href')),
              'img_link': ''.join(book.xpath('tr/td/div[@class="bookimage"]/a/img/@src')),
              }
             for book in book_bloks
             ]
    return books


def download_book(book_link, txt_dir, img_dir, skip_txt=False, skip_img=False):
    book = parse_book_page(get_response(book_link))
    if not book['text_link']:
        return {}
    book_url = f'{ROOT_URL}{book["text_link"]}'
    book_filename = sanitize_filename(f'{book["title"]}.txt')
    book_filepath = os.path.normcase(os.path.join(txt_dir, book_filename))
    if not skip_txt:
        download_file(book_url, book_filepath)
    img_url = f'{ROOT_URL}{book["img_link"]}'
    img_filename = sanitize_filename(urlparse(img_url).path.split('/')[-1])
    img_filepath = os.path.normcase(os.path.join(img_dir, img_filename))
    if not skip_img:
        download_file(img_url, img_filepath)
    return {book['book_link']: {
        'title': book['title'],
        'autor': book['autor'],
        'img_src': img_filepath,
        'book_path': book_filepath,
        'comments': book['comments'],
        'genre': book['genre']
    }}


def main():
    url = f'{ROOT_URL}{TARGET_RUBRIC_URL}'
    limit = parse_rubric_limits(get_response(url))
    parser = argparse.ArgumentParser()
    parser.add_argument('--start_page', type=int, default=1)
    parser.add_argument('--end_page', type=int, default=9999)
    parser.add_argument('--skip_imgs', action='store_true')
    parser.add_argument('--skip_txt', action='store_true')
    parser.add_argument('--dest_folder')
    parser.add_argument('--json_path')
    args = parser.parse_args(sys.argv[1:])
    args.end_page = max(args.start_page, min(limit, args.end_page))
    print(f'скачивание книг со страниц от: {args.start_page} до {args.end_page}')
    root_dir = os.path.normcase(args.dest_folder) if args.dest_folder else LIB_DIR
    txt_dir = os.path.join(root_dir, TEXTS_SUBDIR)
    img_dir = os.path.join(root_dir, IMAGES_SUBDIR)
    if args.json_path:
        json_path = os.path.normcase(args.json_path)
        if os.path.splitext(json_path)[1] != '.json':
            json_path = json_path + '.json'
    else:
        json_path = os.path.join(root_dir, 'catalog.json')
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(txt_dir, exist_ok=True)
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    if os.path.exists(json_path) and os.path.isfile(json_path):
        with open(json_path, 'r') as file:
            catalog = json.load(file)
    else:
        catalog = {}
    print('--- составляю список книг со страниц')
    progressbar = tqdm(total=(args.end_page - args.start_page + 1))
    book_links = []
    for page in range(args.start_page, args.end_page + 1):
        progressbar.update(1)
        try:
            books = parse_rubric_page(get_response(f'{url}{page}'))
            book_links.extend(books)
        except requests.exceptions.HTTPError:
            pass
    progressbar.close()
    print('--- скачиваю книги')
    progressbar = tqdm(total=len(book_links))
    for book in book_links:
        progressbar.update(1)
        try:
            catalog.update(
                download_book(f'{ROOT_URL}{book["book_link"]}',
                              txt_dir,
                              img_dir,
                              skip_txt=args.skip_txt,
                              skip_img=args.skip_imgs
                              )
            )
        except requests.exceptions.HTTPError:
            pass
    progressbar.close()
    if len(catalog) > 0:
        with open(json_path, 'w') as file:
            json.dump(catalog, file, ensure_ascii=False, indent=2)
    print('*** работа завершена ***')


if __name__ == '__main__':
    main()
