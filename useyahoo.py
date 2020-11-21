import time
import random

import requests
from urllib.parse import quote
from bs4 import BeautifulSoup
from lru import LRU


from stats import *
stats['words searched yahoo'] = 0

print("init: yahoo usage")
# TODO test the service

# TODO throttling

cache_yahoo_html = LRU(500)


lastquery_yahoo = 0

# TODO throttling
def fetch_html_yahoo(word, word2=None):
    global cache_yahoo_html
    global stats
    global lastquery_yahoo
    #word = word.strip().lower()
    
    # search cache first
    if word in cache_yahoo_html:
        return cache_yahoo_html[word]
    if word2 is not None and word != word2 and word2 in cache_yahoo_html:
        return cache_yahoo_html[word2]
    
    search = '"'+word+'"'
    if word2 is not None and word != word2:
        search = search + ' OR "'+word2+'"'
    # forge query
    url = 'https://fr.search.yahoo.com/search?p='+quote(search)+'&vl=lang_fr'
    #print(url)
    headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '3600',
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0'
        }
    # actual query
    stats['words searched yahoo'] = stats['words searched yahoo'] + 1
    print('\tsearching yahoo',search,' ',end='')
    # throttle
    time_since_last_query = int(time.time() - lastquery_yahoo)
    if time_since_last_query < 1:   
        delay = time_since_last_query+random.randint(0,2)
        #print('\tthrottling ',delay,'s')
        time.sleep(delay)
    lastquery_yahoo = time.time()
    req = requests.get(url, headers)
    # TODO deal with errors
    # save in cache
    cache_yahoo_html[word] = req.content
    if word2 is not None and word != word2:
        cache_yahoo_html[word2] = req.content
    return req.content


def search_word_yahoo(word, word2=None):
    
    # retrieve html    
    html = fetch_html_yahoo(word, word2)
    
    # parse
    soup = BeautifulSoup(html, 'html.parser') # TODO lxml?
    
    # find the count of results
    body = soup.find('div', class_='compPagination')
    if body is None:
        return 0
    spanCount = body.findChildren("span" , recursive=False)
    count = int(spanCount[0].text.split(' ')[0].replace(',',''))
    print('=>',count)
    return count


if search_word_yahoo('vidéate') > 6000 or search_word_yahoo('réunionite') < 20000:
    print('\tweird results from Yahoo, please double check them')
print('\tYahoo search is up!')

#search_word_yahoo('cassation')
#search_word_yahoo('réunionite')
#search_word_yahoo('vidéate')

