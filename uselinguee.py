
import requests
from urllib.parse import quote
from bs4 import BeautifulSoup
from lru import LRU

from stats import *

print("init: linguee usage")
# TODO test the service

stats['words searched linguee'] = 0

cache_linguee_html = LRU(500)

# TODO throttling
def fetch_html_linguee(word):
    global cache_linguee_html
    global stats
    
    word = word.strip().lower()
        
    # search cache first
    if word in cache_linguee_html:
        return cache_linguee_html[word]
    
    # forge query
    #url = 'https://www.linguee.com/french-english/translation/'+quote(word)+'.html'
    url = 'https://www.linguee.com/english-french/search?source=french&query='+quote(word)
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '3600',
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0'
        }
    # actual query
    stats['words searched linguee'] = stats['words searched linguee'] + 1
    req = requests.get(url, headers)
    # TODO deal with errors
    # save in cache
    cache_linguee_html[word] = req.content
    return req.content


def search_word_linguee(word):
    
    # retrieve html    
    html = fetch_html_linguee(word)
    
    # parse
    soup = BeautifulSoup(html, 'html.parser') # TODO lxml?
    
    #soup.find_all('table', id='result_table') 
    # find examples
    body = soup.find('tbody', class_='examples')
    if body is None:
        return 0
    examples = body.findChildren("tr" , recursive=False)
    
    return len(examples)



search_word_linguee('cassation')
search_word_linguee('réunionite')


