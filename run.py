
import time
import random
import itertools

import re

from datetime import timezone 
import datetime 

from urllib.parse import quote
from urllib.parse import quote_plus

print("init: reading parameters")
import json
config = dict()
config['readonly'] = False

with open('config-reddit.json') as f:
    config['reddit'] = json.load(f)

print("\tusername:",config['reddit']['username'],"\n\tuser agent:", config['reddit']['user_agent'])

if not config['readonly']:
    print("\tWARNING, we are not read-only, we will post messages!")


print("init: reddit API")
import praw
from praw.models import MoreComments

print("init: connecting reddit")
myusername = config['reddit']['username']
reddit = praw.Reddit(
    user_agent=config['reddit']['user_agent'],
    client_id=config['reddit']['client_id'], 
    client_secret=config['reddit']['client_secret'], 
    username=config['reddit']['username'], 
    password=config['reddit']['password'] 
)
# the subreddit we will monitor and reply to
subreddit = reddit.subreddit("france")
print('\twill monitor comments of reddits: ',subreddit.display_name)
# the subreddit we use to know if a term is frequent or not
allreddit = reddit.subreddit("france+news+europe")
print('\twill assess the popularity of terms using reddits: ',allreddit.display_name)
# our username
myprofile = reddit.redditor(config['reddit']['username'])
if myprofile.is_suspended:
    print('\toops, seems like my account is suspended o_O')
    quit()
if not myprofile.verified:
    print('\toops, seems like by profile is not verified')

print('\tcomment-karma:\t', myprofile.comment_karma,    '\t:-(' if myprofile.comment_karma < 0 else '\t:-)')
print('\ttotal karma:\t',   myprofile.total_karma,      '\t:-(' if myprofile.total_karma < 0 else '\t:-)')

print("init: connecting terms database")

import sqlite3
conn = sqlite3.connect('terms.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS rejected (word TEXT PRIMARY KEY, reason TEXT)''')
conn.commit()
c.execute('''SELECT COUNT(*) FROM rejected''')
print("\tthere are",c.fetchone()[0],"words blocked in database")
c.execute('''SELECT reason, COUNT(*) FROM rejected GROUP BY reason''')
for row in c.fetchall():
    print('\t\t',row[0],':\t',row[1])

from lru import LRU
cache_rejected = LRU(50000)
# fill in the cache with entries
c.execute('''SELECT * FROM rejected ORDER BY RANDOM() LIMIT ?''', (int(cache_rejected.get_size()*2/3),))
for row in c:
    cache_rejected[row[0]]=row[1]
print("\tloaded",len(cache_rejected),"items in cache")

def is_word_rejected_db(token):
    global c
    global stats
    global cache_rejected
    
    # first try the cache
    if token.lemma_ in cache_rejected:
        stats['words rejected db (cache)'] = stats['words rejected db (cache)'] + 1
        return cache_rejected[token.lemma_]
    if token.text in cache_rejected:
        stats['words rejected db (cache)'] = stats['words rejected db (cache)'] + 1
        return cache_rejected[token.text]
    
    #print("searching db for word",word)
    stats['words searched db'] = stats['words searched db'] + 1
    c.execute('SELECT * FROM rejected WHERE word=? OR word=? ', (token.lemma_,token.text,))
    row = c.fetchone()
    if row is None:
        return None    
    else:
        reason = row[1]
        # add to cache
        cache_rejected[word.lemma_] = reason
        #print("word ",word," is rejected in db because",reason)
        return reason

def add_word_rejected_db(word, reason):
    global c
    global cache_rejected
    # add to cache
    cache_rejected[word] = reason
    try:
        c.execute('INSERT INTO rejected VALUES (?,?)', (word, reason))
        conn.commit()
    except sqlite3.IntegrityError as e:
        print(e)
        pass


print("init: wiktionary database")
wiktionnaire_conn = sqlite3.connect('./sources/wiktionnaire/wiktionnaire.sqlite')
wiktionnaire_cursor = wiktionnaire_conn.cursor()
wiktionnaire_cursor.execute('''SELECT COUNT(*) FROM definitions''')
print("\tthere are",wiktionnaire_cursor.fetchone()[0],"definitions from wiktionnaire")

