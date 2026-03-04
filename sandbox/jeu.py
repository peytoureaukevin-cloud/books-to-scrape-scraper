import random

nombre_mystere = random.randint(1, 100)
tentatives = 0
max_tentatives = 7

while tentatives < max_tentatives:
    proposition = int(input("Devine le nombre (1 à 100) : "))
    tentatives += 1

    if proposition < nombre_mystere:
        print("Trop petit 😅")
    elif proposition > nombre_mystere:
        print("Trop grand 😬")
    else:
        print("Bravo ! Tu as trouvé en", tentatives, "tentatives 🎉")
        break
else:
    print("Perdu 😈 Le nombre était", nombre_mystere)