
from urllib.parse import quote

import wordfreq

from stats import *
from usedb import *

print("init: wikipedia API")
import wikipedia
wikipedia.set_lang('fr')
# TODO shift to https://www.mediawiki.org/wiki/Manual:Pywikibot

wikipedia_blacklisted_categories = set(['informatique','commune','ébauche'])

blacklisted_wikipedia = ['jeu', 'application', 'marque',
                        'personnalité','naissance','décès',
                        'actrice','acteur']


stats['words searched wikipedia'] = 0
stats['words rejected wikipedia'] = 0
stats['words found wikipedia'] = 0

def search_wikipedia(tok, sentences=1):
    global stats
    global blacklisted_wikipedia
    global wikipedia_blacklisted_categories
    #found = wikipedia.search("brantes")
    explanation = None
    source = None
    page_info = None
    try:
        print("searching wikipedia for ", tok)
        stats['words searched wikipedia'] = stats['words searched wikipedia'] + 1
        # load the page
        page_info = wikipedia.page(tok, auto_suggest=False, redirect=True) # TODO auto_suggest?
    except wikipedia.exceptions.DisambiguationError as e:
        # il y a plus solutions
        # TODO le plus intelligent serait de trouver la définition la plus pertinente d'après la proximité lexico
        # prenons déjà la première
        options = [ s for s in e.options if s != tok and len(s)>0]
        if len(options) > 0:
            print('\tWikipedia en propose les définitions suivantes: ', e.options, 'et donc la première:',options[0],'\n\n')
            for option in options:
                if len(option) < 3: 
                    continue
                # certaines solutions mènent à des erreurs; on boucle et on prend la première solution qui ne plante pas
                try:
                    page_info = wikipedia.page(option, auto_suggest=False, redirect=True)
                    tok = option
                    break
                except:
                    pass
    except:
        pass
    
    # we searched for definitions
    if page_info is None:
        # we did not found any definition...
        # TODO add to a Wikipedia cache so we don't query it again and again
        return (False, None, None)
    
    # so we found a page which seems of interest.
    # let's load more info about it
    
    # we have a title of a page. Is that word very common?
    if wordfreq.zipf_frequency(page_info.title,'fr') > 3 or wordfreq.zipf_frequency(page_info.title,'en') > 3:
        print("\twikipedia redirected",tok,"to",page_info.title, "which is very frequent")
        add_word_rejected_db(tok, "wikipedia redirects to a frequent word")
        return (True, None, None)
        
    # filter based on categories?
    for blacklisted_category in wikipedia_blacklisted_categories:
        if any(blacklisted_category in categorie.lower() for categorie in page_info.categories):
            print("\nthe wikipedia article ",page_info.title," is about ",blacklisted_category,", reject it")
            return (False, None, None)

    # load the summary   
    explanation = page_info.summary
    # emphasis the word defined
    explanation = explanation.replace(' '+tok+' ',' _'+tok+'_ ')
    # replace weird punctuation
    explanation = explanation.replace(', ,',',').replace(', :', ':').replace(',.','.').replace(',:',':')
    # skip lines visibly
    explanation = explanation.replace('\n','\n\n')

    source = '[Wikipedia](https://fr.wikipedia.org/wiki/'+quote(page_info.title)+')'
    
    # so we found a definition
    # a too short explanation might require more sentences
    if len(explanation) < 20:
        return search_wikipedia(tok, sentences=sentences+1)
    
    # do not accept several specific words
    if any(blacklisted_word in explanation.lower() for blacklisted_word in blacklisted_wikipedia):
        print("\n\n!!! rejected word",tok,"in wikipedia because it matches one of blacklisted concepts (",blacklisted_wikipedia,")\n\n")
        stats['words rejected wikipedia'] = stats['words rejected wikipedia'] + 1
        add_word_rejected_db(tok, "blacklisted concept in wikipedia")
        return (True, None, None)
    
    # we accept this definition and return it
    stats['words found wikipedia'] = stats['words found wikipedia'] + 1
    return (False, explanation, source)