def get_word_wiktionnaire(word):
    global wiktionnaire_cursor
    wiktionnaire_cursor.execute('SELECT * FROM definitions WHERE title=?', (word,))
    row = wiktionnaire_cursor.fetchone()
    if row is None:
        return None    
    else:
        return dict(zip([c[0] for c in wiktionnaire_cursor.description], row))       


import mwparserfromhell

config_wiktionnaire = dict()
config_wiktionnaire['templates'] = dict('')
config_wiktionnaire['templates']['name2text'] = {'m':'_masculin_', 'f':'_féminin_', 'pron':'_pronom_'}
config_wiktionnaire['templates']['name2alloptions'] = set(['nom w pc'])
config_wiktionnaire['templates']['name2firstoptions'] = set(['w','petites capitales','pc'])
config_wiktionnaire['templates']['name2namewithparenthesis'] = set(['vieilli','désuet','ironique','négologisme','injure','péjoratif','vulgaire','familier','raciste','figuré'])

#search_word_wiktionnaire('palmipède')


print("init: loading spacy french models")
import spacy
# https://spacy.io/models/fr
#nlp = spacy.load("fr")
#nlp = spacy.load("fr_core_news_sm") => no word vectors...
nlp = spacy.load("fr_core_news_md")     # this model is big enough to have vectors

print("\tloaded",len(nlp.vocab.strings),"words, ",len(nlp.vocab.vectors), "vectors")

# install custom tokenizer
from spacy.tokenizer import Tokenizer

def custom_tokenizer(nlp):
    special_cases = {":)": [{"ORTH": ":)"}]}
    prefix_re = re.compile(r'''^[[("']''')
    suffix_re = re.compile(r'''[])"']$''')
    infix_re = re.compile(r'''[~\(\]/]''')
    simple_url_re = re.compile(r'''^https?://''')
    return Tokenizer(nlp.vocab, rules=special_cases,
                                prefix_search=prefix_re.search,
                                suffix_search=suffix_re.search,
                                infix_finditer=infix_re.finditer,
                                url_match=simple_url_re.match)

nlp.tokenizer = custom_tokenizer(nlp)
print("\tinstalled custom tokenizer")
#doc = nlp("voici un exemple de texte avec [un lien sur un mot compliqué](http://google.fr/complique) pour lequel le mot compliqué devrait être identifié. Oui, sans doute, pas peut-être !")
#print([t.text for t in doc]) # ['hello', '-', 'world.', ':)']

print("init: loading word frequency")
import wordfreq

print("init: wikipedia API")
import wikipedia
wikipedia.set_lang('fr')
# TODO shift to https://www.mediawiki.org/wiki/Manual:Pywikibot

wikipedia_blacklisted_categories = set(['informatique','commune','ébauche'])

# TODO académie française
# ici! https://www.cnrtl.fr/definition/gougnafier
# https://academie.atilf.fr/9/

print("init: urban dictionary")
import urbandictionary
urban_dictionnary_available = True
try:
    urbandictionary.define('amazing')
    print('\turban dictionary up and alive :-)')
except:
    print('\tunable to reach urban dictionary, we will continue without it :-/')
    urban_dictionnary_available = False

print("init: done\n\n")

# TODO adaptative frequency
# TODO introspection, vérifier résultat: mémoriser où on a posté, aller voir de temps en temps (les plus anciens?) messages et mettre à jour les votes


stats = dict()
stats['posts explored'] = 0
stats['comments parsed'] = 0
stats['words parsed'] = 0
stats['words rejected blacklist'] = 0
stats['words rejected linked'] = 0          # how many words were rejected because they were explained in a weblink already?
stats['words searched db'] = 0
stats['words rejected length'] = 0
stats['words rejected names'] = 0
stats['words rejected frequency'] = 0
stats['words rejected exclamation'] = 0
stats['words searched reddit'] = 0
stats['words rejected reddit'] = 0
stats['words rejected db'] = 0
stats['words rejected db (cache)'] = 0
stats['words searched'] = 0
stats['words searched wikipedia'] = 0
stats['words rejected wikipedia'] = 0
stats['words searched Urban Dictionary'] = 0
stats['words found wikipedia'] = 0
stats['words found Urban Dictionary'] = 0
stats['words without definition'] = 0

stats['words searched wiktionnaire'] = 0
stats['words found wiktionnaire'] = 0
stats['words rejected wiktionnaire'] = 0
stats['words defined wiktionnaire'] = 0

