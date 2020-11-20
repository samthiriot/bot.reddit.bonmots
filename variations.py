

import wordfreq
import itertools

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

consonnes_doublables = set(['n','r','m','t','l','s','p'])

def combinaisons_consonnes(word):
    global consonnes_doublables
    
    if len(word) <= 3:
        yield word
        return
    
    w = word.lower()
    dic = dict()
    for letter in consonnes_doublables:
        w = w.replace(letter+letter,letter)
        dic[letter] = [letter, letter+letter]
    
    possibilities = [ dic.get(letter,[letter]) for letter in w[1:-1] ]
    
    for combination in itertools.product(*possibilities):
        yield w[0] + ''.join(combination) + w[-1:]
    
    pass


list(combinaisons_consonnes("maronnier"))


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

