
import time
import random
import itertools

import re

from stats import *

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
subreddit = reddit.subreddit("france") # +zetetique+francophonie+jardin
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

from usedb import *


# load my past contributions
#print('loading our past contributions...')
#for comment in myprofile.comments.hot(limit=10000):
#    print('\t',comment.subreddit.display_name, comment.permalink)
#    remember_I_contributed(comment.subreddit.display_name, comment.submission.id, comment.parent_id, comment.id, None, None, comment.permalink)


from usewiktionnaire import *

from uselinguee import *
from useyahoo import *

print("init: loading spacy french models")
import spacy
# https://spacy.io/models/fr
#nlp = spacy.load("fr")
#nlp = spacy.load("fr_core_news_sm") => no word vectors...
#nlp = spacy.load("fr_core_news_md")     # this model is big enough to have vectors
nlp = spacy.load("fr_core_news_lg")     # ideal, as it has probabilities

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

# load our wikipedia code
from usewikipedia import *

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

from variations import * 



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
        
        count_linguee = search_word_linguee(token.lemma_)
        print('\tcount for linguee:',count_linguee)
        if count_linguee >= 5:
            print('\tword frequent in Linguee')
            # TODO add stat
            add_word_rejected_db(token.lemma_, "more than 5 Linguee results")
            continue
        
        count_yahoo = search_word_yahoo(token.lemma_, token.text)
        print('\tcount for yahoo:',count_yahoo)
        if count_yahoo >= 13000:
            print('\tword frequent in Yahoo')
            # TODO add stat
            add_word_rejected_db(token.lemma_, "more than 8000 Yahoo results")
            continue
        
        # gather information from our corpus
        lexeme = nlp.vocab[token.lemma_]
        l2norm = max(nlp.vocab[token.lemma_].vector_norm, nlp.vocab[token.text].vector_norm)
        print("\nsearching for ", token.text, ", lemma:", token.lemma_, "has_vector=", lexeme.has_vector, ", zf=",zf,", vector_norm=", l2norm, ", tag=", token.tag_)
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
             txt = txt + explanation + '\n\n___\n\n'
             txt = txt + '^(Je suis) ^[un](https://github.com/samthiriot/bot.reddit.bonmots) ^[bot](https://github.com/samthiriot/bot.reddit.bonmots) ^(bienveillant mais en apprentissage; répondez-moi si je me trompe, mon développeur surveille les messages.)'
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
                        source_simplified = '?'
                        if 'Wiktionnaire' in source:
                            source_simplified = 'wiktionnaire'
                        elif 'Wikipedia' in source:
                            source_simplified = 'wikipedia'
                        elif 'Urban Dictionary' in source:
                            source_simplified = 'urban dictionary'
                        
                        remember_I_contributed(comment.subreddit.display_name, comment.submission.id, comment.id, myanswer.id, token.text, source_simplified, myanswer.permalink)
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
        print(':', end='', flush=True)            
        return
    
    # do not explore any message we already contributed to
    if already_contributed_submission(comment.link_id):
        print('x',end='', flush=True)
        return

    # only parse the comment if I never did it in the past
    if alread_parsed_comment(comment.id):
        print('x',end='', flush=True)
    else:
        remember_I_parsed_comment(comment.id)
        
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
            print(',', end='')
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
            print(':', end='')
            continue
        if parse_comment(reply):
            return True
    # we did not commented
    return False


i = 0

def process_submission(submission):
        
    global stats
    global i
    
    if submission.locked or submission.hidden or submission.quarantine or submission.num_comments==0:
        return
    
    if already_contributed_submission(submission.id):
        return
    
    print("\nr/",submission.subreddit.display_name , " > ", submission.title,' (',submission.num_comments,' comments)',sep='')
    dt = datetime.datetime.now() 
    utc_time = dt.replace(tzinfo = timezone.utc) 
    utc_timestamp = utc_time.timestamp()
    # load all the "more comments" of the thread
    #print('!', end='')
    submission.comments.replace_more(limit=0)
    # parse all the comments    
    for comment in submission.comments:
        if parse_comment(comment):
            break
    
    i = i + 1
    if i%50 == 0:
        print('\n',stats,'\n')
        
    stats['posts explored'] = stats['posts explored'] + 1



if __name__ == "__main__":
    i=0
    print('\nprocessing hot threads\n\n')
    for submission in subreddit.rising(limit=1000): # rising #hot
        process_submission(submission)
    
    print('\n\n', stats,'\n\nprocessing comments\n\n')
    i=0
    for comment in subreddit.stream.comments():
        parse_comment(comment)
        # display stats from time to time
        i = i + 1
        if i%100 == 0:
            print('\n',stats,'\n')
     

# ne pas pas alors qu'aurait pu 
# 
# ancillaire: count for yahoo: 14800