stats['replies possible'] = 0
stats['replies posted'] = 0
stats['ratelimit reddit reply'] = 0

blacklist = set([
                "upvote","upvoter",
                "downvote","downvoter",
                "crosspost","crossposter",
                'basvoté','basvote','hautvoter','hautvote',
                'flood','flooder',
                'imageboard',
                "viméo","vimeo",
                "despacito",
                "covid","déconfinement","chloroquinine","reconfinement","confinement"
                ])

accentspossibles = dict()
accentspossibles['a'] = ['a','à','ä']
accentspossibles['e'] = ['e','é','è','ê','ë']
accentspossibles['è'] = ['è','é','e','ê']
accentspossibles['é'] = ['é','è','e','ê']
accentspossibles['i'] = ['i','î','ï','y']
accentspossibles['î'] = ['î','i']
accentspossibles['o'] = ['o','ô','ö']
accentspossibles['u'] = ['u','ù','û','ü']
accentspossibles['y'] = ['y','ÿ','i']
accentspossibles['c'] = ['c','ç']

def combinaisons_diacritiques(word, changed=0):
    global accentspossibles
    cards = [len(accentspossibles.get(letter,[letter])) for letter in word]
    max_cards = max(cards)
    max_tests = max_cards ** 2 * len(word)
    # generate the lists of possible combinations
    possibilities = [ accentspossibles.get(letter,[letter]) for letter in word ]
    i = 0
    for combination in itertools.product(*possibilities):
        i = i + 1
        if i >= max_tests:
            break
        yield ''.join(combination)
    pass

consonnes_doublables = set(['n','r','m','t'])

def combinaisons_consonnes(word):
    global consonnes_doublables
    
    w = word.lower()
    dic = dict()
    for letter in consonnes_doublables:
        w = w.replace(letter+letter,letter)
        dic[letter] = [letter, letter+letter]
    
    possibilities = [ dic.get(letter,[letter]) for letter in w[:-1] ]
    
    for combination in itertools.product(*possibilities):
        yield ''.join(combination) + w[-1:]
    
    pass


#list(combinaisons_consonnes("maronnier"))


def zipf_frequency_of_combinaisons_lower_than(word, threshold):
    '''
    returns the first value having a zipf frequency exceeding the threshold,
    or the highest zipf frequency
    '''
    _max = 0
    #print('\nzipf frequency of',word,'?') #élèment            
    for d1 in combinaisons_consonnes(word.lower()):
        for d in combinaisons_diacritiques(d1): 
            #print(d, end=' ')
            f = wordfreq.zipf_frequency(d,'fr')
            if f >= threshold:
                return f
            if f > _max:
                _max = f
    #print()
    return _max


def wait(seconds):
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        return

def reddit_results_highter_than(word, threshold):
    '''
    returns the threshold if there are that many answers in reddit,
    of the count of answers
    '''
    global subreddit
    global allreddit
    global stats
    stats['words searched reddit'] = stats['words searched reddit'] + 1
    print("searching reddit", word)
    results = allreddit.search(word, syntax='plain') # TODO search french first?
    count = 0;
    for res in results:
        count = count + 1
        if count >= threshold:
            print("\tterm",word,"found more than",threshold,"times")
            return threshold
    print("\tterm",word,"found ",count,"times")
    return count


def substitute_wiki_with_reddit(txt):
    
    result = txt
    
    # replace bold+italic
    result = result.replace("'''''","___")
    # replace bold
    result = result.replace("'''","__")
    # replace italic
    result = result.replace("''","_")
    
    return result

