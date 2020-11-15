
import time
import random
import itertools

from datetime import timezone 
import datetime 

from urllib.parse import quote
from urllib.parse import quote_plus

print("init: reading parameters")
import json
config = dict()
config["readonly"] = True

with open('config-reddit.json') as f:
    config['reddit'] = json.load(f)
print("\tusername:",config['reddit']['username'],"\n\tuser agent:", config['reddit']['user_agent'])

print("init: reddit API")
import praw
from praw.models import MoreComments

print("init: connecting reddit")
myusername = config['reddit']['username']
reddit = praw.Reddit(
    user_agent=config['reddit']['user_agent'],
    client_id=config['reddit']['client_id'], #"-IiKLzm4x62h3w",
    client_secret=config['reddit']['client_secret'], #"pxBe1QxxjuM_MmTYTJfRPC3fMOCDyw",
    username=config['reddit']['username'], #"***REMOVED***",
    password=config['reddit']['password'] #"***REMOVED***"
)

print("init: connecting database")
import sqlite3
conn = sqlite3.connect('dictionary.db')
c = conn.cursor()

print("init: loading spacy french models")
import spacy
# https://spacy.io/models/fr
#nlp = spacy.load("fr")
#nlp = spacy.load("fr_core_news_sm") => no word vectors...
nlp = spacy.load("fr_core_news_md")

print("\tloaded",len(nlp.vocab.strings),"words, ",len(nlp.vocab.vectors), "vectors")

print("init: loading word frequency")
import wordfreq

print("init: wikipedia API")
import wikipedia
wikipedia.set_lang('fr')
# TODO shift to https://www.mediawiki.org/wiki/Manual:Pywikibot

print("init: wiktionary API")
from wiktionaryparser import WiktionaryParser
wiktionary = WiktionaryParser()
wiktionary.set_default_language('french')
#?parser.exclude_part_of_speech('noun')
#parser.include_relation('alternative forms')

# TODO académie française
# ici! https://www.cnrtl.fr/definition/gougnafier
# https://academie.atilf.fr/9/

print("init: urban dictionary")
import urbandictionary

print("init: done")

# TODO adaptative frequency
# TODO introspection, vérifier résultat: mémoriser où on a posté, aller voir de temps en temps (les plus anciens?) messages et mettre à jour les votes


stats = dict()
stats['posts explored'] = 0
stats['comments parsed'] = 0
stats['words parsed'] = 0
stats['words rejected blacklist'] = 0
stats['words rejected names'] = 0
stats['words rejected frequency'] = 0
stats['words rejected exclamation'] = 0
stats['words searched'] = 0
stats['words searched wikipedia'] = 0
stats['words searched wiktionary'] = 0
stats['words searched Urban Dictionary'] = 0
stats['words found wikipedia'] = 0
stats['words found wiktionary'] = 0
stats['words found Urban Dictionary'] = 0
stats['replies possible'] = 0
stats['replies posted'] = 0
stats['ratelimit reddit reply'] = 0

cache = dict()

blacklist = set([
                "upvote","upvoter",
                "downvote","downvoter",
                "crosspost","crossposter",
                "viméo","vimeo",
                "Despacito"])

accentspossibles = dict()
accentspossibles['a'] = ['a','à','ä']
accentspossibles['e'] = ['e','é','è','ê','ë']
accentspossibles['i'] = ['i','î','ï','y']
accentspossibles['o'] = ['o','ô','ö']
accentspossibles['u'] = ['u','ù','û','ü']
accentspossibles['y'] = ['y','ÿ','i']

def combinaisons_diacritiques(word):
    global accentspossibles
    possibilities = [ accentspossibles.get(letter,[letter]) for letter in word ]
    for combination in itertools.product(*possibilities):
        yield ''.join(combination)
    pass

def zipf_frequency_of_combinaisons_lower_than(word, threshold):
    '''
    returns the first value having a zipf frequency exceeding the threshold,
    or the highest zipf frequency
    '''
    _max = 0
    for d in combinaisons_diacritiques(word):
        f = wordfreq.zipf_frequency(d,'fr')
        if f >= threshold:
            return f
        if f > _max:
            _max = f
    return _max


