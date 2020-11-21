
import sqlite3
from lru import LRU

from stats import *

print("init: connecting terms database")

conn = sqlite3.connect('terms.db')
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS rejected (word TEXT PRIMARY KEY, reason TEXT)''')
conn.commit()
c.execute('''SELECT COUNT(*) FROM rejected''')
print("\tthere are",c.fetchone()[0],"words blocked in database")
c.execute('''SELECT reason, COUNT(*) FROM rejected GROUP BY reason''')
for row in c.fetchall():
    print('\t\t',row[0],':\t',row[1])


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


print("init: connecting contributions database")

c2 = conn.cursor()
#c2.execute('''DROP TABLE IF EXISTS contributions''')
#conn.commit()
c2.execute('''CREATE TABLE IF NOT EXISTS contributions (subreddit TEXT NOT NULL, submission_id TEXT NOT NULL, comment_id TEXT NOT NULL, my_comment_id TEXT PRIMARY KEY, word TEXT, source TEXT, permalink TEXT NOT NULL)''')
c2.execute('''CREATE INDEX IF NOT EXISTS idx_contributions_submission_id ON contributions (submission_id)''')
conn.commit()
c2.execute('''CREATE INDEX IF NOT EXISTS idx_contributions_comment_id ON contributions (comment_id)''')
conn.commit()
c2.execute('''SELECT COUNT(*) FROM contributions''')
print("\twe did",c2.fetchone()[0],"contributions in the past:")
c2.execute('''SELECT subreddit, COUNT(*) FROM contributions GROUP BY subreddit''')
for row in c2.fetchall():
    print('\t\t',row[0],':\t',row[1])


def remember_I_contributed(subreddit, submission_id, comment_id, my_comment_id, word, source, permalink):
    global c2
    c2.execute('''INSERT INTO contributions VALUES (?, ?, ?, ?, ?, ?,?)''', (subreddit, submission_id, comment_id, my_comment_id, word, source,permalink,) )
    conn.commit()    

def already_contributed_submission(submission_id):
    global c2
    c2.execute('''SELECT COUNT(*) FROM contributions WHERE submission_id=?''', (submission_id,))        
    return c2.fetchone()[0] > 0

#c2.execute('''DROP TABLE IF EXISTS parsed_already''')
#conn.commit()
c2.execute('''CREATE TABLE IF NOT EXISTS parsed_already (comment_id TEXT PRIMARY KEY)''')
conn.commit()

def remember_I_parsed_comment(comment_id):
    global c2
    c2.execute('''INSERT INTO parsed_already VALUES (?)''', (comment_id, ) )
    conn.commit()    

def alread_parsed_comment(comment_id):
    global c2
    c2.execute('''SELECT COUNT(*) FROM parsed_already WHERE comment_id=?''', (comment_id,))        
    return c2.fetchone()[0] > 0