def format_wiktionnaire_definition_template_recursive(ast):
    
    global config_wiktionnaire
    
    for tl in ast.filter_templates(recursive=False):
        
        tl_name = str(tl.name)
        #print('processing template', tl_name)
        
        # replace content of templates with a constant text
        if tl_name in config_wiktionnaire['templates']['name2text']:
            ast.replace(tl, config_wiktionnaire['templates']['name2text'][tl_name])
        
        # replace tags starting or finishing with something by their content 
        elif tl_name.endswith('rare') or tl_name.startswith('argot') or tl_name in config_wiktionnaire['templates']['name2namewithparenthesis']:
            ast.replace(tl, '_('+tl_name+')_')
        
        # replace content of source
        elif tl_name == 'source':
            ast.replace(tl, ' ^('+str(format_wiktionnaire_definition_template_recursive(tl.params[0].value))+')')
        
        # replace with the content of the first option
        elif tl_name in config_wiktionnaire['templates']['name2firstoptions']:
            ast.replace(tl, str(format_wiktionnaire_definition_template_recursive(tl.params[0].value)))
        
        # replace with name:option[0]
        elif tl_name in set(['ISBN']):
            ast.replace(tl, tl_name+':'+str(format_wiktionnaire_definition_template_recursive(tl.params[0].value)))
        
        # replace template with the concatenation of all the options
        elif tl_name in config_wiktionnaire['templates']['name2alloptions']:
            ast.replace(tl, ' '.join( str(format_wiktionnaire_definition_template_recursive(p.value)) for p in tl.params ) )
        
        # remplace Citations
        elif tl_name.startswith('Citation'):
            tokens = tl_name.split('/')
            ast.replace(tl, tokens[1]+', _'+tokens[2]+'_, '+tokens[3])
        
        # by default, entirely remove the template
        else:
            ast.remove(tl)
            print('mediawiki: ignoring template', tl_name)
    
    return ast


def format_wiktionnaire_definition(definition):
    global config_wiktionnaire
    
    result = ''
    
    ast = mwparserfromhell.parse(definition, skip_style_tags=True)
    
    # replace any comment
    for wc in ast.filter_comments():
        ast.remove(wc)
    
    # process style
    
    # process templates
    format_wiktionnaire_definition_template_recursive(ast)
    
    # process links
    for wl in ast.filter_wikilinks(recursive=False):
        ast.replace(wl, str(wl.title if wl.text is None else wl.text))
    
    # transform AST into text
    result = str(ast)
    
    # replace italics, bold and co
    result = substitute_wiki_with_reddit(result)
    
    # replace enumerations and examples
    toprocess = result
    result = ''    
    current_enumeration = 0
    before = None
    for letter in toprocess:
        # treat enumerations and examples                
        if letter == '*' and before is not None and before == '#':
            # we are in an example
            result = result + '\n  - '
        elif before == '#' and letter.isspace():
            current_enumeration = current_enumeration + 1
            result = result + '\n'+str(current_enumeration)+'. '
        elif not letter in set(['#']):
            result = result + letter 
        before = letter
    
    return result


deftest = """{{fr-rég|}}
'''laudation''' {{pron||fr}} {{f}}
# {{rare|fr}} louange|Louange, éloge.
#* ''Il est vraisemblable que, lors de la '''laudation''' que nous venons de rapporter, Girard de Cossonay n’était plus vivant.'' {{source|''Mémoires et documents'', Société d’histoire de la Suisse romande, 1858}}
"""
#print(format_wiktionnaire_definition(deftest))



deftest = """{{fr-rég|pa.ne.ʒi.ʁik}}
'''panégyrique''' {{pron|pa.ne.ʒi.ʁik|fr}} {{m}}
# [[discours|Discours]] [[public]] [[faire|fait]] à la [[louange]] de [[quelqu’un]] ou de [[quelque chose]], [[éloge]].
#* ''Ô crime ! ô honte ! La tribune du peuple français a retenti du '''panégyrique''' de Louis XVI ; nous avons entendu vanter les vertus et les bienfaits du tyran !'' {{source|{{w|Maximilien Robespierre}}, ''Sur le parti de prendre à l’égard de Louis XVI'', novembre 1792}}
#* ''L’un célébrait les louanges d’Athelsthane dans un '''panégyrique '''lugubre ; un autre redisait, dans un poème généalogique en langue saxonne, les noms étrangement durs et sauvages de ses nobles ancêtres.'' {{source|{{Citation/Walter Scott/Ivanhoé/1820}}}}
#* ''Pendant que des regrets unanimes se formulaient à la Bourse, sur le port, dans toutes les maisons ; quand le '''panégyrique''' d’un homme irréprochable, honorable et bienfaisant, remplissait toutes les bouches, Latournelle et Dumay, […], vendaient, réalisaient, payaient et liquidaient.'' {{source|{{Citation/Honoré de Balzac/Modeste Mignon/1855}}}}
#* ''Un colonel ventripotent lit, trémolos dans la voix, un '''panégyrique''' de l’État ouvrier et paysan.'' {{source|{{nom w pc|Olivier|Guez}} et {{nom w pc|Jean-Marc|Gonin}}, ''{{w|La Chute du Mur}}'', {{w|Le Livre de Poche}}, 2011, {{ISBN|978-2-253-13467-1}}}}
"""
#print(format_wiktionnaire_definition(deftest))