def search_wikipedia(tok, sentences=1):
    global stats
    try:
        print("searching wikipedia for ", tok)
        explanation = wikipedia.summary(tok, sentences=sentences, auto_suggest=False, redirect=True)
        # a too short explanation might require more sentences
        if len(explanation) < 20:
            return search_wikipedia(tok, sentences=sentences+1)
        source = '[Wikipedia](https://fr.wikipedia.org/wiki/'+quote(tok)+')'
        stats['words found wikipedia'] = stats['words found wikipedia'] + 1
        return (explanation, source)
    except wikipedia.exceptions.DisambiguationError as e:
        # il y a plus solutions
        # TODO le plus intelligent serait de trouver la définition la plus pertinente d'après la proximité lexico
        # prenons déjà la première
        options = [ s for s in e.options if s != tok and len(s)>0]
        print('\tWikipedia en propose les définitions suivantes: ', e.options, 'et donc',options[0],'\n\n')
        for option in options:
            # certaines solutions mènent à des erreurs; on boucle et on prend la première solution qui ne plante pas
            try:
                explanation = wikipedia.summary(option, sentences=1, auto_suggest=False, redirect=True)
                source = '[Wikipedia](https://fr.wikipedia.org/wiki/'+quote(option)+')'
                stats['words found wikipedia'] = stats['words found wikipedia'] + 1
                return (explanation, source)
            except:
                pass
    except:
        pass
    return (None, None)


def search_wiktionary(searched):
    global stats
    while True:
        print("searching wiktionary for ",searched)
        defs = wiktionary.fetch(searched, 'french')
        if len(defs) > 0 and len(defs[0]['definitions']) > 0:
            # things detected as interjection lead to many, many useless definitions
            if defs[0]['definitions'][0]['partOfSpeech'] == 'interjection':
                blocksearch = True
                break
            defi = defs[0]['definitions'][0]['text']
            if defi[1].startswith('plural of '):
                searched = defi[10:]
                continue
            explanation = ':'.join(defs[0]['definitions'][0]['text'])
            source = 'Wiktionary'
            stats['words found wiktionary'] = stats['words found wiktionary'] + 1
            print(defs)
            return (explanation, source)
        break
    return (None, None)

