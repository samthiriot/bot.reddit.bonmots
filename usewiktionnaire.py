import sqlite3
import json
from urllib.parse import quote

from stats import *

from usedb import *

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
config_wiktionnaire['templates']['name2text'] = {'m':'_masculin_', 'f':'_féminin_', 'pron':'_pronom_', 'néol':'(néologisme)'}
config_wiktionnaire['templates']['name2alloptions'] = set(['nom w pc'])
config_wiktionnaire['templates']['name2firstoptions'] = set(['w','ws','wq','wsp','petites capitales','pc'])
config_wiktionnaire['templates']['name2namewithparenthesis'] = set(['vieilli','désuet','ironique','néologisme','injure','péjoratif','vulgaire','familier','raciste','figuré','populaire'])

#search_word_wiktionnaire('palmipède')


def remove_nested_emphasis(text):
    
    result = ''
      
    italics = False
    bold = False
    
    for i in range(len(text)):
        letter = text[i]
        letter_ = text[i-1] if i-1 >= 0 else None
        letter__ = text[i-2] if i-2 >= 0 else None
        letter___ = text[i-3] if i-3 >= 0 else None
        
        if letter == '_':
            continue
        
        # ___
        if letter_=='_' and letter__=='_' and letter___=='_':
            if italics and bold:
                # we have to close them
                italics = False
                bold = False
                result = result + '___'
            elif bold:
                # we had bold, we should close bold then add bold italics
                result = result + '__ ___'
                italics = True
            elif italics:
                # we had italics, we should close italits than add bolditalics
                result = result + '_ ___'
                bold = True
            else:
                # we had nothing, we should just open everything
                italics = True
                bold = True
                result = result + '___'
        # __*
        elif letter_=='_' and letter__=='_':
            if bold and italics:
                # we were in bolditalics, we have to remove bold and keep italics   
                result = result + '___ _'
                bold = False 
            elif bold:
                # close bold
                result = result + '__'
                bold = False
            elif italics:
                # close italics, and open italics+bold
                result = result + '_ ___'
                bold = True
            else:
                # open bold
                result = result + '__'
                bold = True
        # _**
        elif letter_=='_':
            if italics and bold:
                # we were in bolditalics, we have to remove italics and keep bold   
                result = result + '___ __'
                italics = False
            elif italics:
                # close italics
                result = result + '_'
                italics = False       
            elif bold:
                # close bold, and open italics+bold
                result = result + '__ ___'
                italics = True
            else:
                # open italics
                result = result + '_'
                italics = True
        # ***
        #elif letter_ != '_':
        #    result = result + letter_
        
        result = result + letter     
    
    # TODO close last
    if italics and bold:
        result = result + '___'
    elif italics:
        result = result + '_'
    elif bold:
        result = result + '__'
    
    return result

#remove_nested_emphasis('_test italique_ et __bold__')


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
            content = str(format_wiktionnaire_definition_template_recursive(tl.params[0].value))
            content.strip().replace('  ',' ')
            content.replace(' ',') ^(')
            ast.replace(tl, ' ^('+content+')')
        
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
        
        # specific case of the e template        
        elif tl_name == 'e':
            if len(tl.params) > 0:
                ast.replace(tl, '^('+str(tl.params[0].value)+')')
            else:
                ast.replace(tl, '^e')
        
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
    result = remove_nested_emphasis(substitute_wiki_with_reddit(result))
    
    # replace html
    result = result.replace('<br/>','\n').replace('<br\n/>','\n').replace('<br>','\n')
    
    # replace enumerations and examples
    toprocess = result
    result = ''    
    current_enumeration = 0
    before = None
    for letter in toprocess:
        # treat enumerations and examples                
        if letter == '*' and before is not None and before == '#':
            # we are in an example
            result = result.strip() + '\n - '
        elif before == '#' and letter.isspace():
            current_enumeration = current_enumeration + 1
            result = result.strip() + '\n\n' + str(current_enumeration)+'. '
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
    # if a defintion is in ébauche, reject
    if len(info['bloc_definition']) <= 150 or info['bloc_definition'].count('ébauche-déf') > 0:
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