deftest = """{{fr-rég|ɲuf}}
'''gnouf''' {{pron|ɲuf|fr}} {{m}}
# {{argot|fr}} {{lexique|prison|fr}} [[prison|Prison]], poste de [[police]].
#* ''C’est tellement vite fait de se retrouver au '''gnouf''' !'' {{source|[[w:Jean Guy Le Dano|Jean Guy Le Dano]], ''La mouscaille'', Flammarion, 1973, page 69}}
#* ''Arrivé dans un garage soupçonné de carambouilles, au moment d’une rafle organisée par la police, il a été embarqué sans discernement, allez, tout le monde au '''gnouf''' !'' {{source|Jean Raje, ''L’encabané, au pays du droit des hommes'', Société des Écrivains, 2007, page 30}}
# {{argot militaire|fr}} {{en particulier}} Prison [[militaire]].
#* ''Jeannet, dans son dernier mois de service, s'était fait arracher ses brisques et mettre au '''gnouf''' après une altercation avec son capitaine.'' {{source|{{w|Hervé Bazin}}, {{w|''Cri de la chouette''}}, Grasset, 1972, réédition Le Livre de Poche, page 93}}"""

#print(format_wiktionnaire_definition(deftest))

deftest = """{{fr-r\u00e9g|\u0281a.s\u0254}}\n'''rasso''' {{pron|\u0281a.s\u0254|fr}} {{m}}\n# [[rassemblement|Rassemblement]] d\u2019amateurs de [[tuning]].\n#* ''Les rassemblements (ou \u00ab '''rassos''' \u00bb) occupent les parkings des hypermarch\u00e9s les soirs de week-end : on s\u2019y rencontre entre amateurs pour \u00e9changer pi\u00e8ces, bons plans et conseils, et pour s\u2019\u00e9clater entre potes.'' {{source|St\u00e9phanie {{pc|Maurice}}, ''La passion du tuning'', Seuil, 2015, coll. Raconter la vie, page 8}}"""

#print(format_wiktionnaire_definition(deftest))



def search_word_wiktionnaire(comment, word):
    
    global stats

    print('searching wiktionnaire', word)
    stats['words searched wiktionnaire'] = stats['words searched wiktionnaire'] + 1

    info = get_word_wiktionnaire(word)

    # if not in Wiktionary
    if info is None:
        return (False, None, None)

    stats['words found wiktionnaire'] = stats['words found wiktionnaire'] + 1
    print('\t',json.dumps(info, sort_keys=True, indent=4))

    # if the definition is too short, reject
    if len(info['bloc_definition']) <= 150:
        return (False, None, None)        

    # if too many definitions, blacklist (too much uncertainty)
    if info['count_definitions'] >= 5:
        add_word_rejected_db(word, "too many definitions in wiktionary")
        print('\trejecting,',word,'too many definition (',str(info['count_definitions'])+') in wiktionnaire')
        stats['words rejected wiktionnaire'] = stats['words rejected wiktionnaire'] + 1
        return (True, None, None)

    if info['injure'] or info['raciste']:
        stats['words rejected wiktionnaire'] = stats['words rejected wiktionnaire'] + 1
        print('this comment contains injurial stuff:\n',comment.body)
        print('\trejecting,',word,'is defined as injurial in wiktionnaire')
        add_word_rejected_db(word, "defined as injurial in wiktionary")
        return (True, None, None)

    if info['sigle']:
        add_word_rejected_db(word, "defined as a sigle in wiktionary")
        print('\trejecting,',word,'is defined as a sigle in wiktionnaire')
        stats['words rejected wiktionnaire'] = stats['words rejected wiktionnaire'] + 1
        return (True, None, None)
    
    # how many points from various indicators?
    points = max(0, 6 - info['count_traductions'])**2 + max(0, 6 - info['count_synonymes']) + max(0, 4 - info['count_derives'])**2 + max(0, 4 - info['count_paronymes'])**2 
    print('=> points ',points)
    
    # if the word is of interest, use it :-)
    if info['argot'] or info['desuet'] or info['vieilli'] or info['rare'] or info['ironique'] or info['familier'] or info['count_traductions'] <= 5:
        # upvote the comment :-)
        comment.upvote()
        stats['words defined wiktionnaire'] = stats['words defined wiktionnaire'] + 1
        explanation = info['bloc_definition']
        explanation = format_wiktionnaire_definition(explanation)
        
        # forge source
        source = '[Wiktionnaire](https://fr.wiktionary.org/wiki/'+quote(info['title'])+')'        
        return (False, explanation, source)
    
    # return nothing
    return (False, None, None)