def find_definitions_in_submission(comment):
    global cache
    global wiktionary
    global c
    global blacklist
    global reddit
    global config
    global stats
    body = comment.body
    # tokenisation: split the string into tokens
    nbsearched = 0
    doc = nlp(body)
    for token in doc:
        # pass what is not words
        if token.is_space or token.is_punct or token.is_stop or not token.is_alpha:
            continue
        
        stats['words parsed'] = stats['words parsed'] + 1
        if token.text in blacklist or token.lemma_ in blacklist:
            stats['words rejected blacklist'] = stats['words rejected blacklist'] + 1
            continue

        # TODO cache
        if token.text in cache:
            continue
        cache[token.text] = 'done'
        
        # pass names
        if token.tag_ == 'PERSON' or token.tag_.startswith('PROPN'):
            stats['words rejected names'] = stats['words rejected names'] + 1
            continue
        
        # only keep the less frequent words
        zf = zipf_frequency_of_combinaisons_lower_than(token.lemma_, 1.5)
        if zf >= 1.5: 
            stats['words rejected frequency'] = stats['words rejected frequency'] + 1
            continue
        zf = max(zf, zipf_frequency_of_combinaisons_lower_than(token.text, 1.5))
        if zf >= 1.5: 
            stats['words rejected frequency'] = stats['words rejected frequency'] + 1
            continue
        # ignorons les anglicismes
        zf_en = max(wordfreq.zipf_frequency(token.text,'en'), wordfreq.zipf_frequency(token.lemma_,'en'))
        if zf_en >= 1.5:
            stats['words rejected frequency'] = stats['words rejected frequency'] + 1
            continue
        # gather information from our corpus
        lexeme = nlp.vocab[token.lemma_]
        print("\nsearching for ", token.text, ", lemma:", token.lemma_, "has_vector=", lexeme.has_vector, ", vector_norm=", lexeme.vector_norm, ", tag=", token.tag_)
        stats['words searched'] = stats['words searched'] + 1
        nbsearched = nbsearched + 1
        explanation = None
        source = None
        blocksearch = False # if true, stop searching for it because we have a good reason to think it is bad

        # search Wikipedia for the token
        (explanation, source) = search_wikipedia(token.text)
        if not blocksearch and explanation is None and token.text.lower() != token.lemma_.lower():
            (explanation, source) = search_wikipedia(token.lemma_)
            stats['words searched wikipedia'] = stats['words searched wikipedia'] + 1

        # search Wiktionary
        # TODO réactiver - peut être
        #if not blocksearch and explanation is None:
        #    (explanation, source) = search_wiktionary(token.lemma_)
        #    stats['words searched wiktionary'] = stats['words searched wiktionary'] + 1

        # search Urban Dictionary
        # TODO isolate
        # TODO make all the isolated search return blocksearch
        if not blocksearch and explanation is None:
            print("searching Urban Dictionary for ",token.lemma_)
            stats['words searched Urban Dictionary'] = stats['words searched Urban Dictionary'] + 1
            try:
                searched = token.lemma_.lower()
                defs = urbandictionary.define(searched)
                if len(defs)> 0 :
                    best = defs[0] 
                    for d in defs:
                        if 'interjection' in d.definition or 'exclamation' in d.definition:
                            blocksearch = True
                            stats['words rejected exclamation'] = stats['words rejected exclamation'] + 1
                            break
                        if not d.word.lower().startswith(searched):
                            continue
                        print(d)
                        if (d.upvotes - d.downvotes) > (best.upvotes - best.downvotes):
                            best = d
                    if not blocksearch and best.word.lower().startswith(searched) and best.upvotes - best.downvotes > 20: # enough votes for interest 
                        explanation = best.word + ':' + best.definition # best.example
                        source = 'Urban Dictionary'
                        stats['words found Urban Dictionary'] = stats['words found Urban Dictionary'] + 1
            except KeyError as e:
                print("error with Urban Dictionary", e)
                
        
        if explanation is not None:
             print('_________________________________________________________\n\n', body, '\n\n---------------------------------------\n\n')
             qualif = random.choice(['très rare','peu connu']) if lexeme.vector_norm == 0 else random.choice(['plutôt rare','assez rare','peu courant','inusité'])
             txt = '*'+token.text+'* est un mot '+qualif+' en Français ! J\'en ai '+random.choice(['trouvé','déniché'])+' une définition sur '+source+':\n\n'+explanation
             print(txt,'\n\n')
             stats['replies possible'] = stats['replies possible'] + 1 
             if not config["readonly"]:
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
                            seconds = int(err[idx1+5:idx2]) * 60
                        else:
                            idx2 = err.find("second", idx1+4)
                            seconds = int(err[idx1+5:idx2])+1
                        # try to identify how long it should take
                        print(reddit.auth.limits)
                        print("waiting",seconds,"s ... (Ctrl+C to skip this post)")
                        try:
                            time.sleep(seconds)
                        except KeyboardInterrupt:
                            break
                 stats['replies posted'] = stats['replies posted'] + 1

             break # do not search any other term for the same post

        # do not search too much on one given post
        if nbsearched > 20:
             break

subreddit = reddit.subreddit("france")

dt = datetime.datetime.now() 
utc_time = dt.replace(tzinfo = timezone.utc) 
utc_timestamp = utc_time.timestamp() 

def parse_comment(comment):
    global utc_timestamp
    global myusername
    global stats
    # skip if moderated
    if comment.locked or comment.archived or comment.collapsed or (comment.banned_by is not None):
        return
    # skip all the comments which are downvoted
    if comment.score < 0:
        return
    # skip if too old
    age_days = (utc_timestamp - comment.created_utc)/60/60/24
    if age_days > 10:
        print('too old:',age_days,'days')
    elif comment.saved or (comment.author is not None and comment.author.name == myusername):
        # we probably worked on it already!
        return
    else:
        find_definitions_in_submission(comment)
        stats['comments parsed'] = stats['comments parsed'] + 1

    # now explore the subcomments!
    for reply in comment.replies:    
        if isinstance(reply, MoreComments):
            continue
        parse_comment(reply)


for submission in subreddit.stream.submissions():
#for submission in subreddit.hot(limit=40):
    if submission.locked or submission.hidden or submission.quarantine:
        continue
    print("THREAD > ", submission.title,'(',submission.num_comments,'comments)\n')
    dt = datetime.datetime.now() 
    utc_time = dt.replace(tzinfo = timezone.utc) 
    utc_timestamp = utc_time.timestamp() 
    for comment in submission.comments:
        parse_comment(comment)
    stats['posts explored'] = stats['posts explored'] + 1
    print('\n',stats,'\n')



