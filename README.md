# bot.reddit.bonmots

Un bot reddit prévu pour les subreddits francophones tels que r/france.

## Objectif 

Le rôle principal du bot est de définir les mots peu connus. 
Il vise ainsi à faciliter la compréhension des messages par le plus grand nombre, y compris ceux qui sont francophones mais pas natifs.
De façon annexe, le bot peut aussi être amusant à l'occasion, lorsqu'il exhume une définition ancienne. 
Il remercie également de l'usage des tournures désuètes. 

## Intérêt

Ce qui a commencé comme un projet amusant est devenu un sujet loin d'être trivial.

Qu'est-ce qu'un mot digne d'une définition ?
* c'est un mot *rare*; s'il n'est pas rare, personne ne s'intéressera à sa définition
* c'est un mot pour lequel *on peut trouver une définition*, et une définition pertinente
* c'est un mot qui n'a pas déjà été défini dans le message

Problèmes propres au texte sur reddit: 
* Il s'agit d'un forum, pas d'un texte relu. L'auteur du message peut réaliser des *fautes d'orthographe et des typos*. Or un mot mal orthographié ne fera pas partie des corpus linguistiques qui sont créés sur des ensemble de textes plutôt bien orthographiés. 
* Parmis les fautes typiques, on trouve les consonnes doublables: "maronnier", "marronnier", "marronier"... Il a fallu générer toutes les combinaisons possibles et les confronter à un modèle statistique local.
* On travaille en français qui contient des *accents* et autres [diacritiques](https://fr.wikipedia.org/wiki/Diacritique). Pourtant en pratique, l'usage des accents et diacritiques est aléatoire. Or dans un corpus linguistique, "mecanicien" n'a rien à voir avec "mécanicien". Il a donc fallu trouver des méthodes pour explorer toutes les combinaisons possibles, et retenir comme fréquence la fréquence la plus élevée.
* La *syntaxe des commentaires* reddit, notamment en terme de liens, impose une tokenisation particulière

Qu'est-ce qu'un bon bot ?
* un bot qui ne poste pas trop fréquemment


Le premier problème est de définir ce qu'est un mot rare. 
* au départ, l'idée est qu'*un mot rare est un mot peu fréquent dans des corpus de texte connus*. Cette approche est traitée en utilisant [wordfreq](https://pypi.org/project/wordfreq/) qui nous calcule une estimation de probability [de Zinpf](https://fr.wikipedia.org/wiki/Loi_de_Zipf). 
* malheureusement, la plupart des mots rares sont des *mots mal orthographiés*. Par exemples avec une mauvaise utilisation des diacritiques. On teste donc des *combinaisons de diacritiques* et on calcule la fréquence de chaque combinaison du mot.
* de nombreux mots rares sont *des noms propres*, qui sont souvent connus s'ils sont mentionnés par l'auteur d'un message; on les élimine par analyse lexicographique à l'aide de [spaCy](https://spacy.io/), qui nous étiquette les noms propres que l'on peut ainsi éliminer
* de nombreux mots rares dans les corpus linguistiques sont *des mots connus mais d'usage récent, donc non présents dans les corpus*. Typiquement "covid", "reconfinement" ou "hydrochloriquine" sont inconnus  dans les corpus, mais leur définition est bien connue des lecteurs. La seule solution pour les détecter et d'*interroger un corpus récent*. Dans notre cas, nous éliminons les termes qui sont utilisés sur reddit plusieurs fois.

Un second problème est d'*identifier des définitions pertinentes*:
* on retire des résultats Wikipedia tout résultat qui correspond à une ébauche, ou a redirigé vers un mot très fréquent
* on conserve quelques définitions de Urban Dictionary qui sont parfois drôles, informatives, et couvrent bien l'argot internet ou anglophone
* identifier les définitions argotiques et non triviales (exemple: un utilisateur qui parle de "chignole" est peu intéressé par le bricolage) 

# setup 

   pip3 install tltk wiktionaryparser lru-dict wikipedia spacy spacy json praw sqlite3 wordfreq urbandictionary

   python3 -m spacy download fr_core_news_sm