blacklisted_wikipedia = ['jeu', 'application', 'marque']

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



def search_urban_dictionary(token):
    global stats
    global urban_dictionnary_available

    # maybe we just cannot use it?
    if not urban_dictionnary_available:
        return (False, None, None)
    
    print("searching Urban Dictionary for ",token.lemma_)
    stats['words searched Urban Dictionary'] = stats['words searched Urban Dictionary'] + 1
    try:
        blocksearch = False
        searched = token.lemma_.lower()
        defs = urbandictionary.define(searched)
        if len(defs)> 0 :
            best = defs[0] 
            for d in defs:
                if 'interjection' in d.definition or 'exclamation' in d.definition:
                    # Urban Dictionary has at least one definition saying this is an exclamation or interjection. We reject the word on this basis
                    blocksearch = True
                    stats['words rejected exclamation'] = stats['words rejected exclamation'] + 1
                    add_word_rejected_db(token.lemma_, "is interjection or exclamation for Urban Dictionary")
                    return (True, None, None)
                if not d.word.lower().startswith(searched):
                    # this proposal is not 
                    continue
                print(d)
                if (d.upvotes - d.downvotes) > (best.upvotes - best.downvotes):
                    best = d
            if not blocksearch and best.word.lower().startswith(searched) and best.upvotes - best.downvotes > 20 and best.upvotes > 100: # enough votes for interest 
                pattern = re.compile('\[([\w]+)\]')
                definition = pattern.sub('[\\1](https://www.urbandictionary.com/define.php?term=\\1)', best.definition)
                explanation = best.word + ': ' + definition # best.example
                source = '[Urban Dictionary](https://www.urbandictionary.com/define.php?term='+quote(best.word)+')'
                stats['words found Urban Dictionary'] = stats['words found Urban Dictionary'] + 1
                return (False, explanation, source) 
    except KeyError as e:
        print("\terror with Urban Dictionary", e)
    except urllib.error.URLError as e:
        print("\tunable to connect Urban Dictionary", e)         
    return (False, None, None)


def find_definitions_in_submission(comment):
    global c
    global blacklist
    global reddit
    global config
    global stats
    print('.', end='', flush=True)
    body = comment.body
    # tokenisation: split the string into tokens
    nbsearched = 0
    openings = 0
    openings_links = 0
    inquote = False
    url_count = 0
    doc = nlp(body)
    words_in_urls = set()
    for token in doc:
        #print(token.text)
        # avoid providing definitions when there were links in the 
        if token.like_url:
           url_count = url_count + 1
        # do not search in the web links 
        if token.is_punct:
            # do detect links & parenthesis
            if token.text in ['(','[']:
                openings = openings + 1
            elif token.text in [')',']']:
                openings = openings - 1
            if token.text == '[':
                openings_links = openings_links + 1
                #print("=> open link !")
            elif token.text == ']':
                openings_links = openings_links - 1
                #print("=> close link !")
        
        # if we are between parenthesis or brackets then just pass
        if openings_links > 0 and token.is_alpha:
            # add the words in the link so we don't redefine something defined already
            words_in_urls.add(token.text.lower())
            #print('words linked in urls',words_in_urls)
            continue

        # do not search in quotes
        if token.is_sent_start:
            if token.text.startswith('>'):
                inquote = True
                #print('start of a quote block!')
            elif inquote:
                inquote = False
                #print('end of a quote block!')
        if inquote:
            continue

        # pass what is not words
        if token.is_space or token.is_punct or token.is_stop or not token.is_alpha or token.like_url:
            continue
        
        stats['words parsed'] = stats['words parsed'] + 1

        # length?
        if len(token.text) < 4:
            stats['words rejected length'] = stats['words rejected length'] + 1
            continue
        
        # blacklist?
        if token.text.lower() in blacklist or token.lemma_.lower() in blacklist:
            stats['words rejected blacklist'] = stats['words rejected blacklist'] + 1
            continue
        
        # was it explained already?
        if token.text.lower() in words_in_urls:
            stats['words rejected linked'] = stats['words rejected linked'] + 1
            continue
        # db
        # TODO: search for what? lemma, text, lower???
        reason = is_word_rejected_db(token)
        if reason is not None:
            stats['words rejected db'] = stats['words rejected db'] + 1
            continue

        # pass names
        if token.tag_ == 'PERSON' or token.tag_.startswith('PROPN'):
            stats['words rejected names'] = stats['words rejected names'] + 1
            add_word_rejected_db(token.lemma_, "word is a Name")
            continue
        
        # only keep the less frequent words
        zf = zipf_frequency_of_combinaisons_lower_than(token.lemma_, 1.5)
        if zf >= 1.5: 
            stats['words rejected frequency'] = stats['words rejected frequency'] + 1
            add_word_rejected_db(token.lemma_, "zipf frequency > 1.5")
            continue
        zf = max(zf, zipf_frequency_of_combinaisons_lower_than(token.text, 1.5))
        if zf >= 1.5: 
            stats['words rejected frequency'] = stats['words rejected frequency'] + 1
            add_word_rejected_db(token.lemma_, "zipf frequency > 1.5")
            continue
        # ignorons les anglicismes
        zf_en = max(wordfreq.zipf_frequency(token.text,'en'), wordfreq.zipf_frequency(token.lemma_,'en'))
        if zf_en >= 1.5:
            stats['words rejected frequency'] = stats['words rejected frequency'] + 1
            add_word_rejected_db(token.lemma_, "en zipf frequency > 1.5")
            continue

        print('\n')
        # ignorons les termes fréquents sur reddit
        count_reddit = reddit_results_highter_than(token.lemma_, 10)
        if count_reddit >= 5:
            stats['words rejected reddit'] = stats['words rejected reddit'] + 1
            add_word_rejected_db(token.lemma_, "more than 10 reddit results")
            continue
        
        # gather information from our corpus
        lexeme = nlp.vocab[token.lemma_]
        print("\nsearching for ", token.text, ", lemma:", token.lemma_, "has_vector=", lexeme.has_vector, ", vector_norm=", lexeme.vector_norm, ", tag=", token.tag_)
        stats['words searched'] = stats['words searched'] + 1
        nbsearched = nbsearched + 1
        explanation = None
        source = None
        blocksearch = False # if true, stop searching for it because we have a good reason to think it is bad

        # search wiktionnaire first (it is local and precise)
        (blocksearch, explanation, source) = search_word_wiktionnaire(comment, token.text)
        if not blocksearch and explanation is None and token.text.lower() != token.lemma_.lower():
            (blocksearch, explanation, source) = search_word_wiktionnaire(comment, token.lemma_)

        # search Wikipedia for the token
        if not blocksearch and explanation is None:
            (blocksearch, explanation, source) = search_wikipedia(token.text)
        if not blocksearch and explanation is None and token.text.lower() != token.lemma_.lower():
            (blocksearch, explanation, source) = search_wikipedia(token.lemma_)

        # search Urban Dictionary
        if not blocksearch and explanation is None:
            (blocksearch, explanation, source) = search_urban_dictionary(token)
        
        if explanation is not None:
             print('\n\n', ''.join(['https://reddit.com',comment.permalink]), '\n', '_________________________________________________________\n\n', body, '\n\n---------------------------------------\n\n')
             qualif = random.choice(['très rare','peu connu']) if lexeme.vector_norm == 0 else random.choice(['plutôt rare','assez rare','peu courant','inusité'])
             txt = ''
             if len(body) > len(token.sent.text)*2:
                # this is a long message, let's quote the sentence
                txt = txt + '> '+token.sent.text.replace('\n','\n> ')+'\n\n'
             txt = txt + '*'+token.text+'* est un mot '+qualif+' en Français ! J\'en ai '+random.choice(['trouvé','déniché'])+' une définition sur '+source+':\n\n'
             txt = txt + explanation + '\n\n'
             txt = txt + '^(Je suis [un bot](https://github.com/samthiriot/bot.reddit.bonmots) bienveillant mais en apprentissage; répondez-moi si je me trompe, mon développeur surveille les messages.)'
             print(txt,'\n\n')
             stats['replies possible'] = stats['replies possible'] + 1 
             publish = not config["readonly"]
             if publish:
                # first let the user confirm
                print("\n\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n")
                try:                 
                     while True:
                        val = input("publish? YES, never or no: ").strip()
                        if val == "YES":
                            print("=> publishing :D")
                            break
                        elif val == 'never':
                            print("blacklisting", token.text)
                            add_word_rejected_db(token.text, "manually blacklisted")
                            publish = False 
                            break
                        elif val == 'no':     
                            publish = False
                            comment.save() # avoids to propose it again
                            break
                        print('?')
                except KeyboardInterrupt:
                    print("=> canceled")
                    publish = False
             if publish:
                 while True:
                    try:
                        comment.save() # avoids to comment it again
                        myanswer = comment.reply(txt)
                        print("OMG I commented! ", myanswer)
                        break
                    except praw.exceptions.APIException as e:
                        if not 'RATELIMIT' in str(e):
                            raise e
                        stats['ratelimit reddit reply'] = stats['ratelimit reddit reply'] + 1
                        print(e)
                        err = str(e)
                        idx1 = err.find("dans ")
                        idx2 = err.find("minute", idx1+4)
                        seconds = 0
                        if idx2 > 0:
                            seconds = int(err[idx1+5:idx2]) * 60 + 3
                        else:
                            idx2 = err.find("second", idx1+4)
                            seconds = int(err[idx1+5:idx2])+1
                        # try to identify how long it should take
                        print(reddit.auth.limits)
                        print("waiting",seconds,"s ... (Ctrl+C to skip this post)")
                        wait(seconds)
                 stats['replies posted'] = stats['replies posted'] + 1

             return True # break and stop searching
        elif not blocksearch:
            # we found no definition
            add_word_rejected_db(token.lemma_, "no definition found")
            stats['words without definition'] = stats['words without definition'] + 1

        # do not search too much on one given post
        if nbsearched > 20:
             break

    # we did not commented anything
    return False


dt = datetime.datetime.now() 
utc_time = dt.replace(tzinfo = timezone.utc) 
utc_timestamp = utc_time.timestamp() 

def parse_comment(comment):
    global utc_timestamp
    global myusername
    global stats
    if isinstance(comment, MoreComments):
        return
    # skip if moderated
    if comment.locked or comment.archived or comment.collapsed or (comment.banned_by is not None):
        return
    # skip all the comments which are downvoted
    if comment.score < 0:
        return
    # skip if too old
    age_days = int((utc_timestamp - comment.created_utc)/60/60/24)
    #print('age of the comment:',int((utc_timestamp - comment.created_utc)/60/60/24),'days')
    if age_days > 10:
        print('too old:',age_days,'days')
    elif comment.saved or (comment.author is not None and comment.author.name == myusername):
        # we probably worked on it already!
        return
    else:
        stats['comments parsed'] = stats['comments parsed'] + 1
        if find_definitions_in_submission(comment):
            return True
        
    # now explore the subcomments!
    for reply in comment.replies:    
        if isinstance(reply, MoreComments):
            continue
        if parse_comment(reply):
            return True
    # we did not commented
    return False


def process_submission(submission, i):
        
    global stats
    
    if submission.locked or submission.hidden or submission.quarantine or submission.num_comments==0:
        return
    
    print("\nTHREAD > ", submission.title,'(',submission.num_comments,'comments)')
    dt = datetime.datetime.now() 
    utc_time = dt.replace(tzinfo = timezone.utc) 
    utc_timestamp = utc_time.timestamp() 
    for comment in submission.comments:
        if parse_comment(comment):
            break
    
    i = i + 1
    if i%50 == 0:
        print('\n',stats,'\n')
        
    stats['posts explored'] = stats['posts explored'] + 1



if __name__ == "__main__":
    
    i = 0
    print('\nprocessing hot threads\n\n')
    for submission in subreddit.hot(limit=500):
        process_submission(submission, i)

    print('\n\n', stats,'\n\nprocessing hot threads\n\n')

    for submission in subreddit.stream.submissions():
        process_submission(submission, i)


